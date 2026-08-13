"""
=====================================================================
 app.py — Interactive Dashboard (Streamlit + Altair)
=====================================================================
 อ่านข้อมูลจาก 03_Data_Warehouse โดยตรง ไม่มีการคำนวณซ้ำจากไฟล์ดิบ

 การแสดงผล
   - กราฟทุกตัวเป็นกราฟแท่งแนวนอน (horizontal bar) เพื่อให้อ่านชื่อหมวดหมู่
     ที่ยาว ๆ เช่นชื่อฟีเจอร์หรือชื่อภาษาได้ครบโดยไม่ต้องเอียงตัวอักษร
   - หมวดหมู่ที่เป็นช่วงตัวเลขถูกบังคับลำดับด้วย sort=[...] เสมอ
     ไม่ปล่อยให้ Altair เรียงตามตัวอักษร (ซึ่งจะได้ "10-20" มาก่อน "2-3")
   - หมวดหมู่ที่ไม่มีลำดับตามธรรมชาติ (ภาษา, ฟีเจอร์) เรียงตามค่าด้วย sort='-x'

 ลำดับการ์ด: Q1 -> Q2 -> Q3 -> Q4 -> Q5 -> วิเคราะห์ตามช่วงเวลา -> Insights

 วิธีใช้ (รันจาก Project Root):
   python -m streamlit run 04_Dashboard/app.py
=====================================================================
"""

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "02_ETL"))

from common import ALL_TABLES, BREAKOUT_OWNERS, DW_DIR, dw_exists

st.set_page_config(page_title="Steam Games Analytics", layout="wide")

# ---------------------------------------------------------------
# ลำดับหมวดหมู่ที่ต้องบังคับ (ห้ามปล่อยให้เรียงตามตัวอักษร)
# ---------------------------------------------------------------
LANG_BANDS = [(1, 1, "1 ภาษา"), (2, 3, "2-3 ภาษา"), (4, 9, "4-9 ภาษา"),
              (10, 20, "10-20 ภาษา"), (21, 999, "21+ ภาษา")]
LANG_BAND_ORDER = [b[2] for b in LANG_BANDS]

PLATFORM_ORDER = ["Windows", "Windows + Mac", "Windows + Linux",
                  "Windows + Mac + Linux"]
PUBLISHER_ORDER = ["จัดจำหน่ายเอง", "มีผู้จัดจำหน่าย"]
PRICE_GROUP_ORDER = ["เกมฟรี", "เกมขาย"]

BAR = "#4C78A8"
BAR_ALT = "#72B7B2"
BASELINE = "#E8A33D"
MIN_N = 25          # ต่ำกว่านี้ถือว่ากลุ่มเล็กเกินกว่าจะสรุป


# ===============================================================
# โหลดข้อมูล
# ===============================================================
@st.cache_data
def load_tables():
    return {t: pd.read_csv(DW_DIR / f"{t}.csv") for t in ALL_TABLES}


