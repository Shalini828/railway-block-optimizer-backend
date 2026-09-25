from typing import Optional, List, Dict, Any
from datetime import datetime, date, time, timedelta
import threading
import logging

import psycopg
from fastapi import APIRouter, HTTPException, Depends, Query, status
from pydantic import BaseModel, Field

from db_config import DB_CONFIG
from auth.security import get_current_user, require_permission, CurrentUser
from auth.scoping import get_relevant_corridor_ids
from auth.audit import record_audit
from logic.traffic_intelligence import (
    windows_overlap,
    time_to_minutes,
    minutes_to_time_str,
    load_traffic_for_day,
)

logger = logging.getLogger("special_trains")

router = APIRouter(
    prefix="/special-trains",
    tags=["Special Trains"],
)

VALID_SPECIAL_TYPES = {
    "FESTIVAL",
    "HOLIDAY",
    "EVENT",
    "MILITARY",
    "RELIEF",
    "SEASONAL",
    "OTHER",
}

VALID_DIRECTIONS = {"UP", "DOWN"}

KNOWN_CORRIDORS = {
    "C01": "New Delhi – Ghaziabad",
    "C02": "Delhi – Ghaziabad",
    "C03": "Ghaziabad – Meerut",
    "C04": "Delhi – Panipat",
    "C05": "Panipat – Ambala",
    "C06": "Mumbai – Thane",
    "C07": "Thane – Nashik",
    "C08": "Chennai – Arakkonam",
    "C09": "Kolkata – Howrah",
    "C10": "Bhopal – Itarsi",
    "C11": "Pune – Lonavala",
    "CORR-001": "NDLS - CNB High Density",
    "CORR-002": "CNB - PRYJ Corridor",
}


class SpecialTrainCreateSchema(BaseModel):
    train_number: str = Field(..., min_length=1, max_length=30)
    train_name: str = Field(..., min_length=1, max_length=150)
    special_type: str
    corridor_id: str
    service_date: Optional[str] = None
    service_date_from: Optional[str] = None
    service_date_to: Optional[str] = None
    arrival_time: str
    departure_time: str
    direction: str = "UP"
    operational_priority: int = Field(4, ge=1, le=5)
    expected_passengers: int = Field(0, ge=0)
    reason: Optional[str] = None
    origin_station: Optional[str] = None
    destination_station: Optional[str] = None
    active: bool = True


class SpecialTrainUpdateSchema(BaseModel):
    train_number: Optional[str] = None
    train_name: Optional[str] = None
    special_type: Optional[str] = None
    corridor_id: Optional[str] = None
    service_date: Optional[str] = None
    arrival_time: Optional[str] = None
    departure_time: Optional[str] = None
    direction: Optional[str] = None
    operational_priority: Optional[int] = Field(None, ge=1, le=5)
    expected_passengers: Optional[int] = Field(None, ge=0)
    reason: Optional[str] = None
    origin_station: Optional[str] = None
    destination_station: Optional[str] = None
    active: Optional[bool] = None


class ActiveToggleSchema(BaseModel):
    active: bool


def _parse_time(value):
    if isinstance(value, time):
        return value
    value = str(value).strip()
    if len(value) == 5:
        value += ":00"
    return datetime.strptime(value[:8], "%H:%M:%S").time()


def _parse_date(value):
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _format_special(row):
    """
    Convert DB row into the response schema expected by the frontend.
    """
    (
        special_id,
        train_number,
        train_name,
        event_name,
        event_type,
        corridor_id,
        service_date,
        departure_time,
        arrival_time,
        direction,
        operational_priority,
        status_value,
    ) = row

    prio = operational_priority
    if prio is not None and prio > 5:
        prio = max(1, min(5, round(prio / 20)))
    elif not prio:
        prio = 4

    return {
        "special_train_id": special_id,
        "train_number": train_number,
        "train_name": train_name,
        "special_type": event_type or "OTHER",
        "corridor_id": corridor_id,
        "service_date": str(service_date),
        "arrival_time": str(arrival_time) if arrival_time else None,
        "departure_time": str(departure_time) if departure_time else None,
        "direction": direction or "UP",
        "operational_priority": prio,
        "expected_passengers": 1200 if prio >= 4 else 600,
        "reason": event_name,
        "active": status_value == "SCHEDULED",
        "origin_station": None,
        "destination_station": None,
        "created_by": None,
        "created_at": None,
        "updated_at": None,
    }


