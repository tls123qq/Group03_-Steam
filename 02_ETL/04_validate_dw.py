"""
=====================================================================
 04_validate_dw.py — VALIDATION: ตรวจความถูกต้องหลัง Load
=====================================================================
 ตรวจ 6 กลุ่มตามหลัก Data Warehouse:
   1. Completeness      — มีครบ 16 ตารางไหม
   2. Primary Key       — คีย์หลักซ้ำหรือว่างไหม
   3. Referential       — FK ทุกตัวหา record ในตารางแม่เจอไหม
   4. Grain             — Fact ทั้งสองตารางมี 1 แถวต่อ 1 เกมจริงไหม
   5. Bridge Integrity  — allocation_factor รวมได้ 1.0 และมี is_primary 1 ตัว
   6. Business Rules    — positive+negative=total, เกมฟรีต้องมีรายได้ 0 ฯลฯ

 คืนค่า exit code 1 ถ้ามีข้อใดไม่ผ่าน เพื่อให้ใช้ใน CI/pipeline ได้

 วิธีใช้ (รันจาก Project Root):
   python 02_ETL/04_validate_dw.py
=====================================================================
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from common import (ALL_TABLES, BRIDGE_TABLES, DW_DIR, FOREIGN_KEYS,
                    PRIMARY_KEYS, VALIDATION_REPORT, banner)

results = []


def check(group, name, passed, detail=""):
    results.append({"กลุ่ม": group, "รายการตรวจสอบ": name,
                    "ผล": "ผ่าน" if passed else "ไม่ผ่าน", "รายละเอียด": detail})
    mark = "  ok " if passed else "  FAIL"
    print(f"{mark} {name}  {detail}")
    return passed


def main():
    banner("VALIDATION — ตรวจความถูกต้องของ Data Warehouse")

    # ---------- 1. Completeness ----------
    print("\n[1] Completeness — ตารางครบไหม")
    missing = [t for t in ALL_TABLES if not (DW_DIR / f"{t}.csv").exists()]
    if not check("Completeness", f"มีครบ {len(ALL_TABLES)} ตาราง",
                 not missing, f"ขาด: {missing}" if missing else ""):
        print("\nยังไม่มีตารางครบ — รัน 02_ETL/03_transform_load.py ก่อน")
        sys.exit(1)

    tables = {t: pd.read_csv(DW_DIR / f"{t}.csv") for t in ALL_TABLES}
    for t, df in tables.items():
        check("Completeness", f"{t} มีข้อมูล", len(df) > 0, f"{len(df):,} แถว")

    # ---------- 2. Primary Key ----------
    print("\n[2] Primary Key — คีย์หลักไม่ซ้ำและไม่ว่าง")
    for t, keys in PRIMARY_KEYS.items():
        df = tables[t]
        dup = int(df.duplicated(subset=keys).sum())
        null = int(df[keys].isna().sum().sum())
        check("PrimaryKey", f"{t} PK ไม่ซ้ำ", dup == 0, f"ซ้ำ {dup} แถว")
        check("PrimaryKey", f"{t} PK ไม่ว่าง", null == 0, f"ว่าง {null} ค่า")

    # ---------- 3. Referential Integrity ----------
    print("\n[3] Referential Integrity — FK หา record ในตารางแม่เจอ")
    for child, fk, parent, pk in FOREIGN_KEYS:
        c, p = tables[child], tables[parent]
        vals = c[fk].dropna()
        orphan = int((~vals.isin(set(p[pk]))).sum())
        check("Referential", f"{child}.{fk} -> {parent}.{pk}", orphan == 0,
              f"หาไม่เจอ {orphan} แถว")

    # ---------- 4. Grain ----------
    print("\n[4] Grain — 1 แถวต่อ 1 เกม")
    n_game = len(tables["DIM_GAME"])
    for t in ("FACT_GAME_ENGAGEMENT", "FACT_GAME_PLAYTIME"):
        df = tables[t]
        check("Grain", f"{t} มี 1 แถวต่อ 1 เกม",
              len(df) == n_game and df["game_key"].duplicated().sum() == 0,
              f"{len(df):,} แถว / เกม {n_game:,} เกม")

    # ---------- 5. Bridge Integrity ----------
    print("\n[5] Bridge Integrity — allocation_factor และ is_primary")
    for t in BRIDGE_TABLES:
        df = tables[t]
        key_col = [c for c in df.columns
                   if c.endswith("_key") and c != "game_key"][0]
        alloc = df.groupby("game_key")["allocation_factor"].sum().round(3)
        bad_alloc = int((alloc != 1.0).sum())
        prim = df.groupby("game_key")["is_primary"].sum()
        bad_prim = int((prim != 1).sum())
        check("Bridge", f"{t} allocation_factor รวมได้ 1.0", bad_alloc == 0,
              f"ผิด {bad_alloc} เกม")
        check("Bridge", f"{t} มี is_primary 1 ตัวต่อเกม", bad_prim == 0,
              f"ผิด {bad_prim} เกม")
        check("Bridge", f"{t} ไม่มีคู่ซ้ำ",
              int(df.duplicated(subset=["game_key", key_col]).sum()) == 0)

    # ---------- 6. Business Rules ----------
    print("\n[6] Business Rules — กฎทางธุรกิจที่ต้องเป็นจริงเสมอ")
    eng = tables["FACT_GAME_ENGAGEMENT"]
    game = tables["DIM_GAME"]
    m = eng.merge(game, on="game_key")

    check("BusinessRule", "positive + negative = total_reviews",
          int((m["total_positive"] + m["total_negative"]
               != m["total_reviews"]).sum()) == 0)
    check("BusinessRule", "เกมฟรีต้องมี estimated_revenue = 0",
          int(((m["is_free"] == 1) & (m["estimated_revenue"] != 0)).sum()) == 0)
    check("BusinessRule", "owners มากกว่า 0 ทุกแถว",
          int((eng["owners"] <= 0).sum()) == 0)
    check("BusinessRule", "ccu ไม่เกิน owners",
          int((eng["ccu"] > eng["owners"]).sum()) == 0)
    check("BusinessRule", "concurrent_engagement_rate อยู่ในช่วง 0-1",
          int((eng["concurrent_engagement_rate"].dropna() > 1).sum()) == 0)
    check("BusinessRule", "ไม่มี measure ติดลบ",
          int(sum((eng[c] < 0).sum() for c in
                  ["total_positive", "total_negative", "total_reviews",
                   "recommendations", "ccu", "estimated_revenue",
                   "content_depth_score"])) == 0)
    check("BusinessRule", "content_depth_score ตรงกับ achievements + dlc*5",
          int((m["content_depth_score"]
               != m["achievements_total"] + m["dlc_count"] * 5).sum()) == 0)
    check("BusinessRule", "review_score อยู่ในช่วง 0-9",
          int((~tables["DIM_REVIEW_SCORE"]["review_score"]
               .between(0, 9)).sum()) == 0)

    # ---------- สรุป ----------
    banner("สรุปผล Validation")
    report = pd.DataFrame(results)
    report.to_csv(VALIDATION_REPORT, index=False, encoding="utf-8-sig")

    summary = report.groupby(["กลุ่ม", "ผล"]).size().unstack(fill_value=0)
    print(summary.to_string())

    failed = report[report["ผล"] == "ไม่ผ่าน"]
    print(f"\nตรวจทั้งหมด {len(report)} รายการ | ผ่าน {len(report) - len(failed)} "
          f"| ไม่ผ่าน {len(failed)}")
    print(f"บันทึกรายงาน: {VALIDATION_REPORT}")

    if len(failed):
        print("\nรายการที่ไม่ผ่าน:")
        print(failed.to_string(index=False))
        sys.exit(1)
    print("\nData Warehouse ผ่านการตรวจสอบทั้งหมด พร้อมใช้งาน")


if __name__ == "__main__":
    main()
