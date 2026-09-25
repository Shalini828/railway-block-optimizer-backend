import sys
import os

VERBOSE_OPTIMIZER_LOGS = os.getenv(
    "VERBOSE_OPTIMIZER_LOGS",
    "false"
).lower() == "true"


def optimizer_log(*args, **kwargs):
    if VERBOSE_OPTIMIZER_LOGS:
        print(*args, **kwargs)
from datetime import datetime, timedelta

sys.path.append(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)
import psycopg
from dotenv import load_dotenv
import psycopg
from db_config import DB_CONFIG
from logic.traffic_intelligence import evaluate_window

from ml.predict_service import predict_asset_risk
from ml.traffic_predict_service import predict_traffic_impact
from ml.goods_forecast_service import predict_goods_train_demand

load_dotenv()
# ==========================================
# SETTINGS
# ==========================================

MAX_BLOCK_DURATION = 240       # 4 hours
MAX_CONSOLIDATION_GAP = 15     # 15 minutes

# ==========================================
# AI OPTIMIZATION WEIGHTS
# ==========================================

WEIGHT_MAINTENANCE_PRIORITY = 0.25
WEIGHT_ASSET_RISK = 0.20
WEIGHT_UTILIZATION = 0.20
WEIGHT_TRAFFIC = 0.15
WEIGHT_GOODS = 0.10
WEIGHT_CONSOLIDATION = 0.10


# ==========================================
# DATABASE CONNECTION
# ==========================================

connection = psycopg.connect(**DB_CONFIG)
cursor = connection.cursor()


# ==========================================
# DEVELOPMENT RESET DISABLED: importing the optimizer must not mutate the database.

# GET BLOCK REQUESTS + PRIORITY
# ==========================================

cursor.execute("""
    SELECT
        br.request_id,
        br.task_id,
        br.team_id,
        br.corridor_id,
        br.requested_date,
        br.requested_start,
        br.requested_end,
        br.requested_duration_min,
        COALESCE(mt.priority_score, 0)
    FROM block_requests br

    LEFT JOIN maintenance_tasks mt
        ON br.task_id = mt.task_id

    WHERE br.request_status = 'PENDING'

    ORDER BY
        br.corridor_id,
        br.requested_date,
        mt.priority_score DESC,
        br.requested_start
""")

requests = cursor.fetchall()


# ==========================================
# GET BLOCK REQUESTS + PRIORITY
# ==========================================

cursor.execute("""
    SELECT
        br.request_id,
        br.task_id,
        br.team_id,
        br.corridor_id,
        br.requested_date,
        br.requested_start,
        br.requested_end,
        br.requested_duration_min,
        COALESCE(mt.priority_score, 0)
    FROM block_requests br

    LEFT JOIN maintenance_tasks mt
        ON br.task_id = mt.task_id

    WHERE br.request_status = 'PENDING'

    ORDER BY
        br.corridor_id,
        br.requested_date,
        mt.priority_score DESC,
        br.requested_start
""")

requests = cursor.fetchall()

# ==========================================
# DEBUG REQUEST STATUS
# ==========================================

cursor.execute("""
    SELECT request_status, COUNT(*)
    FROM block_requests
    GROUP BY request_status
    ORDER BY request_status
""")

request_status_counts = cursor.fetchall()

optimizer_log()
optimizer_log("REQUEST STATUS COUNTS:")
optimizer_log("--------------------------------")

for status, count in request_status_counts:
    optimizer_log(f"{status}: {count}")

optimizer_log("--------------------------------")
optimizer_log()


# ==========================================
# GET TRAINS
# ==========================================

cursor.execute("""
    SELECT
        train_id,
        train_number,
        train_name,
        train_type,
        corridor_id,
        travel_date,
        arrival_time,
        departure_time
    FROM trains
""")

trains = cursor.fetchall()


# ==========================================
# TIME FUNCTIONS
# ==========================================

def time_to_minutes(t):
    """
    Convert either a datetime.time object or a HH:MM string
    into minutes from midnight.
    """

    if isinstance(t, str):
        parts = t.split(":")

        hour = int(parts[0])
        minute = int(parts[1])

        return hour * 60 + minute

    return t.hour * 60 + t.minute

def minutes_to_time(minutes):

    minutes = minutes % (24 * 60)

    hour = minutes // 60
    minute = minutes % 60

    return f"{hour:02d}:{minute:02d}:00"



# ==========================================
# AI SCORING HELPERS
# ==========================================

def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def calculate_asset_risk_for_task(task_id):
    """
    Calculate AI asset risk for a maintenance task.
    """

    cursor.execute("""
        SELECT
            mt.asset_id,
            a.asset_id,
            a.criticality,
            a.health_score,
            a.failure_risk,
            a.installation_date,
            a.last_inspection_date
        FROM maintenance_tasks mt
        LEFT JOIN assets a
            ON mt.asset_id = a.asset_id
        WHERE mt.task_id = %s
    """, (task_id,))

    row = cursor.fetchone()

    if not row or not row[1]:
        return 0.0

    asset = {
        "asset_id": row[1],
        "criticality": row[2] or 3,
        "health_score": row[3] or 70,
        "failure_risk": row[4] or 30,
        "installation_date": row[5],
        "last_inspection_date": row[6],
    }

    cursor.execute("""
        SELECT
            severity,
            safety_impact,
            repeat_failure
        FROM defects
        WHERE asset_id = %s
    """, (row[1],))

    defect_rows = cursor.fetchall()

    defects = [
        {
            "severity": d[0],
            "safety_impact": d[1],
            "repeat_failure": d[2],
        }
        for d in defect_rows
    ]

    cursor.execute("""
        SELECT
            maintenance_type,
            failure_after_maintenance
        FROM maintenance_history
        WHERE asset_id = %s
    """, (row[1],))

    history_rows = cursor.fetchall()

    maintenance_history = [
        {
            "maintenance_type": h[0],
            "failure_after_maintenance": h[1],
        }
        for h in history_rows
    ]

    prediction = predict_asset_risk(
        asset=asset,
        defects=defects,
        maintenance_history=maintenance_history,
    )

    return safe_float(
        prediction.get("risk_score"),
        0.0
    )


def calculate_goods_impact(
    corridor_id,
    block_date,
    start_hour,
):
    """
    Get predicted goods traffic for this corridor/time.
    """

    previous_day_demand = 20.0

    cursor.execute("""
        SELECT expected_goods_trains
        FROM goods_train_forecast
        WHERE corridor_id = %s
          AND forecast_date < %s
        ORDER BY forecast_date DESC, forecast_id DESC
        LIMIT 1
    """, (
        corridor_id,
        block_date,
    ))

    previous_row = cursor.fetchone()

    if previous_row:
        previous_day_demand = safe_float(
            previous_row[0],
            20.0
        )

    cursor.execute("""
        SELECT traffic_level
        FROM corridors
        WHERE corridor_id = %s
    """, (corridor_id,))

    traffic_row = cursor.fetchone()

    traffic_level = (
        str(traffic_row[0]).upper()
        if traffic_row and traffic_row[0]
        else "MEDIUM"
    )

    traffic_pressure = {
        "LOW": 25,
        "MEDIUM": 50,
        "HIGH": 75,
        "VERY HIGH": 90,
        "CRITICAL": 100,
    }

    operational_pressure = traffic_pressure.get(
        traffic_level,
        50
    )

    industrial_demand = min(
        100,
        operational_pressure + 10
    )

    result = predict_goods_train_demand(
        day_of_week=block_date.weekday(),
        month=block_date.month,
        is_weekend=int(block_date.weekday() >= 5),
        festival_period=int(
            block_date.month in [9, 10, 11]
        ),
        operational_pressure=operational_pressure,
        industrial_demand=industrial_demand,
        previous_day_demand=previous_day_demand,
        corridor_id=corridor_id,
        commodity="COAL",
    )

    predicted_goods = safe_float(
        result.get("predicted_goods_train_demand"),
        0.0
    )

    return min(
        100,
        round(
            (predicted_goods / 60) * 100,
            2
        )
    )



# ==========================================
# AI 7-DAY PLANNING INTELLIGENCE
# ==========================================