@st.cache_data
def build_analysis_frame():
    """ประกอบตารางวิเคราะห์หลัก: 1 แถวต่อ 1 เกม"""
    t = load_tables()
    df = (t["FACT_GAME_ENGAGEMENT"]
          .merge(t["DIM_GAME"], on="game_key")
          .merge(t["FACT_GAME_PLAYTIME"][["game_key", "average_forever",
                                          "median_forever", "has_playtime"]],
                 on="game_key")
          .merge(t["DIM_DATE"][["date_key", "year", "quarter"]], on="date_key")
          .merge(t["DIM_REVIEW_SCORE"][["review_score_key", "review_score",
                                        "sentiment_band"]], on="review_score_key")
          .merge(t["DIM_PLATFORM"][["platform_key", "platform_count",
                                    "platform_desc"]], on="platform_key"))

    # self_published: ผู้พัฒนาหลักกับผู้จัดจำหน่ายหลักเป็นรายเดียวกันหรือไม่
    dev = (t["BRIDGE_GAME_DEVELOPERS"].query("is_primary == 1")
           .merge(t["DIM_DEVELOPER"], on="developer_key")[["game_key", "developer_name"]])
    pub = (t["BRIDGE_GAME_PUBLISHERS"].query("is_primary == 1")
           .merge(t["DIM_PUBLISHER"], on="publisher_key")[["game_key", "publisher_name"]])
    sp = dev.merge(pub, on="game_key")
    sp["self_published"] = (sp["developer_name"].str.lower().str.strip()
                            == sp["publisher_name"].str.lower().str.strip()).astype(int)
    df = df.merge(sp[["game_key", "self_published"]], on="game_key", how="left")

    genre = (t["BRIDGE_GAME_GENRES"].query("is_primary == 1")
             .merge(t["DIM_GENRE"][["genre_key", "genre_name"]], on="genre_key"))
    df = df.merge(genre[["game_key", "genre_name"]], on="game_key", how="left")

    df["breakout"] = (df["owners"] >= BREAKOUT_OWNERS).astype(int)
    return df


def breakout_pct(d):
    return d["breakout"].mean() * 100 if len(d) else 0.0


# ===============================================================
# ฟังก์ชันวาดกราฟแท่งแนวนอน (ใช้ร่วมกันทุกกราฟในหน้านี้)
# ===============================================================
def hbar(df, cat_col, val_col, sort_order=None, x_title="", fmt=".1f",
         color=BAR, baseline=None, n_col=None):
    """
    กราฟแท่งแนวนอนมาตรฐานของ Dashboard นี้

    sort_order  ส่ง list ของชื่อหมวดหมู่เพื่อบังคับลำดับแกน Y
                ใช้กับหมวดหมู่ที่เป็นช่วงตัวเลข เช่น
                "1 ภาษา" -> "2-3 ภาษา" -> "4-9 ภาษา" -> "10-20 ภาษา" -> "21+ ภาษา"
                ถ้าไม่ส่ง จะเรียงจากค่ามากไปน้อยด้วย '-x'
    baseline    ค่าเส้นอ้างอิง (ค่าเฉลี่ยของคลังเกมตามตัวกรองปัจจุบัน)
    n_col       ชื่อคอลัมน์จำนวนเกม ถ้าส่งมาจะแสดงใน tooltip
    """
    if df is None or df.empty:
        return None

    y_enc = alt.Y(f"{cat_col}:N", title=None,
                  sort=list(sort_order) if sort_order else "-x",
                  axis=alt.Axis(labelLimit=220))

    tooltip = [alt.Tooltip(f"{cat_col}:N", title="หมวดหมู่"),
               alt.Tooltip(f"{val_col}:Q", title=x_title or "ค่า", format=fmt)]
    if n_col and n_col in df.columns:
        tooltip.append(alt.Tooltip(f"{n_col}:Q", title="จำนวนเกม", format=","))

    base = alt.Chart(df)
    bars = base.mark_bar(color=color, size=18).encode(
        y=y_enc,
        x=alt.X(f"{val_col}:Q", title=x_title,
                axis=alt.Axis(grid=True, tickCount=5)),
        tooltip=tooltip,
    )
    labels = base.mark_text(align="left", baseline="middle", dx=5,
                            fontSize=12).encode(
        y=y_enc,
        x=alt.X(f"{val_col}:Q"),
        text=alt.Text(f"{val_col}:Q", format=fmt),
    )
    layers = [bars, labels]

    if baseline is not None:
        rule = (alt.Chart(pd.DataFrame({"baseline": [baseline]}))
                .mark_rule(color=BASELINE, strokeDash=[5, 4], size=2)
                .encode(x=alt.X("baseline:Q", title=x_title),
                        tooltip=[alt.Tooltip("baseline:Q",
                                             title="เส้นฐานของกลุ่มที่เลือก",
                                             format=".1f")]))
        layers.append(rule)

    return (alt.layer(*layers)
            .properties(height=max(160, 34 * len(df) + 30)))


