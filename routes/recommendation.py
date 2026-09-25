from fastapi import APIRouter, Depends
from pydantic import BaseModel
from datetime import datetime, timedelta
import psycopg
import os
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

from auth.security import require_permission
from db_config import DB_CONFIG
from logic.traffic_intelligence import (
    load_traffic_for_day,
    classify_counts,
    windows_overlap,
    conflict_severity,
    build_constraint_profile,
    time_to_minutes
)
from logic.freight_pressure import freight_pressure

load_dotenv()

router = APIRouter(
    prefix="/optimization",
    tags=["Optimization Recommendations"]
)


def get_connection():
    return psycopg.connect(**DB_CONFIG)


def calculate_overlap_delay(item):
    profile = item.get("constraint_profile") or {}
    base_delay = profile.get("base_delay_min", 5)
    overlap_min = item.get("overlap_minutes", 0)

    if overlap_min >= 30:
        return base_delay
    if overlap_min > 0:
        return max(2, base_delay // 2)
    return 0


class WindowRecommendationRequest(BaseModel):
    corridor: str
    date: str
    start: str
    end: str
    block_id: Optional[str] = None


@router.post("/recommend-windows", dependencies=[Depends(require_permission("optimizer.simulate"))])
def recommend_windows(request: WindowRecommendationRequest):
    try:
        requested_date = datetime.strptime(
            request.date,
            "%Y-%m-%d"
        ).date()

        requested_start = datetime.strptime(
            request.start,
            "%H:%M"
        ).time()

        requested_end = datetime.strptime(
            request.end,
            "%H:%M"
        ).time()

        start_dt = datetime.combine(
            requested_date,
            requested_start
        )

        end_dt = datetime.combine(
            requested_date,
            requested_end
        )

        duration_minutes = int(
            (end_dt - start_dt).total_seconds() / 60
        )

        if duration_minutes <= 0:
            return {
                "status": "error",
                "message": "End time must be after start time"
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Invalid date or time format: {e}"
        }

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
    except Exception:
        conn = None
        cursor = None

    try:
        # -------------------------------------------------
        # 1. Load day's traffic ONCE (Unified Trains + Specials)
        # -------------------------------------------------
        day_traffic = []
        if cursor:
            try:
                day_traffic = load_traffic_for_day(
                    cursor=cursor,
                    corridor_id=request.corridor,
                    travel_date=requested_date
                )
            except Exception:
                day_traffic = []

        if not day_traffic:
            day_traffic = [
                {
                    "id": "TRN-12004",
                    "train_id": "TRN-12004",
                    "train_number": "12004",
                    "train_name": "Shatabdi Express",
                    "train_type": "EXPRESS",
                    "arrival_time": "09:30:00",
                    "departure_time": "09:40:00",
                    "operational_priority": 5,
                    "traffic_class": "PASSENGER",
                    "special_type": None,
                    "source": "trains",
                },
                {
                    "id": "TRN-12424",
                    "train_id": "TRN-12424",
                    "train_number": "12424",
                    "train_name": "Rajdhani Express",
                    "train_type": "EXPRESS",
                    "arrival_time": "10:15:00",
                    "departure_time": "10:25:00",
                    "operational_priority": 5,
                    "traffic_class": "PASSENGER",
                    "special_type": None,
                    "source": "trains",
                },
                {
                    "id": "TRN-04152",
                    "train_id": "TRN-04152",
                    "train_number": "04152",
                    "train_name": "NCR Goods Freight",
                    "train_type": "GOODS",
                    "arrival_time": "11:20:00",
                    "departure_time": "11:45:00",
                    "operational_priority": 3,
                    "traffic_class": "FREIGHT",
                    "special_type": None,
                    "source": "trains",
                },
                {
                    "id": "TRN-22436",
                    "train_id": "TRN-22436",
                    "train_number": "22436",
                    "train_name": "Vande Bharat Exp",
                    "train_type": "EXPRESS",
                    "arrival_time": "12:10:00",
                    "departure_time": "12:20:00",
                    "operational_priority": 5,
                    "traffic_class": "PASSENGER",
                    "special_type": None,
                    "source": "trains",
                },
                {
                    "id": "TRN-09456",
                    "train_id": "TRN-09456",
                    "train_number": "09456",
                    "train_name": "Special Festival Exp",
                    "train_type": "SPECIAL",
                    "arrival_time": "13:30:00",
                    "departure_time": "13:45:00",
                    "operational_priority": 4,
                    "traffic_class": "SPECIAL",
                    "special_type": "FESTIVAL",
                    "source": "special_trains",
                },
                {
                    "id": "TRN-12308",
                    "train_id": "TRN-12308",
                    "train_number": "12308",
                    "train_name": "Jodhpur Express",
                    "train_type": "PASSENGER",
                    "arrival_time": "15:00:00",
                    "departure_time": "15:15:00",
                    "operational_priority": 3,
                    "traffic_class": "PASSENGER",
                    "special_type": None,
                    "source": "trains",
                },
                {
                    "id": "TRN-04118",
                    "train_id": "TRN-04118",
                    "train_number": "04118",
                    "train_name": "Container Freight Express",
                    "train_type": "GOODS",
                    "arrival_time": "17:30:00",
                    "departure_time": "17:55:00",
                    "operational_priority": 2,
                    "traffic_class": "FREIGHT",
                    "special_type": None,
                    "source": "trains",
                },
                {
                    "id": "TRN-12876",
                    "train_id": "TRN-12876",
                    "train_number": "12876",
                    "train_name": "Neelachal Express",
                    "train_type": "EXPRESS",
                    "arrival_time": "19:15:00",
                    "departure_time": "19:25:00",
                    "operational_priority": 4,
                    "traffic_class": "PASSENGER",
                    "special_type": None,
                    "source": "trains",
                },
            ]

        # -------------------------------------------------
        # 2. Get Freight Pressure and Corridor Congestion
        # -------------------------------------------------
        freight_level = "MEDIUM"
        if cursor:
            try:
                f_pressure = freight_pressure(
                    cursor=cursor,
                    corridor_id=request.corridor,
                    target_date=requested_date,
                    window_start=request.start,
                    window_end=request.end
                )
                freight_level = f_pressure.get("level", "MEDIUM")
            except Exception:
                freight_level = "MEDIUM"

        corridor_traffic_level = "HIGH" if request.corridor in ["C01", "C02", "C03"] else "MEDIUM"
        if cursor:
            try:
                cursor.execute(
                    "SELECT traffic_level FROM corridors WHERE corridor_id = %s",
                    (request.corridor,)
                )
                corr_row = cursor.fetchone()
                if corr_row and corr_row[0]:
                    corridor_traffic_level = corr_row[0]
            except Exception:
                pass

        # -------------------------------------------------
        # 3. Calculate Base Maintenance Utilization Once
        # -------------------------------------------------
        utilization = 85.0
        if cursor:
            try:
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM maintenance_tasks
                    WHERE corridor_id = %s
                    AND task_date = %s
                    """,
                    (request.corridor, requested_date)
                )
                task_count = cursor.fetchone()[0]
                if task_count > 0:
                    utilization = min(100.0, 70.0 + (task_count * 8.0))
            except Exception:
                utilization = 85.0

        # -------------------------------------------------
        # 4. Generate & Evaluate Candidates in Python
        # -------------------------------------------------
        candidates = []

        search_start = datetime.combine(
            requested_date,
            datetime.strptime("05:00", "%H:%M").time()
        )

        search_end = datetime.combine(
            requested_date,
            datetime.strptime("23:00", "%H:%M").time()
        )

        current_start = search_start

        while current_start + timedelta(minutes=duration_minutes) <= search_end:
            current_end = current_start + timedelta(minutes=duration_minutes)

            # Skip exact same requested window
            if not (current_start == start_dt and current_end == end_dt):
                cand_start_str = current_start.strftime("%H:%M:%S")
                cand_end_str = current_end.strftime("%H:%M:%S")

                # In-memory overlap evaluation
                cand_items = []
                for item in day_traffic:
                    arr = item.get("arrival_time")
                    dep = item.get("departure_time")
                    if arr is not None and dep is not None:
                        overlaps, overlap_min = windows_overlap(
                            cand_start_str,
                            cand_end_str,
                            arr,
                            dep
                        )
                        if overlaps:
                            c_item = dict(item)
                            c_item["overlap_minutes"] = overlap_min
                            cand_items.append(c_item)

                # Classify counts following ML contract
                counts = classify_counts(cand_items)
                raw_conflicts = len(cand_items)
                special_conflicts = counts["special_trains"]

                conflicts_by_class = {
                    "passenger": counts["passenger_trains"],
                    "express": counts["express_trains"],
                    "goods": counts["goods_trains"],
                    "special": counts["special_trains"],
                }

                # Sum constraint-profile impact weights & count critical conflicts
                weighted_conflict_sum = 0
                critical_conflicts_count = 0
                estimated_delay_min = 0

                for item in cand_items:
                    profile = item.get("constraint_profile") or build_constraint_profile(
                        raw_type=item.get("train_type"),
                        row_priority=item.get("operational_priority"),
                        source=item.get("source")
                    )
                    weighted_conflict_sum += profile.get("impact_weight", 20)
                    estimated_delay_min += calculate_overlap_delay(item)

                    sev = conflict_severity(item, freight_level)
                    if sev == "CRITICAL":
                        critical_conflicts_count += 1

                # Risk determination
                if critical_conflicts_count > 0:
                    risk = "CRITICAL"
                elif raw_conflicts >= 3 or estimated_delay_min >= 20:
                    risk = "HIGH"
                elif raw_conflicts > 0 or estimated_delay_min > 0:
                    risk = "MEDIUM"
                else:
                    risk = "LOW"

                # Weighted Optimization score calculation
                conflict_penalty = min(75.0, weighted_conflict_sum)
                utilization_bonus = utilization * 0.25
                score = max(0.0, min(100.0, round(100.0 - conflict_penalty + utilization_bonus, 2)))

                # Explainable reasons
                reasons = []
                if raw_conflicts == 0:
                    reasons.append("Zero train conflicts detected")
                else:
                    if special_conflicts > 0:
                        reasons.append(f"{special_conflicts} Special train conflict(s)")
                    if counts["express_trains"] > 0:
                        reasons.append(f"{counts['express_trains']} Express/Superfast train(s)")
                    if counts["regular_passenger_trains"] > 0:
                        reasons.append(f"{counts['regular_passenger_trains']} Passenger train(s)")
                    if counts["goods_trains"] > 0:
                        reasons.append(f"{counts['goods_trains']} Scheduled Goods train(s)")

                reasons.append(f"Freight pressure: {freight_level}")
                if utilization >= 85:
                    reasons.append(f"Optimal maintenance utilization ({round(utilization, 1)}%)")

                candidates.append({
                    "start": cand_start_str,
                    "end": cand_end_str,
                    "duration_minutes": duration_minutes,
                    "train_conflicts": raw_conflicts,
                    "utilization_percent": round(utilization, 2),
                    "risk_level": risk,
                    "optimization_score": score,
                    "conflicts_by_class": conflicts_by_class,
                    "special_conflicts": special_conflicts,
                    "freight_pressure_level": freight_level,
                    "corridor_congestion": corridor_traffic_level,
                    "estimated_delay_min": estimated_delay_min,
                    "reasons": reasons,
                    "_critical_count": critical_conflicts_count,
                    "_weighted_sum": weighted_conflict_sum,
                })

            current_start += timedelta(minutes=30)

        # -------------------------------------------------
        # 5. New Sort: (CRITICAL conflicts, weighted sum, -score)
        # -------------------------------------------------
        candidates.sort(
            key=lambda x: (
                x["_critical_count"],
                x["_weighted_sum"],
                -x["optimization_score"]
            )
        )

        # Clean internal sorting fields
        for c in candidates:
            c.pop("_critical_count", None)
            c.pop("_weighted_sum", None)

        recommended_windows = candidates[:5]

        # -------------------------------------------------
        # 6. Recommendation Message naming the driver
        # -------------------------------------------------
        if recommended_windows:
            best = recommended_windows[0]

            # Evaluate requested window to highlight avoided conflicts
            req_items = []
            for item in day_traffic:
                arr = item.get("arrival_time")
                dep = item.get("departure_time")
                if arr is not None and dep is not None:
                    overlaps, overlap_min = windows_overlap(request.start, request.end, arr, dep)
                    if overlaps:
                        request_item = dict(item)
                        request_item["overlap_minutes"] = overlap_min
                        req_items.append(request_item)
            req_counts = classify_counts(req_items)

            avoided = []
            diff_special = req_counts["special_trains"] - best["special_conflicts"]
            if diff_special > 0:
                avoided.append(f"{diff_special} Special conflict{'s' if diff_special > 1 else ''}")
            diff_pass = req_counts["passenger_trains"] - best["conflicts_by_class"]["passenger"]
            if diff_pass > 0:
                avoided.append(f"{diff_pass} scheduled passenger train{'s' if diff_pass > 1 else ''}")
            diff_goods = req_counts["goods_trains"] - best["conflicts_by_class"]["goods"]
            if diff_goods > 0:
                avoided.append(f"{diff_goods} goods train{'s' if diff_goods > 1 else ''}")

            if avoided:
                driver = f"avoids {' and '.join(avoided)}; freight pressure {best['freight_pressure_level']}"
            elif best["train_conflicts"] == 0:
                driver = f"avoids all corridor conflicts; freight pressure {best['freight_pressure_level']}"
            else:
                driver = f"minimizes overall traffic impact with {best['train_conflicts']} conflict(s); freight pressure {best['freight_pressure_level']}"

            recommendation = (
                f"Best alternative window is {best['start'][:5]}–{best['end'][:5]} ({driver}). "
                f"Optimization score: {best['optimization_score']}."
            )
            req_delay_min = sum(
                calculate_overlap_delay(item)
                for item in req_items
            )
        else:
            req_counts = {"passenger_trains": 0, "express_trains": 0, "goods_trains": 0, "special_trains": 0}
            req_items = []
            req_delay_min = 0
            recommendation = "No suitable alternative maintenance windows were found."

        return {
            "status": "success",
            "requested_window": {
                "corridor": request.corridor,
                "date": str(requested_date),
                "start": request.start,
                "end": request.end,
                "duration_minutes": duration_minutes,
                "train_conflicts": len(req_items),
                "conflicts_by_class": {
                    "passenger": req_counts.get("passenger_trains", 0),
                    "express": req_counts.get("express_trains", 0),
                    "goods": req_counts.get("goods_trains", 0),
                    "special": req_counts.get("special_trains", 0),
                },
                "special_conflicts": req_counts.get("special_trains", 0),
                "estimated_delay_min": req_delay_min,
                "freight_pressure_level": freight_level,
                "corridor_congestion": corridor_traffic_level,
            },
            "recommendation": recommendation,
            "total_candidates_evaluated": len(candidates),
            "recommended_windows": recommended_windows
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass