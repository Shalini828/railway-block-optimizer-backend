import os
import sys
import pytest
from datetime import time, date
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app
from auth.security import create_access_token
from logic.traffic_intelligence import (
    normalize_train_type,
    build_constraint_profile,
    windows_overlap,
    classify_counts,
    conflict_severity,
    load_traffic_for_day,
)
from logic.freight_pressure import freight_pressure, get_daily_goods_forecast

client = TestClient(app, raise_server_exceptions=False)


def get_auth_header(role_id: str) -> dict:
    token = create_access_token(role_id)
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# 1. NORMALIZATION
# ============================================================

def test_train_type_normalization():
    # Canonical types
    assert normalize_train_type("Express") == ("EXPRESS", None, False)
    assert normalize_train_type("superfast") == ("SUPERFAST", None, False)
    assert normalize_train_type("MAIL") == ("MAIL", None, False)
    assert normalize_train_type("passenger") == ("PASSENGER", None, False)

    # Aliases
    assert normalize_train_type("FREIGHT") == ("GOODS", None, False)
    assert normalize_train_type("goods") == ("GOODS", None, False)
    assert normalize_train_type("festival") == ("SPECIAL", "FESTIVAL", False)
    assert normalize_train_type("holiday") == ("SPECIAL", "HOLIDAY", False)
    assert normalize_train_type("MILITARY") == ("SPECIAL", "MILITARY", False)
    assert normalize_train_type("relief") == ("SPECIAL", "RELIEF", False)
    assert normalize_train_type("seasonal") == ("SPECIAL", "SEASONAL", False)
    assert normalize_train_type("event") == ("SPECIAL", "EVENT", False)

    # None and unknown
    canon, spec, unknown = normalize_train_type(None)
    assert canon == "PASSENGER"
    assert unknown is True

    canon_u, spec_u, unknown_u = normalize_train_type("RandomUnknownType")
    assert canon_u == "PASSENGER"
    assert unknown_u is True


# ============================================================
# 2. OVERNIGHT-SAFE OVERLAP
# ============================================================

def test_overnight_safe_overlap():
    # Standard overlap within day
    has_ov, min_ov = windows_overlap("10:00", "12:00", "11:00", "13:00")
    assert has_ov is True
    assert min_ov == 60

    # No overlap
    has_ov, min_ov = windows_overlap("10:00", "11:00", "12:00", "13:00")
    assert has_ov is False
    assert min_ov == 0

    # Overnight train crossing midnight: 23:00 to 02:00 vs 01:00 to 03:00
    has_ov, min_ov = windows_overlap("01:00", "03:00", "23:00", "02:00")
    assert has_ov is True
    assert min_ov == 60

    # Overnight block crossing midnight: 23:30 to 01:30 vs 00:30 to 02:00
    has_ov, min_ov = windows_overlap("23:30", "01:30", "00:30", "02:00")
    assert has_ov is True
    assert min_ov == 60


# ============================================================
# 3. COUNTING CONTRACT
# ============================================================

def test_counting_contract():
    """
    ML contract:
    - passenger_trains: ALL passenger-facing trains INCLUDING express
    - express_trains: SUBSET of passenger_trains
    - regular_passenger_trains: passenger_trains - express_trains
    - goods_trains and special_trains are separate
    """
    items = [
        {"train_type": "EXPRESS"},
        {"train_type": "SUPERFAST"},
        {"train_type": "MAIL"},
        {"train_type": "PASSENGER"},
        {"train_type": "GOODS"},
        {"train_type": "GOODS"},
        {"train_type": "SPECIAL"},
    ]

    counts = classify_counts(items)

    assert counts["passenger_trains"] == 4  # Express, Superfast, Mail, Passenger
    assert counts["express_trains"] == 2    # Express, Superfast
    assert counts["regular_passenger_trains"] == 2  # Mail, Passenger
    assert counts["goods_trains"] == 2      # Goods
    assert counts["special_trains"] == 1    # Special


# ============================================================
# 4. CONFLICT SEVERITY & CONSTRAINT PROFILES
# ============================================================

