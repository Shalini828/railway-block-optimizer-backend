"""
Traffic Timeline Route.
IR-ABPS Block Planning Engine.

Provides unified corridor timeline data:
- Scheduled trains, goods trains, and active special trains (from traffic_intelligence)
- Optimized maintenance blocks
- Forecast-based freight pressure strip (marked with hourly_distribution: "estimated")
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, date
import psycopg
from fastapi import APIRouter, HTTPException, Depends, Query

from db_config import DB_CONFIG
from auth.security import get_current_user, require_permission, CurrentUser
from auth.scoping import get_relevant_corridor_ids
from logic.traffic_intelligence import (
    load_traffic_for_day,
    windows_overlap,
)
from logic.freight_pressure import freight_pressure

router = APIRouter(
    prefix="/traffic",
    tags=["Traffic Timeline"]
)


@router.get("/timeline", dependencies=[Depends(require_permission("trains.view"))])
def get_corridor_timeline(
    corridor_id: str = Query(..., description="Corridor ID e.g. CORR-001"),
    date: str = Query(..., description="Date YYYY-MM-DD"),
    user: CurrentUser = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Unified corridor timeline for Gantt planner and corridor scheduling:
    - items: scheduled trains, goods trains, and active specials with canonical type and constraint profile
    - blocks: optimized maintenance blocks on that corridor and date
    - freight_forecast: freight demand and pressure estimate (hourly_distribution: 'estimated')
    """
    target_date_str = date[:10]

    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            # 1. Department scoping check
            if user.scope != "network":
                allowed_corridors = get_relevant_corridor_ids(cur, user.dept)
                if corridor_id not in allowed_corridors:
                    return {
                        "status": "success",
                        "corridor_id": corridor_id,
                        "date": target_date_str,
                        "items": [],
                        "blocks": [],
                        "freight_forecast": {
                            "expected_daily": 0,
                            "expected_in_window": 0,
                            "level": "LOW",
                            "confidence": 0,
                            "hourly_distribution": "estimated",
                            "source": "unauthorized_scope"
                        }
                    }

            # 2. Unified traffic items (trains + active specials, deduped)
            day_items = load_traffic_for_day(cur, corridor_id, target_date_str)
            timeline_items = []

            for item in day_items:
                arr = item.get("arrival_time")
                dep = item.get("departure_time")
                timeline_items.append({
                    "id": item.get("id") or item.get("train_id"),
                    "train_id": item.get("id") or item.get("train_id"),
                    "train_number": item.get("train_number"),
                    "train_name": item.get("train_name"),
                    "train_type": item.get("train_type"),
                    "raw_train_type": item.get("raw_train_type"),
                    "traffic_class": item.get("traffic_class", "PASSENGER"),
                    "start": str(arr) if arr else None,
                    "end": str(dep) if dep else None,
                    "priority": item.get("operational_priority", 3),
                    "operational_priority": item.get("operational_priority", 3),
                    "direction": item.get("direction"),
                    "source": item.get("source", "trains"),
                    # Special train specific attributes
                    "special_type": item.get("special_type"),
                    "expected_passengers": item.get("expected_passengers", 0),
                    "origin_station": item.get("origin_station"),
                    "destination_station": item.get("destination_station"),
                    "origin": item.get("origin_station"),
                    "destination": item.get("destination_station"),
                    "reason": item.get("reason"),
                })

            # 3. Optimized maintenance blocks for corridor + date
            cur.execute("""
                SELECT
                    block_id,
                    corridor_id,
                    block_date,
                    start_time,
                    end_time,
                    duration_min,
                    utilization_percent,
                    train_impact_score,
                    optimization_score,
                    block_status
                FROM optimized_blocks
                WHERE corridor_id = %s
                  AND block_date = %s
                ORDER BY start_time ASC
            """, (corridor_id, target_date_str))

            block_rows = cur.fetchall()
            blocks = []
            for b in block_rows:
                blocks.append({
                    "block_id": b[0],
                    "corridor_id": b[1],
                    "date": str(b[2]),
                    "start": str(b[3]) if b[3] else None,
                    "end": str(b[4]) if b[4] else None,
                    "duration_min": b[5],
                    "utilization_percent": float(b[6] or 0),
                    "train_impact_score": float(b[7] or 0),
                    "optimization_score": float(b[8] or 0),
                    "status": b[9] or "PLANNED",
                })

            # 4. Freight demand pressure forecast for the day
            fp = freight_pressure(cur, corridor_id, target_date_str, "00:00:00", "23:59:59")
            fp["hourly_distribution"] = "estimated"

            return {
                "status": "success",
                "corridor_id": corridor_id,
                "date": target_date_str,
                "items": timeline_items,
                "blocks": blocks,
                "freight_forecast": fp
            }
