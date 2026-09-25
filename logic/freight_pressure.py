"""
Freight Demand & Pressure Module.
IR-ABPS Block Planning Engine.

Provides:
1. get_daily_goods_forecast: Shared daily goods train demand forecast with duplicate-safe persistence.
2. freight_pressure: Hourly-profile window pressure calculation with multi-tier fallback.
"""

from datetime import datetime, timedelta, date, time
import logging
from typing import Dict, Any, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# ============================================================
# HOURLY FREIGHT PROFILE
# ============================================================
# Normalized weights for hours 0 through 23 (24 values).
# Sum of weights = 24.0, so the average weight across 24 hours is exactly 1.0.
# Freight traffic typically peaks during night-time hours (22:00-06:00) when passenger density is lower.
# NOTE: Because goods demand is forecasted daily, this hourly distribution is an ESTIMATE.
HOURLY_FREIGHT_PROFILE = [
    1.25, 1.30, 1.35, 1.30, 1.20, 1.05,  # 00:00 - 05:59 (early morning freight peak)
    0.80, 0.65, 0.60, 0.70, 0.85, 0.95,  # 06:00 - 11:59 (morning passenger rush)
    1.05, 1.00, 0.95, 0.90, 0.75, 0.65,  # 12:00 - 17:59 (afternoon / evening passenger rush)
    0.80, 0.95, 1.15, 1.25, 1.30, 1.25   # 18:00 - 23:59 (night freight run)
]

COMMODITIES = [
    "COAL",
    "IRON_ORE",
    "CEMENT",
    "FOOD_GRAINS",
    "FERTILIZER",
    "CONTAINER",
    "PETROLEUM"
]

TRAFFIC_LEVEL_DEFAULTS = {
    "LOW": 10.0,
    "MEDIUM": 22.0,
    "HIGH": 35.0,
    "VERY HIGH": 45.0,
    "VERY_HIGH": 45.0,
    "CRITICAL": 50.0,
}

TRAFFIC_PRESSURE_MAP = {
    "LOW": 25,
    "MEDIUM": 50,
    "HIGH": 75,
    "VERY HIGH": 90,
    "VERY_HIGH": 90,
    "CRITICAL": 100
}


