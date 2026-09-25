"""
Unified Traffic Intelligence & Classification Module.
IR-ABPS Block Planning Engine.

Provides:
1. normalize_train_type: Cleans raw types to canonical set (EXPRESS, SUPERFAST, MAIL, PASSENGER, GOODS, SPECIAL).
2. build_constraint_profile: Runtime constraint parameters (traffic class, priority, impact weights, delay).
3. windows_overlap: Overnight-safe window overlap detection and duration in minutes.
4. load_traffic_for_day / load_traffic_in_window: Unified loader merging `trains` and `special_train_services`.
5. classify_counts: Strict ML feature contract for train count breakdowns.
6. conflict_severity: Tiered severity calculation for train conflicts.
"""

from datetime import datetime, time, date
import logging
from typing import Dict, Any, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)
_logged_unknown_types = set()

# ============================================================
# TRAIN CLASSIFICATION CONFIGURATION
# ============================================================

TRAIN_TYPE_CONFIG: Dict[str, Dict[str, Any]] = {
    "EXPRESS": {
        "traffic_class": "PASSENGER",
        "default_priority": 5,
        "passenger_impact": 90,
        "freight_impact": 0,
        "block_sensitivity": 95,
        "impact_weight": 40,
        "base_delay_min": 10,
    },
    "SUPERFAST": {
        "traffic_class": "PASSENGER",
        "default_priority": 5,
        "passenger_impact": 85,
        "freight_impact": 0,
        "block_sensitivity": 90,
        "impact_weight": 35,
        "base_delay_min": 10,
    },
    "MAIL": {
        "traffic_class": "PASSENGER",
        "default_priority": 4,
        "passenger_impact": 80,
        "freight_impact": 0,
        "block_sensitivity": 85,
        "impact_weight": 30,
        "base_delay_min": 10,
    },
    "PASSENGER": {
        "traffic_class": "PASSENGER",
        "default_priority": 3,
        "passenger_impact": 60,
        "freight_impact": 0,
        "block_sensitivity": 70,
        "impact_weight": 25,
        "base_delay_min": 5,
    },
    "GOODS": {
        "traffic_class": "FREIGHT",
        "default_priority": 3,
        "passenger_impact": 0,
        "freight_impact": 75,
        "block_sensitivity": 70,
        "impact_weight": 15,
        "base_delay_min": 5,
    },
    "SPECIAL": {
        "traffic_class": "SPECIAL",
        "default_priority": 4,
        "passenger_impact": 90,
        "freight_impact": 0,
        "block_sensitivity": 95,
        "impact_weight": 45,
        "base_delay_min": 10,
    },
}

SPECIAL_ALIASES = {
    "FESTIVAL",
    "HOLIDAY",
    "EVENT",
    "RELIEF",
    "MILITARY",
    "SEASONAL",
}

CANONICAL_TYPES = {
    "EXPRESS",
    "SUPERFAST",
    "MAIL",
    "PASSENGER",
    "GOODS",
    "SPECIAL",
}


# ============================================================
# 1. TRAIN TYPE NORMALIZATION
# ============================================================

def normalize_train_type(raw: Optional[str]) -> Tuple[str, Optional[str], bool]:
    """
    Normalize raw train_type text to canonical set:
    EXPRESS, SUPERFAST, MAIL, PASSENGER, GOODS, SPECIAL.

    Returns:
        (canonical_type, special_type, unknown_type)
    """
    if raw is None:
        if "None" not in _logged_unknown_types:
            logger.warning("Train type is None; defaulting conservatively to PASSENGER.")
            _logged_unknown_types.add("None")
        return "PASSENGER", None, True

    cleaned = str(raw).strip().upper().replace(" ", "_").replace("-", "_")

    if not cleaned:
        return "PASSENGER", None, True

    # Freight alias
    if cleaned in ("FREIGHT", "GOODS"):
        return "GOODS", None, False

    # Special aliases
    if cleaned in SPECIAL_ALIASES:
        return "SPECIAL", cleaned, False

    if cleaned == "SPECIAL":
        return "SPECIAL", None, False

    # Standard passenger canonicals
    if cleaned in ("EXPRESS", "SUPERFAST", "MAIL", "PASSENGER"):
        return cleaned, None, False

    # Substring / variant matching
    if "SUPERFAST" in cleaned:
        return "SUPERFAST", None, False
    if "EXPRESS" in cleaned:
        return "EXPRESS", None, False
    if "MAIL" in cleaned:
        return "MAIL", None, False
    if "FREIGHT" in cleaned or "GOODS" in cleaned:
        return "GOODS", None, False
    if "PASSENGER" in cleaned or "LOCAL" in cleaned or "DEMU" in cleaned or "MEMU" in cleaned:
        return "PASSENGER", None, False

    # Unknown type: conservative fallback to PASSENGER, logged once
    if cleaned not in _logged_unknown_types:
        logger.warning(f"Unknown train_type '{raw}' encountered; defaulting to PASSENGER.")
        _logged_unknown_types.add(cleaned)

    return "PASSENGER", None, True


# ============================================================
# 2. CONSTRAINT PROFILES
# ============================================================

def build_constraint_profile(
    raw_type: Optional[str],
    row_priority: Optional[Union[int, str]] = None,
    expected_passengers: Optional[Union[int, str]] = None,
    source: str = "trains"
) -> Dict[str, Any]:
    """
    Derive runtime constraint profile for a train. Not stored in DB.
    """
    canonical_type, special_type, unknown = normalize_train_type(raw_type)
    config = TRAIN_TYPE_CONFIG.get(canonical_type, TRAIN_TYPE_CONFIG["PASSENGER"])

    # Determine schedule certainty
    if source == "special_train_services":
        schedule_certainty = "CONFIRMED"
    elif source == "forecast":
        schedule_certainty = "FORECASTED"
    else:
        schedule_certainty = "SCHEDULED"

    # Determine operational priority
    prio = None
    if row_priority is not None:
        try:
            parsed = int(row_priority)
            if 1 <= parsed <= 5:
                prio = parsed
        except (ValueError, TypeError):
            pass

    if prio is None:
        prio = config["default_priority"]

    # Calculate impact weight
    impact_weight = config["impact_weight"]
    if canonical_type == "SPECIAL" and expected_passengers:
        try:
            pax = int(expected_passengers)
            if pax > 0:
                # Scale up to +15 based on expected passenger load (1000 pax = +15)
                additional = min(15, int((pax / 1000) * 15))
                impact_weight += additional
        except (ValueError, TypeError):
            pass

    return {
        "train_type": canonical_type,
        "raw_train_type": str(raw_type) if raw_type is not None else None,
        "special_type": special_type,
        "traffic_class": config["traffic_class"],
        "schedule_certainty": schedule_certainty,
        "operational_priority": prio,
        "passenger_impact": config["passenger_impact"],
        "freight_impact": config["freight_impact"],
        "block_sensitivity": config["block_sensitivity"],
        "impact_weight": impact_weight,
        "base_delay_min": config["base_delay_min"],
        "unknown_type": unknown,
    }


# ============================================================
# 3. OVERNIGHT-SAFE TIME & OVERLAP CALCULATIONS
# ============================================================

def time_to_minutes(value: Any) -> int:
    """
    Convert time, datetime, or time string (HH:MM or HH:MM:SS) to minutes since 00:00.
    """
    if isinstance(value, int):
        return value % 1440
    if isinstance(value, (datetime, time)):
        return value.hour * 60 + value.minute

    s = str(value).strip()
    parts = s.split(":")
    if len(parts) >= 2:
        try:
            return int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            pass
    return 0


def minutes_to_time_str(minutes: int) -> str:
    """
    Convert minutes from midnight to HH:MM:00 string.
    """
    m = minutes % 1440
    return f"{m // 60:02d}:{m % 60:02d}:00"


def _interval_overlap(s1: int, e1: int, s2: int, e2: int) -> Tuple[bool, int]:
    overlap_start = max(s1, s2)
    overlap_end = min(e1, e2)
    if overlap_start < overlap_end:
        return True, overlap_end - overlap_start
    return False, 0