def generate_7_day_planning(
    corridor_id,
    start_date,
):
    """
    Generate AI planning intelligence for the next 7 days.

    This is decision-support only.
    It does not modify optimized blocks.
    """

    planning_days = []

    for day_offset in range(7):

        planning_date = (
            start_date
            + timedelta(days=day_offset)
        )

        # --------------------------------------
        # Goods demand
        # --------------------------------------

        try:

            goods_impact = calculate_goods_impact(
                corridor_id=corridor_id,
                block_date=planning_date,
                start_hour=12,
            )

        except Exception as exc:

            optimizer_log(
                "7-DAY GOODS FORECAST ERROR:",
                corridor_id,
                planning_date,
                exc
            )

            goods_impact = 0.0

        # --------------------------------------
        # Corridor traffic pressure
        # --------------------------------------

        cursor.execute("""
            SELECT traffic_level
            FROM corridors
            WHERE corridor_id = %s
        """, (corridor_id,))

        traffic_row = cursor.fetchone()

        traffic_level = (
            str(traffic_row[0]).upper()
            if traffic_row and traffic_row[0]
            else "MEDIUM"
        )

        traffic_pressure_map = {
            "LOW": 25,
            "MEDIUM": 50,
            "HIGH": 75,
            "VERY HIGH": 90,
            "CRITICAL": 100,
        }

        traffic_pressure = traffic_pressure_map.get(
            traffic_level,
            50
        )

        # --------------------------------------
        # Maintenance demand
        # --------------------------------------

        cursor.execute("""
            SELECT
                COUNT(*)
            FROM block_requests
            WHERE corridor_id = %s
            AND requested_date = %s
            AND request_status = 'PENDING'
        """, (
            corridor_id,
            planning_date,
        ))

        maintenance_row = cursor.fetchone()

        maintenance_count = (
            int(maintenance_row[0])
            if maintenance_row
            else 0
        )

        maintenance_pressure = min(
            100,
            maintenance_count * 20
        )

        # --------------------------------------
        # Planning pressure
        # --------------------------------------

        planning_pressure = round(
            (
                traffic_pressure * 0.40
                +
                goods_impact * 0.30
                +
                maintenance_pressure * 0.30
            ),
            2
        )

        # Lower pressure = more suitable
        # for scheduling maintenance.

        if planning_pressure >= 75:

            planning_level = "HIGH"

        elif planning_pressure >= 50:

            planning_level = "MEDIUM"

        else:

            planning_level = "LOW"

        planning_days.append(
            {
                "date": str(planning_date),
                "day_of_week": planning_date.strftime(
                    "%A"
                ),
                "corridor": corridor_id,
                "traffic_pressure": round(
                    traffic_pressure,
                    2
                ),
                "goods_impact": round(
                    goods_impact,
                    2
                ),
                "maintenance_count": (
                    maintenance_count
                ),
                "maintenance_pressure": round(
                    maintenance_pressure,
                    2
                ),
                "planning_pressure": (
                    planning_pressure
                ),
                "planning_level": (
                    planning_level
                ),
            }
        )

    # --------------------------------------
    # Rank days
    # --------------------------------------

    planning_days.sort(
        key=lambda item: (
            item["planning_pressure"],
            item["goods_impact"],
            item["traffic_pressure"],
        )
    )

    return {
        "corridor": corridor_id,
        "start_date": str(start_date),
        "days": planning_days,
        "recommended_day": (
            planning_days[0]
            if planning_days
            else None
        ),
    }


# ==========================================
# AI 30-DAY MAINTENANCE INTELLIGENCE
# ==========================================

def generate_30_day_maintenance_intelligence(
    start_date,
    corridor_id=None
):
    """
    Rank pending maintenance tasks over a 30-day planning horizon.

    Uses existing:
    - Asset Risk ML
    - Traffic pressure
    - Goods demand
    - Maintenance priority

    This is planning intelligence.
    It does not modify the optimization schedule.
    """

    end_date = (
        start_date
        + timedelta(days=29)
    )

    # --------------------------------------
    # Get pending maintenance requests
    # --------------------------------------

    if corridor_id:

        cursor.execute("""
            SELECT
                br.request_id,
                br.task_id,
                br.corridor_id,
                br.requested_date,
                COALESCE(
                    mt.priority_score,
                    0
                )
            FROM block_requests br
            LEFT JOIN maintenance_tasks mt
                ON br.task_id = mt.task_id
            WHERE br.request_status IN ('PENDING', 'OPTIMIZED')
                AND br.requested_date
                    BETWEEN %s AND %s
              AND br.corridor_id = %s
            ORDER BY
                mt.priority_score DESC,
                br.requested_date
        """, (
            start_date,
            end_date,
            corridor_id,
        ))

    else:

        cursor.execute("""
            SELECT
                br.request_id,
                br.task_id,
                br.corridor_id,
                br.requested_date,
                COALESCE(
                    mt.priority_score,
                    0
                )
            FROM block_requests br
            LEFT JOIN maintenance_tasks mt
                ON br.task_id = mt.task_id
            WHERE br.request_status IN ('PENDING', 'OPTIMIZED')
              AND br.requested_date
                  BETWEEN %s AND %s
            ORDER BY
                mt.priority_score DESC,
                br.requested_date
        """, (
            start_date,
            end_date,
        ))

    rows = cursor.fetchall()

    task_intelligence = []

    # --------------------------------------
    # Analyze every maintenance request
    # --------------------------------------

    for row in rows:

        request_id = row[0]
        task_id = row[1]
        corridor = row[2]
        requested_date = row[3]
        maintenance_priority = safe_float(
            row[4],
            0.0
        )

        # ----------------------------------
        # Asset Risk ML
        # ----------------------------------

        try:

            asset_risk = calculate_asset_risk_for_task(
                task_id
            )

        except Exception as exc:

            optimizer_log(
                "30-DAY ASSET RISK ERROR:",
                task_id,
                exc
            )

            asset_risk = 0.0

        # ----------------------------------
        # Traffic pressure
        # ----------------------------------

        cursor.execute("""
            SELECT traffic_level
            FROM corridors
            WHERE corridor_id = %s
        """, (corridor,))

        traffic_row = cursor.fetchone()

        traffic_level = (
            str(
                traffic_row[0]
            ).upper()
            if traffic_row
            and traffic_row[0]
            else "MEDIUM"
        )

        traffic_pressure_map = {
            "LOW": 25,
            "MEDIUM": 50,
            "HIGH": 75,
            "VERY HIGH": 90,
            "CRITICAL": 100,
        }

        traffic_pressure = (
            traffic_pressure_map.get(
                traffic_level,
                50
            )
        )

        # ----------------------------------
        # Goods demand
        # ----------------------------------

        try:

            goods_impact = calculate_goods_impact(
                corridor_id=corridor,
                block_date=requested_date,
                start_hour=12,
            )

        except Exception as exc:

            optimizer_log(
                "30-DAY GOODS ERROR:",
                corridor,
                requested_date,
                exc
            )

            goods_impact = 0.0

        # ----------------------------------
        # Maintenance urgency
        # ----------------------------------

        urgency_score = min(
            100.0,
            (
                asset_risk * 0.40
                +
                maintenance_priority * 0.30
                +
                goods_impact * 0.15
                +
                traffic_pressure * 0.15
            )
        )

        urgency_score = round(
            urgency_score,
            2
        )

        # ----------------------------------
        # Maintenance level
        # ----------------------------------

        if urgency_score >= 75:

            urgency_level = "CRITICAL"

        elif urgency_score >= 60:

            urgency_level = "HIGH"

        elif urgency_score >= 35:

            urgency_level = "MEDIUM"

        else:

            urgency_level = "LOW"

        task_intelligence.append(
            {
                "request_id": request_id,
                "task_id": task_id,
                "corridor": corridor,
                "requested_date": str(
                    requested_date
                ),

                "asset_risk": round(
                    asset_risk,
                    2
                ),

                "maintenance_priority": round(
                    maintenance_priority,
                    2
                ),

                "traffic_pressure": round(
                    traffic_pressure,
                    2
                ),

                "goods_impact": round(
                    goods_impact,
                    2
                ),

                "maintenance_urgency": (
                    urgency_score
                ),

                "urgency_level": (
                    urgency_level
                ),
            }
        )

    # --------------------------------------
    # Rank highest urgency first
    # --------------------------------------

    task_intelligence.sort(
        key=lambda item: (
            item["maintenance_urgency"],
            item["asset_risk"],
            item["maintenance_priority"],
        ),
        reverse=True
    )

    # --------------------------------------
    # Summary
    # --------------------------------------

    critical_count = sum(
        1
        for item in task_intelligence
        if item["urgency_level"]
        == "CRITICAL"
    )

    high_count = sum(
        1
        for item in task_intelligence
        if item["urgency_level"]
        == "HIGH"
    )

    return {
        "start_date": str(start_date),
        "end_date": str(end_date),
        "corridor": corridor_id,

        "total_tasks": len(
            task_intelligence
        ),

        "critical_tasks": critical_count,
        "high_priority_tasks": high_count,

        "tasks": task_intelligence,

        "highest_priority_task": (
            task_intelligence[0]
            if task_intelligence
            else None
        ),
    }

def calculate_traffic_impact(
    duration,
    start_hour,
    passenger_trains,
    goods_trains,
    special_trains,
    express_trains,
    corridor_congestion,
    criticality,
    maintenance_priority,
):
    """
    Existing traffic ML model.
    """

    result = predict_traffic_impact(
        block_duration_min=int(duration),
        start_hour=int(start_hour),
        passenger_trains=int(passenger_trains),
        goods_trains=int(goods_trains),
        special_trains=int(special_trains),
        express_trains=int(express_trains),
        corridor_congestion=float(
            corridor_congestion
        ),
        criticality=int(criticality),
        maintenance_priority=float(
            maintenance_priority
        ),
    )

    return result