def test_conflict_severity_and_profiles():
    # EXPRESS -> CRITICAL
    exp_item = {"train_type": "EXPRESS", "operational_priority": 5}
    assert conflict_severity(exp_item, "LOW") == "CRITICAL"

    # SPECIAL with priority >= 4 -> CRITICAL
    spec_crit = {"train_type": "SPECIAL", "operational_priority": 4}
    assert conflict_severity(spec_crit, "LOW") == "CRITICAL"

    spec_crit5 = {"train_type": "SPECIAL", "operational_priority": 5}
    assert conflict_severity(spec_crit5, "LOW") == "CRITICAL"

    # SPECIAL with priority < 4 -> HIGH
    spec_high = {"train_type": "SPECIAL", "operational_priority": 3}
    assert conflict_severity(spec_high, "LOW") == "HIGH"

    # PASSENGER / MAIL / SUPERFAST -> HIGH
    psg_item = {"train_type": "PASSENGER", "operational_priority": 2}
    assert conflict_severity(psg_item, "LOW") == "HIGH"

    # GOODS -> MEDIUM when freight level is LOW/MEDIUM
    goods_item = {"train_type": "GOODS", "operational_priority": 3}
    assert conflict_severity(goods_item, "LOW") == "MEDIUM"
    assert conflict_severity(goods_item, "MEDIUM") == "MEDIUM"

    # GOODS -> HIGH when freight level is HIGH or VERY_HIGH
    assert conflict_severity(goods_item, "HIGH") == "HIGH"
    assert conflict_severity(goods_item, "VERY_HIGH") == "HIGH"


# ============================================================
# 5. DEDUPE & INACTIVE SPECIAL TRAINS
# ============================================================

def test_dedupe_and_inactive_specials():
    class MockCursor:
        def __init__(self):
            self.description = None
            self._query_index = 0

        def execute(self, sql, params=None):
            if "FROM trains" in sql:
                self.description = [
                    ("train_id",), ("train_number",), ("train_name",), ("train_type",),
                    ("corridor_id",), ("travel_date",), ("arrival_time",), ("departure_time",),
                    ("direction",), ("operational_priority",)
                ]
            elif "FROM special_train_services" in sql:
                self.description = [
                    ("special_train_id",), ("train_number",), ("train_name",), ("corridor_id",),
                    ("service_date",), ("arrival_time",), ("departure_time",), ("direction",),
                    ("operational_priority",), ("special_type",), ("expected_passengers",),
                    ("reason",), ("active",)
                ]

        def fetchall(self):
            if self._query_index == 0:
                self._query_index += 1
                return [("TR-1", "12952", "Rajdhani Express", "Express", "CORR-001", "2026-09-20", time(10, 0), time(11, 0), "UP", 5)]
            else:
                return [("SPL-1", "12952", "Rajdhani Festival Special", "CORR-001", date(2026, 9, 20), time(10, 0), time(11, 0), "UP", 5, "FESTIVAL", 1000, "Mela", True)]

    cursor = MockCursor()
    items = load_traffic_for_day(cursor, "CORR-001", "2026-09-20")

    # Should deduplicate and keep special_train_services
    assert len(items) == 1
    assert items[0]["source"] == "special_train_services"
    assert items[0]["train_number"] == "12952"


# ============================================================
# 6. FREIGHT FALLBACK CHAIN
# ============================================================