def compute_hourly_weight(start_min: int, end_min: int) -> float:
    """
    Computes average hourly weight across a time window in minutes.
    Handles overnight spans cleanly.
    """
    s = start_min % 1440
    e = end_min % 1440
    if e <= s:
        e += 1440

    duration = e - s
    if duration <= 0:
        return 1.0

    total_weight = sum(HOURLY_FREIGHT_PROFILE[(m // 60) % 24] for m in range(s, e))
    return total_weight / duration


def get_daily_goods_forecast(
    cursor: Any,
    corridor_id: str,
    forecast_date: Any,
    persist: bool = True
) -> Dict[str, Any]:
    """
    Generates daily goods-train demand forecast for a corridor/date.
    If persist=True: updates existing row for (corridor_id, forecast_date) or inserts new row.
    If persist=False: returns predictions without modifying DB.
    """
    if isinstance(forecast_date, (datetime, date)):
        target_date = forecast_date if isinstance(forecast_date, date) else forecast_date.date()
    else:
        target_date = datetime.strptime(str(forecast_date)[:10], "%Y-%m-%d").date()

    day_of_week = target_date.weekday()
    month = target_date.month
    is_weekend = 1 if day_of_week >= 5 else 0
    festival_period = 1 if month in (9, 10, 11) else 0

    # 1. Previous day demand
    previous_date = target_date - timedelta(days=1)
    cursor.execute("""
        SELECT expected_goods_trains
        FROM goods_train_forecast
        WHERE corridor_id = %s
          AND forecast_date = %s
        ORDER BY forecast_id DESC
        LIMIT 1
    """, (corridor_id, previous_date))
    prev_row = cursor.fetchone()
    previous_day_demand = float(prev_row[0]) if prev_row and prev_row[0] is not None else 20.0

    # 2. Operational pressure proxy
    cursor.execute("""
        SELECT traffic_level
        FROM corridors
        WHERE corridor_id = %s
    """, (corridor_id,))
    c_row = cursor.fetchone()
    raw_traffic_level = str(c_row[0]).upper() if c_row and c_row[0] else "MEDIUM"
    operational_pressure = TRAFFIC_PRESSURE_MAP.get(raw_traffic_level, 50)
    industrial_demand = min(100.0, operational_pressure + 10.0)

    # 3. Commodity predictions via ML
    from ml.goods_forecast_service import predict_goods_train_demand

    predictions = []
    commodity_predictions = {}
    for commodity in COMMODITIES:
        res = predict_goods_train_demand(
            day_of_week=day_of_week,
            month=month,
            is_weekend=is_weekend,
            festival_period=festival_period,
            operational_pressure=operational_pressure,
            industrial_demand=industrial_demand,
            previous_day_demand=previous_day_demand,
            corridor_id=corridor_id,
            commodity=commodity
        )
        val = res.get("predicted_goods_train_demand", 0.0)
        predictions.append(val)
        commodity_predictions[commodity] = round(val, 2)

    predicted_demand = sum(predictions) / len(predictions) if predictions else 20.0
    predicted_demand = max(0.0, min(60.0, float(round(predicted_demand))))

    spread = abs(max(predictions) - min(predictions)) if predictions else 0.0
    confidence = max(0.0, min(100.0, 100.0 - (spread * 2.0)))
    confidence = round(confidence, 2)

    if predicted_demand >= 40:
        traffic_level = "VERY_HIGH"
    elif predicted_demand >= 30:
        traffic_level = "HIGH"
    elif predicted_demand >= 15:
        traffic_level = "MEDIUM"
    else:
        traffic_level = "LOW"

    forecast_id = None
    if persist:
        # Check if row exists for corridor_id + forecast_date
        cursor.execute("""
            SELECT forecast_id
            FROM goods_train_forecast
            WHERE corridor_id = %s
              AND forecast_date = %s
            ORDER BY forecast_id DESC
            LIMIT 1
        """, (corridor_id, target_date))
        existing = cursor.fetchone()

        if existing:
            forecast_id = existing[0]
            cursor.execute("""
                UPDATE goods_train_forecast
                SET expected_goods_trains = %s,
                    forecast_confidence = %s,
                    traffic_level = %s
                WHERE forecast_id = %s
            """, (
                int(predicted_demand),
                confidence,
                traffic_level,
                forecast_id
            ))
        else:
            cursor.execute("""
                INSERT INTO goods_train_forecast (
                    corridor_id,
                    forecast_date,
                    expected_goods_trains,
                    forecast_confidence,
                    traffic_level
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING forecast_id
            """, (
                corridor_id,
                target_date,
                int(predicted_demand),
                confidence,
                traffic_level
            ))
            forecast_id = cursor.fetchone()[0]

    return {
        "status": "success",
        "forecast_id": forecast_id,
        "corridor_id": corridor_id,
        "forecast_date": str(target_date),
        "expected_goods_trains": int(predicted_demand),
        "forecast_confidence": confidence,
        "traffic_level": traffic_level,
        "forecast": {
            "expected_goods_trains": int(predicted_demand),
            "forecast_confidence": confidence,
            "traffic_level": traffic_level
        },
        "commodity_predictions": commodity_predictions
    }


def freight_pressure(
    cursor: Any,
    corridor_id: str,
    target_date: Any,
    start_time: Any,
    end_time: Any
) -> Dict[str, Any]:
    """
    Evaluate freight demand pressure for a corridor window.
    Fallback chain:
    1. goods_train_forecast table row (latest by forecast_id)
    2. goods_forecast_service ML prediction
    3. corridors.traffic_level mapping

    Returns:
    {
        expected_daily,
        expected_in_window,
        scheduled_goods_in_window,
        unscheduled_expected,
        level,
        confidence,
        source,
        hourly_distribution: "estimated",
        window_minutes
    }
    """
    from logic.traffic_intelligence import time_to_minutes, load_traffic_in_window

    date_str = str(target_date)[:10]
    expected_daily = None
    confidence = 50.0
    level = "MEDIUM"
    source = "corridor_level_fallback"

    # Step 1: Try latest forecast row from table
    try:
        cursor.execute("""
            SELECT expected_goods_trains, forecast_confidence, traffic_level
            FROM goods_train_forecast
            WHERE corridor_id = %s
              AND forecast_date = %s
            ORDER BY forecast_id DESC
            LIMIT 1
        """, (corridor_id, date_str))
        row = cursor.fetchone()
        if row and row[0] is not None:
            expected_daily = float(row[0])
            confidence = float(row[1]) if row[1] is not None else 85.0
            level = str(row[2]).upper() if row[2] else "MEDIUM"
            source = "forecast_table"
    except Exception as e:
        logger.warning(f"Error querying goods_train_forecast table: {e}")

    # Step 2: Try ML forecast service (without writing to DB)
    if expected_daily is None:
        try:
            fc = get_daily_goods_forecast(cursor, corridor_id, date_str, persist=False)
            expected_daily = float(fc["expected_goods_trains"])
            confidence = float(fc["forecast_confidence"])
            level = fc["traffic_level"]
            source = "goods_forecast_service"
        except Exception as e:
            logger.warning(f"ML goods forecast fallback error: {e}")

    # Step 3: Corridor level mapping fallback
    if expected_daily is None:
        try:
            cursor.execute("""
                SELECT traffic_level
                FROM corridors
                WHERE corridor_id = %s
            """, (corridor_id,))
            c_row = cursor.fetchone()
            c_level = str(c_row[0]).upper() if c_row and c_row[0] else "MEDIUM"
            expected_daily = TRAFFIC_LEVEL_DEFAULTS.get(c_level, 22.0)
            level = "VERY_HIGH" if c_level in ("VERY HIGH", "CRITICAL") else c_level
            confidence = 60.0
            source = "corridor_level_fallback"
        except Exception:
            expected_daily = 22.0
            level = "MEDIUM"
            confidence = 50.0
            source = "corridor_level_fallback"

    # Normalize level thresholds on daily figure
    if expected_daily >= 40:
        level = "VERY_HIGH"
    elif expected_daily >= 30:
        level = "HIGH"
    elif expected_daily >= 15:
        level = "MEDIUM"
    else:
        level = "LOW"

    # Calculate window span
    s_min = time_to_minutes(start_time)
    e_min = time_to_minutes(end_time)
    if e_min <= s_min:
        e_min += 1440
    window_minutes = e_min - s_min

    # Calculate hourly weight
    hourly_weight = compute_hourly_weight(s_min, e_min)
    expected_in_window = (expected_daily * (window_minutes / 1440.0)) * hourly_weight
    expected_in_window = round(expected_in_window, 2)

    # Scheduled goods trains in window
    scheduled_items = load_traffic_in_window(cursor, corridor_id, date_str, start_time, end_time)
    scheduled_goods = sum(1 for item in scheduled_items if item.get("traffic_class") == "FREIGHT" or item.get("train_type") == "GOODS")

    unscheduled_expected = max(0.0, round(expected_in_window - scheduled_goods, 2))

    return {
        "expected_daily": round(expected_daily, 2),
        "expected_in_window": expected_in_window,
        "scheduled_goods_in_window": scheduled_goods,
        "unscheduled_expected": unscheduled_expected,
        "level": level,
        "confidence": round(confidence, 2),
        "source": source,
        "hourly_distribution": "estimated",
        "window_minutes": window_minutes,
    }
