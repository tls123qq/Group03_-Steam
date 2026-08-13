"""
=====================================================================
 common.py — ค่าคงที่และฟังก์ชันที่ใช้ร่วมกันทุกสคริปต์ใน 02_ETL
=====================================================================
 ทุก path ในไฟล์นี้อ้างอิงจาก Project Root โดยคำนวณจากตำแหน่งไฟล์เอง
 จึงรันจากที่ไหนก็ได้โดยไม่ต้องแก้ path ด้วยมือ

 หมายเหตุเรื่องการ import: ชื่อไฟล์สคริปต์ขึ้นต้นด้วยตัวเลข (01_, 02_, ...)
 ซึ่ง Python import ตรง ๆ ไม่ได้ แต่ละสคริปต์จึงเติมโฟลเดอร์ 02_ETL
 เข้า sys.path แล้ว import จากไฟล์นี้แทน
=====================================================================
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------
# PATHS — คำนวณจากตำแหน่งของไฟล์นี้ ( <ROOT>/02_ETL/common.py )
# ---------------------------------------------------------------
ETL_DIR = Path(__file__).resolve().parent
ROOT = ETL_DIR.parent

RAW_DIR = ROOT / "01_Raw_Data"
CLEAN_DIR = ETL_DIR / "cleaned"
REPORT_DIR = ETL_DIR / "reports"
DW_DIR = ROOT / "03_Data_Warehouse"
DASH_DIR = ROOT / "04_Dashboard"

# ไฟล์ดิบ (ชื่อต้องตรงกับที่ระบบเดิมใช้ ห้ามเปลี่ยน)
SEED_CSV = RAW_DIR / "games.csv"
SPY_CSV = RAW_DIR / "all_data.csv"
STORE_JSON = RAW_DIR / "steam_store_API.json"
STORE_FAILED = RAW_DIR / "failed_app_ids.json"
REVIEW_JSON = RAW_DIR / "steam_reviews_summary_data.json"
REVIEW_FAILED = RAW_DIR / "failed_reviews_app_ids.json"

# ไฟล์ที่ผ่านการ clean แล้ว
STORE_CLEAN = CLEAN_DIR / "steam_store_API_Cleaned.csv"
SPY_CLEAN = CLEAN_DIR / "allData_cleaned.csv"
REVIEW_CLEAN = CLEAN_DIR / "steam_reviews_summary_data.csv"

# รายงาน
PROFILE_JSON = REPORT_DIR / "data_profile.json"
PROFILE_MD = REPORT_DIR / "data_profile.md"
QA_LOG = REPORT_DIR / "qa_log_cleaning.json"
DQ_REPORT = REPORT_DIR / "data_quality_report.csv"
VALIDATION_REPORT = REPORT_DIR / "validation_report.csv"

for _d in (RAW_DIR, CLEAN_DIR, REPORT_DIR, DW_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------
# PARAMETERS — ปรับค่าที่นี่จุดเดียว
# ---------------------------------------------------------------
SEED_YEAR_FROM = 2020           # ดึงเฉพาะเกมที่วางจำหน่ายตั้งแต่ปีนี้
API_DELAY_SEC = 1.5             # หน่วงเวลาระหว่างการยิง API
API_BATCH_SAVE = 500            # บันทึก checkpoint ทุกกี่เกม
API_TIMEOUT = 10

DLC_WEIGHT = 5                  # weight ของ dlc_count ใน content_depth_score
PREMIUM_MULTIPLIER = 1.5        # เกม premium = ราคาสูงกว่าค่าเฉลี่ยของแนวหลักกี่เท่า

PRICE_TIER_BINS = [0, 0.01, 99, 199, 299, 499, 799, float("inf")]
PRICE_TIER_LABELS = ["Free", "1-99", "100-199", "200-299", "300-499", "500-799", "800+"]

DEPTH_TIER_BINS = [-1, 10, 30, 60, float("inf")]
DEPTH_TIER_LABELS = ["low", "medium", "high", "very high"]

BREAKOUT_OWNERS = 75_000        # เกณฑ์ "เข้าถึงผู้เล่นได้กว้าง" ที่ใช้ใน Dashboard

CORP_SUFFIX = {
    "inc", "llc", "l.l.c", "ltd", "co", "corp", "gmbh", "s.a", "s.l", "sa",
    "llp", "pte", "pty", "srl", "bv", "b.v", "ab", "as", "oy", "kk", "k.k",
    "plc", "ag", "ug", "sas", "sarl", "s.r.o", "z o.o", "limited", "company",
    "jsc", "ooo",
}

# ลำดับตารางใน Data Warehouse — ใช้ทั้งตอน export, validate และ test
DIM_TABLES = ["DIM_GAME", "DIM_DATE", "DIM_PLATFORM", "DIM_REVIEW_SCORE",
              "DIM_DEVELOPER", "DIM_PUBLISHER", "DIM_GENRE", "DIM_CATEGORY",
              "DIM_LANGUAGE"]
FACT_TABLES = ["FACT_GAME_ENGAGEMENT", "FACT_GAME_PLAYTIME"]
BRIDGE_TABLES = ["BRIDGE_GAME_GENRES", "BRIDGE_GAME_CATEGORIES",
                 "BRIDGE_GAME_DEVELOPERS", "BRIDGE_GAME_PUBLISHERS",
                 "BRIDGE_GAME_LANGUAGES"]
ALL_TABLES = DIM_TABLES + FACT_TABLES + BRIDGE_TABLES

# คีย์หลักของแต่ละตาราง ใช้ตรวจสอบใน 04_validate_dw.py และ pytest
PRIMARY_KEYS = {
    "DIM_GAME": ["game_key"],
    "DIM_DATE": ["date_key"],
    "DIM_PLATFORM": ["platform_key"],
    "DIM_REVIEW_SCORE": ["review_score_key"],
    "DIM_DEVELOPER": ["developer_key"],
    "DIM_PUBLISHER": ["publisher_key"],
    "DIM_GENRE": ["genre_key"],
    "DIM_CATEGORY": ["category_key"],
    "DIM_LANGUAGE": ["language_key"],
    "FACT_GAME_ENGAGEMENT": ["engagement_key"],
    "FACT_GAME_PLAYTIME": ["playtime_key"],
    "BRIDGE_GAME_GENRES": ["game_key", "genre_key"],
    "BRIDGE_GAME_CATEGORIES": ["game_key", "category_key"],
    "BRIDGE_GAME_DEVELOPERS": ["game_key", "developer_key"],
    "BRIDGE_GAME_PUBLISHERS": ["game_key", "publisher_key"],
    "BRIDGE_GAME_LANGUAGES": ["game_key", "language_key"],
}

# ความสัมพันธ์ FK: (ตารางลูก, คอลัมน์) -> (ตารางแม่, คอลัมน์)
FOREIGN_KEYS = [
    ("FACT_GAME_ENGAGEMENT", "game_key", "DIM_GAME", "game_key"),
    ("FACT_GAME_ENGAGEMENT", "date_key", "DIM_DATE", "date_key"),
    ("FACT_GAME_ENGAGEMENT", "platform_key", "DIM_PLATFORM", "platform_key"),
    ("FACT_GAME_ENGAGEMENT", "review_score_key", "DIM_REVIEW_SCORE", "review_score_key"),
    ("FACT_GAME_ENGAGEMENT", "primary_developer_key", "DIM_DEVELOPER", "developer_key"),
    ("FACT_GAME_ENGAGEMENT", "primary_publisher_key", "DIM_PUBLISHER", "publisher_key"),
    ("FACT_GAME_PLAYTIME", "game_key", "DIM_GAME", "game_key"),
    ("FACT_GAME_PLAYTIME", "date_key", "DIM_DATE", "date_key"),
    ("FACT_GAME_PLAYTIME", "platform_key", "DIM_PLATFORM", "platform_key"),
    ("FACT_GAME_PLAYTIME", "primary_genre_key", "DIM_GENRE", "genre_key"),
    ("FACT_GAME_PLAYTIME", "primary_category_key", "DIM_CATEGORY", "category_key"),
    ("BRIDGE_GAME_GENRES", "game_key", "DIM_GAME", "game_key"),
    ("BRIDGE_GAME_GENRES", "genre_key", "DIM_GENRE", "genre_key"),
    ("BRIDGE_GAME_CATEGORIES", "game_key", "DIM_GAME", "game_key"),
    ("BRIDGE_GAME_CATEGORIES", "category_key", "DIM_CATEGORY", "category_key"),
    ("BRIDGE_GAME_DEVELOPERS", "game_key", "DIM_GAME", "game_key"),
    ("BRIDGE_GAME_DEVELOPERS", "developer_key", "DIM_DEVELOPER", "developer_key"),
    ("BRIDGE_GAME_PUBLISHERS", "game_key", "DIM_GAME", "game_key"),
    ("BRIDGE_GAME_PUBLISHERS", "publisher_key", "DIM_PUBLISHER", "publisher_key"),
    ("BRIDGE_GAME_LANGUAGES", "game_key", "DIM_GAME", "game_key"),
    ("BRIDGE_GAME_LANGUAGES", "language_key", "DIM_LANGUAGE", "language_key"),
]


# ===============================================================
# ฟังก์ชันช่วย — อ่านไฟล์
# ===============================================================
def iter_json_array(path, chunk_size=1 << 20):
    """
    อ่านไฟล์ JSON ที่เป็น array ขนาดใหญ่แบบทีละชิ้น (streaming)
    steam_store_API.json มีขนาดกว่า 400 MB ถ้าใช้ json.load() ปกติ
    จะกินแรมหลาย GB จนเครื่องหยุดทำงาน วิธีนี้ใช้แรมคงที่ไม่ถึง 100 MB
    """
    decoder = json.JSONDecoder()
    buf = ""
    started = False

    with open(path, "r", encoding="utf-8") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            buf += chunk
            while True:
                s = buf.lstrip()
                if not started:
                    if s.startswith("["):
                        buf = s[1:]
                        started = True
                        continue
                    break
                if s.startswith(","):
                    buf = s[1:]
                    continue
                if s.startswith("]"):
                    return
                if not s:
                    buf = s
                    break
                try:
                    obj, idx = decoder.raw_decode(s)
                except ValueError:
                    buf = s          # ข้อมูลยังไม่ครบ object รออ่านก้อนถัดไป
                    break
                buf = s[idx:]
                yield obj

    while True:
        s = buf.lstrip()
        if s.startswith(","):
            buf = s[1:]
            continue
        if not s or s.startswith("]"):
            return
        try:
            obj, idx = decoder.raw_decode(s)
        except ValueError:
            return
        buf = s[idx:]
        yield obj


def load_json(path, default=None):
    """อ่านไฟล์ JSON ถ้าไม่มีไฟล์หรืออ่านไม่ได้ให้คืนค่า default"""
    p = Path(path)
    if not p.exists():
        return default
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# ===============================================================
# ฟังก์ชันช่วย — แปลงค่า (ใช้ในขั้น Clean)
# ===============================================================
def to_bool(v):
    """แปลงเป็น boolean ที่เชื่อถือได้ รองรับทั้ง True/False, 'True'/'False', 1/0"""
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "1", "yes")


def to_int(v, default=0):
    """แปลงเป็นจำนวนเต็ม ถ้าแปลงไม่ได้คืน default (เช่น required_age ที่บางเกมเป็นข้อความ)"""
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return default
        return int(float(str(v).strip()))
    except (ValueError, TypeError):
        return default


def dict_total(v, default=0):
    """ดึงค่า total ออกจาก dict เช่น achievements, recommendations"""
    if isinstance(v, dict):
        return to_int(v.get("total"), default)
    return default


def clean_languages(val):
    """
    ตัด HTML และหมายเหตุท้ายข้อความออกจาก supported_languages
    'English<br><strong>*</strong>languages with full audio' -> 'English'
    """
    if val is None:
        return ""
    text = str(val)
    text = re.sub(r"<br>.*", "", text, flags=re.DOTALL)
    text = re.sub(r"\*languages.*", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    return text.replace("*", "").strip()


def descriptions_of(val):
    """แปลง [{'id':1,'description':'Action'}, ...] ให้เหลือ ['Action', ...]"""
    if not isinstance(val, (list, tuple)):
        return []
    out = []
    for item in val:
        if isinstance(item, dict) and item.get("description"):
            out.append(str(item["description"]).strip())
        elif isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def parse_release_date(val):
    """ดึงวันที่จาก {'coming_soon': False, 'date': '10 Mar, 2021'} -> 'YYYY-MM-DD'"""
    date_str = val.get("date") if isinstance(val, dict) else val
    if not date_str or not isinstance(date_str, str):
        return None
    parsed = pd.to_datetime(date_str, errors="coerce")
    return parsed.strftime("%Y-%m-%d") if pd.notna(parsed) else None


def owners_to_number(val):
    """
    แปลง owners จากช่วงข้อความเป็นตัวเลข
    '10,000 .. 20,000' -> 15000  (ใช้ค่ากลางของช่วง)
    """
    if pd.isna(val):
        return np.nan
    if isinstance(val, (int, float, np.integer, np.floating)):
        return float(val)
    txt = str(val).replace(",", "").strip()
    if ".." in txt:
        parts = [p.strip() for p in txt.split("..")]
        try:
            return (float(parts[0]) + float(parts[1])) / 2
        except (ValueError, IndexError):
            return np.nan
    try:
        return float(txt)
    except ValueError:
        return np.nan


def parse_list_cell(value):
    """
    genres / categories ถูกเก็บเป็นสตริงของ list เช่น "['Indie', 'Strategy']"
    ฟังก์ชันนี้แปลงกลับเป็น list ของ Python จริง ๆ
    """
    import ast
    if pd.isna(value):
        return []
    if isinstance(value, list):
        return value
    txt = str(value).strip()
    if txt in ("", "[]", "nan"):
        return []
    try:
        parsed = ast.literal_eval(txt)
        if isinstance(parsed, (list, tuple)):
            return [str(x).strip() for x in parsed if str(x).strip()]
        return [str(parsed).strip()]
    except (ValueError, SyntaxError):
        return [x.strip() for x in txt.split(",") if x.strip()]


def split_names(raw):
    """
    แยกชื่อผู้พัฒนา/ผู้จัดจำหน่ายที่ต่อกันด้วยคอมมา
        "Sketchbook Developments, Fourth State" -> 2 ราย
    แต่ต้องไม่ตัดคอมมาที่เป็นส่วนหนึ่งของชื่อบริษัท
        "CAPCOM Co., Ltd."                      -> 1 ราย
    """
    if pd.isna(raw) or str(raw).strip() == "":
        return ["Unknown"]
    parts = [p.strip() for p in str(raw).split(",")]
    out = []
    for p in parts:
        if out and p.lower().rstrip(".").strip() in CORP_SUFFIX:
            out[-1] = out[-1] + ", " + p
        elif p:
            out.append(p)
    return out if out else ["Unknown"]


# ===============================================================
# ฟังก์ชันช่วย — สร้าง Dimension / Bridge
# ===============================================================
def build_dim_from_values(values, key_name, value_name):
    """สร้างตารางมิติจากรายชื่อ พร้อมรัน surrogate key 1..N"""
    uniques = sorted(set(v for v in values if pd.notna(v) and str(v).strip() != ""))
    dim = pd.DataFrame({value_name: uniques})
    dim.insert(0, key_name, range(1, len(dim) + 1))
    return dim, dict(zip(dim[value_name], dim[key_name]))


def add_bridge_weights(bridge, key_col, primary_map):
    """
    เติม 2 คอลัมน์ให้ bridge table:
      - allocation_factor = 1/n  กันการนับ measure ซ้ำ
                            เวลา SUM ผ่าน bridge ให้คูณ factor นี้ ผลรวมจะเท่ากับยอดจริง
      - is_primary        = 1 ถ้าเป็นรายแรก (ตัวเดียวกับที่เก็บใน FACT)
    """
    bridge = bridge.copy()
    n = bridge.groupby("game_key")[key_col].transform("size")
    bridge["allocation_factor"] = (1 / n).round(6)
    bridge["is_primary"] = (
        bridge[key_col] == bridge["game_key"].map(primary_map)
    ).astype(int)
    return bridge


def read_dw(table):
    """อ่านตารางจาก Data Warehouse"""
    return pd.read_csv(DW_DIR / f"{table}.csv")


def dw_exists():
    """ตรวจว่า Data Warehouse ถูกสร้างครบทุกตารางแล้วหรือยัง"""
    return all((DW_DIR / f"{t}.csv").exists() for t in ALL_TABLES)


def banner(text):
    print("\n" + "=" * 68)
    print(text)
    print("=" * 68)