def render(chart, empty_msg="ข้อมูลไม่พอสรุป ลองผ่อนตัวกรองลง"):
    if chart is None:
        st.info(empty_msg)
    else:
        st.altair_chart(chart, use_container_width=True)


# ===============================================================
# ตรวจว่ามี Data Warehouse แล้วหรือยัง
# ===============================================================
if not dw_exists():
    st.error("ยังไม่พบตารางใน 03_Data_Warehouse")
    st.code("python 02_ETL/03_transform_load.py", language="bash")
    st.stop()

tables = load_tables()
data = build_analysis_frame()

st.title("Steam Games — Market & Player Behaviour Analytics")
st.caption(f"ข้อมูลจาก Data Warehouse | {len(data):,} เกม | "
           f"เกณฑ์ 'เข้าถึงผู้เล่นได้กว้าง' = owners ตั้งแต่ {BREAKOUT_OWNERS:,} คนขึ้นไป | "
           f"เส้นประสีส้มในกราฟคือค่าเฉลี่ยของคลังเกมตามตัวกรองปัจจุบัน")

# ===============================================================
# Interactive Controls — ส่วนนี้คงเดิมทุกอย่าง ไม่ได้แก้ไข
# ===============================================================
with st.sidebar:
    st.header("ตัวกรองข้อมูล")

    years = sorted(data["year"].unique())
    year_range = st.slider("ปีที่วางจำหน่าย", int(min(years)), int(max(years)),
                           (2020, 2023))

    price_mode = st.radio("รูปแบบราคา", ["ทั้งหมด", "เกมฟรี", "เกมขาย"])

    top_genres = (data["genre_name"].value_counts().head(12).index.tolist())
    genres = st.multiselect("แนวเกมหลัก", sorted(top_genres), default=[])

    min_langs = st.slider("จำนวนภาษาขั้นต่ำ", 1,
                          int(data["language_count"].max()), 1)

    st.divider()
    st.caption("ตัวกรองมีผลกับทุกกราฟ ยกเว้นกราฟรายปี "
               "ซึ่งแสดงทุกปีเสมอเพื่อให้เห็นแนวโน้ม")

f = data[(data["year"].between(*year_range))
         & (data["language_count"] >= min_langs)]
if price_mode == "เกมฟรี":
    f = f[f["is_free"] == 1]
elif price_mode == "เกมขาย":
    f = f[f["is_free"] == 0]
if genres:
    f = f[f["genre_name"].isin(genres)]

if f.empty:
    st.warning("ไม่มีเกมที่ตรงกับตัวกรอง ลองผ่อนเงื่อนไขลง")
    st.stop()

baseline = breakout_pct(f)

# ===============================================================
# Measures สรุป
# ===============================================================
c1, c2, c3, c4 = st.columns(4)
c1.metric("เกมที่เลือกอยู่", f"{len(f):,}", f"จากทั้งหมด {len(data):,}")
c2.metric("เข้าถึงเกิน 75,000 คน", f"{baseline:.1f}%")
pt = f[f["has_playtime"] == 1]["median_forever"]
c3.metric("เวลาเล่นกลาง (นาที)",
          f"{pt.median():,.0f}" if len(pt) else "–",
          f"จาก {len(pt):,} เกมที่มีข้อมูล")
c4.metric("คะแนนรีวิวเฉลี่ย (0-9)", f"{f['review_score'].mean():.2f}")

st.divider()

# ===============================================================
# Q1 — ภาษา
# ===============================================================
st.subheader("Q1 · การแปลภาษาช่วยขยายฐานผู้เล่นได้จริงไหม และภาษาไหนคุ้มที่สุด")
q1a, q1b = st.columns(2)