def windows_overlap(
    a_start: Any,
    a_end: Any,
    b_start: Any,
    b_end: Any
) -> Tuple[bool, int]:
    """
    Overnight-safe overlap detection between window A and window B.
    Handles intervals crossing midnight (where end < start).
    Returns (has_overlap, overlap_minutes).
    """
    s_a = time_to_minutes(a_start)
    e_a = time_to_minutes(a_end)
    if e_a <= s_a:
        e_a += 1440

    s_b = time_to_minutes(b_start)
    e_b = time_to_minutes(b_end)
    if e_b <= s_b:
        e_b += 1440

    # Test baseline [0..1440+] overlap
    has_overlap, overlap_min = _interval_overlap(s_a, e_a, s_b, e_b)
    best_overlap = overlap_min if has_overlap else 0

    # Test periodic shifts (e.g. if one window spans into next day)
    has_shift1, min1 = _interval_overlap(s_a, e_a, s_b + 1440, e_b + 1440)
    if has_shift1 and min1 > best_overlap:
        has_overlap = True
        best_overlap = min1

    has_shift2, min2 = _interval_overlap(s_a + 1440, e_a + 1440, s_b, e_b)
    if has_shift2 and min2 > best_overlap:
        has_overlap = True
        best_overlap = min2

    return (best_overlap > 0, best_overlap)


# ============================================================
# 4. UNIFIED TRAFFIC LOADERS
# ============================================================

def load_traffic_for_day(
    cursor: Any,
    corridor_id: str,
    travel_date: Any
) -> List[Dict[str, Any]]:
    """
    Load all active traffic for a corridor and date:
    UNION of `trains` (corridor + travel_date) and active rows from
    `special_train_services` (corridor + service_date).

    Deduplication: if same train_number appears in both, keep the
    special_train_services entry.
    """
    target_date = str(travel_date)

    # 1. Load regular scheduled trains
    cursor.execute("""
        SELECT
            train_id,
            train_number,
            train_name,
            train_type,
            corridor_id,
            travel_date,
            arrival_time,
            departure_time,
            direction,
            operational_priority
        FROM trains
        WHERE corridor_id = %s
          AND travel_date = %s
    """, (corridor_id, target_date))

    train_rows = cursor.fetchall()
    col_names = [d[0] for d in cursor.description]

    trains_list = []
    for r in train_rows:
        row = dict(zip(col_names, r))
        canonical, spec_type, _ = normalize_train_type(row["train_type"])
        profile = build_constraint_profile(
            raw_type=row["train_type"],
            row_priority=row["operational_priority"],
            source="trains"
        )
        trains_list.append({
            "id": row["train_id"],
            "train_id": row["train_id"],
            "train_number": row["train_number"],
            "train_name": row["train_name"],
            "train_type": canonical,
            "raw_train_type": row["train_type"],
            "special_type": spec_type,
            "traffic_class": profile["traffic_class"],
            "corridor_id": row["corridor_id"],
            "date": str(row["travel_date"]),
            "arrival_time": row["arrival_time"],
            "departure_time": row["departure_time"],
            "direction": row.get("direction"),
            "operational_priority": profile["operational_priority"],
            "expected_passengers": 0,
            "source": "trains",
            "active": True,
            "constraint_profile": profile,
        })

    # 2. Load active special train services
    specials_list = []
    try:
        cursor.execute("""
            SELECT
                special_train_id,
                train_number,
                train_name,
                                special_type,
                corridor_id,
                service_date,
                departure_time,
                arrival_time,
                direction,
                operational_priority,
                                active
            FROM special_train_services
            WHERE corridor_id = %s
              AND service_date = %s
                            AND active = TRUE
        """, (corridor_id, target_date))

        spec_rows = cursor.fetchall()
        spec_cols = [d[0] for d in cursor.description]

        for r in spec_rows:
            row = dict(zip(spec_cols, r))

            raw_type = row["special_type"] or "SPECIAL"

            canonical, spec_type, _ = normalize_train_type(raw_type)

            profile = build_constraint_profile(
                raw_type=raw_type,
                row_priority=row["operational_priority"],
                source="special_train_services"
            )

            specials_list.append({
                "id": row["special_train_id"],
                "train_id": row["special_train_id"],
                "train_number": row["train_number"],
                "train_name": row["train_name"],
                "train_type": canonical,
                "raw_train_type": raw_type,
                "special_type": spec_type or raw_type,
                "traffic_class": profile["traffic_class"],
                "corridor_id": row["corridor_id"],
                "date": str(row["service_date"]),
                "arrival_time": row["arrival_time"],
                "departure_time": row["departure_time"],
                "direction": row.get("direction"),
                "operational_priority": profile["operational_priority"],
                "expected_passengers": 0,
                "source": "special_train_services",
                "active": True,
                "constraint_profile": profile,
            })

    except Exception as e:
        logger.warning(f"Could not load special_train_services: {e}")

    # 3. Deduplicate by train_number, preferring special_train_services
    deduped: Dict[str, Dict[str, Any]] = {}
    for t in trains_list:
        key = t["train_number"] or t["id"]
        deduped[key] = t

    for s in specials_list:
        key = s["train_number"] or s["id"]
        deduped[key] = s

    

    print("TRAFFIC DEBUG:", corridor_id, target_date)
    print("TRAINS LOADED:", trains_list)
    print("SPECIALS LOADED:", specials_list)

    return list(deduped.values())