# ==========================================
# TRAIN CONFLICT DETECTION
# ==========================================

def get_train_conflicts(
    corridor,
    block_date,
    start_time,
    end_time,
    cur=None
):
    if cur is not None:
        assessment = evaluate_window(cur, corridor, block_date, start_time, end_time)
        return assessment.get("conflicts", [])
    assessment = evaluate_window(cursor, corridor, block_date, start_time, end_time)
    return assessment.get("conflicts", [])


# ==========================================
# CANDIDATE WINDOW GENERATOR
# ==========================================

def generate_candidate_windows(
    requested_start,
    requested_end,
    step_minutes=30,
    search_before_minutes=120,
    search_after_minutes=120
):
    """
    Generate alternative maintenance windows around
    the originally requested window.

    Example:
        Requested: 09:00 - 12:00

    Candidates:
        07:00 - 10:00
        07:30 - 10:30
        08:00 - 11:00
        ...
        11:00 - 14:00
        11:30 - 14:30
        12:00 - 15:00
    """

    start_minutes = time_to_minutes(
        requested_start
    )

    end_minutes = time_to_minutes(
        requested_end
    )

    duration = end_minutes - start_minutes

    if duration <= 0:
        duration += 24 * 60

    candidates = []

    search_start = (
        start_minutes
        - search_before_minutes
    )

    search_end = (
        start_minutes
        + search_after_minutes
    )

    current_start = search_start

    while current_start <= search_end:

        current_end = (
            current_start + duration
        )

        # Don't create windows longer than
        # the maximum allowed block duration.
        if duration <= MAX_BLOCK_DURATION:

            candidates.append(
                {
                    "start": minutes_to_time(
                        current_start
                    ),
                    "end": minutes_to_time(
                        current_end
                    ),
                    "duration": duration,
                }
            )

        current_start += step_minutes

    return candidates

# ==========================================
# AI WHAT-IF WINDOW SIMULATION
# ==========================================

def simulate_what_if_windows(
    corridor,
    block_date,
    group,
    maintenance_priority,
    alternative_offsets=None
):
    """
    Simulate alternative maintenance windows for an
    existing maintenance group.

    This is decision-support only.
    It does NOT modify the optimized schedule.
    """

    if alternative_offsets is None:
        alternative_offsets = [
            -120,
            -60,
            60,
            120
        ]

    original_start = time_to_minutes(
        group["start"]
    )

    original_end = time_to_minutes(
        group["end"]
    )

    duration = (
        original_end
        - original_start
    )

    if duration <= 0:
        return {
            "corridor": corridor,
            "date": str(block_date),
            "current_window": None,
            "alternatives": [],
            "best_alternative": None
        }

    # --------------------------------------
    # Current window
    # --------------------------------------

    current_candidate = {
        "start": group["start"],
        "end": group["end"],
        "duration": duration
    }

    try:

        current_utilization = 100.0

        current_result = score_candidate_window(
            corridor=corridor,
            block_date=block_date,
            candidate=current_candidate,
            group=group,
            maintenance_priority=maintenance_priority,
            utilization=current_utilization
        )

    except Exception as exc:

        optimizer_log(
            "WHAT-IF CURRENT WINDOW ERROR:",
            exc
        )

        current_result = None

    alternatives = []

    # --------------------------------------
    # Generate alternative windows
    # --------------------------------------

    for offset in alternative_offsets:

        alternative_start = (
            original_start
            + offset
        )

        # Keep the window inside one day
        if alternative_start < 0:
            continue

        if alternative_start + duration > 1440:
            continue

        alternative_end = (
            alternative_start
            + duration
        )

        start_hour = (
            alternative_start // 60
        )

        start_minute = (
            alternative_start % 60
        )

        end_hour = (
            alternative_end // 60
        )

        end_minute = (
            alternative_end % 60
        )

        candidate_start = (
            f"{start_hour:02d}:"
            f"{start_minute:02d}:00"
        )

        candidate_end = (
            f"{end_hour:02d}:"
            f"{end_minute:02d}:00"
        )

        candidate = {
            "start": candidate_start,
            "end": candidate_end,
            "duration": duration
        }

        # ----------------------------------
        # Score alternative
        # ----------------------------------

        try:

            result = score_candidate_window(
                corridor=corridor,
                block_date=block_date,
                candidate=candidate,
                group=group,
                maintenance_priority=maintenance_priority,
                utilization=100.0
            )

        except Exception as exc:

            optimizer_log(
                "WHAT-IF CANDIDATE ERROR:",
                candidate_start,
                candidate_end,
                exc
            )

            continue

        # Don't duplicate current window
        if (
            current_result
            and
            result["start"] == current_result["start"]
        ):
            continue

        alternatives.append(
            {
                "start": str(
                    result["start"]
                )[:8],

                "end": str(
                    result["end"]
                )[:8],

                "duration": result["duration"],

                "score": result["score"],

                "asset_risk": result[
                    "asset_risk"
                ],

                "traffic_impact": result[
                    "traffic_impact"
                ],

                "goods_impact": result[
                    "goods_impact"
                ],

                "conflict_count": result[
                    "conflict_count"
                ],

                "utilization": result[
                    "utilization"
                ]
            }
        )

    # --------------------------------------
    # Rank alternatives
    # --------------------------------------

    alternatives.sort(
        key=lambda item: (
            item["score"],
            -item["conflict_count"]
        ),
        reverse=True
    )

    best_alternative = (
        alternatives[0]
        if alternatives
        else None
    )

    # --------------------------------------
    # Build response
    # --------------------------------------

    current_window = None

    if current_result:

        current_window = {
            "start": str(
                current_result["start"]
            )[:8],

            "end": str(
                current_result["end"]
            )[:8],

            "duration": current_result[
                "duration"
            ],

            "score": current_result[
                "score"
            ],

            "asset_risk": current_result[
                "asset_risk"
            ],

            "traffic_impact": current_result[
                "traffic_impact"
            ],

            "goods_impact": current_result[
                "goods_impact"
            ],

            "conflict_count": current_result[
                "conflict_count"
            ],

            "utilization": current_result[
                "utilization"
            ]
        }

    score_difference = 0

    if (
        current_window
        and best_alternative
    ):
        score_difference = round(
            best_alternative["score"]
            - current_window["score"],
            2
        )

    return {
        "corridor": corridor,
        "date": str(block_date),

        "current_window":
            current_window,

        "alternatives":
            alternatives,

        "best_alternative":
            best_alternative,

        "best_score_difference":
            score_difference
    }


# ============================================================
# AI EMERGENCY / URGENT BLOCK OPTIMIZATION
# ============================================================