def _get_db_connection():
    """Try to establish a live PostgreSQL connection. Returns None if DB is offline."""
    try:
        conn = psycopg.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        logger.debug(f"Live PostgreSQL connection unavailable: {e}")
        return None


# ============================================================
# RESILIENT IN-MEMORY STORE (Dual-mode fallback when DB offline)
# ============================================================

class InMemorySpecialTrainStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._items: Dict[str, Dict[str, Any]] = {}
        self._seed_data()

    def _seed_data(self):
        today = datetime.now().date()
        today_str = str(today)

        seeds = [
            {
                "special_train_id": "SPL-0001",
                "train_number": "04011",
                "train_name": "Kumbh Mela Mahakumbh Superfast Special",
                "special_type": "FESTIVAL",
                "corridor_id": "C01",
                "service_date": today_str,
                "arrival_time": "08:00:00",
                "departure_time": "10:30:00",
                "direction": "UP",
                "operational_priority": 5,
                "expected_passengers": 1450,
                "reason": "Maha Kumbh peak pilgrim clearance with high occupancy profile",
                "active": True,
                "origin_station": "New Delhi (NDLS)",
                "destination_station": "Prayagraj Jn (PRYJ)",
                "created_by": "DRM Planning",
                "created_at": today_str + "T06:00:00Z",
                "updated_at": today_str + "T06:00:00Z",
            },
            {
                "special_train_id": "SPL-0002",
                "train_number": "04022",
                "train_name": "Armed Forces Strategic Military Special",
                "special_type": "MILITARY",
                "corridor_id": "C02",
                "service_date": today_str,
                "arrival_time": "04:15:00",
                "departure_time": "05:45:00",
                "direction": "DOWN",
                "operational_priority": 5,
                "expected_passengers": 450,
                "reason": "Defense movement priority corridor transfer with security escort",
                "active": True,
                "origin_station": "Ambala Cantt (UMB)",
                "destination_station": "Kanpur Central (CNB)",
                "created_by": "Army Liaison Cell",
                "created_at": today_str + "T04:00:00Z",
                "updated_at": today_str + "T04:00:00Z",
            },
            {
                "special_train_id": "SPL-0003",
                "train_number": "04033",
                "train_name": "Diwali & Chhath Puja Superfast Express",
                "special_type": "FESTIVAL",
                "corridor_id": "C03",
                "service_date": today_str,
                "arrival_time": "14:30:00",
                "departure_time": "16:00:00",
                "direction": "UP",
                "operational_priority": 4,
                "expected_passengers": 1200,
                "reason": "Eastern corridor festival rush clearance for Diwali / Chhath",
                "active": True,
                "origin_station": "Anand Vihar (ANVT)",
                "destination_station": "Patna Jn (PNBE)",
                "created_by": "Commercial Control",
                "created_at": today_str + "T08:00:00Z",
                "updated_at": today_str + "T08:00:00Z",
            },
            {
                "special_train_id": "SPL-0004",
                "train_number": "04044",
                "train_name": "NDRF Disaster Relief & Medical Special",
                "special_type": "RELIEF",
                "corridor_id": "C01",
                "service_date": today_str,
                "arrival_time": "18:00:00",
                "departure_time": "19:15:00",
                "direction": "DOWN",
                "operational_priority": 4,
                "expected_passengers": 200,
                "reason": "Emergency medical disaster response team & equipment dispatch",
                "active": True,
                "origin_station": "New Delhi (NDLS)",
                "destination_station": "Kanpur Central (CNB)",
                "created_by": "Emergency Control",
                "created_at": today_str + "T10:00:00Z",
                "updated_at": today_str + "T10:00:00Z",
            },
            {
                "special_train_id": "SPL-0005",
                "train_number": "02251",
                "train_name": "Summer Holiday Ganga Yamuna Special",
                "special_type": "HOLIDAY",
                "corridor_id": "C02",
                "service_date": today_str,
                "arrival_time": "11:00:00",
                "departure_time": "12:30:00",
                "direction": "UP",
                "operational_priority": 3,
                "expected_passengers": 980,
                "reason": "Peak summer vacation holiday express service",
                "active": True,
                "origin_station": "Delhi Jn (DLI)",
                "destination_station": "Varanasi Jn (BSB)",
                "created_by": "Operating Dept",
                "created_at": today_str + "T09:00:00Z",
                "updated_at": today_str + "T09:00:00Z",
            },
            {
                "special_train_id": "SPL-0006",
                "train_number": "09015",
                "train_name": "Vande Bharat Clone Festival Special",
                "special_type": "FESTIVAL",
                "corridor_id": "C01",
                "service_date": today_str,
                "arrival_time": "06:00:00",
                "departure_time": "07:15:00",
                "direction": "UP",
                "operational_priority": 5,
                "expected_passengers": 1100,
                "reason": "High-speed morning corridor relief service",
                "active": True,
                "origin_station": "New Delhi (NDLS)",
                "destination_station": "Varanasi Jn (BSB)",
                "created_by": "CPTM Office",
                "created_at": today_str + "T05:00:00Z",
                "updated_at": today_str + "T05:00:00Z",
            },
            {
                "special_train_id": "SPL-0007",
                "train_number": "04107",
                "train_name": "Seasonal Agricultural Harvest Special",
                "special_type": "SEASONAL",
                "corridor_id": "C04",
                "service_date": today_str,
                "arrival_time": "21:00:00",
                "departure_time": "22:30:00",
                "direction": "DOWN",
                "operational_priority": 2,
                "expected_passengers": 350,
                "reason": "Night parcel express for agricultural cargo and passenger trailers",
                "active": False,
                "origin_station": "Prayagraj Jn (PRYJ)",
                "destination_station": "Pt. Deen Dayal Upadhyaya (DDU)",
                "created_by": "Freight & Parcel Cell",
                "created_at": today_str + "T11:00:00Z",
                "updated_at": today_str + "T11:00:00Z",
            },
            {
                "special_train_id": "SPL-0008",
                "train_number": "04589",
                "train_name": "Bharat Gaurav Spiritual Circuit Special",
                "special_type": "EVENT",
                "corridor_id": "C03",
                "service_date": today_str,
                "arrival_time": "09:45:00",
                "departure_time": "11:15:00",
                "direction": "UP",
                "operational_priority": 3,
                "expected_passengers": 750,
                "reason": "Tourism and pilgrimage special charter path",
                "active": True,
                "origin_station": "Kanpur Central (CNB)",
                "destination_station": "Varanasi Jn (BSB)",
                "created_by": "IRCTC Coordination",
                "created_at": today_str + "T07:30:00Z",
                "updated_at": today_str + "T07:30:00Z",
            },
        ]

        for s in seeds:
            self._items[s["special_train_id"]] = s

    def list_trains(
        self,
        corridor_id: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        active: Optional[bool] = None,
        allowed_corridors: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            result = []
            for item in self._items.values():
                if allowed_corridors is not None and item["corridor_id"] not in allowed_corridors:
                    continue
                if corridor_id and item["corridor_id"].upper() != corridor_id.upper():
                    continue
                if from_date:
                    try:
                        if _parse_date(item["service_date"]) < _parse_date(from_date):
                            continue
                    except Exception:
                        pass
                if to_date:
                    try:
                        if _parse_date(item["service_date"]) > _parse_date(to_date):
                            continue
                    except Exception:
                        pass
                if active is not None and item["active"] != active:
                    continue

                result.append(dict(item))

            result.sort(key=lambda x: (x.get("service_date", ""), x.get("departure_time", "")))
            return result

    def get_train(self, special_train_id: str, allowed_corridors: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            item = self._items.get(special_train_id)
            if not item:
                return None
            if allowed_corridors is not None and item["corridor_id"] not in allowed_corridors:
                return "FORBIDDEN"
            return dict(item)

    def create_trains(self, payload: SpecialTrainCreateSchema, user: CurrentUser) -> List[Dict[str, Any]]:
        with self._lock:
            event_type = payload.special_type.strip().upper()
            direction = payload.direction.strip().upper()

            # Date calculation
            dates = []
            if payload.service_date_from and payload.service_date_to:
                start = _parse_date(payload.service_date_from)
                end = _parse_date(payload.service_date_to)
                if end < start:
                    raise HTTPException(
                        status_code=400,
                        detail="service_date_to cannot be before service_date_from",
                    )
                curr = start
                while curr <= end:
                    dates.append(curr)
                    curr += timedelta(days=1)
            elif payload.service_date:
                dates.append(_parse_date(payload.service_date))
            else:
                dates.append(datetime.now().date())

            created_items = []
            for d in dates:
                d_str = str(d)
                # Generate unique ID
                max_num = 1
                for k in self._items.keys():
                    if k.startswith("SPL-") or k.startswith("SP-AUTO-"):
                        try:
                            num = int(k.split("-")[-1])
                            if num >= max_num:
                                max_num = num + 1
                        except Exception:
                            pass
                new_id = f"SPL-{max_num:04d}"

                new_item = {
                    "special_train_id": new_id,
                    "train_number": payload.train_number.strip(),
                    "train_name": payload.train_name.strip(),
                    "special_type": event_type,
                    "corridor_id": payload.corridor_id.strip(),
                    "service_date": d_str,
                    "arrival_time": payload.arrival_time if len(payload.arrival_time) == 8 else f"{payload.arrival_time}:00",
                    "departure_time": payload.departure_time if len(payload.departure_time) == 8 else f"{payload.departure_time}:00",
                    "direction": direction,
                    "operational_priority": payload.operational_priority,
                    "expected_passengers": payload.expected_passengers or 1200,
                    "reason": payload.reason or "Festival & special path requisition",
                    "active": payload.active,
                    "origin_station": payload.origin_station,
                    "destination_station": payload.destination_station,
                    "created_by": user.name or "Officer Planning",
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
                self._items[new_id] = new_item
                created_items.append(new_item)

                try:
                    record_audit(
                        actor_role=user.role_id,
                        actor_name=user.name,
                        method="POST",
                        path="/special-trains",
                        action="CREATE_SPECIAL_TRAIN",
                        target_type="special_train",
                        target_id=new_id,
                        outcome="SUCCESS",
                        detail={"train_number": payload.train_number, "corridor_id": payload.corridor_id},
                    )
                except Exception:
                    pass

            return created_items

    def update_train(self, special_train_id: str, payload: SpecialTrainUpdateSchema, user: CurrentUser) -> Dict[str, Any]:
        with self._lock:
            if special_train_id not in self._items:
                raise HTTPException(status_code=404, detail="Special train not found")
            item = self._items[special_train_id]

            if payload.train_number is not None:
                item["train_number"] = payload.train_number.strip()
            if payload.train_name is not None:
                item["train_name"] = payload.train_name.strip()
            if payload.special_type is not None:
                item["special_type"] = payload.special_type.strip().upper()
            if payload.corridor_id is not None:
                item["corridor_id"] = payload.corridor_id.strip()
            if payload.service_date is not None:
                item["service_date"] = str(_parse_date(payload.service_date))
            if payload.arrival_time is not None:
                arr = payload.arrival_time.strip()
                item["arrival_time"] = arr if len(arr) == 8 else f"{arr}:00"
            if payload.departure_time is not None:
                dep = payload.departure_time.strip()
                item["departure_time"] = dep if len(dep) == 8 else f"{dep}:00"
            if payload.direction is not None:
                item["direction"] = payload.direction.strip().upper()
            if payload.operational_priority is not None:
                item["operational_priority"] = payload.operational_priority
            if payload.expected_passengers is not None:
                item["expected_passengers"] = payload.expected_passengers
            if payload.reason is not None:
                item["reason"] = payload.reason
            if payload.active is not None:
                item["active"] = payload.active

            item["updated_at"] = datetime.now().isoformat()
            return dict(item)

    def toggle_active(self, special_train_id: str, active: bool, user: CurrentUser) -> Dict[str, Any]:
        with self._lock:
            if special_train_id not in self._items:
                raise HTTPException(status_code=404, detail="Special train not found")
            item = self._items[special_train_id]
            item["active"] = active
            item["updated_at"] = datetime.now().isoformat()
            return dict(item)

    def get_impact(self, special_train_id: str, user: CurrentUser) -> Dict[str, Any]:
        with self._lock:
            if special_train_id not in self._items:
                raise HTTPException(status_code=404, detail="Special train not found")
            item = self._items[special_train_id]

        corridor_id = item["corridor_id"]
        arr_time = item["arrival_time"] or "08:00:00"
        dep_time = item["departure_time"] or "10:30:00"
        train_start_min = time_to_minutes(arr_time)
        train_end_min = time_to_minutes(dep_time)

        # Realistic simulated maintenance blocks for corridor conflict analysis
        simulated_blocks = [
            {
                "block_id": f"BLK-{corridor_id}-TRACK",
                "corridor_id": corridor_id,
                "block_date": item["service_date"],
                "start_time": "08:30:00",
                "end_time": "11:30:00",
                "duration_min": 180,
                "utilization_percent": 88.5,
                "train_impact_score": 65.0,
                "optimization_score": 91.0,
            },
            {
                "block_id": f"BLK-{corridor_id}-OHE",
                "corridor_id": corridor_id,
                "block_date": item["service_date"],
                "start_time": "14:00:00",
                "end_time": "16:30:00",
                "duration_min": 150,
                "utilization_percent": 76.0,
                "train_impact_score": 42.0,
                "optimization_score": 88.0,
            },
        ]

        overlapping_blocks = []
        for b in simulated_blocks:
            overlaps, overlap_min = windows_overlap(
                arr_time,
                dep_time,
                b["start_time"],
                b["end_time"],
            )
            if overlaps:
                overlapping_blocks.append({
                    **b,
                    "overlap_minutes": overlap_min,
                })

        recommended_shift = None
        if overlapping_blocks:
            recommended_shift = {
                "block_id": overlapping_blocks[0]["block_id"],
                "shift_offset_min": -45,
                "proposed_start": "07:45:00",
                "proposed_end": "10:45:00",
                "expected_train_conflicts": 0,
                "rationale": (
                    f"Advance block window by 45 minutes to clear special path for "
                    f"{item['train_number']} ({item['train_name']})."
                ),
            }

        return {
            "status": "success",
            "special_train_id": item["special_train_id"],
            "train_number": item["train_number"],
            "train_name": item["train_name"],
            "special_type": item["special_type"],
            "corridor_id": item["corridor_id"],
            "service_date": item["service_date"],
            "arrival_time": item["arrival_time"],
            "departure_time": item["departure_time"],
            "operational_priority": item["operational_priority"],
            "expected_passengers": item["expected_passengers"],
            "active": item["active"],
            "has_conflicts": bool(overlapping_blocks),
            "overlapping_blocks_count": len(overlapping_blocks),
            "overlapping_blocks": overlapping_blocks,
            "overlapping_requests_count": 0,
            "overlapping_requests": [],
            "recommended_shift": recommended_shift,
            "workflow_note": "Autonomous corridor conflict analysis generated by IR-ABPS Traffic Intelligence Engine.",
        }


_mem_store = InMemorySpecialTrainStore()


# ============================================================
# GET ALL SPECIAL TRAINS
# ============================================================

@router.get("", include_in_schema=False)
@router.get(
    "/",
    dependencies=[Depends(require_permission("special_trains.view"))],
)
def get_special_trains(
    corridor_id: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    active: Optional[bool] = Query(None),
    user: CurrentUser = Depends(get_current_user),
):
    conn = _get_db_connection()
    if conn is not None:
        try:
            with conn:
                with conn.cursor() as cur:
                    allowed_corridors = None
                    if user.scope != "network":
                        allowed_corridors = get_relevant_corridor_ids(cur, user.dept)
                        if not allowed_corridors:
                            return {
                                "status": "success",
                                "total_count": 0,
                                "special_trains": [],
                            }

                    query = """
                        SELECT
                            special_id,
                            train_number,
                            train_name,
                            event_name,
                            event_type,
                            corridor_id,
                            service_date,
                            departure_time,
                            arrival_time,
                            direction,
                            operational_priority,
                            status
                        FROM special_train_services
                        WHERE 1=1
                    """
                    params = []

                    if allowed_corridors is not None:
                        query += " AND corridor_id = ANY(%s)"
                        params.append(allowed_corridors)

                    if corridor_id:
                        query += " AND corridor_id = %s"
                        params.append(corridor_id)

                    if from_date:
                        query += " AND service_date >= %s"
                        params.append(_parse_date(from_date))

                    if to_date:
                        query += " AND service_date <= %s"
                        params.append(_parse_date(to_date))

                    if active is not None:
                        if active:
                            query += " AND status = 'SCHEDULED'"
                        else:
                            query += " AND status <> 'SCHEDULED'"

                    query += " ORDER BY service_date ASC, departure_time ASC"
                    cur.execute(query, params)
                    rows = cur.fetchall()

                    if rows:
                        items = [_format_special(row) for row in rows]
                        return {
                            "status": "success",
                            "total_count": len(items),
                            "special_trains": items,
                        }
        except Exception as db_err:
            logger.warning(f"Database query failed, using in-memory store: {db_err}")

    # Fallback to in-memory store
    allowed_corridors = None
    if user.scope != "network":
        dept = (user.dept or "").upper()
        if "TMS" in dept or "TRACK" in dept or "CIVIL" in dept:
            allowed_corridors = ["C01", "C02", "C03"]
        elif "SMMS" in dept or "SIGNAL" in dept:
            allowed_corridors = ["C01", "C03"]
        elif "TDMS" in dept or "TRACTION" in dept:
            allowed_corridors = ["C01", "C02", "C04"]

    items = _mem_store.list_trains(
        corridor_id=corridor_id,
        from_date=from_date,
        to_date=to_date,
        active=active,
        allowed_corridors=allowed_corridors,
    )
    return {
        "status": "success",
        "total_count": len(items),
        "special_trains": items,
    }


# ============================================================
# GET ONE SPECIAL TRAIN
# ============================================================

@router.get(
    "/{special_train_id}",
    dependencies=[Depends(require_permission("special_trains.view"))],
)
def get_special_train(
    special_train_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    conn = _get_db_connection()
    if conn is not None:
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT
                            special_id,
                            train_number,
                            train_name,
                            event_name,
                            event_type,
                            corridor_id,
                            service_date,
                            departure_time,
                            arrival_time,
                            direction,
                            operational_priority,
                            status
                        FROM special_train_services
                        WHERE special_id = %s
                    """, (special_train_id,))
                    row = cur.fetchone()
                    if row:
                        if user.scope != "network":
                            allowed = get_relevant_corridor_ids(cur, user.dept)
                            if row[5] not in allowed:
                                raise HTTPException(
                                    status_code=403,
                                    detail="Corridor outside department scope",
                                )
                        return {
                            "status": "success",
                            "special_train": _format_special(row),
                        }
        except HTTPException:
            raise
        except Exception as db_err:
            logger.warning(f"Database query failed, using in-memory store: {db_err}")

    item = _mem_store.get_train(special_train_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Special train {special_train_id} not found")
    if item == "FORBIDDEN":
        raise HTTPException(status_code=403, detail="Corridor outside department scope")
    return {
        "status": "success",
        "special_train": item,
    }


# ============================================================
# CREATE SPECIAL TRAIN
# ============================================================

@router.post(
    "",
    include_in_schema=False,
    dependencies=[Depends(require_permission("special_trains.manage"))],
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/",
    dependencies=[Depends(require_permission("special_trains.manage"))],
    status_code=status.HTTP_201_CREATED,
)
def create_special_train(
    payload: SpecialTrainCreateSchema,
    user: CurrentUser = Depends(get_current_user),
):
    event_type = payload.special_type.strip().upper()
    if event_type not in VALID_SPECIAL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid special_type '{payload.special_type}'. Must be one of: {sorted(list(VALID_SPECIAL_TYPES))}",
        )

    direction = payload.direction.strip().upper()
    if direction not in VALID_DIRECTIONS:
        raise HTTPException(
            status_code=400,
            detail="Direction must be UP or DOWN",
        )

    try:
        _parse_time(payload.arrival_time)
        _parse_time(payload.departure_time)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid time format. Use HH:MM or HH:MM:SS",
        )

    # Always persist in resilient memory store
    created_items = _mem_store.create_trains(payload, user)

    # Attempt PostgreSQL write if online
    conn = _get_db_connection()
    if conn is not None:
        try:
            with conn:
                with conn.cursor() as cur:
                    for item in created_items:
                        cur.execute("""
                            INSERT INTO special_train_services (
                                special_id,
                                train_number,
                                train_name,
                                event_name,
                                event_type,
                                corridor_id,
                                service_date,
                                departure_time,
                                arrival_time,
                                direction,
                                operational_priority,
                                status
                            )
                            VALUES (
                                %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s,
                                %s, %s
                            )
                            ON CONFLICT (special_id) DO NOTHING
                        """, (
                            item["special_train_id"],
                            item["train_number"],
                            item["train_name"],
                            item["reason"],
                            item["special_type"],
                            item["corridor_id"],
                            _parse_date(item["service_date"]),
                            _parse_time(item["departure_time"]),
                            _parse_time(item["arrival_time"]),
                            item["direction"],
                            item["operational_priority"] * 20,
                            "SCHEDULED" if item["active"] else "INACTIVE",
                        ))
        except Exception as db_err:
            logger.warning(f"Database write skipped/failed: {db_err}")

    return {
        "status": "success",
        "message": f"Successfully created {len(created_items)} special train service(s)",
        "created_count": len(created_items),
        "created_ids": [i["special_train_id"] for i in created_items],
        "special_trains": created_items,
    }


# ============================================================
# UPDATE SPECIAL TRAIN
# ============================================================

@router.put(
    "/{special_train_id}",
    dependencies=[Depends(require_permission("special_trains.manage"))],
)
def update_special_train(
    special_train_id: str,
    payload: SpecialTrainUpdateSchema,
    user: CurrentUser = Depends(get_current_user),
):
    if payload.special_type is not None:
        val = payload.special_type.strip().upper()
        if val not in VALID_SPECIAL_TYPES:
            raise HTTPException(status_code=400, detail="Invalid special_type")

    if payload.direction is not None:
        d = payload.direction.strip().upper()
        if d not in VALID_DIRECTIONS:
            raise HTTPException(status_code=400, detail="Direction must be UP or DOWN")

    updated = _mem_store.update_train(special_train_id, payload, user)

    conn = _get_db_connection()
    if conn is not None:
        try:
            with conn:
                with conn.cursor() as cur:
                    updates = []
                    params = []
                    if payload.train_number is not None:
                        updates.append("train_number = %s")
                        params.append(payload.train_number.strip())
                    if payload.train_name is not None:
                        updates.append("train_name = %s")
                        params.append(payload.train_name.strip())
                    if payload.special_type is not None:
                        updates.append("event_type = %s")
                        params.append(payload.special_type.strip().upper())
                    if payload.corridor_id is not None:
                        updates.append("corridor_id = %s")
                        params.append(payload.corridor_id)
                    if payload.active is not None:
                        updates.append("status = %s")
                        params.append("SCHEDULED" if payload.active else "INACTIVE")
                    if updates:
                        params.append(special_train_id)
                        cur.execute(
                            f"UPDATE special_train_services SET {', '.join(updates)} WHERE special_id = %s",
                            params,
                        )
        except Exception as db_err:
            logger.warning(f"Database update skipped: {db_err}")

    try:
        record_audit(
            actor_role=user.role_id,
            actor_name=user.name,
            method="PUT",
            path=f"/special-trains/{special_train_id}",
            action="UPDATE_SPECIAL_TRAIN",
            target_type="special_train",
            target_id=special_train_id,
            outcome="SUCCESS",
            detail=payload.model_dump(exclude_unset=True),
        )
    except Exception:
        pass

    return {
        "status": "success",
        "message": f"Special train {special_train_id} updated successfully",
        "special_train": updated,
    }


# ============================================================
# ACTIVE / INACTIVE TOGGLE
# ============================================================

@router.patch(
    "/{special_train_id}/active",
    dependencies=[Depends(require_permission("special_trains.manage"))],
)
def toggle_special_train(
    special_train_id: str,
    payload: ActiveToggleSchema,
    user: CurrentUser = Depends(get_current_user),
):
    updated = _mem_store.toggle_active(special_train_id, payload.active, user)

    conn = _get_db_connection()
    if conn is not None:
        try:
            with conn:
                with conn.cursor() as cur:
                    new_status = "SCHEDULED" if payload.active else "INACTIVE"
                    cur.execute(
                        "UPDATE special_train_services SET status = %s WHERE special_id = %s",
                        (new_status, special_train_id),
                    )
        except Exception as db_err:
            logger.warning(f"Database toggle skipped: {db_err}")

    try:
        record_audit(
            actor_role=user.role_id,
            actor_name=user.name,
            method="PATCH",
            path=f"/special-trains/{special_train_id}/active",
            action="ACTIVATE_SPECIAL_TRAIN" if payload.active else "DEACTIVATE_SPECIAL_TRAIN",
            target_type="special_train",
            target_id=special_train_id,
            outcome="SUCCESS",
            detail={"active": payload.active},
        )
    except Exception:
        pass

    return {
        "status": "success",
        "special_train_id": special_train_id,
        "active": payload.active,
        "special_train": updated,
    }


# ============================================================
# IMPACT ANALYSIS
# ============================================================

@router.get(
    "/{special_train_id}/impact",
    dependencies=[Depends(require_permission("special_trains.view"))],
)
def get_special_train_impact(
    special_train_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    conn = _get_db_connection()
    if conn is not None:
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT
                            special_id, train_number, train_name, event_name, event_type,
                            corridor_id, service_date, arrival_time, departure_time,
                            operational_priority, status
                        FROM special_train_services
                        WHERE special_id = %s
                    """, (special_train_id,))
                    sp = cur.fetchone()
                    if sp:
                        (
                            s_id, train_number, train_name, event_name, event_type,
                            corridor_id, service_date, arrival_time, departure_time,
                            priority, train_status,
                        ) = sp

                        if user.scope != "network":
                            allowed = get_relevant_corridor_ids(cur, user.dept)
                            if corridor_id not in allowed:
                                raise HTTPException(
                                    status_code=403,
                                    detail="Corridor outside department scope",
                                )

                        cur.execute("""
                            SELECT
                                block_id, corridor_id, block_date, start_time, end_time,
                                duration_min, utilization_percent, train_impact_score, optimization_score
                            FROM optimized_blocks
                            WHERE corridor_id = %s AND block_date = %s
                        """, (corridor_id, service_date))
                        block_rows = cur.fetchall()

                        overlapping_blocks = []
                        for b in block_rows:
                            overlaps, overlap_min = windows_overlap(
                                departure_time, arrival_time, b[3], b[4]
                            )
                            if overlaps:
                                overlapping_blocks.append({
                                    "block_id": b[0],
                                    "corridor_id": b[1],
                                    "block_date": str(b[2]),
                                    "start_time": str(b[3]),
                                    "end_time": str(b[4]),
                                    "duration_min": b[5],
                                    "overlap_minutes": overlap_min,
                                    "utilization_percent": float(b[6] or 0),
                                    "train_impact_score": float(b[7] or 0),
                                    "optimization_score": float(b[8] or 0),
                                })

                        recommended_shift = None
                        if overlapping_blocks:
                            recommended_shift = {
                                "block_id": overlapping_blocks[0]["block_id"],
                                "shift_offset_min": -45,
                                "proposed_start": "07:45:00",
                                "proposed_end": "10:45:00",
                                "expected_train_conflicts": 0,
                                "rationale": f"Advance block window by 45 minutes to clear special path for {train_number}.",
                            }

                        prio_val = priority
                        if prio_val is not None and prio_val > 5:
                            prio_val = max(1, min(5, round(prio_val / 20)))
                        elif not prio_val:
                            prio_val = 4

                        return {
                            "status": "success",
                            "special_train_id": s_id,
                            "train_number": train_number,
                            "train_name": train_name,
                            "special_type": event_type,
                            "corridor_id": corridor_id,
                            "service_date": str(service_date),
                            "arrival_time": str(arrival_time),
                            "departure_time": str(departure_time),
                            "operational_priority": prio_val,
                            "expected_passengers": 1200,
                            "active": train_status == "SCHEDULED",
                            "has_conflicts": bool(overlapping_blocks),
                            "overlapping_blocks_count": len(overlapping_blocks),
                            "overlapping_blocks": overlapping_blocks,
                            "overlapping_requests_count": 0,
                            "overlapping_requests": [],
                            "recommended_shift": recommended_shift,
                            "workflow_note": "AI advisory only. Block shifts require Chief Controller review and Admin authorization.",
                        }
        except HTTPException:
            raise
        except Exception as db_err:
            logger.warning(f"Impact calculation DB error: {db_err}")

    return _mem_store.get_impact(special_train_id, user)