with q1a:
    st.markdown("**จำนวนภาษาที่รองรับ**")
    rows = []
    for lo, hi, label in LANG_BANDS:
        s = f[f["language_count"].between(lo, hi)]
        rows.append({"กลุ่มภาษา": label,
                     "breakout": round(breakout_pct(s), 1),
                     "n": len(s)})
    band_df = pd.DataFrame(rows)
    # บังคับลำดับแกน Y ตามขนาดของช่วง ไม่ใช่ตามตัวอักษร
    render(hbar(band_df, "กลุ่มภาษา", "breakout",
                sort_order=LANG_BAND_ORDER,
                x_title="เข้าถึงเกิน 75,000 คน (%)",
                baseline=baseline, n_col="n"))
    best = band_df[band_df["n"] >= MIN_N].nlargest(1, "breakout")
    if len(best):
        r = best.iloc[0]
        st.caption(f"กลุ่มที่ทำได้ดีที่สุดคือ **{r['กลุ่มภาษา']}** ที่ "
                   f"**{r['breakout']:.1f}%** เทียบกับเส้นฐาน {baseline:.1f}%")

with q1b:
    st.markdown("**ภาษาที่มาคู่กับเกมที่ไปได้ไกล**")
    bl = tables["BRIDGE_GAME_LANGUAGES"].merge(tables["DIM_LANGUAGE"],
                                               on="language_key")
    lm = bl.merge(f[["game_key", "breakout"]], on="game_key")
    top = (lm.groupby("language_name")
           .agg(n=("game_key", "size"),
                breakout=("breakout", lambda s: s.mean() * 100))
           .reset_index())
    top = top[top["n"] >= MIN_N].sort_values("breakout", ascending=False).head(10)
    top["breakout"] = top["breakout"].round(1)
    top = top.rename(columns={"language_name": "ภาษา"})
    # ไม่มีลำดับตามธรรมชาติ จึงเรียงตามค่าด้วย sort='-x'
    render(hbar(top, "ภาษา", "breakout",
                x_title="เข้าถึงเกิน 75,000 คน (%)",
                baseline=baseline, n_col="n"))
    st.caption(f"เฉพาะภาษาที่มีอย่างน้อย {MIN_N} เกมในกลุ่มที่เลือก")

st.divider()

# ===============================================================
# Q2 — จัดจำหน่ายเอง vs มีผู้จัดจำหน่าย (กราฟเปรียบเทียบ)
# ===============================================================
st.subheader("Q2 · เกมที่จัดจำหน่ายเองต่างจากเกมที่มีผู้จัดจำหน่ายอย่างไร")
groups = {"จัดจำหน่ายเอง": f[f["self_published"] == 1],
          "มีผู้จัดจำหน่าย": f[f["self_published"] == 0]}

q2a, q2b = st.columns(2)
with q2a:
    st.markdown("**การเข้าถึงผู้เล่น**")
    reach = pd.DataFrame([{"กลุ่ม": k, "breakout": round(breakout_pct(v), 1),
                           "n": len(v)} for k, v in groups.items()])
    render(hbar(reach, "กลุ่ม", "breakout", sort_order=PUBLISHER_ORDER,
                x_title="เข้าถึงเกิน 75,000 คน (%)",
                baseline=baseline, n_col="n"))
with q2b:
    st.markdown("**คุณภาพที่ผู้เล่นให้คะแนน**")
    quality = pd.DataFrame([
        {"กลุ่ม": k,
         "คะแนนรีวิว": round(v["review_score"].mean(), 2) if len(v) else 0.0,
         "n": len(v)} for k, v in groups.items()])
    render(hbar(quality, "กลุ่ม", "คะแนนรีวิว", sort_order=PUBLISHER_ORDER,
                x_title="คะแนนรีวิวเฉลี่ย (0-9)", fmt=".2f",
                color=BAR_ALT, n_col="n"))

