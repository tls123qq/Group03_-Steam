# โครงการวิเคราะห์แนวโน้มตลาดและพฤติกรรมผู้เล่นเกมบนแพลตฟอร์ม Steam

Mini Data Warehouse & Analytics Dashboard — Group 03

---

## โครงสร้างโปรเจกต์

```
Group03_โครงการวิเคราะห์แนวโน้มตลาดและพฤติกรรมผู้เล่นเกมบนแพลตฟอร์ม Steam/
├── 01_Raw_Data/                    ข้อมูลดิบ (ไม่แก้ไขด้วยมือเด็ดขาด)
│   ├── games.csv                     seed จาก Kaggle
│   ├── all_data.csv                  SteamSpy จาก Kaggle
│   ├── steam_store_API.json          ผลดึงจาก Steam Store API (~420 MB)
│   ├── steam_reviews_summary_data.json  ผลดึงจาก Steam Reviews API
│   ├── failed_app_ids.json           รายการที่ดึงพลาด (Store)
│   └── failed_reviews_app_ids.json   รายการที่ดึงพลาด (Reviews)
│
├── 02_ETL/
│   ├── common.py                   path, พารามิเตอร์, ฟังก์ชันที่ใช้ร่วมกัน
│   ├── 01_fetch_api_data.py        EXTRACT  — ดึงจาก API ทั้ง 2 แหล่ง
│   ├── 02_profile_data.py          PROFILE  — ตรวจคุณภาพข้อมูล (ไม่แก้ข้อมูล)
│   ├── 03_transform_load.py        CLEAN + TRANSFORM + INTEGRATE + LOAD
│   ├── 04_validate_dw.py           VALIDATE — ตรวจ 95 รายการหลัง Load
│   ├── cleaned/                    ไฟล์ระหว่างทางที่ clean แล้ว
│   └── reports/                    รายงานคุณภาพข้อมูลและผลตรวจสอบ
│
├── 03_Data_Warehouse/              Star Schema 16 ตาราง (.csv)
├── 04_Dashboard/app.py             Streamlit Dashboard
├── 05_AI_Usage_Log/                บันทึกการใช้ AI
├── tests/test_pipeline.py          pytest 73 เคส
├── pytest.ini
└── requirements.txt
```

---

## วิธีรันทั้งระบบ (รันจาก Project Root ทุกคำสั่ง)

```bash
# 0) สร้าง Virtual Environment และติดตั้ง dependency
# สร้าง .venv (ทำแค่ครั้งแรก)
py -m venv .venv

# เปิดใช้งาน venv (ต้องทำทุกครั้งก่อนรันสคริปต์)
# สำหรับ Windows:
.venv\Scripts\activate
# สำหรับ macOS/Linux:
source .venv/bin/activate

# ติดตั้ง dependency
python -m pip install -r requirements.txt

# 1) EXTRACT — ดึงข้อมูลจาก Steam API ทั้ง 2 แหล่ง
#    ใช้เวลานานมาก (~10 ชม. สำหรับ 23,000 เกม เพราะหน่วง 1.5 วิ/เกม)
#    มีระบบ checkpoint ถ้าหลุดกลางทางรันซ้ำได้เลย จะดึงต่อจากเดิม
python 02_ETL/01_fetch_api_data.py
python 02_ETL/01_fetch_api_data.py --limit 100      # ทดลองแค่ 100 เกม
python 02_ETL/01_fetch_api_data.py --source review  # ดึงเฉพาะรีวิว

# 2) PROFILE — ตรวจปัญหาคุณภาพข้อมูลก่อน clean
python 02_ETL/02_profile_data.py

# 3) CLEAN + TRANSFORM + LOAD — สร้าง Star Schema
python 02_ETL/03_transform_load.py
python 02_ETL/03_transform_load.py --skip-clean     # ใช้ไฟล์ cleaned เดิม

# 4) VALIDATE — ตรวจความถูกต้องหลัง Load
python 02_ETL/04_validate_dw.py

# 5) TEST — ทดสอบตรรกะและความถูกต้องของ pipeline
python -m pytest -q

# 6) DASHBOARD
python -m streamlit run 04_Dashboard/app.py
```

**ทุก path เป็น relative จาก Project Root** โดยคำนวณจากตำแหน่งไฟล์เอง
(`Path(__file__).resolve().parents[1]`) จึงรันจากโฟลเดอร์ไหนก็ได้ ไม่ต้องแก้ path

ถ้าไม่มีไฟล์ดิบ `01_Raw_Data/steam_store_API.json` แล้วอยากข้ามขั้น Extract
ให้วางไฟล์ที่ clean แล้ว 3 ไฟล์ไว้ใน `02_ETL/cleaned/` แล้วรันด้วย `--skip-clean`

---

## ผลลัพธ์เมื่อรันครบ

| ขั้นตอน | จำนวน |
|---|---|
| Store API หลัง clean | 21,066 เกม |
| Reviews API หลัง clean | 23,061 แถว |
| SteamSpy หลัง clean | 82,891 แถว |
| **หลัง inner join 3 แหล่ง** | **15,076 เกม** |
| ผลตรวจ validation | ผ่าน 95 / 95 รายการ |
| ผลทดสอบ pytest | ผ่าน 73 / 73 เคส |

