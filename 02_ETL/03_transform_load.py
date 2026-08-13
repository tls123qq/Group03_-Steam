"""
=====================================================================
 03_transform_load.py — CLEAN + TRANSFORM + INTEGRATE + LOAD
=====================================================================
 รวมตรรกะเดิมจาก Data_Cleaning_Pipeline.ipynb และ etl_star_schema.py
 ไว้ในไฟล์เดียว โดยผลลัพธ์ Star Schema ต้องเหมือนเดิมทุกคอลัมน์

 ขั้นตอนภายในไฟล์นี้
   PART A — CLEAN     : ทำความสะอาดข้อมูล 3 แหล่ง -> 02_ETL/cleaned/*.csv
   PART B — TRANSFORM : สร้าง derived columns, surrogate keys, tier
   PART C — INTEGRATE : inner join 3 แหล่ง + สร้าง Dimension / Bridge
   PART D — LOAD      : เขียน 16 ตารางลง 03_Data_Warehouse/

 วิธีใช้ (รันจาก Project Root):
   python 02_ETL/03_transform_load.py
   python 02_ETL/03_transform_load.py --skip-clean   # ใช้ไฟล์ cleaned เดิม
=====================================================================
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from common import (BRIDGE_TABLES, CLEAN_DIR, DEPTH_TIER_BINS,
                    DEPTH_TIER_LABELS, DLC_WEIGHT, DW_DIR, PRICE_TIER_BINS,
                    PRICE_TIER_LABELS, PREMIUM_MULTIPLIER, QA_LOG, REVIEW_CLEAN,
                    REVIEW_JSON, SPY_CLEAN, SPY_CSV, STORE_CLEAN, STORE_JSON,
                    add_bridge_weights, banner, build_dim_from_values,
                    clean_languages, descriptions_of, dict_total,
                    iter_json_array, load_json, owners_to_number,
                    parse_list_cell, parse_release_date, save_json,
                    split_names, to_bool, to_int)

qa = {}


# ===============================================================
# PART A1 — CLEAN: Steam Store API (Nested JSON)
# ===============================================================
def clean_store():
    banner("CLEAN 1/3 — Steam Store API")
    records = []
    n_raw = 0

    # อ่านทีละเกม ไม่โหลดทั้งไฟล์เข้าหน่วยความจำ (ไฟล์ใหญ่กว่า 400 MB)
    for g in iter_json_array(STORE_JSON):
        n_raw += 1
        platforms = g.get("platforms") or {}
        price = g.get("price_overview")

        if isinstance(price, dict):
            initial_price = to_int(price.get("initial")) / 100.0   # สตางค์ -> บาท
            currency = price.get("currency", "UNKNOWN")
        else:
            initial_price = 0.0
            currency = None            # รอดูค่า is_free ก่อนค่อยตัดสิน

        records.append({
            "type": g.get("type"),
            "name": g.get("name"),
            "steam_appid": g.get("steam_appid"),
            "required_age": to_int(g.get("required_age")),
            "is_free": to_bool(g.get("is_free")),
            "supported_languages": clean_languages(g.get("supported_languages")),
            "developers": ", ".join(g.get("developers") or []),
            "publishers": ", ".join(g.get("publishers") or []),
            "categories": descriptions_of(g.get("categories")),
            "genres": descriptions_of(g.get("genres")),
            "recommendations": dict_total(g.get("recommendations")),
            "release_date": parse_release_date(g.get("release_date")),
            "controller_support": 0 if g.get("controller_support") in (None, "") else 1,
            "dlc_count": len(g.get("dlc") or []),
            "achievements_total": dict_total(g.get("achievements")),
            "platform_windows": 1 if platforms.get("windows") else 0,
            "platform_mac": 1 if platforms.get("mac") else 0,
            "platform_linux": 1 if platforms.get("linux") else 0,
            "initial_price": initial_price,
            "price_currency": currency,
            "has_price_data": isinstance(price, dict),
        })

    store = pd.DataFrame(records)
    del records
    qa["store_00_rows_raw"] = n_raw
    print(f"อ่านจาก JSON: {n_raw:,} เกม")

    # --- ลบข้อมูลซ้ำ ---
    dups = int(store["steam_appid"].duplicated().sum())
    store = store.drop_duplicates(subset=["steam_appid"], keep="first")
    qa["store_01_duplicates_removed"] = dups
    print(f"ลบ steam_appid ซ้ำ: {dups:,} แถว")

    # --- เกมที่ไม่มีข้อมูลราคา ---
    # เกมฟรีไม่มีคีย์ price_overview เป็นเรื่องปกติ ไม่ใช่ข้อมูลเสีย จึงต้องเก็บไว้
    # ลบเฉพาะเกมที่ "ไม่ฟรี แต่ไม่มีข้อมูลราคา" ซึ่งคือข้อมูลผิดปกติจริง
    n_free = int(store["is_free"].sum())
    mask_paid_no_price = (~store["is_free"]) & (~store["has_price_data"])
    n_paid_no_price = int(mask_paid_no_price.sum())
    store = store[~mask_paid_no_price].copy()

    store.loc[store["is_free"], "initial_price"] = 0.0
    store.loc[store["is_free"], "price_currency"] = "FREE"
    store["price_currency"] = store["price_currency"].fillna("UNKNOWN")

    qa["store_02_free_games_kept"] = n_free
    qa["store_02_paid_without_price_dropped"] = n_paid_no_price
    print(f"เก็บเกมฟรีไว้: {n_free:,} เกม | ลบเกมไม่ฟรีที่ไม่มีราคา: {n_paid_no_price:,} เกม")

    # --- ลบแถวที่ข้อมูลจำเป็นไม่ครบ ---
    n_before = len(store)
    for c in ("developers", "publishers", "supported_languages", "name"):
        store[c] = store[c].replace("", np.nan)
    store.loc[store["categories"].apply(len) == 0, "categories"] = np.nan
    store.loc[store["genres"].apply(len) == 0, "genres"] = np.nan

    required = ["name", "developers", "publishers", "categories", "genres",
                "supported_languages", "release_date"]
    store = store.dropna(subset=required)
    qa["store_03_rows_dropped_missing"] = n_before - len(store)
    print(f"ลบแถวที่ข้อมูลไม่ครบ: {n_before - len(store):,} แถว")

    # --- ตรวจสกุลเงิน ---
    cur = store["price_currency"].value_counts()
    qa["store_04_currencies"] = cur.to_dict()
    print(f"สกุลเงินที่พบ: {cur.to_dict()}")
    non_thb = cur.drop(labels=["THB", "FREE"], errors="ignore")
    if len(non_thb):
        print(f"  เตือน: พบสกุลเงินอื่นปนอยู่ {non_thb.to_dict()} ต้องแปลงก่อนคำนวณรายได้")

    # --- Sanity check + บันทึก ---
    n_before = len(store)
    for c in ("required_age", "recommendations", "dlc_count",
              "achievements_total", "initial_price"):
        store = store[store[c] >= 0]
    qa["store_05_rows_dropped_negative"] = n_before - len(store)

    store["is_free"] = store["is_free"].astype(int)
    store = store.drop(columns=["has_price_data"])
    store = store[["type", "name", "steam_appid", "required_age", "is_free",
                   "supported_languages", "developers", "publishers",
                   "categories", "genres", "recommendations", "release_date",
                   "controller_support", "dlc_count", "achievements_total",
                   "platform_windows", "platform_mac", "platform_linux",
                   "initial_price", "price_currency"]]
    store.to_csv(STORE_CLEAN, index=False, encoding="utf-8-sig")
    qa["store_06_rows_final"] = len(store)
    print(f"บันทึก: {STORE_CLEAN.name} ({len(store):,} แถว)")
    return store


# ===============================================================
# PART A2 — CLEAN: Steam Reviews API
# ===============================================================
def clean_reviews():
    banner("CLEAN 2/3 — Steam Reviews API")
    raw = load_json(REVIEW_JSON, [])
    qa["review_00_rows_raw"] = len(raw)
    print(f"อ่านจาก JSON: {len(raw):,} แถว")

    # รวบรวมคีย์จากทุกแถว ไม่ใช่แค่แถวแรก
    # (ของเดิมใช้ data[0].keys() ถ้าแถวหลังมีคีย์เพิ่มจะเขียน CSV ไม่ผ่าน)
    all_keys = set()
    for row in raw:
        all_keys.update(row.keys())

    review = pd.DataFrame(raw)
    del raw

    # num_reviews เป็น 0 ทุกแถวเพราะตอนดึงตั้ง num_per_page=0 -> ไม่มีประโยชน์
    if "num_reviews" in review.columns:
        review = review.drop(columns=["num_reviews"])

    dups = int(review["steam_appid"].duplicated().sum())
    review = review.dropna(subset=["steam_appid"])
    review = review.drop_duplicates(subset=["steam_appid"], keep="first")
    qa["review_01_duplicates_removed"] = dups
    print(f"ลบ steam_appid ซ้ำ: {dups:,} แถว")

    for c in ("review_score", "total_positive", "total_negative",
              "total_reviews", "steam_appid"):
        review[c] = pd.to_numeric(review[c], errors="coerce")
    review = review.dropna(subset=["steam_appid"])

    # กฎที่ต้องเป็นจริงเสมอ: positive + negative = total
    mismatch = (review["total_positive"] + review["total_negative"]
                != review["total_reviews"])
    qa["review_02_sum_mismatch"] = int(mismatch.sum())
    review = review[~mismatch]

    bad_score = ~review["review_score"].between(0, 9)
    qa["review_02_bad_score"] = int(bad_score.sum())
    review = review[~bad_score]

    n_before = len(review)
    for c in ("total_positive", "total_negative", "total_reviews"):
        review = review[review[c] >= 0]
    qa["review_02_rows_dropped_negative"] = n_before - len(review)
    print(f"ลบแถวที่ตัวเลขขัดแย้งกัน: {qa['review_02_sum_mismatch']:,} แถว")

    int_cols = ["review_score", "total_positive", "total_negative",
                "total_reviews", "steam_appid"]
    review[int_cols] = review[int_cols].astype(int)
    review = review[["review_score", "review_score_desc", "total_positive",
                     "total_negative", "total_reviews", "steam_appid"]]
    review.to_csv(REVIEW_CLEAN, index=False, encoding="utf-8-sig")
    qa["review_03_rows_final"] = len(review)
    print(f"บันทึก: {REVIEW_CLEAN.name} ({len(review):,} แถว)")
    return review


# ===============================================================
# PART A3 — CLEAN: SteamSpy
# ===============================================================
def clean_spy():
    banner("CLEAN 3/3 — SteamSpy (all_data.csv)")
    spy = pd.read_csv(SPY_CSV)
    qa["spy_00_rows_raw"] = len(spy)
    print(f"อ่านจาก CSV: {len(spy):,} แถว x {spy.shape[1]} คอลัมน์")

    # ลบคอลัมน์ที่ซ้ำกับแหล่งอื่น / ไม่มีข้อมูล / เป็น index ที่ติดมา
    drop_cols = ["Unnamed: 0", "name", "developer", "publisher", "score_rank",
                 "positive", "negative", "userscore", "price", "initialprice",
                 "discount"]
    dropped = [c for c in drop_cols if c in spy.columns]
    spy = spy.drop(columns=dropped)
    spy = spy.loc[:, ~spy.columns.str.match(r"^Unnamed")]
    qa["spy_01_cols_dropped"] = dropped
    print(f"ลบคอลัมน์: {dropped}")

    dups = int(spy.duplicated(subset=["appid"]).sum())
    spy = spy.drop_duplicates(subset=["appid"], keep="first")
    qa["spy_02_duplicates_removed"] = dups
    print(f"ลบ appid ซ้ำ: {dups:,} แถว")

    n_before = len(spy)
    spy = spy.replace(r"^\s*$", np.nan, regex=True)      # ช่องว่างเปล่า -> NaN
    spy = spy.dropna(how="any")
    qa["spy_03_rows_dropped_missing"] = n_before - len(spy)
    print(f"ลบแถวที่มีค่าว่าง: {n_before - len(spy):,} แถว")

    # ต้องบังคับแปลงเป็นตัวเลขก่อน Sanity Check
    # ถ้าคอลัมน์ใดเคยมีช่องว่างปน pandas จะอ่านเป็น object ทำให้ค่าติดลบรอดไปได้
    metric_cols = [c for c in ("average_forever", "average_2weeks",
                               "median_forever", "median_2weeks", "ccu")
                   if c in spy.columns]
    n_before = len(spy)
    for c in metric_cols:
        spy[c] = pd.to_numeric(spy[c], errors="coerce")
    spy = spy.dropna(subset=metric_cols)
    qa["spy_04_rows_dropped_nonnumeric"] = n_before - len(spy)

    n_before = len(spy)
    for c in metric_cols:
        spy = spy[spy[c] >= 0]
    qa["spy_04_rows_dropped_negative"] = n_before - len(spy)
    print(f"ลบแถวค่าติดลบ: {qa['spy_04_rows_dropped_negative']:,} แถว")

    spy["appid"] = spy["appid"].astype(int)
    spy[metric_cols] = spy[metric_cols].astype(int)

    # owners เป็นข้อความช่วง "10,000 .. 20,000" -> ใช้ค่ากลาง
    n_before = len(spy)
    spy["owners"] = spy["owners"].apply(owners_to_number)
    spy = spy.dropna(subset=["owners"])
    spy["owners"] = spy["owners"].astype(int)
    qa["spy_05_rows_dropped_bad_owners"] = n_before - len(spy)
    qa["spy_05_owners_distinct"] = int(spy["owners"].nunique())
    print(f"แปลง owners เป็นตัวเลข | ค่าที่เป็นไปได้ {spy['owners'].nunique()} ค่า")

    spy.to_csv(SPY_CLEAN, index=False)
    qa["spy_06_rows_final"] = len(spy)
    print(f"บันทึก: {SPY_CLEAN.name} ({len(spy):,} แถว)")
    return spy


# ===============================================================
# PART B/C/D — สร้าง Star Schema
# ===============================================================
def build_star_schema():
    banner("TRANSFORM + INTEGRATE — สร้าง Star Schema")

    df1 = pd.read_csv(STORE_CLEAN)
    df2 = pd.read_csv(SPY_CLEAN)
    df3 = pd.read_csv(REVIEW_CLEAN)
    df2 = df2.drop(columns=[c for c in df2.columns if c.startswith("Unnamed")],
                   errors="ignore")
    print(f"store {df1.shape} | steamspy {df2.shape} | review {df3.shape}")

    # --- เตรียมคีย์: 3 แหล่งใช้ชื่อคีย์ต่างกัน ต้อง rename ให้ตรงก่อน join ---
    df1 = df1.rename(columns={"steam_appid": "app_id"})
    df2 = df2.rename(columns={"appid": "app_id"})
    df3 = df3.rename(columns={"steam_appid": "app_id"})
    for d in (df1, df2, df3):
        d.drop_duplicates(subset="app_id", keep="first", inplace=True)

    # --- INNER JOIN ทั้ง 3 แหล่ง ---
    master = df1.merge(df2, on="app_id", how="inner").merge(df3, on="app_id",
                                                            how="inner")
    print(f"หลัง inner join: {master.shape[0]:,} เกม")
    qa["join_rows"] = int(master.shape[0])

    master["owners_numeric"] = master["owners"].apply(owners_to_number)
    master["initial_price"] = pd.to_numeric(master["initial_price"],
                                            errors="coerce").fillna(0)
    master["is_free"] = pd.to_numeric(master["is_free"],
                                      errors="coerce").fillna(0).astype(int)
    master["release_date"] = pd.to_datetime(master["release_date"], errors="coerce")
    for col in ["recommendations", "dlc_count", "achievements_total", "ccu",
                "total_positive", "total_negative", "total_reviews",
                "average_forever", "average_2weeks", "median_forever",
                "median_2weeks"]:
        master[col] = pd.to_numeric(master[col], errors="coerce").fillna(0)

    # ---------------- DIM_GAME ----------------
    master["language_count"] = (master["supported_languages"].fillna("").astype(str)
                                .apply(lambda t: len([x for x in t.split(",") if x.strip()])))
    if "price_currency" not in master.columns:
        master["price_currency"] = "UNKNOWN"
    master["price_currency"] = master["price_currency"].fillna("UNKNOWN")

    master["content_depth_score"] = (master["achievements_total"]
                                     + master["dlc_count"] * DLC_WEIGHT)
    master["price_tier"] = pd.cut(master["initial_price"], bins=PRICE_TIER_BINS,
                                  labels=PRICE_TIER_LABELS, right=False,
                                  include_lowest=True).astype(str)
    master["content_depth_tier"] = pd.cut(master["content_depth_score"],
                                          bins=DEPTH_TIER_BINS,
                                          labels=DEPTH_TIER_LABELS).astype(str)

    dim_game = master[["app_id", "name", "type", "is_free", "required_age",
                       "initial_price", "price_tier", "controller_support",
                       "dlc_count", "achievements_total", "content_depth_tier",
                       "language_count", "price_currency"]].copy()
    dim_game = dim_game.rename(columns={"app_id": "steam_appid"})
    dim_game.insert(0, "game_key", range(1, len(dim_game) + 1))
    master["game_key"] = master["app_id"].map(
        dict(zip(dim_game["steam_appid"], dim_game["game_key"])))

    # ---------------- DIM_DATE ----------------
    dates = master["release_date"].dropna().drop_duplicates().sort_values()
    dim_date = pd.DataFrame({"full_date": dates})
    dim_date["date_key"] = dim_date["full_date"].dt.strftime("%Y%m%d").astype(int)
    dim_date["day"] = dim_date["full_date"].dt.day
    dim_date["month"] = dim_date["full_date"].dt.month
    dim_date["month_name"] = dim_date["full_date"].dt.month_name()
    dim_date["quarter"] = dim_date["full_date"].dt.quarter
    dim_date["year"] = dim_date["full_date"].dt.year
    dim_date = dim_date[["date_key", "full_date", "day", "month", "month_name",
                         "quarter", "year"]]
    master["date_key"] = pd.to_numeric(
        master["release_date"].dt.strftime("%Y%m%d"), errors="coerce").astype("Int64")

    # ---------------- DIM_PLATFORM ----------------
    plat_cols = ["platform_windows", "platform_mac", "platform_linux"]
    for c in plat_cols:
        master[c] = pd.to_numeric(master[c], errors="coerce").fillna(0).astype(int)
    dim_platform = (master[plat_cols].drop_duplicates()
                    .sort_values(plat_cols).reset_index(drop=True))
    dim_platform.insert(0, "platform_key", range(1, len(dim_platform) + 1))
    dim_platform["platform_desc"] = dim_platform.apply(
        lambda r: " + ".join([n for n, c in zip(["Windows", "Mac", "Linux"], plat_cols)
                              if r[c] == 1]) or "Unknown", axis=1)
    dim_platform["platform_count"] = dim_platform[plat_cols].sum(axis=1)
    master = master.merge(dim_platform[plat_cols + ["platform_key"]],
                          on=plat_cols, how="left")

    # ---------------- DIM_REVIEW_SCORE ----------------
    desc_mode = (master.groupby("review_score")["review_score_desc"]
                 .agg(lambda s: s.value_counts().idxmax()).reset_index())
    desc_mode.loc[desc_mode["review_score"] == 0,
                  "review_score_desc"] = "No / Too Few Reviews"
    dim_review_score = desc_mode.sort_values("review_score").reset_index(drop=True)
    dim_review_score.insert(0, "review_score_key",
                            range(1, len(dim_review_score) + 1))

    def sentiment_band(score):
        if score == 0:
            return "No / Too Few Reviews"
        if score <= 4:
            return "Negative"
        if score == 5:
            return "Mixed"
        return "Positive"

    dim_review_score["sentiment_band"] = dim_review_score["review_score"].apply(
        sentiment_band)
    master = master.merge(dim_review_score[["review_score", "review_score_key"]],
                          on="review_score", how="left")

    # ---------------- DIM_DEVELOPER / DIM_PUBLISHER + Bridge ----------------
    master["developers"] = master["developers"].fillna("Unknown").astype(str).str.strip()
    master["publishers"] = master["publishers"].fillna("Unknown").astype(str).str.strip()
    master["developer_list"] = master["developers"].apply(split_names)
    master["publisher_list"] = master["publishers"].apply(split_names)

    dim_developer, dev_map = build_dim_from_values(
        [d for lst in master["developer_list"] for d in lst],
        "developer_key", "developer_name")
    dim_publisher, pub_map = build_dim_from_values(
        [p for lst in master["publisher_list"] for p in lst],
        "publisher_key", "publisher_name")

    def explode_bridge(list_col, name_col, key_col, mapping):
        b = (master[["game_key", list_col]].explode(list_col)
             .dropna(subset=[list_col]).rename(columns={list_col: name_col}))
        b[key_col] = b[name_col].map(mapping)
        return (b[["game_key", key_col]].dropna().astype(int)
                .drop_duplicates().reset_index(drop=True))

    bridge_game_developers = explode_bridge("developer_list", "developer_name",
                                            "developer_key", dev_map)
    bridge_game_publishers = explode_bridge("publisher_list", "publisher_name",
                                            "publisher_key", pub_map)
    master["primary_developer_key"] = master["developer_list"].apply(
        lambda lst: dev_map.get(lst[0]) if lst else np.nan)
    master["primary_publisher_key"] = master["publisher_list"].apply(
        lambda lst: pub_map.get(lst[0]) if lst else np.nan)
    bridge_game_developers = add_bridge_weights(
        bridge_game_developers, "developer_key",
        dict(zip(master["game_key"], master["primary_developer_key"])))
    bridge_game_publishers = add_bridge_weights(
        bridge_game_publishers, "publisher_key",
        dict(zip(master["game_key"], master["primary_publisher_key"])))

    # ---------------- DIM_GENRE / DIM_CATEGORY + Bridge ----------------
    master["genre_list"] = master["genres"].apply(parse_list_cell)
    master["category_list"] = master["categories"].apply(parse_list_cell)
    dim_genre, genre_map = build_dim_from_values(
        [g for lst in master["genre_list"] for g in lst], "genre_key", "genre_name")
    dim_category, cat_map = build_dim_from_values(
        [c for lst in master["category_list"] for c in lst],
        "category_key", "category_name")

    bridge_game_genres = explode_bridge("genre_list", "genre_name",
                                        "genre_key", genre_map)
    bridge_game_categories = explode_bridge("category_list", "category_name",
                                            "category_key", cat_map)
    master["primary_genre_key"] = master["genre_list"].apply(
        lambda lst: genre_map.get(lst[0]) if lst else np.nan)
    master["primary_category_key"] = master["category_list"].apply(
        lambda lst: cat_map.get(lst[0]) if lst else np.nan)
    bridge_game_genres = add_bridge_weights(
        bridge_game_genres, "genre_key",
        dict(zip(master["game_key"], master["primary_genre_key"])))
    bridge_game_categories = add_bridge_weights(
        bridge_game_categories, "category_key",
        dict(zip(master["game_key"], master["primary_category_key"])))

    # ---------------- genre benchmark + is_premium ----------------
    master["recommendation_rate"] = np.where(
        master["owners_numeric"].fillna(0) > 0,
        master["recommendations"] / master["owners_numeric"], np.nan)

    gs = bridge_game_genres[["game_key", "genre_key"]].merge(
        master[["game_key", "initial_price", "is_free",
                "recommendation_rate", "review_score"]], on="game_key", how="left")
    # genre_avg_price นับเฉพาะเกมที่ขาย ถ้ารวมเกมฟรีค่าเฉลี่ยจะถูกดึงลง
    paid_only = gs[gs["is_free"] == 0]
    dim_genre = (dim_genre
                 .merge(paid_only.groupby("genre_key")["initial_price"].mean()
                        .rename("genre_avg_price"), on="genre_key", how="left")
                 .merge(gs.groupby("genre_key")["recommendation_rate"].mean()
                        .rename("genre_avg_recommendation_rate"),
                        on="genre_key", how="left")
                 .merge(gs.groupby("genre_key")["review_score"].mean()
                        .rename("genre_avg_review_score"), on="genre_key", how="left"))
    missing_price = dim_genre.loc[dim_genre["genre_avg_price"].isna(),
                                  "genre_name"].tolist()
    if missing_price:
        print(f"แนวที่ไม่มีเกมขายเลย (genre_avg_price ว่าง): {missing_price}")
    dim_genre["genre_avg_price"] = dim_genre["genre_avg_price"].round(2)
    dim_genre["genre_avg_recommendation_rate"] = dim_genre[
        "genre_avg_recommendation_rate"].round(6)
    dim_genre["genre_avg_review_score"] = dim_genre["genre_avg_review_score"].round(3)

    avg_price_map = dict(zip(dim_genre["genre_key"], dim_genre["genre_avg_price"]))
    master["primary_genre_avg_price"] = master["primary_genre_key"].map(avg_price_map)
    master["is_premium"] = ((master["is_free"] == 0)
                            & (master["initial_price"]
                               > PREMIUM_MULTIPLIER * master["primary_genre_avg_price"])
                            ).astype(int)
    dim_game = dim_game.merge(master[["game_key", "is_premium"]],
                              on="game_key", how="left")
    print(f"เกมที่เข้าเกณฑ์ premium: {int(dim_game['is_premium'].sum()):,} เกม")

    # ---------------- DIM_LANGUAGE + Bridge ----------------
    master["language_list"] = (master["supported_languages"].fillna("").astype(str)
                               .apply(lambda t: [x.strip() for x in t.split(",")
                                                 if x.strip()]))
    dim_language, lang_map = build_dim_from_values(
        [l for lst in master["language_list"] for l in lst],
        "language_key", "language_name")
    bridge_game_languages = explode_bridge("language_list", "language_name",
                                           "language_key", lang_map)
    master["primary_language_key"] = master["language_list"].apply(
        lambda lst: lang_map.get(lst[0]) if lst else np.nan)
    bridge_game_languages = add_bridge_weights(
        bridge_game_languages, "language_key",
        dict(zip(master["game_key"], master["primary_language_key"])))

    # ---------------- FACT_GAME_ENGAGEMENT ----------------
    fact_engagement = master[[
        "game_key", "date_key", "platform_key", "review_score_key",
        "primary_developer_key", "primary_publisher_key",
        "total_positive", "total_negative", "total_reviews",
        "recommendations", "owners", "ccu",
        "owners_numeric", "initial_price", "is_free",
        "content_depth_score", "recommendation_rate"]].copy()

    # (1) estimated_revenue = owners_numeric * initial_price ; เกมฟรี = 0
    fact_engagement["estimated_revenue"] = np.where(
        fact_engagement["is_free"] == 1, 0.0,
        fact_engagement["owners_numeric"].fillna(0)
        * fact_engagement["initial_price"].fillna(0)).round(2)
    # (2) concurrent_engagement_rate = ccu / owners_numeric (กันหารด้วย 0)
    fact_engagement["concurrent_engagement_rate"] = np.where(
        fact_engagement["owners_numeric"].fillna(0) > 0,
        fact_engagement["ccu"] / fact_engagement["owners_numeric"], np.nan).round(8)
    # (3) content_depth_score และ (4) recommendation_rate คำนวณไว้ก่อนหน้าแล้ว
    fact_engagement["recommendation_rate"] = fact_engagement[
        "recommendation_rate"].round(8)

    fact_engagement = fact_engagement[[
        "game_key", "date_key", "platform_key", "review_score_key",
        "primary_developer_key", "primary_publisher_key",
        "total_positive", "total_negative", "total_reviews",
        "recommendations", "owners", "ccu",
        "estimated_revenue", "concurrent_engagement_rate",
        "content_depth_score", "recommendation_rate"]]
    fact_engagement.insert(0, "engagement_key", range(1, len(fact_engagement) + 1))

    # ---------------- FACT_GAME_PLAYTIME ----------------
    fact_playtime = master[["game_key", "date_key", "platform_key",
                            "primary_genre_key", "primary_category_key",
                            "average_forever", "average_2weeks",
                            "median_forever", "median_2weeks"]].copy()
    fact_playtime["has_playtime"] = (fact_playtime[
        ["average_forever", "average_2weeks", "median_forever", "median_2weeks"]
    ].sum(axis=1) > 0).astype(int)
    fact_playtime.insert(0, "playtime_key", range(1, len(fact_playtime) + 1))

    return {
        "DIM_GAME": dim_game, "DIM_DATE": dim_date, "DIM_PLATFORM": dim_platform,
        "DIM_REVIEW_SCORE": dim_review_score, "DIM_DEVELOPER": dim_developer,
        "DIM_PUBLISHER": dim_publisher, "DIM_GENRE": dim_genre,
        "DIM_CATEGORY": dim_category, "DIM_LANGUAGE": dim_language,
        "FACT_GAME_ENGAGEMENT": fact_engagement,
        "FACT_GAME_PLAYTIME": fact_playtime,
        "BRIDGE_GAME_GENRES": bridge_game_genres,
        "BRIDGE_GAME_CATEGORIES": bridge_game_categories,
        "BRIDGE_GAME_DEVELOPERS": bridge_game_developers,
        "BRIDGE_GAME_PUBLISHERS": bridge_game_publishers,
        "BRIDGE_GAME_LANGUAGES": bridge_game_languages,
    }


# ===============================================================
# PART D — LOAD
# ===============================================================
def load_tables(tables):
    banner("LOAD — เขียนตารางลง 03_Data_Warehouse")
    for name, df in tables.items():
        path = DW_DIR / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        tag = "bridge" if name in BRIDGE_TABLES else ""
        print(f"  {name:26s} rows={len(df):>7,}  cols={df.shape[1]:>2}  {tag}")
    qa["dw_tables"] = {k: len(v) for k, v in tables.items()}


def main():
    ap = argparse.ArgumentParser(description="Clean + Transform + Load")
    ap.add_argument("--skip-clean", action="store_true",
                    help="ข้ามขั้น Clean แล้วใช้ไฟล์ใน 02_ETL/cleaned เดิม")
    args = ap.parse_args()

    if args.skip_clean:
        missing = [p.name for p in (STORE_CLEAN, SPY_CLEAN, REVIEW_CLEAN)
                   if not p.exists()]
        if missing:
            sys.exit(f"ใช้ --skip-clean ไม่ได้ เพราะยังไม่มีไฟล์: {missing}")
        print(f"ข้ามขั้น Clean — ใช้ไฟล์เดิมใน {CLEAN_DIR}")
    else:
        for p, label in ((STORE_JSON, "steam_store_API.json"),
                         (REVIEW_JSON, "steam_reviews_summary_data.json"),
                         (SPY_CSV, "all_data.csv")):
            if not p.exists():
                sys.exit(f"ไม่พบไฟล์ดิบ {label} ใน 01_Raw_Data "
                         f"— รัน 01_fetch_api_data.py ก่อน")
        clean_store()
        clean_reviews()
        clean_spy()

    tables = build_star_schema()
    load_tables(tables)
    save_json(QA_LOG, qa)
    print(f"\nบันทึก QA log: {QA_LOG}")
    print("เสร็จสิ้น — ขั้นถัดไป: python 02_ETL/04_validate_dw.py")


if __name__ == "__main__":
    main()