if all(len(v) >= MIN_N for v in groups.values()):
    gap = breakout_pct(groups["มีผู้จัดจำหน่าย"]) - breakout_pct(groups["จัดจำหน่ายเอง"])
    st.caption(f"เกมที่มีผู้จัดจำหน่ายเข้าถึงคนได้มากกว่า **{gap:.1f} จุด** "
               f"ขณะที่คะแนนรีวิวต่างกันเพียงเล็กน้อย "
               f"— คอขวดอยู่ที่การกระจายสินค้า ไม่ใช่คุณภาพเกม")

st.divider()

# ===============================================================
# Q3 — ฟีเจอร์ Steam
# ===============================================================
st.subheader("Q3 · ฟีเจอร์ Steam ตัวไหนมาคู่กับเกมที่เข้าถึงคนได้กว้าง")
bc = tables["BRIDGE_GAME_CATEGORIES"].merge(tables["DIM_CATEGORY"],
                                            on="category_key")
cm = bc.merge(f[["game_key", "breakout"]], on="game_key")
feat = (cm.groupby("category_name")
        .agg(n=("game_key", "size"),
             breakout=("breakout", lambda s: s.mean() * 100))
        .reset_index())
feat = feat[feat["n"] >= 100].sort_values("breakout", ascending=False).head(10)
feat["breakout"] = feat["breakout"].round(1)
feat = feat.rename(columns={"category_name": "ฟีเจอร์"})
render(hbar(feat, "ฟีเจอร์", "breakout",
            x_title="เข้าถึงเกิน 75,000 คน (%)", baseline=baseline, n_col="n"))
st.caption("ระวังการตีความ: Steam Trading Cards เปิดใช้ได้ต่อเมื่อเกมผ่านเกณฑ์ยอดขายแล้ว "
           "จึงเป็นผลของความสำเร็จ ไม่ใช่สาเหตุ ต่างจาก Workshop และโหมดเล่นร่วมกันออนไลน์ "
           "ที่ผู้พัฒนาเลือกใส่เองได้ตั้งแต่วันแรก")

st.divider()

# ===============================================================
# Q4 — เกมฟรี vs เกมขาย (กราฟเปรียบเทียบ)
# ===============================================================
st.subheader("Q4 · เกมฟรีกับเกมขาย ต่างกันตรงไหนระหว่างการเข้าถึงกับการรักษาผู้เล่น")
if price_mode != "ทั้งหมด":
    st.info("ตั้งตัวกรอง 'รูปแบบราคา' เป็น ทั้งหมด เพื่อดูการเปรียบเทียบนี้")
else:
    fp = {"เกมฟรี": f[f["is_free"] == 1], "เกมขาย": f[f["is_free"] == 0]}
    q4a, q4b = st.columns(2)

    with q4a:
        st.markdown("**การเข้าถึง**")
        reach_df = pd.DataFrame([{"กลุ่ม": k, "breakout": round(breakout_pct(v), 1),
                                  "n": len(v)} for k, v in fp.items()])
        render(hbar(reach_df, "กลุ่ม", "breakout", sort_order=PRICE_GROUP_ORDER,
                    x_title="เข้าถึงเกิน 75,000 คน (%)",
                    baseline=baseline, n_col="n"))

    with q4b:
        st.markdown("**การรักษาผู้เล่น**")
        ret_rows = []
        for k, v in fp.items():
            played = v[v["has_playtime"] == 1]["median_forever"]
            ret_rows.append({"กลุ่ม": k,
                             "เวลาเล่นกลาง": float(played.median()) if len(played) else 0.0,
                             "n": len(played)})
        ret_df = pd.DataFrame(ret_rows)
        render(hbar(ret_df, "กลุ่ม", "เวลาเล่นกลาง", sort_order=PRICE_GROUP_ORDER,
                    x_title="เวลาเล่นสะสม ค่ามัธยฐาน (นาที)", fmt=",.0f",
                    color=BAR_ALT, n_col="n"))

    if all(len(v) >= MIN_N for v in fp.values()):
        st.caption(
            f"เกมฟรีเข้าถึงคนได้มากกว่า "
            f"**{breakout_pct(fp['เกมฟรี']) - breakout_pct(fp['เกมขาย']):.1f} จุด** "
            f"แต่ผู้เล่นอยู่กับเกมสั้นกว่า — โมเดลเกมฟรีเหมาะกับเกมที่หารายได้"
            f"จากการซื้อในเกม ไม่ใช่เกมที่ขายตัวเกมอย่างเดียว")