---

## Star Schema (16 ตาราง)

**Fact (2)** — grain: 1 แถวต่อ 1 เกม
- `FACT_GAME_ENGAGEMENT` — 10 measures รวม derived 4 ตัว
  (`estimated_revenue`, `concurrent_engagement_rate`, `content_depth_score`, `recommendation_rate`)
- `FACT_GAME_PLAYTIME` — 4 measures เวลาเล่น + `has_playtime`

**Dimension (9)** — `DIM_GAME`, `DIM_DATE`, `DIM_PLATFORM`, `DIM_REVIEW_SCORE`,
`DIM_DEVELOPER`, `DIM_PUBLISHER`, `DIM_GENRE`, `DIM_CATEGORY`, `DIM_LANGUAGE`

**Bridge (5)** — `BRIDGE_GAME_GENRES`, `BRIDGE_GAME_CATEGORIES`,
`BRIDGE_GAME_DEVELOPERS`, `BRIDGE_GAME_PUBLISHERS`, `BRIDGE_GAME_LANGUAGES`

> **สำคัญเรื่อง Bridge:** เกม 1 เกมมีได้หลายแนว/หลายภาษา จึงต้องใช้ bridge table
> เวลานับจำนวนเกมใช้ bridge ตรง ๆ ได้ แต่**เวลารวมตัวเลข measure ต้องคูณ
> `allocation_factor` เสมอ** ไม่งั้นจะนับซ้ำ (ทดสอบแล้ว: รวม owners ผ่าน bridge
> เฉย ๆ เกินจริง 196% แต่คูณ factor แล้วตรงกับยอดจริงพอดี)

---

## ปัญหาคุณภาพข้อมูลที่ตรวจพบและวิธีแก้

| ประเภท | ตัวอย่างที่พบ | แก้ที่ไหน |
|---|---|---|
| Missing Values | เกมฟรี 4,394 เกมไม่มี `price_overview` | เช็ค `is_free` ก่อน ถ้าฟรีให้เก็บไว้และตั้งราคา 0 |
| Duplicate Records | `appid` ซ้ำใน SteamSpy | `drop_duplicates` ก่อน join กัน fan-out |
| Mismatched Keys | `steam_appid` กับ `appid` คนละชื่อ | rename เป็น `app_id` ก่อน join |
| หน่วยวัดไม่ตรงกัน | ราคาเป็นสตางค์, `owners` เป็นข้อความช่วง | หาร 100 / แปลงเป็นค่ากลางของช่วง |
| รูปแบบวันที่ไม่ตรงกัน | `release_date` เป็น dict, มี "Coming Soon" | แตก dict แล้ว `to_datetime(errors='coerce')` |
| Invalid Values | `positive + negative != total` | ตัดแถวที่ขัดแย้งกันเองทิ้ง |
| Zero Variance | `num_reviews` เป็น 0 ทุกแถว | ลบคอลัมน์ทิ้ง |
| Nested JSON | `platforms`, `achievements` เป็น dict ซ้อน | แตกเป็นคอลัมน์เดี่ยว |

---

## ข้อจำกัดของข้อมูลที่ต้องอ่านประกอบทุกกราฟ

1. **`owners` เป็นค่าประมาณ ไม่ใช่ยอดจริง** — SteamSpy ให้มาเป็นช่วง มีเพียง 13 ค่า
   ที่เป็นไปได้ และเกมส่วนใหญ่กองอยู่ที่ช่วงต่ำสุด ค่ามัธยฐานจึงไม่มีความหมาย
   Dashboard จึงใช้**สัดส่วนเกมที่เข้าถึงผู้เล่นเกิน 75,000 คน**เป็นตัววัดหลักแทน
2. **ข้อมูลเป็น snapshot ณ เวลาเดียว** — กราฟรายปีคือการเทียบรุ่นเกมตามปีที่วางจำหน่าย
   ไม่ใช่การเติบโตตามเวลา
3. **ทุกความสัมพันธ์เป็นความสัมพันธ์ ไม่ใช่เหตุและผล** — สตูดิโอที่มีทุนมากกว่า
   ย่อมแปลหลายภาษา หาผู้จัดจำหน่ายได้ และเปิดฟีเจอร์ครบกว่าอยู่แล้ว

---

## แหล่งข้อมูล

| แหล่ง | ประเภท | ที่มา |
|---|---|---|
| Steam Store API | Nested JSON ผ่าน API | `store.steampowered.com/api/appdetails` (`cc=th`) |
| Steam Reviews API | Nested JSON ผ่าน API | `store.steampowered.com/appreviews` (`num_per_page=0`) |
| SteamSpy | CSV | Kaggle — ระบุลิงก์และวันที่ดาวน์โหลดในรายงาน |
| games.csv (seed) | CSV | Kaggle — ระบุลิงก์และวันที่ดาวน์โหลดในรายงาน |