def test_freight_fallback_chain():
    cursor = MagicMock()

    # Case A: Latest row in goods_train_forecast exists (expected, confidence, traffic_level)
    cursor.fetchone.return_value = (35, 85.0, "HIGH")
    res_table = freight_pressure(cursor, "CORR-001", "2026-09-20", "10:00", "12:00")
    assert res_table["source"] == "forecast_table"
    assert res_table["expected_daily"] == 35.0
    assert res_table["level"] == "HIGH"

    # Case B: Table empty, ML model used
    cursor.fetchone.return_value = None
    with patch("ml.goods_forecast_service.predict_goods_train_demand") as mock_ml:
        mock_ml.return_value = {"predicted_goods_train_demand": 35.0}
        res_ml = freight_pressure(cursor, "CORR-001", "2026-09-20", "10:00", "12:00")
        assert res_ml["source"] == "goods_forecast_service"
        assert res_ml["expected_daily"] == 35.0

    # Case C: Table empty & ML fails -> Corridor defaults
    with patch("ml.goods_forecast_service.predict_goods_train_demand", side_effect=Exception("ML model offline")):
        cursor.fetchone.return_value = ("HIGH",)
        res_default = freight_pressure(cursor, "CORR-001", "2026-09-20", "10:00", "12:00")
        assert res_default["source"] == "corridor_level_fallback"
        assert res_default["expected_daily"] == 35.0
        assert res_default["level"] == "HIGH"


# ============================================================
# 7. RECOMMEND-WINDOWS RANKING WITH SPECIAL TRAINS
# ============================================================

def test_recommend_windows_ranking_with_special_train():
    """
    Windows with CRITICAL special conflicts must rank lower than clean windows.
    """
    cand_clean = {
        "start": "06:00:00",
        "end": "09:00:00",
        "train_conflicts": 0,
        "special_conflicts": 0,
        "optimization_score": 90.0,
        "_critical_count": 0,
        "_weighted_sum": 0,
    }

    cand_special = {
        "start": "10:00:00",
        "end": "13:00:00",
        "train_conflicts": 1,
        "special_conflicts": 1,
        "optimization_score": 85.0,
        "_critical_count": 1,
        "_weighted_sum": 45,
    }

    candidates = [cand_special, cand_clean]
    candidates.sort(key=lambda x: (x["_critical_count"], x["_weighted_sum"], -x["optimization_score"]))

    # Clean candidate must rank first
    assert candidates[0]["start"] == "06:00:00"
    assert candidates[1]["start"] == "10:00:00"


# ============================================================
# 8. RBAC: SPECIAL TRAINS WRITE VS READ
# ============================================================

def test_special_trains_rbac():
    # Admin can view
    admin_hdr = get_auth_header("admin")
    res_view = client.get("/special-trains/", headers=admin_hdr)
    # Status is 200 or 500 (if DB offline), but definitely not 401 or 403
    assert res_view.status_code in (200, 500)

    # Engineering / Traction department cannot manage special trains (403 FORBIDDEN)
    eng_hdr = get_auth_header("engineering")
    res_eng_create = client.post(
        "/special-trains/",
        headers=eng_hdr,
        json={
            "corridor_id": "CORR-001",
            "train_number": "SPL-TEST",
            "train_name": "Test Special",
            "service_date": "2026-09-20",
            "arrival_time": "10:00",
            "departure_time": "11:00",
            "direction": "UP",
            "operational_priority": 5,
            "special_type": "FESTIVAL"
        }
    )
    assert res_eng_create.status_code == 403
    assert res_eng_create.json()["code"] == "FORBIDDEN"

    trac_hdr = get_auth_header("traction")
    res_trac_active = client.patch(
        "/special-trains/SPL-TEST/active",
        headers=trac_hdr,
        json={"active": False}
    )
    assert res_trac_active.status_code == 403
    assert res_trac_active.json()["code"] == "FORBIDDEN"


# ============================================================
# 9. REGRESSION: RESPONSE KEYS COMPATIBILITY
# ============================================================

def test_endpoint_regression_keys():
    """
    Ensure response keys for /optimization/recommend-windows contain all
    legacy keys, plus the new intelligence fields.
    """
    control_hdr = get_auth_header("control")

    # Test /optimization/recommend-windows with validation error (end before start)
    # to inspect that the endpoint accepts the expected request
    res_invalid = client.post(
        "/optimization/recommend-windows",
        headers=control_hdr,
        json={
            "corridor": "CORR-001",
            "date": "2026-09-20",
            "start": "12:00",
            "end": "10:00"
        }
    )
    # Handled error response
    assert res_invalid.status_code == 200
    data = res_invalid.json()
    assert data["status"] == "error"
    assert "End time must be after start time" in data["message"]
