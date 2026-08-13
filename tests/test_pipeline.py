"""
=====================================================================
 test_pipeline.py — ชุดทดสอบ Data Pipeline ด้วย pytest
=====================================================================
 แบ่งเป็น 2 กลุ่ม

 กลุ่ม A — Unit Test ของฟังก์ชันแปลงข้อมูล
   ไม่ต้องมีข้อมูลจริง รันได้เสมอ ทดสอบตรรกะการ clean ทีละฟังก์ชัน
   รวมถึงเคสที่เคยเป็นบั๊กจริงในโปรเจกต์นี้

 กลุ่ม B — Integration Test ของ Data Warehouse
   ต้องรัน 03_transform_load.py มาก่อน ถ้ายังไม่มีตารางจะ skip อัตโนมัติ

 วิธีใช้ (รันจาก Project Root):
   python -m pytest -q
   python -m pytest -q -m unit          # เฉพาะกลุ่ม A
   python -m pytest -q -k bridge        # เฉพาะเทสต์ที่ชื่อมีคำว่า bridge
=====================================================================
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "02_ETL"))

from common import (ALL_TABLES, BRIDGE_TABLES, DLC_WEIGHT, DW_DIR,
                    FOREIGN_KEYS, PRIMARY_KEYS, clean_languages,
                    descriptions_of, dict_total, dw_exists, owners_to_number,
                    parse_list_cell, parse_release_date, split_names, to_bool,
                    to_int)

needs_dw = pytest.mark.skipif(
    not dw_exists(),
    reason="ยังไม่มี Data Warehouse — รัน python 02_ETL/03_transform_load.py ก่อน")


# ===============================================================
# กลุ่ม A — Unit Test ของฟังก์ชันแปลงข้อมูล
# ===============================================================
class TestCleaningFunctions:

    def test_split_names_keeps_company_suffix(self):
        """คอมมาในชื่อบริษัทต้องไม่ถูกใช้เป็นตัวคั่น"""
        assert split_names("CAPCOM Co., Ltd.") == ["CAPCOM Co., Ltd."]
        assert split_names("KOEI TECMO GAMES CO., LTD.") == ["KOEI TECMO GAMES CO., LTD."]

    def test_split_names_splits_multiple_studios(self):
        assert split_names("Sketchbook Developments, Fourth State") == \
            ["Sketchbook Developments", "Fourth State"]
        assert split_names("Nippon Ichi Software, Inc., Engine Software BV") == \
            ["Nippon Ichi Software, Inc.", "Engine Software BV"]

    def test_split_names_handles_apostrophe_and_blank(self):
        assert split_names("Chilla's Art") == ["Chilla's Art"]
        assert split_names("") == ["Unknown"]
        assert split_names(None) == ["Unknown"]

    def test_owners_range_becomes_midpoint(self):
        """owners เป็นข้อความช่วง ต้องแปลงเป็นค่ากลางที่เป็นตัวเลข"""
        assert owners_to_number("10,000 .. 20,000") == 15000
        assert owners_to_number("0 .. 20,000") == 10000
        assert owners_to_number(15000) == 15000
        assert pd.isna(owners_to_number("ไม่ใช่ตัวเลข"))

    def test_clean_languages_strips_html(self):
        raw = "English<br><strong>*</strong>languages with full audio support"
        assert clean_languages(raw) == "English"
        assert clean_languages("English, French, German") == "English, French, German"
        assert clean_languages(None) == ""

    def test_release_date_parsing(self):
        assert parse_release_date({"coming_soon": False, "date": "10 Mar, 2021"}) \
            == "2021-03-10"
        assert parse_release_date({"coming_soon": True, "date": "Coming Soon"}) is None
        assert parse_release_date(None) is None

    def test_to_int_handles_string_and_junk(self):
        """required_age บางเกมส่งมาเป็นข้อความ ต้องไม่ทำให้ pipeline ล้ม"""
        assert to_int("18") == 18
        assert to_int(None) == 0
        assert to_int("ไม่ทราบ") == 0
        assert to_int("17+", default=-1) == -1

    def test_to_bool_variants(self):
        assert to_bool(True) is True
        assert to_bool("True") is True
        assert to_bool("false") is False
        assert to_bool(0) is False

    def test_descriptions_and_list_parsing(self):
        assert descriptions_of([{"id": 1, "description": "Action"}]) == ["Action"]
        assert descriptions_of(None) == []
        assert parse_list_cell("['Indie', 'RPG']") == ["Indie", "RPG"]
        assert parse_list_cell("[]") == []

    def test_dict_total(self):
        assert dict_total({"total": 42}) == 42
        assert dict_total(None) == 0


# ===============================================================
# กลุ่ม B — Integration Test ของ Data Warehouse
# ===============================================================
@pytest.fixture(scope="module")
def dw():
    """โหลดทุกตารางครั้งเดียวแล้วใช้ร่วมกันทุกเทสต์"""
    return {t: pd.read_csv(DW_DIR / f"{t}.csv") for t in ALL_TABLES}


@needs_dw
class TestWarehouseStructure:

    def test_all_tables_exist_and_not_empty(self, dw):
        for t in ALL_TABLES:
            assert len(dw[t]) > 0, f"{t} ไม่มีข้อมูล"

    @pytest.mark.parametrize("table", list(PRIMARY_KEYS))
    def test_primary_key_unique(self, dw, table):
        keys = PRIMARY_KEYS[table]
        assert dw[table].duplicated(subset=keys).sum() == 0
        assert dw[table][keys].isna().sum().sum() == 0

    @pytest.mark.parametrize("fk", FOREIGN_KEYS,
                             ids=[f"{c}.{k}" for c, k, _, _ in FOREIGN_KEYS])
    def test_foreign_key_resolves(self, dw, fk):
        child, col, parent, pk = fk
        vals = dw[child][col].dropna()
        assert vals.isin(set(dw[parent][pk])).all(), \
            f"{child}.{col} มีค่าที่หาใน {parent} ไม่เจอ"

    def test_dim_game_columns_unchanged(self, dw):
        """โครงสร้าง DIM_GAME ต้องตรงกับที่ระบบเดิมใช้ ห้ามสลับลำดับ"""
        assert list(dw["DIM_GAME"].columns) == [
            "game_key", "steam_appid", "name", "type", "is_free",
            "required_age", "initial_price", "price_tier", "controller_support",
            "dlc_count", "achievements_total", "content_depth_tier",
            "language_count", "price_currency", "is_premium"]

    def test_fact_engagement_columns_unchanged(self, dw):
        assert list(dw["FACT_GAME_ENGAGEMENT"].columns) == [
            "engagement_key", "game_key", "date_key", "platform_key",
            "review_score_key", "primary_developer_key", "primary_publisher_key",
            "total_positive", "total_negative", "total_reviews",
            "recommendations", "owners", "ccu", "estimated_revenue",
            "concurrent_engagement_rate", "content_depth_score",
            "recommendation_rate"]

    def test_bridge_tables_have_weight_columns(self, dw):
        for t in BRIDGE_TABLES:
            assert "allocation_factor" in dw[t].columns
            assert "is_primary" in dw[t].columns


@needs_dw
class TestWarehouseGrain:

    @pytest.mark.parametrize("table", ["FACT_GAME_ENGAGEMENT", "FACT_GAME_PLAYTIME"])
    def test_one_row_per_game(self, dw, table):
        assert len(dw[table]) == len(dw["DIM_GAME"])
        assert dw[table]["game_key"].duplicated().sum() == 0

    def test_date_dimension_has_no_gap_in_key(self, dw):
        d = dw["DIM_DATE"]
        assert d["date_key"].between(19000101, 21001231).all()
        assert (d["month"].between(1, 12)).all()
        assert (d["quarter"].between(1, 4)).all()


@needs_dw
class TestBridgeIntegrity:

    @pytest.mark.parametrize("table", BRIDGE_TABLES)
    def test_allocation_factor_sums_to_one(self, dw, table):
        s = dw[table].groupby("game_key")["allocation_factor"].sum().round(3)
        assert (s == 1.0).all(), f"{table} มีเกมที่ allocation_factor รวมไม่ได้ 1"

    @pytest.mark.parametrize("table", BRIDGE_TABLES)
    def test_exactly_one_primary(self, dw, table):
        s = dw[table].groupby("game_key")["is_primary"].sum()
        assert (s == 1).all(), f"{table} มีเกมที่ is_primary ไม่เท่ากับ 1 ตัว"

    def test_allocation_prevents_double_counting(self, dw):
        """
        นี่คือเหตุผลที่ต้องมี allocation_factor:
        SUM ผ่าน bridge ตรง ๆ จะเกินจริง แต่คูณ factor แล้วต้องกลับมาเท่าเดิม
        """
        eng = dw["FACT_GAME_ENGAGEMENT"][["game_key", "owners"]]
        b = dw["BRIDGE_GAME_GENRES"].merge(eng, on="game_key")
        actual = eng["owners"].sum()
        naive = b["owners"].sum()
        weighted = (b["owners"] * b["allocation_factor"]).sum()
        assert naive > actual, "ถ้าไม่เกินแสดงว่าไม่มีเกมที่มีหลายแนว"
        assert abs(weighted - actual) / actual < 0.0001


@needs_dw
class TestBusinessRules:

    def test_review_counts_add_up(self, dw):
        e = dw["FACT_GAME_ENGAGEMENT"]
        assert (e["total_positive"] + e["total_negative"] == e["total_reviews"]).all()

    def test_free_games_have_zero_revenue(self, dw):
        m = dw["FACT_GAME_ENGAGEMENT"].merge(dw["DIM_GAME"], on="game_key")
        assert (m.loc[m["is_free"] == 1, "estimated_revenue"] == 0).all()

    def test_content_depth_formula(self, dw):
        m = dw["FACT_GAME_ENGAGEMENT"].merge(dw["DIM_GAME"], on="game_key")
        expected = m["achievements_total"] + m["dlc_count"] * DLC_WEIGHT
        assert (m["content_depth_score"] == expected).all()

    def test_no_negative_measures(self, dw):
        e = dw["FACT_GAME_ENGAGEMENT"]
        for c in ["total_positive", "total_negative", "total_reviews",
                  "recommendations", "owners", "ccu", "estimated_revenue",
                  "content_depth_score"]:
            assert (e[c] >= 0).all(), f"{c} มีค่าติดลบ"

    def test_ccu_not_greater_than_owners(self, dw):
        e = dw["FACT_GAME_ENGAGEMENT"]
        assert (e["ccu"] <= e["owners"]).all()

    def test_free_games_survived_cleaning(self, dw):
        """
        เคยมีบั๊กที่เกมฟรีถูก dropna ลบทิ้งเกือบหมดเพราะไม่มี price_overview
        เทสต์นี้กันไม่ให้บั๊กเดิมกลับมา
        """
        n_free = int((dw["DIM_GAME"]["is_free"] == 1).sum())
        assert n_free > 100, f"เกมฟรีเหลือแค่ {n_free} เกม — น่าจะโดนลบผิดอีกแล้ว"

    def test_price_tier_matches_price(self, dw):
        g = dw["DIM_GAME"]
        assert (g.loc[g["initial_price"] == 0, "price_tier"] == "Free").all()
        assert (g.loc[g["price_tier"] == "800+", "initial_price"] >= 799).all()

    def test_premium_games_are_not_free(self, dw):
        g = dw["DIM_GAME"]
        assert (g.loc[g["is_premium"] == 1, "is_free"] == 0).all()