def optimize_emergency_block(
    task_id,
    corridor_id,
    block_date,
    requested_start,
    requested_end,
):
    """
    Find the safest available maintenance window for an
    emergency / urgent maintenance task.

    Uses:
        - Asset risk
        - Maintenance priority
        - Traffic impact
        - Goods demand
        - Train conflicts
    """

    # --------------------------------------------------------
    # Get task priority / asset risk
    # --------------------------------------------------------

    try:
        asset_risk = calculate_asset_risk_for_task(task_id)
    except Exception as exc:
        optimizer_log("EMERGENCY ASSET RISK ERROR:", exc)
        asset_risk = 0.0

    cursor.execute(
        """
        SELECT COALESCE(priority_score, 0)
        FROM maintenance_tasks
        WHERE task_id = %s
        """,
        (task_id,)
    )

    priority_row = cursor.fetchone()

    maintenance_priority = (
        safe_float(priority_row[0], 0.0)
        if priority_row
        else 0.0
    )

    # Emergency tasks receive urgency emphasis.
    emergency_priority = max(
        maintenance_priority,
        asset_risk
    )

    # --------------------------------------------------------
    # Convert requested window to minutes
    # --------------------------------------------------------

    requested_start_min = time_to_minutes(requested_start)
    requested_end_min = time_to_minutes(requested_end)

    duration = max(
        1,
        requested_end_min - requested_start_min
    )

    # --------------------------------------------------------
    # Generate candidate windows
    # --------------------------------------------------------

    candidates = []

    candidate_starts = set()

    # Requested start
    candidate_starts.add(requested_start_min)

    # Search around requested window
    for offset in range(
        -180,
        181,
        30
    ):
        candidate_start = requested_start_min + offset

        if candidate_start < 0:
            continue

        if candidate_start + duration > 24 * 60:
            continue

        candidate_starts.add(candidate_start)

    # --------------------------------------------------------
    # Evaluate every candidate
    # --------------------------------------------------------

    for candidate_start_min in sorted(candidate_starts):

        candidate_end_min = (
            candidate_start_min + duration
        )

        candidate_start = minutes_to_time(
            candidate_start_min
        )

        candidate_end = minutes_to_time(
            candidate_end_min
        )

        conflicts = get_train_conflicts(
            corridor_id,
            block_date,
            candidate_start,
            candidate_end
        )

        conflict_count = len(conflicts)

        # ----------------------------------------------------
        # Traffic ML
        # ----------------------------------------------------

        passenger_trains = 0
        goods_trains = 0
        special_trains = 0
        express_trains = 0

        for train in conflicts:

            train_type = str(
                train.get("train_type", "")
            ).upper()

            if train_type == "EXPRESS":
                express_trains += 1
                passenger_trains += 1

            elif train_type in (
                "PASSENGER",
                "MAIL",
                "SUPERFAST"
            ):
                passenger_trains += 1

            elif train_type in (
                "FREIGHT",
                "GOODS"
            ):
                goods_trains += 1

            elif train_type in (
                "SPECIAL",
                "FESTIVAL"
            ):
                special_trains += 1

            else:
                passenger_trains += 1

        try:
            traffic_prediction = predict_traffic_impact(
                block_duration_min=int(duration),
                start_hour=int(
                    candidate_start_min // 60
                ),
                passenger_trains=passenger_trains,
                goods_trains=goods_trains,
                special_trains=special_trains,
                express_trains=express_trains,
                corridor_congestion=50,
                criticality=3,
                maintenance_priority=float(
                    maintenance_priority
                )
            )

            traffic_impact = safe_float(
                traffic_prediction.get(
                    "traffic_impact_score",
                    traffic_prediction.get(
                        "impact_score",
                        0
                    )
                ),
                0
            )

        except Exception as exc:

            optimizer_log(
                "EMERGENCY TRAFFIC ML ERROR:",
                exc
            )

            traffic_impact = 0.0

        # ----------------------------------------------------
        # Goods ML
        # ----------------------------------------------------

        try:

            goods_impact = calculate_goods_impact(
                corridor_id=corridor_id,
                block_date=block_date,
                start_hour=int(
                    candidate_start_min // 60
                )
            )

        except Exception as exc:

            optimizer_log(
                "EMERGENCY GOODS ML ERROR:",
                exc
            )

            goods_impact = 0.0

        # ----------------------------------------------------
        # Emergency score
        # ----------------------------------------------------

        conflict_penalty = min(
            100,
            conflict_count * 25
        )

        emergency_score = (
            emergency_priority * 0.40
            +
            asset_risk * 0.25
            +
            (100 - traffic_impact) * 0.20
            +
            (100 - goods_impact) * 0.15
            -
            conflict_penalty
        )

        candidates.append(
            {
                "start": str(candidate_start),
                "end": str(candidate_end),
                "duration": duration,
                "emergency_score": round(
                    emergency_score,
                    2
                ),
                "asset_risk": round(
                    asset_risk,
                    2
                ),
                "maintenance_priority": round(
                    maintenance_priority,
                    2
                ),
                "traffic_impact": round(
                    traffic_impact,
                    2
                ),
                "goods_impact": round(
                    goods_impact,
                    2
                ),
                "conflict_count": conflict_count,
                "passenger_trains": passenger_trains,
                "goods_trains": goods_trains,
                "special_trains": special_trains,
                "express_trains": express_trains,
            }
        )

    # --------------------------------------------------------
    # Select best emergency window
    # --------------------------------------------------------

    candidates.sort(
        key=lambda x: x["emergency_score"],
        reverse=True
    )

    best_window = (
        candidates[0]
        if candidates
        else None
    )

    return {
        "task_id": task_id,
        "corridor_id": corridor_id,
        "block_date": str(block_date),
        "emergency": True,
        "requested_window": {
            "start": str(requested_start),
            "end": str(requested_end),
            "duration": duration,
        },
        "best_window": best_window,
        "alternatives": candidates[1:4],
        "candidates_evaluated": len(
            candidates
        ),
    }

# ==========================================
# AI CANDIDATE WINDOW SCORING
# ==========================================

def score_candidate_window(
    corridor,
    block_date,
    candidate,
    group,
    maintenance_priority,
    utilization
):
    """
    Evaluate one candidate maintenance window
    using the existing AI/ML services.
    """

    candidate_start = candidate["start"]
    candidate_end = candidate["end"]
    duration = candidate["duration"]

    # --------------------------------------
    # Train conflicts
    # --------------------------------------

    conflicts = get_train_conflicts(
        corridor,
        block_date,
        candidate_start,
        candidate_end
    )

    passenger_trains = 0
    goods_trains = 0
    special_trains = 0
    express_trains = 0

    for train in conflicts:

        train_type = str(
            train.get("train_type", "")
        ).upper()

        if train_type == "EXPRESS":

            express_trains += 1
            passenger_trains += 1

        elif train_type in (
            "PASSENGER",
            "MAIL",
            "SUPERFAST"
        ):

            passenger_trains += 1

        elif train_type in (
            "FREIGHT",
            "GOODS"
        ):

            goods_trains += 1

        elif train_type in (
            "SPECIAL",
            "FESTIVAL"
        ):

            special_trains += 1

        else:

            passenger_trains += 1

    # --------------------------------------
    # Asset risk
    # --------------------------------------

    asset_risks = []

    for request in group["requests"]:

        task_id = request[1]

        try:

            risk = calculate_asset_risk_for_task(
                task_id
            )

            asset_risks.append(risk)

        except Exception as exc:

            optimizer_log(
                "CANDIDATE ASSET RISK ERROR:",
                task_id,
                exc
            )

    asset_risk_score = (
        max(asset_risks)
        if asset_risks
        else 0
    )

    # --------------------------------------
    # Corridor traffic
    # --------------------------------------

    cursor.execute("""
        SELECT traffic_level
        FROM corridors
        WHERE corridor_id = %s
    """, (corridor,))

    corridor_row = cursor.fetchone()

    traffic_level = (
        str(corridor_row[0]).upper()
        if corridor_row and corridor_row[0]
        else "MEDIUM"
    )

    traffic_map = {
        "LOW": 25,
        "MEDIUM": 50,
        "HIGH": 75,
        "VERY HIGH": 90,
        "CRITICAL": 100
    }

    corridor_congestion = traffic_map.get(
        traffic_level,
        50
    )

    # --------------------------------------
    # Traffic ML
    # --------------------------------------

    try:

        traffic_prediction = predict_traffic_impact(
            block_duration_min=int(duration),
            start_hour=int(
                str(candidate_start)[:2]
            ),
            passenger_trains=passenger_trains,
            goods_trains=goods_trains,
            special_trains=special_trains,
            express_trains=express_trains,
            corridor_congestion=corridor_congestion,
            criticality=3,
            maintenance_priority=float(
                maintenance_priority
            )
        )

        traffic_impact = safe_float(
            traffic_prediction.get(
                "traffic_impact_score",
                traffic_prediction.get(
                    "impact_score",
                    0
                )
            ),
            0
        )

    except Exception as exc:

        optimizer_log(
            "CANDIDATE TRAFFIC ML ERROR:",
            exc
        )

        traffic_impact = 0

    # --------------------------------------
    # Goods ML
    # --------------------------------------

    try:

        goods_impact = calculate_goods_impact(
            corridor_id=corridor,
            block_date=block_date,
            start_hour=int(
                str(candidate_start)[:2]
            )
        )

    except Exception as exc:

        optimizer_log(
            "CANDIDATE GOODS ML ERROR:",
            exc
        )

        goods_impact = 0

    # --------------------------------------
    # Conflict penalty
    # --------------------------------------

    conflict_penalty = min(
        100,
        len(conflicts) * 20
    )

    # --------------------------------------
    # Consolidation
    # --------------------------------------

    number_of_tasks = len(
        group["requests"]
    )

    consolidation_score = min(
        100,
        number_of_tasks * 25
    )

    # --------------------------------------
    # Final candidate score
    # --------------------------------------

    candidate_score = (
        maintenance_priority
        * WEIGHT_MAINTENANCE_PRIORITY

        +

        asset_risk_score
        * WEIGHT_ASSET_RISK

        +

        utilization
        * WEIGHT_UTILIZATION

        +

        (100 - traffic_impact)
        * WEIGHT_TRAFFIC

        +

        (100 - goods_impact)
        * WEIGHT_GOODS

        +

        consolidation_score
        * WEIGHT_CONSOLIDATION

        -

        conflict_penalty
    )

    candidate_score = round(
        max(
            0,
            min(
                candidate_score,
                100
            )
        ),
        2
    )

    return {
        "start": candidate_start,
        "end": candidate_end,
        "duration": duration,

        "score": candidate_score,

        "asset_risk": round(
            asset_risk_score,
            2
        ),

        "traffic_impact": round(
            traffic_impact,
            2
        ),

        "goods_impact": round(
            goods_impact,
            2
        ),

        "conflicts": conflicts,

        "conflict_count": len(
            conflicts
        ),

        "utilization": utilization,

        "consolidation_score":
            consolidation_score
    }


# ==========================================
# GROUP COMPATIBLE REQUESTS
# ==========================================

groups = []