st.divider()

# ===============================================================
# Q5 — แพลตฟอร์ม
# ===============================================================
st.subheader("Q5 · รองรับหลายแพลตฟอร์มแล้วได้ผู้เล่นมากขึ้นไหม")
plat = (f.groupby("platform_desc")
        .agg(n=("game_key", "size"),
             breakout=("breakout", lambda s: s.mean() * 100))
        .reset_index())
plat = plat[plat["n"] >= MIN_N]
plat["breakout"] = plat["breakout"].round(1)
plat = plat.rename(columns={"platform_desc": "แพลตฟอร์ม"})
# บังคับลำดับจากน้อยไปมากตามจำนวนแพลตฟอร์ม ไม่ใช่ตามตัวอักษร
plat_order = [p for p in PLATFORM_ORDER if p in set(plat["แพลตฟอร์ม"])]
render(hbar(plat, "แพลตฟอร์ม", "breakout", sort_order=plat_order,
            x_title="เข้าถึงเกิน 75,000 คน (%)", baseline=baseline, n_col="n"))
if len(plat) >= 2:
    spread = plat["breakout"].max() - plat["breakout"].min()
    st.caption(f"ต่างกันเพียง **{spread:.1f} จุด** ระหว่างกลุ่มสูงสุดกับต่ำสุด "
               f"เทียบกับจำนวนภาษาที่ต่างกันกว่า 30 จุด "
               f"— จำนวนแพลตฟอร์มแทบไม่มีผลต่อการเข้าถึงผู้เล่น")

st.divider()

# ===============================================================
# การวิเคราะห์ตามช่วงเวลา
# ===============================================================
st.subheader("วิเคราะห์ตามช่วงเวลา · ความลึกของเนื้อหาตอนเปิดตัว แยกตามปีที่วางจำหน่าย")
yearly = (data.groupby("year")
          .agg(n=("game_key", "size"),
               achievements=("achievements_total", "mean"))
          .reset_index())
yearly = yearly[yearly["n"] >= 100].sort_values("year")
yearly["achievements"] = yearly["achievements"].round(1)
yearly["ปี"] = yearly["year"].astype(int).astype(str)
# บังคับลำดับปีจากน้อยไปมาก ไม่ใช่เรียงตามค่าหรือตามตัวอักษร
year_order = yearly["ปี"].tolist()
render(hbar(yearly, "ปี", "achievements", sort_order=year_order,
            x_title="ค่าเฉลี่ย achievements ต่อเกม", color=BAR_ALT, n_col="n"))
st.caption("ใช้ achievements เป็นตัวหลักเพราะกำหนดตอนเปิดตัวและแทบไม่เปลี่ยน "
           "ส่วน DLC สะสมเพิ่มได้หลังวางขาย ถ้าเอามารวมจะเอนเอียงเข้าข้างเกมเก่า "
           "| กราฟนี้ไม่ขึ้นกับตัวกรอง เพื่อให้เห็นแนวโน้มครบทุกปี")

# ===============================================================
# Insights และข้อเสนอแนะ
# ===============================================================
st.divider()
st.subheader("Business Insights และข้อเสนอแนะ")

