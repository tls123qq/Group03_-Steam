"""
=====================================================================
 02_profile_data.py — DATA PROFILING: สำรวจปัญหาคุณภาพข้อมูลก่อน Clean
=====================================================================
 ขั้นตอนนี้ "ไม่แก้ไขข้อมูล" ทำหน้าที่ตรวจและรายงานอย่างเดียว
 เพื่อให้เห็นว่าปัญหาคุณภาพข้อมูลแต่ละประเภทมีอยู่จริงกี่รายการ
 ก่อนที่ 03_transform_load.py จะเข้าไปแก้

 ปัญหาที่ตรวจ (ตรงกับที่ระบุในรายงาน):
   1. Missing Values          — ค่าว่างในคอลัมน์จำเป็น
   2. Duplicate Records       — appid ซ้ำ
   3. Mismatched Keys         — คีย์คนละชื่อ / จำนวนที่ join ติดกัน
   4. Invalid Values          — ค่าติดลบ, review_score นอกช่วง 0-9
   5. หน่วยวัดไม่ตรงกัน        — owners เป็นข้อความช่วง, ราคาเป็นสตางค์
   6. รูปแบบวันที่ไม่ตรงกัน     — release_date เป็น dict / 'Coming Soon'
   7. Zero Variance           — คอลัมน์ที่มีค่าเดียวทั้งไฟล์ (ไม่มีประโยชน์)

 ผลลัพธ์: 02_ETL/reports/data_profile.json  และ  data_profile.md

 วิธีใช้ (รันจาก Project Root):
   python 02_ETL/02_profile_data.py
=====================================================================
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from common import (PROFILE_JSON, PROFILE_MD, REVIEW_JSON, SPY_CSV, STORE_JSON,
                    banner, iter_json_array, load_json, save_json)

profile = {}
findings = []      # (แหล่งข้อมูล, ประเภทปัญหา, รายละเอียด, จำนวน)


def add(source, issue, detail, count):
    findings.append({"source": source, "issue": issue,
                     "detail": detail, "count": count})
    print(f"  [{issue}] {detail}: {count:,}")


# ===============================================================
# 1. Steam Store API (Nested JSON)
# ===============================================================
def profile_store():
    banner("PROFILE 1/3 — steam_store_API.json (Nested JSON)")
    if not STORE_JSON.exists():
        print(f"ไม่พบไฟล์ {STORE_JSON.name} — ข้ามขั้นนี้")
        return

    n = 0
    ids = []
    type_counter = Counter()
    currency_counter = Counter()
    free_games = 0
    no_price = 0
    free_no_price = 0
    bad_date = 0
    date_dict = 0
    html_lang = 0
    nested_fields = Counter()
    missing = Counter()
    required = ["name", "developers", "publishers", "categories",
                "genres", "supported_languages", "release_date"]

    for g in iter_json_array(STORE_JSON):
        n += 1
        ids.append(g.get("steam_appid"))
        type_counter[g.get("type")] += 1

        for f in required:
            v = g.get(f)
            if v is None or v == "" or v == []:
                missing[f] += 1

        price = g.get("price_overview")
        is_free = bool(g.get("is_free"))
        if is_free:
            free_games += 1
        if isinstance(price, dict):
            currency_counter[price.get("currency")] += 1
        else:
            no_price += 1
            if is_free:
                free_no_price += 1

        rd = g.get("release_date")
        if isinstance(rd, dict):
            date_dict += 1
            if not rd.get("date") or pd.isna(pd.to_datetime(rd.get("date"),
                                                            errors="coerce")):
                bad_date += 1

        if "<" in str(g.get("supported_languages", "")):
            html_lang += 1

        for f in ("platforms", "achievements", "recommendations", "price_overview"):
            if isinstance(g.get(f), dict):
                nested_fields[f] += 1

    dup = len(ids) - len(set(ids))
    print(f"จำนวนเกมทั้งหมด: {n:,}")
    print(f"ประเภทเนื้อหา: {dict(type_counter)}\n")

    add("store", "Duplicate", "steam_appid ซ้ำ", dup)
    for f, c in missing.items():
        add("store", "Missing", f"คอลัมน์ {f} ว่าง", c)
    add("store", "Missing", "ไม่มี price_overview", no_price)
    add("store", "Missing", "เกมฟรีที่ไม่มี price_overview (ปกติ ห้ามลบ)", free_no_price)
    add("store", "Date", "release_date เป็น dict ต้องแตกออกก่อน", date_dict)
    add("store", "Date", "วันที่แปลงไม่ได้ เช่น Coming Soon", bad_date)
    add("store", "Format", "supported_languages มี HTML ปน", html_lang)
    add("store", "Unit", "ราคาเป็นหน่วยสตางค์ ต้องหาร 100", sum(currency_counter.values()))
    for f, c in nested_fields.items():
        add("store", "Nested", f"คอลัมน์ {f} เป็น dict ซ้อน", c)

    print(f"\nสกุลเงินที่ API ตอบกลับ: {dict(currency_counter)}")
    if len(currency_counter) > 1:
        add("store", "Unit", "พบสกุลเงินปนกัน ต้องแปลงค่าก่อนคำนวณ",
            len(currency_counter))

    profile["store"] = {
        "rows": n, "duplicates": dup, "types": dict(type_counter),
        "free_games": free_games, "no_price_overview": no_price,
        "free_without_price": free_no_price,
        "currencies": dict(currency_counter),
        "missing_required": dict(missing),
    }


# ===============================================================
# 2. Steam Reviews API (JSON แบน)
# ===============================================================
def profile_reviews():
    banner("PROFILE 2/3 — steam_reviews_summary_data.json")
    data = load_json(REVIEW_JSON)
    if data is None:
        print(f"ไม่พบไฟล์ {REVIEW_JSON.name} — ข้ามขั้นนี้")
        return

    df = pd.DataFrame(data)
    print(f"จำนวนแถว: {len(df):,} | คอลัมน์: {list(df.columns)}\n")

    keysets = Counter(tuple(sorted(r.keys())) for r in data)
    add("review", "Schema", "รูปแบบคีย์ที่ต่างกันระหว่างแถว", len(keysets))

    dup = int(df["steam_appid"].duplicated().sum())
    add("review", "Duplicate", "steam_appid ซ้ำ", dup)
    add("review", "Missing", "ค่าว่างทั้งไฟล์", int(df.isna().sum().sum()))

    for c in ("review_score", "total_positive", "total_negative", "total_reviews"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    mismatch = int((df["total_positive"] + df["total_negative"]
                    != df["total_reviews"]).sum())
    add("review", "Invalid", "positive + negative != total", mismatch)
    add("review", "Invalid", "review_score นอกช่วง 0-9",
        int((~df["review_score"].between(0, 9)).sum()))
    neg = int(sum((df[c] < 0).sum() for c in
                  ("total_positive", "total_negative", "total_reviews")))
    add("review", "Invalid", "ค่าติดลบ", neg)

    # Zero Variance: คอลัมน์ที่มีค่าเดียวทั้งไฟล์ ใช้วิเคราะห์ไม่ได้
    zero_var = [c for c in df.columns if df[c].nunique(dropna=False) <= 1]
    add("review", "ZeroVariance", f"คอลัมน์ที่มีค่าเดียวทั้งไฟล์ {zero_var}",
        len(zero_var))

    profile["review"] = {"rows": len(df), "duplicates": dup,
                         "sum_mismatch": mismatch, "zero_variance": zero_var}


# ===============================================================
# 3. SteamSpy (CSV จาก Kaggle)
# ===============================================================
def profile_spy():
    banner("PROFILE 3/3 — all_data.csv (SteamSpy)")
    if not SPY_CSV.exists():
        print(f"ไม่พบไฟล์ {SPY_CSV.name} — ข้ามขั้นนี้")
        return

    df = pd.read_csv(SPY_CSV)
    print(f"จำนวนแถว: {len(df):,} | คอลัมน์: {df.shape[1]}\n")

    unnamed = [c for c in df.columns if c.startswith("Unnamed")]
    add("steamspy", "Format", f"คอลัมน์ index ติดมาจากการ export {unnamed}",
        len(unnamed))
    add("steamspy", "Duplicate", "appid ซ้ำ", int(df["appid"].duplicated().sum()))

    nulls = df.isna().sum()
    for c, v in nulls[nulls > 0].items():
        add("steamspy", "Missing", f"คอลัมน์ {c} ว่าง", int(v))

    if "owners" in df.columns:
        as_range = int(df["owners"].astype(str).str.contains(r"\.\.").sum())
        add("steamspy", "Unit", "owners เป็นข้อความช่วง ต้องแปลงเป็นตัวเลข", as_range)

    metric_cols = ["average_forever", "average_2weeks", "median_forever",
                   "median_2weeks", "ccu"]
    non_numeric = 0
    negative = 0
    for c in metric_cols:
        if c not in df.columns:
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        non_numeric += int(s.isna().sum() - df[c].isna().sum())
        negative += int((s < 0).sum())
    add("steamspy", "Invalid", "ค่าที่แปลงเป็นตัวเลขไม่ได้", non_numeric)
    add("steamspy", "Invalid", "ค่าติดลบในคอลัมน์ที่ไม่ควรติดลบ", negative)

    zero_var = [c for c in df.columns if df[c].nunique(dropna=False) <= 1]
    add("steamspy", "ZeroVariance", f"คอลัมน์ที่มีค่าเดียวทั้งไฟล์ {zero_var}",
        len(zero_var))

    profile["steamspy"] = {"rows": len(df), "columns": df.shape[1],
                           "zero_variance": zero_var}


# ===============================================================
# 4. Mismatched Keys — ตรวจว่า 3 แหล่ง join กันติดแค่ไหน
# ===============================================================
def profile_keys():
    banner("PROFILE — Mismatched Keys ระหว่าง 3 แหล่ง")
    sets = {}

    if STORE_JSON.exists():
        sets["store (steam_appid)"] = {g.get("steam_appid")
                                       for g in iter_json_array(STORE_JSON)}
    rv = load_json(REVIEW_JSON)
    if rv is not None:
        sets["review (steam_appid)"] = {r.get("steam_appid") for r in rv}
    if SPY_CSV.exists():
        sets["steamspy (appid)"] = set(pd.read_csv(SPY_CSV, usecols=["appid"])["appid"])

    if len(sets) < 2:
        print("ข้อมูลไม่พอเทียบคีย์")
        return

    for name, s in sets.items():
        print(f"  {name:24s} {len(s):>8,} คีย์")
    inter = set.intersection(*sets.values())
    print(f"\n  คีย์ที่มีครบทุกแหล่ง       {len(inter):>8,}")
    add("all", "MismatchedKeys",
        "คีย์คนละชื่อ (steam_appid vs appid) ต้อง rename ก่อน join", 1)
    for name, s in sets.items():
        add("all", "MismatchedKeys", f"มีใน {name} แต่ไม่ครบแหล่งอื่น",
            len(s) - len(inter))
    profile["joinable_keys"] = len(inter)


# ===============================================================
# 5. เขียนรายงาน
# ===============================================================
def write_report():
    banner("สรุปผล Data Profiling")
    df = pd.DataFrame(findings)
    if df.empty:
        print("ไม่มีผลการตรวจ (อาจยังไม่มีไฟล์ดิบ)")
        return

    summary = df.groupby("issue")["count"].agg(["size", "sum"])
    summary.columns = ["จำนวนรายการตรวจ", "จำนวนที่พบรวม"]
    print(summary.to_string())

    profile["findings"] = findings
    save_json(PROFILE_JSON, profile)

    lines = ["# Data Profiling Report", "",
             "ตรวจก่อนเข้าขั้น Clean — ขั้นนี้ไม่แก้ไขข้อมูลใด ๆ", "",
             "| แหล่งข้อมูล | ประเภทปัญหา | รายละเอียด | จำนวน |",
             "|---|---|---|---|"]
    for f in findings:
        lines.append(f"| {f['source']} | {f['issue']} | {f['detail']} | {f['count']:,} |")
    PROFILE_MD.write_text("\n".join(lines), encoding="utf-8")

    print(f"\nบันทึกรายงานแล้ว:")
    print(f"  {PROFILE_JSON}")
    print(f"  {PROFILE_MD}")


def main():
    profile_store()
    profile_reviews()
    profile_spy()
    profile_keys()
    write_report()


if __name__ == "__main__":
    main()