for request in requests:

    (
        request_id,
        task_id,
        team_id,
        corridor_id,
        request_date,
        request_start,
        request_end,
        duration,
        priority
    ) = request


    start = time_to_minutes(request_start)
    end = time_to_minutes(request_end)


    placed = False


    for group in groups:

        # Same corridor
        if group["corridor"] != corridor_id:
            continue

        # Same date
        if group["date"] != request_date:
            continue


        group_start = time_to_minutes(
            group["start"]
        )

        group_end = time_to_minutes(
            group["end"]
        )


        # Distance between request and group

        if start > group_end:

            gap = start - group_end

        elif group_start > end:

            gap = group_start - end

        else:

            gap = 0


        # New combined window

        combined_start = min(
            group_start,
            start
        )

        combined_end = max(
            group_end,
            end
        )


        combined_duration = (
            combined_end - combined_start
        )


        # ----------------------------------
        # CONSOLIDATION CONDITIONS
        # ----------------------------------

        if (
            gap <= MAX_CONSOLIDATION_GAP
            and combined_duration <= MAX_BLOCK_DURATION
        ):

            group["start"] = min(
                group["start"],
                request_start
            )

            group["end"] = max(
                group["end"],
                request_end
            )

            group["requests"].append(request)

            placed = True

            break


    # --------------------------------------
    # CREATE NEW GROUP
    # --------------------------------------

    if not placed:

        groups.append(
            {
                "corridor": corridor_id,
                "date": request_date,
                "start": request_start,
                "end": request_end,
                "requests": [request]
            }
        )

optimizer_log("GROUPS CREATED:", len(groups))


# ==========================================
# SHADOW BLOCK OPPORTUNITIES
# ==========================================

def find_shadow_block_opportunities(groups):
    """
    Find near-miss maintenance consolidation opportunities.

    Shadow blocks are advisory only. They do NOT modify the
    optimized schedule or the existing grouping logic.

    A pair is reported when:
    - both groups use the same corridor and date
    - their task sets are different
    - they do not already overlap
    - their gap is slightly larger than the normal consolidation
      limit but still within a reasonable coordination window
    - the combined window is within the shadow duration limit

    Group requests are database tuples, so request[0] is the
    request_id and request[5]/request[6] are start/end times.
    """

    opportunities = []
    seen = set()

    # Normal grouping allows a 15-minute gap.
    # Shadow blocks intentionally look a little farther ahead.
    shadow_max_gap = 60
    shadow_max_duration = MAX_BLOCK_DURATION + 120

    for i in range(len(groups)):

        for j in range(i + 1, len(groups)):

            first = groups[i]
            second = groups[j]

            if first["corridor"] != second["corridor"]:
                continue

            if first["date"] != second["date"]:
                continue

            # Requests are database tuples.
            first_task_ids = [
                request[1]
                for request in first["requests"]
            ]

            second_task_ids = [
                request[1]
                for request in second["requests"]
            ]

            if set(first_task_ids) & set(second_task_ids):
                continue

            first_start = time_to_minutes(first["start"])
            first_end = time_to_minutes(first["end"])
            second_start = time_to_minutes(second["start"])
            second_end = time_to_minutes(second["end"])

            # Ignore overlapping groups.
            if not (first_end <= second_start or second_end <= first_start):
                continue

            if first_end <= second_start:
                earlier = first
                later = second
                gap_minutes = second_start - first_end
            else:
                earlier = second
                later = first
                gap_minutes = first_start - second_end

            # Normal optimizer already handles gaps up to this limit.
            if gap_minutes <= MAX_CONSOLIDATION_GAP:
                continue

            # Shadow only looks one extra consolidation window ahead.
            if gap_minutes > shadow_max_gap:
                continue

            combined_start = min(
                time_to_minutes(earlier["start"]),
                time_to_minutes(later["start"])
            )

            combined_end = max(
                time_to_minutes(earlier["end"]),
                time_to_minutes(later["end"])
            )

            combined_duration = combined_end - combined_start

            if combined_duration > shadow_max_duration:
                continue

            task_pair = tuple(sorted(
                first_task_ids + second_task_ids
            ))

            key = (
                str(first["corridor"]),
                str(first["date"]),
                task_pair,
            )

            if key in seen:
                continue

            seen.add(key)

            opportunities.append(
                {
                    "corridor": first["corridor"],
                    "date": first["date"],
                    "base_tasks": first_task_ids,
                    "candidate_tasks": second_task_ids,
                    "base_window": {
                        "start": str(first["start"]),
                        "end": str(first["end"]),
                    },
                    "candidate_window": {
                        "start": str(second["start"]),
                        "end": str(second["end"]),
                    },
                    "gap_minutes": round(
                        gap_minutes,
                        2
                    ),
                    "combined_duration_minutes": round(
                        combined_duration,
                        2
                    ),
                    "reason": (
                        "Nearby maintenance blocks are outside the normal "
                        "consolidation gap but could be coordinated as a "
                        "shadow maintenance opportunity."
                    ),
                }
            )

    return opportunities


shadow_block_opportunities = find_shadow_block_opportunities(groups)

optimizer_log(
    "SHADOW BLOCK OPPORTUNITIES:",
    len(shadow_block_opportunities)
)


# ==========================================
# AI EXPLAINABILITY
# ==========================================

def build_window_explanation(
    best_candidate,
    candidate_results,
    requested_start,
    requested_end,
    number_of_tasks,
    maintenance_priority,
    asset_risk_score,
    utilization,
    traffic_impact_score,
    goods_impact_score,
    ai_decision_confidence,
):
    """
    Build a human-readable explanation for why the AI
    selected the final maintenance window.

    This is decision-support metadata only. It does not
    change the optimization score or railway operations.
    """

    original_start_minutes = time_to_minutes(requested_start)

    ranked_candidates = sorted(
        candidate_results,
        key=lambda item: (
            item["score"],
            -item["conflict_count"],
            -abs(
                time_to_minutes(item["start"])
                - original_start_minutes
            )
        ),
        reverse=True,
    )

    requested_candidate = min(
        candidate_results,
        key=lambda item: abs(
            time_to_minutes(item["start"])
            - original_start_minutes
        )
    )

    score_delta = round(
        best_candidate["score"]
        - requested_candidate["score"],
        2,
    )

    reasons = []

    # ==========================================
    # AI DECISION CONFIDENCE
    # ==========================================

    reasons.append(
        f"AI decision confidence: "
        f"{ai_decision_confidence['level']} "
        f"(score gap: "
        f"{ai_decision_confidence['score_gap']:.2f})"
    )

    if best_candidate["conflict_count"] == 0:
        reasons.append(
            "No train conflicts in the selected window"
        )
    else:
        reasons.append(
            f"Selected with {best_candidate['conflict_count']} train conflict(s)"
        )

    if utilization >= 80:
        reasons.append(
            f"High block utilization ({utilization:.2f}%)"
        )

    if traffic_impact_score < 30:
        reasons.append(
            f"Low predicted traffic impact ({traffic_impact_score:.2f})"
        )
    else:
        reasons.append(
            f"Traffic impact considered ({traffic_impact_score:.2f})"
        )

    if goods_impact_score < 30:
        reasons.append(
            f"Low predicted goods impact ({goods_impact_score:.2f})"
        )
    else:
        reasons.append(
            f"Goods traffic impact considered ({goods_impact_score:.2f})"
        )

    if asset_risk_score >= 70:
        reasons.append(
            f"High-risk asset prioritized ({asset_risk_score:.2f})"
        )
    elif asset_risk_score > 0:
        reasons.append(
            f"Asset risk included in scoring ({asset_risk_score:.2f})"
        )

    if maintenance_priority >= 80:
        reasons.append(
            f"High-priority maintenance included ({maintenance_priority:.2f})"
        )
    else:
        reasons.append(
            f"Maintenance priority included ({maintenance_priority:.2f})"
        )

    if number_of_tasks >= 2:
        reasons.append(
            f"{number_of_tasks} maintenance tasks consolidated"
        )

    if score_delta > 0:
        reasons.append(
            f"AI score improved by {score_delta:.2f} over the requested window"
        )
    elif score_delta == 0:
        reasons.append(
            "Selected window ties the requested window on AI score"
        )

    alternatives = []

    for candidate in ranked_candidates:

        if candidate is best_candidate:
            continue

        alternatives.append(
            {
                "start": str(candidate["start"])[:5],
                "end": str(candidate["end"])[:5],
                "score": round(candidate["score"], 2),
                "conflicts": candidate["conflict_count"],
                "traffic_impact": round(
                    candidate["traffic_impact"],
                    2
                ),
                "goods_impact": round(
                    candidate["goods_impact"],
                    2
                ),
            }
        )

        if len(alternatives) >= 3:
            break

    return {
        "selected_window": (
            f"{str(best_candidate['start'])[:5]}-"
            f"{str(best_candidate['end'])[:5]}"
        ),
        "requested_window": (
            f"{str(requested_start)[:5]}-"
            f"{str(requested_end)[:5]}"
        ),
        "candidate_count": len(candidate_results),
        "selected_score": round(
            best_candidate["score"],
            2
        ),
        "requested_window_score": round(
            requested_candidate["score"],
            2
        ),
        "score_delta_vs_requested": score_delta,
        "reasons": reasons,
        "alternatives": alternatives,
        "factors": {
            "maintenance_priority": round(
                maintenance_priority,
                2
            ),
            "asset_risk": round(
                asset_risk_score,
                2
            ),
            "utilization": round(
                utilization,
                2
            ),
            "traffic_impact": round(
                traffic_impact_score,
                2
            ),
            "goods_impact": round(
                goods_impact_score,
                2
            ),
            "train_conflicts": best_candidate[
                "conflict_count"
            ],
            "consolidated_tasks": number_of_tasks,
        },
    }