INSIGHTS = [
    ("Q1 · การแปลภาษาคือตัวแปรที่สัมพันธ์กับการเข้าถึงผู้เล่นมากที่สุด",
     "เกมภาษาเดียวเข้าถึงเกิน 75,000 คนได้ 15.4% ส่วนเกมที่รองรับ 10-20 ภาษาทำได้ 52.3%",
     "ถ้าต้องเลือกระหว่างพอร์ตลง Mac/Linux กับแปลภาษาเพิ่ม ให้เลือกแปลภาษาก่อน "
     "โดยเริ่มจากโปแลนด์ เกาหลี และโปรตุเกส-บราซิล"),
    ("Q2 · คอขวดของสตูดิโออิสระอยู่ที่การกระจายสินค้า ไม่ใช่คุณภาพเกม",
     "เกมจัดจำหน่ายเองเข้าถึงคนได้ 20.9% เทียบกับ 33.6% แต่คะแนนรีวิวบวกสูงกว่า",
     "ลงทุนด้านการตลาดหรือหาผู้จัดจำหน่าย น่าจะคุ้มกว่าการขัดเกลาตัวเกมเพิ่ม"),
    ("Q3 · ฟีเจอร์ที่สัมพันธ์กับความสำเร็จสูงสุด เป็นผลของความสำเร็จ ไม่ใช่สาเหตุ",
     "Steam Trading Cards นำที่ 59.7% แต่ต้องผ่านเกณฑ์ยอดขายก่อนถึงเปิดใช้ได้",
     "เลือกลงทุนฟีเจอร์ที่ควบคุมได้เองตั้งแต่วันแรก เช่น Workshop และโหมดเล่นร่วมกันออนไลน์"),
    ("Q4 · เกมฟรีชนะเรื่องการเข้าถึง แต่แพ้เรื่องการรั้งผู้เล่น",
     "เกมฟรีเข้าถึงคนได้ 33.7% เทียบกับเกมขาย 23.7% "
     "แต่เวลาเล่นกลาง 94 นาที เทียบกับ 250 นาที",
     "โมเดลเกมฟรีเหมาะกับเกมที่หารายได้จากการซื้อในเกมหรือ DLC "
     "ไม่ใช่เกมที่พึ่งรายได้จากการขายตัวเกมอย่างเดียว"),
    ("Q5 · จำนวนแพลตฟอร์มแทบไม่มีผล ต่างจากภาษาอย่างชัดเจน",
     "ทุกกลุ่มแพลตฟอร์มต่างกันไม่กี่จุด ขณะที่กลุ่มภาษาต่างกันกว่า 30 จุด",
     "งบพอร์ตเกมลง Mac/Linux ควรย้ายไปลงกับการแปลภาษาแทน "
     "ยกเว้นกรณีที่เกมพึ่งฐานผู้เล่น Steam Deck เป็นหลัก"),
    ("เพิ่มเติม · ความคาดหวังด้านเนื้อหาสูงขึ้นจริงในช่วง 4 ปี",
     "ค่าเฉลี่ย achievements ต่อเกมเพิ่มจาก 19.7 ในปี 2020 เป็น 27.0 ในปี 2023",
     "เกมที่วางแผนออกปีถัดไปควรตั้งงบเนื้อหาเสริมไว้ที่ระดับ 27 achievements ขึ้นไป"),
]

for i, (title, finding, rec) in enumerate(INSIGHTS, 1):
    with st.expander(f"{i}. {title}"):
        st.write(f"**สิ่งที่พบ:** {finding}")
        st.success(f"**ข้อเสนอแนะ:** {rec}")

st.divider()
st.caption(
    "ข้อจำกัดของข้อมูล: (1) owners จาก SteamSpy เป็นค่ากลางของช่วง มีเพียง 13 ค่าที่เป็นไปได้ "
    "จึงใช้สัดส่วนเกมที่เข้าถึงเกิน 75,000 คนแทนค่ามัธยฐาน "
    "(2) ข้อมูลเป็น snapshot ณ เวลาเดียว กราฟรายปีคือการเทียบรุ่นเกมตามปีที่วางจำหน่าย "
    "ไม่ใช่การเติบโตตามเวลา "
    "(3) ทุกความสัมพันธ์ในหน้านี้เป็นความสัมพันธ์ ไม่ใช่เหตุและผล")
