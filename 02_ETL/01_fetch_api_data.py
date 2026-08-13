"""
=====================================================================
 01_fetch_api_data.py — EXTRACT: ดึงข้อมูลจาก Steam API ทั้ง 2 แหล่ง
=====================================================================
 รวมงานของ Extract_steam_store_API.ipynb และ Extract_reviewAPI.ipynb
 ไว้ในไฟล์เดียว โดยคงตรรกะเดิมทุกอย่าง:
   - seed รายชื่อเกมจาก games.csv กรองเฉพาะปี 2020 เป็นต้นไป
   - ยิง Steam Store API (appdetails) ด้วย cc=th เพื่อให้ราคาเป็นเงินบาท
   - ยิง Steam Reviews API (appreviews) ด้วย num_per_page=0 เอาเฉพาะ summary
   - ระบบ Checkpoint: ดึงต่อจากที่ค้างไว้ได้ ไม่ต้องเริ่มใหม่
   - หน่วงเวลา 1.5 วินาที และพัก 30 วินาทีเมื่อติด Rate Limit (429)

 ชื่อไฟล์ผลลัพธ์ใน 01_Raw_Data ยังเหมือนเดิมทุกไฟล์:
   steam_store_API.json / failed_app_ids.json
   steam_reviews_summary_data.json / failed_reviews_app_ids.json

 วิธีใช้ (รันจาก Project Root):
   python 02_ETL/01_fetch_api_data.py                 # ดึงทั้งสองแหล่ง
   python 02_ETL/01_fetch_api_data.py --source store  # เฉพาะ Store API
   python 02_ETL/01_fetch_api_data.py --source review # เฉพาะ Reviews API
   python 02_ETL/01_fetch_api_data.py --limit 100     # ทดลองดึงแค่ 100 เกม
=====================================================================
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from common import (API_BATCH_SAVE, API_DELAY_SEC, API_TIMEOUT, REVIEW_FAILED,
                    REVIEW_JSON, SEED_CSV, SEED_YEAR_FROM, STORE_FAILED,
                    STORE_JSON, banner, iter_json_array, load_json)

STORE_URL = "https://store.steampowered.com/api/appdetails"
REVIEW_URL = "https://store.steampowered.com/appreviews/{}"


# ===============================================================
# ตัวช่วยร่วมของทั้งสองแหล่ง
# ===============================================================
def save_progress(data_path, data, failed_path, failed):
    """บันทึก checkpoint ทั้งไฟล์ข้อมูลสำเร็จและรายการที่ดึงพลาด"""
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    with open(failed_path, "w", encoding="utf-8") as f:
        json.dump(failed, f, ensure_ascii=False, indent=4)


def load_seed_app_ids():
    """อ่าน games.csv แล้วกรองเฉพาะเกมที่วางจำหน่ายตั้งแต่ปี SEED_YEAR_FROM"""
    if not SEED_CSV.exists():
        print(f"ไม่พบไฟล์ seed: {SEED_CSV}")
        print("ต้องมี games.csv (จาก Kaggle) ใน 01_Raw_Data ก่อน")
        return []
    df = pd.read_csv(SEED_CSV)
    df["date_release"] = pd.to_datetime(df["date_release"], errors="coerce")
    df = df[df["date_release"].dt.year >= SEED_YEAR_FROM]
    ids = df["app_id"].dropna().unique().tolist()
    print(f"เกมที่วางจำหน่ายตั้งแต่ปี {SEED_YEAR_FROM}: {len(ids):,} เกม")
    return ids


def existing_store_app_ids():
    """
    อ่าน steam_store_API.json เพื่อเอา steam_appid ที่ดึงสำเร็จแล้ว
    ใช้ streaming เพราะไฟล์นี้อาจใหญ่หลายร้อย MB
    """
    if not STORE_JSON.exists():
        return []
    return [g.get("steam_appid") for g in iter_json_array(STORE_JSON)
            if g.get("steam_appid") is not None]


# ===============================================================
# 1. Steam Store API
# ===============================================================
def fetch_store(limit=None):
    banner("EXTRACT 1/2 — Steam Store API (appdetails)")
    import requests

    target_app_ids = load_seed_app_ids()
    if not target_app_ids:
        return

    all_games_data = load_json(STORE_JSON, []) or []
    fetched_app_ids = {item.get("steam_appid") for item in all_games_data
                       if "steam_appid" in item}
    failed_app_ids = load_json(STORE_FAILED, []) or []
    print(f"ดึงสำเร็จแล้ว: {len(fetched_app_ids):,} เกม | เคยพลาด: {len(failed_app_ids):,} เกม")

    skip_ids = fetched_app_ids.union(set(failed_app_ids))
    remaining = [a for a in target_app_ids if a not in skip_ids]
    if limit:
        remaining = remaining[:limit]
    print(f"ต้องดึงเพิ่มรอบนี้: {len(remaining):,} เกม\n")

    if not remaining:
        print("ข้อมูลจาก Store API ครบแล้ว ไม่มีเกมค้าง")
        return

    for index, app_id in enumerate(remaining):
        params = {"appids": app_id, "cc": "th", "l": "english"}
        try:
            resp = requests.get(STORE_URL, params=params, timeout=API_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                if data and str(app_id) in data and data[str(app_id)]["success"]:
                    all_games_data.append(data[str(app_id)]["data"])
                else:
                    failed_app_ids.append(app_id)
            elif resp.status_code == 429:
                print("ติด Rate Limit (429) พัก 30 วินาที...")
                time.sleep(30)
                failed_app_ids.append(app_id)
            else:
                failed_app_ids.append(app_id)
                print(f"ดึงเกม {app_id} ไม่สำเร็จ (status {resp.status_code})")
        except Exception as e:                              # noqa: BLE001
            failed_app_ids.append(app_id)
            print(f"เกิดข้อผิดพลาดกับเกม {app_id}: {e}")

        if (index + 1) % API_BATCH_SAVE == 0 or (index + 1) == len(remaining):
            save_progress(STORE_JSON, all_games_data, STORE_FAILED, failed_app_ids)
            print(f"[Checkpoint] บันทึกแล้ว {len(all_games_data):,} เกม "
                  f"| พลาดสะสม {len(failed_app_ids):,} เกม")
        if (index + 1) % 50 == 0:
            print(f"คืบหน้า: {index + 1:,} / {len(remaining):,}")

        time.sleep(API_DELAY_SEC)

    print(f"\nเสร็จสิ้น | สำเร็จรวม {len(all_games_data):,} เกม "
          f"| พลาดรวม {len(failed_app_ids):,} เกม")


# ===============================================================
# 2. Steam Reviews API
# ===============================================================
def fetch_reviews(limit=None):
    banner("EXTRACT 2/2 — Steam Reviews API (appreviews)")
    import requests

    target_app_ids = list(set(existing_store_app_ids()))
    if not target_app_ids:
        print("ยังไม่มี steam_store_API.json — ต้องรันขั้น Store API ให้เสร็จก่อน")
        return
    print(f"เกมที่ต้องดึงรีวิวทั้งหมด: {len(target_app_ids):,} เกม")

    all_reviews = load_json(REVIEW_JSON, []) or []
    fetched_app_ids = {item.get("steam_appid") for item in all_reviews
                       if "steam_appid" in item}
    failed_app_ids = load_json(REVIEW_FAILED, []) or []
    print(f"ดึงสำเร็จแล้ว: {len(fetched_app_ids):,} เกม | เคยพลาด: {len(failed_app_ids):,} เกม")

    skip_ids = fetched_app_ids.union(set(failed_app_ids))
    remaining = [a for a in target_app_ids if a not in skip_ids]
    if limit:
        remaining = remaining[:limit]
    print(f"ต้องดึงเพิ่มรอบนี้: {len(remaining):,} เกม\n")

    if not remaining:
        print("ข้อมูลรีวิวครบแล้ว ไม่มีเกมค้าง")
        return

    for index, app_id in enumerate(remaining):
        # num_per_page=0 คือไม่เอาข้อความรีวิว เอาแค่ query_summary
        params = {"json": 1, "language": "all", "num_per_page": 0}
        try:
            resp = requests.get(REVIEW_URL.format(int(app_id)),
                                params=params, timeout=API_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                if data and data.get("success") == 1:
                    summary = data.get("query_summary", {})
                    summary["steam_appid"] = app_id     # แนบ id กลับเข้าไปอ้างอิง
                    all_reviews.append(summary)
                else:
                    failed_app_ids.append(app_id)
            elif resp.status_code == 429:
                print("ติด Rate Limit (429) พัก 30 วินาที...")
                time.sleep(30)
                failed_app_ids.append(app_id)
            else:
                failed_app_ids.append(app_id)
                print(f"ดึงรีวิวเกม {app_id} ไม่สำเร็จ (status {resp.status_code})")
        except Exception as e:                              # noqa: BLE001
            failed_app_ids.append(app_id)
            print(f"เกิดข้อผิดพลาดกับเกม {app_id}: {e}")

        if (index + 1) % API_BATCH_SAVE == 0 or (index + 1) == len(remaining):
            save_progress(REVIEW_JSON, all_reviews, REVIEW_FAILED, failed_app_ids)
            print(f"[Checkpoint] บันทึกแล้ว {len(all_reviews):,} เกม")
        if (index + 1) % 50 == 0:
            print(f"คืบหน้า: {index + 1:,} / {len(remaining):,}")

        time.sleep(API_DELAY_SEC)

    print(f"\nเสร็จสิ้น | สำเร็จรวม {len(all_reviews):,} เกม "
          f"| พลาดรวม {len(failed_app_ids):,} เกม")


def main():
    ap = argparse.ArgumentParser(description="ดึงข้อมูลจาก Steam API")
    ap.add_argument("--source", choices=["all", "store", "review"], default="all",
                    help="เลือกแหล่งที่จะดึง (ค่าเริ่มต้น: all)")
    ap.add_argument("--limit", type=int, default=None,
                    help="จำกัดจำนวนเกมต่อรอบ ใช้ตอนทดสอบ")
    args = ap.parse_args()

    if args.source in ("all", "store"):
        fetch_store(args.limit)
    if args.source in ("all", "review"):
        fetch_reviews(args.limit)

    banner("สรุปไฟล์ใน 01_Raw_Data")
    for p in (STORE_JSON, STORE_FAILED, REVIEW_JSON, REVIEW_FAILED):
        status = f"{p.stat().st_size / 1024 / 1024:,.1f} MB" if p.exists() else "ยังไม่มี"
        print(f"  {p.name:38s} {status}")


if __name__ == "__main__":
    main()