# ==========================================
# CREATE OPTIMIZED BLOCKS
# ==========================================


optimized_blocks = []


block_number = 1


for group in groups:

    optimizer_log("PROCESSING GROUP:", group["corridor"], group["date"])

    corridor = group["corridor"]
    block_date = group["date"]

    start_time = group["start"]
    end_time = group["end"]

    start_minutes = time_to_minutes(
        start_time
    )

    end_minutes = time_to_minutes(
        end_time
    )

    duration = end_minutes - start_minutes

    if duration < 0:
        duration += 1440

    # ======================================
    # CANDIDATE WINDOW OPTIMIZATION
    # ======================================

    candidate_windows = generate_candidate_windows(
        requested_start=start_time,
        requested_end=end_time,
        step_minutes=30,
        search_before_minutes=120,
        search_after_minutes=120
    )

    optimizer_log()
    optimizer_log(
        "CANDIDATE WINDOWS:",
        corridor,
        block_date
    )

    # ======================================
    # AI CANDIDATE WINDOW OPTIMIZATION
    # ======================================

    # Calculate maintenance priority before evaluating
    # candidate windows. The same group priority is used
    # for every candidate.
    maintenance_priority = max(
        [
            safe_float(request[8], 0)
            for request in group["requests"]
        ],
        default=0
    )

    # Normalize priority to the 0-100 range because the
    # multi-objective score expects percentage-like values.
    maintenance_priority = max(
        0,
        min(
            maintenance_priority,
            100
        )
    )

    # Calculate the actual task occupancy once.
    # This value is used by every candidate window.
    number_of_tasks = len(
        group["requests"]
    )

    task_intervals = []

    for request in group["requests"]:

        request_start = time_to_minutes(
            request[5]
        )

        request_end = time_to_minutes(
            request[6]
        )

        if request_end < request_start:
            request_end += 1440

        task_intervals.append(
            (
                request_start,
                request_end
            )
        )

    task_intervals.sort()

    occupied_start = None
    occupied_end = None
    occupied_minutes = 0

    for interval_start, interval_end in task_intervals:

        if occupied_start is None:

            occupied_start = interval_start
            occupied_end = interval_end

        elif interval_start <= occupied_end:

            occupied_end = max(
                occupied_end,
                interval_end
            )

        else:

            occupied_minutes += (
                occupied_end - occupied_start
            )

            occupied_start = interval_start
            occupied_end = interval_end

    if occupied_start is not None:

        occupied_minutes += (
            occupied_end - occupied_start
        )

    candidate_results = []

    optimizer_log()
    optimizer_log(
        "CANDIDATE WINDOWS:",
        corridor,
        block_date
    )

    for candidate in candidate_windows:

        candidate_duration = candidate["duration"]

        if candidate_duration <= 0:
            continue

        candidate_utilization = round(
            min(
                (
                    occupied_minutes
                    / candidate_duration
                ) * 100,
                100
            ),
            2
        )

        try:

            result = score_candidate_window(
                corridor=corridor,
                block_date=block_date,
                candidate=candidate,
                group=group,
                maintenance_priority=maintenance_priority,
                utilization=candidate_utilization
            )

        except Exception as exc:

            optimizer_log(
                "CANDIDATE SCORING ERROR:",
                exc
            )

            continue

        candidate_results.append(
            result
        )

        optimizer_log(
            f"  {str(result['start'])[:5]}-"
            f"{str(result['end'])[:5]} "
            f"| conflicts={result['conflict_count']} "
            f"| traffic={result['traffic_impact']} "
            f"| goods={result['goods_impact']} "
            f"| utilization={result['utilization']} "
            f"| AI score={result['score']}"
        )

    # ======================================
    # SELECT HIGHEST AI SCORE
    # ======================================

    if not candidate_results:

        optimizer_log(
            "NO FEASIBLE CANDIDATE:",
            corridor,
            block_date
        )

        continue

    # Higher AI score is better.
    # If scores are tied:
    #   1. fewer train conflicts
    #   2. closer to requested start time
    original_start_minutes = time_to_minutes(
        start_time
    )

    def candidate_sort_key(result):

        candidate_start_minutes = time_to_minutes(
            result["start"]
        )

        distance_from_requested = abs(
            candidate_start_minutes
            - original_start_minutes
        )

        return (
            result["score"],
            -result["conflict_count"],
            -distance_from_requested
        )

    best_candidate = max(
        candidate_results,
        key=candidate_sort_key
    )


    # ==========================================
    # AI DECISION CONFIDENCE
    # ==========================================

    sorted_candidates = sorted(
        candidate_results,
        key=candidate_sort_key,
        reverse=True
    )

    best_candidate = sorted_candidates[0]

    if len(sorted_candidates) > 1:
        second_best_candidate = sorted_candidates[1]

        best_score = safe_float(
            best_candidate.get("score"),
            0.0
        )

        second_best_score = safe_float(
            second_best_candidate.get("score"),
            0.0
        )

        score_gap = round(
            best_score - second_best_score,
            2
        )
    else:
        second_best_candidate = None
        score_gap = 0.0

    if score_gap >= 10:
        confidence_level = "HIGH"
    elif score_gap >= 3:
        confidence_level = "MODERATE"
    else:
        confidence_level = "LOW"

    ai_decision_confidence = {
        "level": confidence_level,
        "score_gap": score_gap,
        "candidates_evaluated": len(
            sorted_candidates
        ),
        "best_score": round(
            safe_float(
                best_candidate.get("score"),
                0.0
            ),
            2
        ),
        "second_best_score": (
            round(
                safe_float(
                    second_best_candidate.get("score"),
                    0.0
                ),
                2
            )
            if second_best_candidate
            else None
        )
    }



    # ======================================
    # APPLY AI RECOMMENDATION
    # ======================================

    start_time = best_candidate["start"]
    end_time = best_candidate["end"]
    duration = best_candidate["duration"]

    train_conflicts = best_candidate["conflicts"]

    # Candidate-specific values are preserved so the
    # final block score exactly matches the selected
    # candidate rather than recalculating a different
    # score later.
    utilization = best_candidate["utilization"]

    traffic_impact_score = (
        best_candidate["traffic_impact"]
    )

    goods_impact_score = (
        best_candidate["goods_impact"]
    )

    candidate_optimization_score = (
        best_candidate["score"]
    )

    try:
        assessment = evaluate_window(
            cursor=cursor,
            corridor_id=corridor,
            travel_date=block_date,
            start_time=start_time,
            end_time=end_time
        )
        estimated_delay = assessment.get("estimated_delay_min", 0)
    except Exception:
        assessment = {}
        estimated_delay = 0

    # ======================================
    # BUILD AI EXPLANATION
    # ======================================

    ai_explanation = build_window_explanation(
        best_candidate=best_candidate,
        candidate_results=candidate_results,
        requested_start=group["start"],
        requested_end=group["end"],
        number_of_tasks=len(group["requests"]),
        maintenance_priority=maintenance_priority,
        asset_risk_score=best_candidate.get(
            "asset_risk",
            0
        ),
        utilization=best_candidate.get(
            "utilization",
            0
        ),
        traffic_impact_score=best_candidate.get(
            "traffic_impact",
            0
        ),
        goods_impact_score=best_candidate.get(
            "goods_impact",
            0
        ),

        ai_decision_confidence=ai_decision_confidence,

    )

    optimizer_log()
    optimizer_log(
        "AI SELECTED WINDOW:",
        str(start_time)[:5],
        "-",
        str(end_time)[:5]
    )

    optimizer_log(
        "AI SCORE:",
        candidate_optimization_score
    )

    optimizer_log(
        "TRAIN CONFLICTS:",
        len(train_conflicts)
    )

    optimizer_log(
        "TRAFFIC IMPACT:",
        traffic_impact_score
    )

    optimizer_log(
        "GOODS IMPACT:",
        goods_impact_score
    )

    optimizer_log()
    optimizer_log("WHY THIS WINDOW?")
    optimizer_log("--------------------------------------")

    for reason in ai_explanation["reasons"]:
        optimizer_log("[OK]", reason)

    optimizer_log(
        "Candidates evaluated:",
        ai_explanation["candidate_count"]
    )

    optimizer_log(
        "Requested window score:",
        ai_explanation["requested_window_score"]
    )

    optimizer_log(
        "Selected window score:",
        ai_explanation["selected_score"]
    )

    optimizer_log(
        "Score improvement:",
        ai_explanation["score_delta_vs_requested"]
    )

    optimizer_log("Top alternatives:")

    for alternative in ai_explanation["alternatives"]:
        optimizer_log(
            f"  {alternative['start']}-"
            f"{alternative['end']} "
            f"| score={alternative['score']} "
            f"| conflicts={alternative['conflicts']} "
            f"| traffic={alternative['traffic_impact']} "
            f"| goods={alternative['goods_impact']}"
        )

    optimizer_log("--------------------------------------")

    # ======================================
    # TRAIN IMPACT SCORE
    # ======================================

    train_impact_score = 0

    for train in train_conflicts:

        if train["train_type"] == "EXPRESS":

            train_impact_score += 40

        elif train["train_type"] == "PASSENGER":

            train_impact_score += 25

        elif train["train_type"] == "FREIGHT":

            train_impact_score += 15

        else:

            train_impact_score += 20


    train_impact_score = min(
        train_impact_score,
        100
    )

    # ======================================
    # MAINTENANCE UTILIZATION
    # ======================================

    number_of_tasks = len(
        group["requests"]
    )


    # Calculate actual occupied time
    # instead of blindly summing overlapping
    # task durations.

    intervals = []

    for request in group["requests"]:

        request_start = time_to_minutes(
            request[5]
        )

        request_end = time_to_minutes(
            request[6]
        )

        # Handle overnight requests
        if request_end < request_start:
            request_end += 1440

        intervals.append(
            (
                request_start,
                request_end
            )
        )


    intervals.sort()


    occupied_start = None
    occupied_end = None
    occupied_minutes = 0


    for start, end in intervals:

        if occupied_start is None:

            occupied_start = start
            occupied_end = end

        elif start <= occupied_end:

            occupied_end = max(
                occupied_end,
                end
            )

        else:

            occupied_minutes += (
                occupied_end - occupied_start
            )

            occupied_start = start
            occupied_end = end


    if occupied_start is not None:

        occupied_minutes += (
            occupied_end - occupied_start
        )


    if duration > 0:

        utilization = (
            occupied_minutes
            / duration
        ) * 100

    else:

        utilization = 0


    utilization = round(
        min(utilization, 100),
        2
    )


    # ======================================
    # BLOCK ID
    # ======================================

    block_id = (
        f"OPT-{block_date}-"
        f"{block_number:03d}"
    )


   # ======================================
    # ======================================
    # AI / ML INTELLIGENCE
    # ======================================

    # --------------------------------------
    # Maintenance priority
    # --------------------------------------

    maintenance_priority = max(
        [
            safe_float(request[8], 0)
            for request in group["requests"]
        ],
        default=0
    )

    # --------------------------------------
    # Asset risk
    # --------------------------------------

    asset_risks = []

    for request in group["requests"]:
        task_id = request[1]

        try:
            risk = calculate_asset_risk_for_task(task_id)
            asset_risks.append(risk)

        except Exception as exc:
            optimizer_log(
                "ASSET RISK ERROR:",
                task_id,
                exc
            )

    if asset_risks:
        asset_risk_score = max(asset_risks)
    else:
        asset_risk_score = 0

    # --------------------------------------
    # Train counts
    # --------------------------------------

    passenger_trains = 0
    goods_trains = 0
    special_trains = 0
    express_trains = 0

    for train in train_conflicts:
        train_type = str(
            train["train_type"]
        ).upper()

        if train_type == "EXPRESS":
            express_trains += 1
            passenger_trains += 1

        elif train_type in (
            "PASSENGER",
            "MAIL",
            "SUPERFAST",
        ):
            passenger_trains += 1

        elif train_type in (
            "FREIGHT",
            "GOODS",
        ):
            goods_trains += 1

        elif train_type in (
            "SPECIAL",
            "FESTIVAL",
        ):
            special_trains += 1

        else:
            passenger_trains += 1

    # --------------------------------------
    # Corridor congestion
    # --------------------------------------

    cursor.execute(
        """
        SELECT traffic_level
        FROM corridors
        WHERE corridor_id = %s
        """,
        (corridor,)
    )

    corridor_row = cursor.fetchone()

    traffic_level = (
        str(corridor_row[0]).upper()
        if corridor_row and corridor_row[0]
        else "MEDIUM"
    )

    traffic_map = {
        "LOW": 25,
        "MEDIUM": 50,
        "HIGH": 75,
        "VERY HIGH": 90,
        "CRITICAL": 100,
    }

    corridor_congestion = traffic_map.get(
        traffic_level,
        50
    )

    # --------------------------------------
    # Traffic ML
    # --------------------------------------

    try:
        traffic_prediction = calculate_traffic_impact(
            duration=duration,
            start_hour=int(str(start_time)[:2]),
            passenger_trains=passenger_trains,
            goods_trains=goods_trains,
            special_trains=special_trains,
            express_trains=express_trains,
            corridor_congestion=corridor_congestion,
            criticality=max(
                [
                    safe_float(
                        request[8],
                        0
                    )
                    for request in group["requests"]
                ],
                default=3
            ),
            maintenance_priority=maintenance_priority,
        )

        traffic_impact_score = safe_float(
            traffic_prediction.get(
                "traffic_impact_score",
                traffic_prediction.get(
                    "impact_score",
                    0
                )
            ),
            0
        )

    except Exception as exc:
        optimizer_log(
            "TRAFFIC ML ERROR:",
            exc
        )

        traffic_prediction = {}
        traffic_impact_score = 0

    # --------------------------------------
    # Goods ML
    # --------------------------------------

    try:
        goods_impact_score = calculate_goods_impact(
            corridor_id=corridor,
            block_date=block_date,
            start_hour=int(str(start_time)[:2]),
        )

    except Exception as exc:
        optimizer_log(
            "GOODS ML ERROR:",
            exc
        )

        goods_impact_score = 0

    # --------------------------------------
    # Consolidation benefit
    # --------------------------------------

    consolidation_score = min(
        100,
        number_of_tasks * 25
    )

    # --------------------------------------
    # AI optimization score
    # --------------------------------------

    # Keep the persisted block score consistent with the
    # candidate score used to select the window.
    conflict_penalty = min(
        100,
        len(train_conflicts) * 20
    )

    optimization_score = (
        maintenance_priority
        * WEIGHT_MAINTENANCE_PRIORITY
        +
        asset_risk_score
        * WEIGHT_ASSET_RISK
        +
        utilization
        * WEIGHT_UTILIZATION
        +
        (
            100 - traffic_impact_score
        )
        * WEIGHT_TRAFFIC
        +
        (
            100 - goods_impact_score
        )
        * WEIGHT_GOODS
        +
        consolidation_score
        * WEIGHT_CONSOLIDATION
        -
        conflict_penalty
    )

    optimization_score = round(
        max(
            0,
            min(
                optimization_score,
                100
            )
        ),
        2
    )

    # --------------------------------------
    # Explanation
    # --------------------------------------

    reasons = list(
        ai_explanation["reasons"]
    )

    optimized_blocks.append(
        {
            "block_id": block_id,
            "corridor": corridor,
            "date": block_date,
            "start": start_time,
            "end": end_time,
            "duration": duration,

            "utilization": utilization,
            "train_impact_score": train_impact_score,
            "train_impact": train_impact_score,
            "estimated_delay": estimated_delay,

            "maintenance_priority": round(
                maintenance_priority,
                2
            ),

            "asset_risk_score": round(
                asset_risk_score,
                2
            ),

            "traffic_impact_score": round(
                traffic_impact_score,
                2
            ),

            "goods_impact_score": round(
                goods_impact_score,
                2
            ),

            "consolidation_score": round(
                consolidation_score,
                2
            ),

            "optimization_score": optimization_score,

            "tasks": group["requests"],

            "train_conflicts": train_conflicts,

            "ai_reasons": reasons,

            "ai_explanation": ai_explanation,

            "traffic_prediction": traffic_prediction,

            "reason": (
                f"AI scored this {duration}-minute block "
                f"at {optimization_score}/100 using "
                f"maintenance priority, asset risk, "
                f"traffic impact, goods demand, "
                f"utilization and consolidation."
            ),
        }
    )

    block_number += 1