def load_traffic_in_window(
    cursor: Any,
    corridor_id: str,
    travel_date: Any,
    start_time: Any,
    end_time: Any
) -> List[Dict[str, Any]]:
    """
    Load traffic overlapping with a specific window on a corridor and date.
    Returns list of traffic items with 'overlap_minutes' attached.
    """
    day_traffic = load_traffic_for_day(
        cursor,
        corridor_id,
        travel_date
    )

    in_window = []

    for item in day_traffic:
        arr = item["arrival_time"]
        dep = item["departure_time"]

        if arr is None or dep is None:
            continue

        overlaps, overlap_min = windows_overlap(
            start_time,
            end_time,
            arr,
            dep
        )

        if overlaps:
            item_copy = dict(item)
            item_copy["overlap_minutes"] = overlap_min
            in_window.append(item_copy)

    return in_window


# ============================================================
# 5. ML-COMPLIANT COUNT CLASSIFICATION
# ============================================================

def classify_counts(items: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Counts train items following ML feature contract:
    - passenger_trains: ALL passenger-facing trains INCLUDING express
    - express_trains: SUBSET of passenger_trains
    - regular_passenger_trains: passenger_trains - express_trains
    - goods_trains: counted separately
    - special_trains: counted separately
    """
    passenger_trains = 0
    express_trains = 0
    goods_trains = 0
    special_trains = 0

    for item in items:
        canonical = item.get("train_type")
        if not canonical:
            canonical, _, _ = normalize_train_type(item.get("raw_train_type"))

        if canonical in ("EXPRESS", "SUPERFAST", "MAIL", "PASSENGER"):
            passenger_trains += 1
            if canonical in ("EXPRESS", "SUPERFAST"):
                express_trains += 1
        elif canonical == "GOODS":
            goods_trains += 1
        elif canonical == "SPECIAL":
            special_trains += 1

    regular_passenger_trains = max(0, passenger_trains - express_trains)

    return {
        "passenger_trains": passenger_trains,
        "express_trains": express_trains,
        "goods_trains": goods_trains,
        "special_trains": special_trains,
        "regular_passenger_trains": regular_passenger_trains,
    }


# ============================================================
# 6. CONFLICT SEVERITY
# ============================================================

def conflict_severity(item: Dict[str, Any], freight_level: str = "LOW") -> str:
    """
    Severity rule:
    - EXPRESS -> CRITICAL
    - SPECIAL with priority >= 4 -> CRITICAL, other SPECIAL -> HIGH
    - SUPERFAST / MAIL / PASSENGER -> HIGH
    - GOODS -> MEDIUM (HIGH when freight_level is HIGH or VERY_HIGH)
    """
    canonical = item.get("train_type")
    if not canonical:
        canonical, _, _ = normalize_train_type(item.get("raw_train_type"))

    profile = item.get("constraint_profile", {})
    prio = int(item.get("operational_priority") or profile.get("operational_priority") or 3)

    if canonical == "EXPRESS":
        return "CRITICAL"
    if canonical == "SPECIAL":
        return "CRITICAL" if prio >= 4 else "HIGH"
    if canonical in ("SUPERFAST", "MAIL", "PASSENGER"):
        return "HIGH"
    if canonical == "GOODS":
        if freight_level in ("HIGH", "VERY_HIGH"):
            return "HIGH"
        return "MEDIUM"

    return "HIGH"


# ============================================================
# 7. WINDOW EVALUATION & DETERMINISTIC SCORING ADJUSTMENT
# ============================================================

SCORING_ADJUSTMENTS_CONFIG = {
    "SPECIAL_CRITICAL_PENALTY": 15.0,   # Points added per CRITICAL special train conflict
    "SPECIAL_HIGH_PENALTY": 8.0,        # Points added per HIGH special train conflict
    "FREIGHT_VERY_HIGH_PENALTY": 12.0,  # Points added if freight pressure is VERY_HIGH with unscheduled freight
    "FREIGHT_HIGH_PENALTY": 6.0,        # Points added if freight pressure is HIGH with unscheduled freight
    "FREIGHT_PRESSURE_VERY_HIGH_PENALTY": 12.0,
    "FREIGHT_PRESSURE_HIGH_PENALTY": 6.0,
}

CONGESTION_MAP = {
    "LOW": 25,
    "MEDIUM": 50,
    "HIGH": 75,
    "VERY HIGH": 90,
    "VERY_HIGH": 90,
    "CRITICAL": 100,
}


def evaluate_window(
    cursor: Any,
    corridor_id: str,
    travel_date: Any,
    start_time: Any,
    end_time: Any,
    criticality: int = 3,
    maintenance_priority: float = 50.0
) -> Dict[str, Any]:
    """
    Evaluates operational impact for a window on a corridor and date:
    - Counts by class
    - Conflict list with constraint profile, overlap minutes, severity, delay
    - Freight demand pressure
    - Corridor congestion (25-100)
    - ML traffic impact score
    - Deterministic adjustment layer (special + freight)
    - Capped 0-100 train impact score
    - Overall risk level (LOW/MEDIUM/HIGH/CRITICAL)
    """
    from logic.freight_pressure import freight_pressure

    date_str = str(travel_date)[:10]

    # 1. Load overlapping traffic items
    items = load_traffic_in_window(cursor, corridor_id, date_str, start_time, end_time)
    counts = classify_counts(items)

    # 2. Freight pressure
    f_pressure = freight_pressure(cursor, corridor_id, date_str, start_time, end_time)

    # 3. Corridor congestion
    cursor.execute("""
        SELECT traffic_level
        FROM corridors
        WHERE corridor_id = %s
    """, (corridor_id,))
    c_row = cursor.fetchone()
    raw_traffic_level = str(c_row[0]).upper() if c_row and c_row[0] else "MEDIUM"
    corridor_congestion = float(CONGESTION_MAP.get(raw_traffic_level, 50))

    # 4. Process conflicts
    conflicts = []
    total_estimated_delay = 0

    for item in items:
        profile = item.get("constraint_profile") or build_constraint_profile(
            raw_type=item.get("raw_train_type") or item.get("train_type"),
            row_priority=item.get("operational_priority"),
            expected_passengers=item.get("expected_passengers"),
            source=item.get("source", "trains")
        )

        overlap_min = item.get("overlap_minutes", 0)
        base_delay = profile.get("base_delay_min", 5)

        if overlap_min >= 30:
            item_delay = base_delay
        elif overlap_min > 0:
            item_delay = max(2, base_delay // 2)
        else:
            item_delay = 0

        total_estimated_delay += item_delay
        sev = conflict_severity(item, freight_level=f_pressure.get("level", "LOW"))

        conflicts.append({
            "train_id": item["train_id"],
            "train_number": item["train_number"],
            "train_name": item["train_name"],
            "train_type": item["train_type"],
            "raw_train_type": item.get("raw_train_type"),
            "traffic_class": item.get("traffic_class", "PASSENGER"),
            "operational_priority": item.get("operational_priority", 3),
            "constraint_profile": profile,
            "overlap_minutes": overlap_min,
            "severity": sev,
            "estimated_delay_min": item_delay,
            "source": item.get("source", "trains"),
        })

    # 5. Base ML traffic impact score
    s_min = time_to_minutes(start_time)
    e_min = time_to_minutes(end_time)
    if e_min <= s_min:
        e_min += 1440
    duration_min = e_min - s_min
    start_hour = (s_min // 60) % 24

    from ml.traffic_predict_service import predict_traffic_impact

    ml_result = predict_traffic_impact(
        block_duration_min=duration_min,
        start_hour=start_hour,
        passenger_trains=counts["passenger_trains"],
        goods_trains=counts["goods_trains"],
        special_trains=counts["special_trains"],
        express_trains=counts["express_trains"],
        corridor_congestion=corridor_congestion,
        criticality=int(criticality),
        maintenance_priority=float(maintenance_priority)
    )
    ml_score = float(ml_result.get("traffic_impact_score", 0.0))

    # 6. Deterministic Explainable Adjustments
    adjustments = []

    # (a) Special train adjustments
    for c in conflicts:
        if c.get("traffic_class") == "SPECIAL":
            train_num = c.get("train_number") or c.get("train_id")
            if c.get("severity") == "CRITICAL":
                pts = SCORING_ADJUSTMENTS_CONFIG["SPECIAL_CRITICAL_PENALTY"]
                adjustments.append({
                    "reason": f"CRITICAL Special train conflict ({train_num})",
                    "points": pts
                })
            else:
                pts = SCORING_ADJUSTMENTS_CONFIG["SPECIAL_HIGH_PENALTY"]
                adjustments.append({
                    "reason": f"Special train conflict ({train_num})",
                    "points": pts
                })

    # (b) Freight pressure adjustments
    unscheduled = f_pressure.get("unscheduled_expected", 0.0)
    freight_lvl = f_pressure.get("level", "LOW")
    if unscheduled >= 0.5:
        if freight_lvl == "VERY_HIGH":
            pts = SCORING_ADJUSTMENTS_CONFIG["FREIGHT_PRESSURE_VERY_HIGH_PENALTY"]
            adjustments.append({
                "reason": f"VERY HIGH freight pressure ({unscheduled} unscheduled trains expected)",
                "points": pts
            })
        elif freight_lvl == "HIGH":
            pts = SCORING_ADJUSTMENTS_CONFIG["FREIGHT_PRESSURE_HIGH_PENALTY"]
            adjustments.append({
                "reason": f"HIGH freight pressure ({unscheduled} unscheduled trains expected)",
                "points": pts
            })

    total_adjustments = sum(a["points"] for a in adjustments)
    adjusted_score = max(0.0, min(100.0, round(ml_score + total_adjustments, 2)))
    train_impact_score = adjusted_score

    # 7. Risk Level Determination
    has_critical = any(c.get("severity") == "CRITICAL" for c in conflicts)
    if has_critical or train_impact_score >= 80 or total_estimated_delay >= 30:
        risk_level = "CRITICAL"
    elif train_impact_score >= 60 or total_estimated_delay >= 20 or len(conflicts) >= 3:
        risk_level = "HIGH"
    elif train_impact_score >= 35 or total_estimated_delay > 0 or len(conflicts) > 0:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return {
        "counts": counts,
        "conflicts": conflicts,
        "freight_pressure": f_pressure,
        "corridor_congestion": corridor_congestion,
        "ml_score": ml_score,
        "adjustments": adjustments,
        "adjusted_score": adjusted_score,
        "train_impact_score": train_impact_score,
        "estimated_delay_min": total_estimated_delay,
        "risk_level": risk_level,
        "duration_minutes": duration_min,
        "start_hour": start_hour,
    }

if __name__ == "__main__":
    import psycopg
    import os
    from dotenv import load_dotenv

    load_dotenv()

    conn = psycopg.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )

    with conn.cursor() as cur:
        result = evaluate_window(
            cur,
            "C01",
            "2026-08-28",
            "10:00:00",
            "11:00:00"
        )

        print("\n===== WINDOW CONFLICT TEST =====")
        print("Conflicts:", result.get("conflicts"))
        print("Total delay:", result.get("total_estimated_delay"))

    conn.close()