# ==========================================
# DELETE PREVIOUS OPTIMIZATION
# ==========================================

# Do not wipe the existing optimized plan.
# New optimized blocks are persisted alongside existing blocks.
# ==========================================
# INSERT OPTIMIZED BLOCKS
# ==========================================
for block in optimized_blocks:

    department_count = 0

    if block["tasks"]:

        task_ids = [
            request[1]
            for request in block["tasks"]
        ]

        cursor.execute(
            """
            SELECT COUNT(DISTINCT department)
            FROM maintenance_tasks
            WHERE task_id = ANY(%s)
            """,
            (task_ids,)
        )

        department_count = cursor.fetchone()[0]
        optimizer_log("DEPARTMENT COUNT:", department_count)

    optimizer_log(
        "BEFORE INSERT:",
        block["block_id"],
        "CORRIDOR =", block["corridor"],
        "DATE =", block["date"],
        "START =", block["start"],
        "END =", block["end"],
        "DURATION =", block["duration"],
        "UTILIZATION =", block["utilization"],
        "TRAIN IMPACT =", block.get(
            "traffic_impact_score",
            0
        ),
        "TASKS =", len(block["tasks"]),
        "DEPARTMENTS =", department_count
    )

    cursor.execute(
        """
        INSERT INTO optimized_blocks
        (
            block_id,
            corridor_id,
            block_date,
            start_time,
            end_time,
            duration_min,
            utilization_percent,
            train_impact_score,
            optimization_score,
            number_of_tasks,
            number_of_departments
        )
        VALUES
        (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (block_id) DO UPDATE SET
        corridor_id = EXCLUDED.corridor_id,
        block_date = EXCLUDED.block_date,
        start_time = EXCLUDED.start_time,
        end_time = EXCLUDED.end_time,
        duration_min = EXCLUDED.duration_min,
        utilization_percent = EXCLUDED.utilization_percent,
        train_impact_score = EXCLUDED.train_impact_score,
        optimization_score = EXCLUDED.optimization_score,
        number_of_tasks = EXCLUDED.number_of_tasks,
        number_of_departments = EXCLUDED.number_of_departments;
        """,
        (
            block["block_id"],
            block["corridor"],
            block["date"],
            block["start"],
            block["end"],
            block["duration"],
            block["utilization"],
            block.get(
                "train_impact_score",
                block.get("traffic_impact_score", 0)
            ),
            block["optimization_score"],
            len(block["tasks"]),
            department_count
        )
    )

    optimizer_log("OPTIMIZED BLOCK INSERTED:", block["block_id"])


    # ======================================
    # BLOCK <-> TASK
    # ======================================

    for request in block["tasks"]:

        task_id = request[1]

        cursor.execute(
            """
            INSERT INTO block_tasks
            (
                block_id,
                task_id
            )
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                block["block_id"],
                task_id
            )
        )
    cursor.execute(
    """
    UPDATE optimized_blocks ob
    SET number_of_departments = (
        SELECT COUNT(DISTINCT mt.department)
        FROM block_tasks bt
        JOIN maintenance_tasks mt
            ON bt.task_id = mt.task_id
        WHERE bt.block_id = ob.block_id
    )
    WHERE ob.block_id = %s
    """,
    (block["block_id"],)
)


    # ======================================
    # BLOCK <-> TRAIN
    # ======================================

    for train in block["train_conflicts"]:

        cursor.execute(
            """
            INSERT INTO block_train_impact
            (
                block_id,
                train_id,
                impact_type,
                estimated_delay_min
            )
            VALUES (%s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                block["block_id"],
                train["train_id"],
                "SCHEDULE_CONFLICT",
                5
            )
        )

# ==========================================
# SAVE
# ==========================================

# MARK PROCESSED REQUESTS AS OPTIMIZED
for block in optimized_blocks:
    for request in block["tasks"]:
        request_id = request[0]

        cursor.execute(
            """
            UPDATE block_requests
            SET request_status = 'OPTIMIZED'
            WHERE request_id = %s
            """,
            (request_id,)
        )
connection.commit()


# ==========================================
# DISPLAY
# ==========================================

optimizer_log()
optimizer_log("==============================================================")
optimizer_log("                 BLOCK OPTIMIZER V2")
optimizer_log("==============================================================")
optimizer_log()

optimizer_log(
    f"Requests processed : {len(requests)}"
)

optimizer_log(
    f"Blocks generated   : {len(optimized_blocks)}"
)

optimizer_log()

optimizer_log(
    f"{'BLOCK':<25}"
    f"{'CORRIDOR':<10}"
    f"{'TIME':<20}"
    f"{'TASKS':<8}"
    f"{'UTIL':<8}"
    f"TRAIN IMPACT"
)

optimizer_log("-" * 90)


for block in optimized_blocks:

    optimizer_log(
        f"{block['block_id']:<25}"
        f"{block['corridor']:<10}"
        f"{str(block['start'])[:5]}-"
        f"{str(block['end'])[:5]:<14}"
        f"{len(block['tasks']):<8}"
        f"{block['utilization']:<8}"
        f"{block.get('traffic_impact_score', 0)}"
    )


# ==========================================
# FINAL AI EXPLANATION SUMMARY
# ==========================================

optimizer_log()
optimizer_log("==============================================================")
optimizer_log("                 AI EXPLAINABILITY")
optimizer_log("==============================================================")

for block in optimized_blocks:

    explanation = block.get(
        "ai_explanation",
        {}
    )

    optimizer_log()
    optimizer_log(
        f"{block['block_id']} | "
        f"{block['corridor']} | "
        f"{explanation.get('selected_window', 'N/A')}"
    )

    optimizer_log(
        f"AI SCORE: "
        f"{explanation.get('selected_score', block.get('optimization_score', 0))}"
    )

    optimizer_log("WHY:")

    for reason in explanation.get(
        "reasons",
        []
    ):
        optimizer_log("  [OK]", reason)

    alternatives = explanation.get(
        "alternatives",
        []
    )

    if alternatives:
        optimizer_log("ALTERNATIVES:")

        for alternative in alternatives:
            optimizer_log(
                f"  {alternative['start']}-"
                f"{alternative['end']} "
                f"| score={alternative['score']} "
                f"| conflicts={alternative['conflicts']}"
            )

optimizer_log()
optimizer_log("==============================================================")
optimizer_log("              OPTIMIZATION COMPLETE")
optimizer_log("==============================================================")

# ==========================================
# TEST 30-DAY MAINTENANCE INTELLIGENCE
# ==========================================

try:
    optimizer_log()
    optimizer_log("==========================================")
    optimizer_log("30-DAY MAINTENANCE INTELLIGENCE TEST")
    optimizer_log("==========================================")

    maintenance_30_result = generate_30_day_maintenance_intelligence(
        start_date=datetime(2026, 9, 1).date(),
        corridor_id="C02",
    )

    optimizer_log(
        "CORRIDOR:",
        maintenance_30_result["corridor"]
    )

    optimizer_log(
        "START DATE:",
        maintenance_30_result["start_date"]
    )

    optimizer_log(
        "END DATE:",
        maintenance_30_result["end_date"]
    )

    optimizer_log(
        "TOTAL TASKS:",
        maintenance_30_result["total_tasks"]
    )

    optimizer_log(
        "CRITICAL TASKS:",
        maintenance_30_result["critical_tasks"]
    )

    optimizer_log(
        "HIGH PRIORITY TASKS:",
        maintenance_30_result["high_priority_tasks"]
    )

    for task in maintenance_30_result["tasks"]:

        optimizer_log(
            f"{task['task_id']} | "
            f"{task['corridor']} | "
            f"{task['requested_date']} | "
            f"asset_risk={task['asset_risk']} | "
            f"maintenance_priority={task['maintenance_priority']} | "
            f"traffic={task['traffic_pressure']} | "
            f"goods={task['goods_impact']} | "
            f"urgency={task['maintenance_urgency']} | "
            f"level={task['urgency_level']}"
        )

    optimizer_log(
        "HIGHEST PRIORITY TASK:",
        maintenance_30_result["highest_priority_task"]
    )

    optimizer_log("==========================================")
except Exception as exc:
    optimizer_log("30-day maintenance test error/skipped:", exc)

try:
    optimizer_log("\n" + "=" * 60)
    optimizer_log("EMERGENCY BLOCK OPTIMIZATION TEST")
    optimizer_log("=" * 60)

    emergency_result = optimize_emergency_block(
        task_id="T-AUTO-0001",
        corridor_id="C02",
        block_date=datetime(2026, 9, 1).date(),
        requested_start="10:00:00",
        requested_end="13:00:00",
    )

    optimizer_log("TASK:", emergency_result["task_id"])
    optimizer_log("CORRIDOR:", emergency_result["corridor_id"])
    optimizer_log(
        "REQUESTED WINDOW:",
        emergency_result["requested_window"]
    )

    optimizer_log(
        "CANDIDATES EVALUATED:",
        emergency_result["candidates_evaluated"]
    )

    optimizer_log(
        "BEST EMERGENCY WINDOW:",
        emergency_result["best_window"]
    )

    optimizer_log("\nALTERNATIVES:")

    for alternative in emergency_result["alternatives"]:
        optimizer_log(alternative)
except Exception as exc:
    optimizer_log("Emergency test error/skipped:", exc)

try:
    cursor.close()
except Exception:
    pass
try:
    connection.close()
except Exception:
    pass
