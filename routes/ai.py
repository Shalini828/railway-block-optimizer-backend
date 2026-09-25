from fastapi import APIRouter, HTTPException, Depends
import psycopg

from db_config import DB_CONFIG

from ml.predict_service import predict_asset_risk
from auth.security import require_permission, get_current_user, CurrentUser
from auth.permissions import is_network_scope, department_of
from auth.audit import record_audit



from ml.traffic_predict_service import predict_traffic_impact
from ml.goods_forecast_service import predict_goods_train_demand
from ml.block_intelligence import analyze_block
from logic.traffic_intelligence import (
    load_traffic_in_window,
    classify_counts,
    normalize_train_type,
    windows_overlap,
    evaluate_window,
)
from logic.freight_pressure import get_daily_goods_forecast

router = APIRouter(
    prefix="/ai",
    tags=["AI / ML"]
)


@router.get("/health")
def ai_health():
    return {
        "status": "ok",
        "service": "railway-ai-ml"
    }


@router.post("/test-prediction", dependencies=[Depends(require_permission("optimizer.simulate"))])
def test_prediction():
    asset = {
        "asset_id": "AST-TEST-001",
        "criticality": 5,
        "health_score": 42,
        "failure_risk": 78,
        "installation_date": "2008-01-15",
        "last_inspection_date": "2026-04-27"
    }

    defects = [
        {
            "severity": 5,
            "safety_impact": 5,
            "repeat_failure": True
        },
        {
            "severity": 4,
            "safety_impact": 4,
            "repeat_failure": False
        }
    ]

    history = [
        {
            "maintenance_type": "Corrective Maintenance",
            "failure_after_maintenance": True
        },
        {
            "maintenance_type": "Preventive Maintenance",
            "failure_after_maintenance": False
        }
    ]

    return predict_asset_risk(
        asset,
        defects,
        history
    )


@router.get("/assets/{asset_id}/risk", dependencies=[Depends(require_permission("ai.risk.view"))])
def get_asset_risk(
    asset_id: str,
    user: CurrentUser = Depends(get_current_user)
):

    connection = None

    try:
        connection = psycopg.connect(**DB_CONFIG)

        # =====================================================
        # GET ASSET
        # =====================================================

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    asset_id,
                    criticality,
                    health_score,
                    failure_risk,
                    installation_date,
                    last_inspection_date,
                    department
                FROM assets
                WHERE asset_id = %s
                """,
                (asset_id,)
            )

            row = cursor.fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"Asset '{asset_id}' not found"
            )

        if not is_network_scope(user.role_id):
            dept = department_of(user.role_id)
            if row[6] != dept:
                raise HTTPException(
                    status_code=404,
                    detail=f"Asset '{asset_id}' not found"
                )

        asset = {
            "asset_id": row[0],
            "criticality": row[1],
            "health_score": row[2],
            "failure_risk": row[3],
            "installation_date": row[4],
            "last_inspection_date": row[5],
        }

        # =====================================================
        # GET DEFECTS
        # =====================================================

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    severity,
                    safety_impact,
                    repeat_failure
                FROM defects
                WHERE asset_id = %s
                """,
                (asset_id,)
            )

            defect_rows = cursor.fetchall()

        defects = [
            {
                "severity": row[0],
                "safety_impact": row[1],
                "repeat_failure": row[2],
            }
            for row in defect_rows
        ]

        # =====================================================
        # GET MAINTENANCE HISTORY
        # =====================================================

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    maintenance_type,
                    failure_after_maintenance
                FROM maintenance_history
                WHERE asset_id = %s
                """,
                (asset_id,)
            )

            history_rows = cursor.fetchall()

        maintenance_history = [
            {
                "maintenance_type": row[0],
                "failure_after_maintenance": row[1],
            }
            for row in history_rows
        ]

        # =====================================================
        # ML PREDICTION
        # =====================================================

        result = predict_asset_risk(
            asset=asset,
            defects=defects,
            maintenance_history=maintenance_history,
        )

        return result

    finally:

        if connection:
            connection.close()

@router.get("/assets/risk-ranking", dependencies=[Depends(require_permission("ai.risk.view"))])
def get_asset_risk_ranking(user: CurrentUser = Depends(get_current_user)):

    connection = None

    try:
        connection = psycopg.connect(**DB_CONFIG)

        # =====================================================
        # GET ALL ASSETS
        # =====================================================

        dept = department_of(user.role_id)
        is_dept = not is_network_scope(user.role_id) and bool(dept)

        with connection.cursor() as cursor:

            if is_dept:
                cursor.execute(
                    """
                    SELECT
                        asset_id,
                        criticality,
                        health_score,
                        failure_risk,
                        installation_date,
                        last_inspection_date
                    FROM assets
                    WHERE department = %s
                    ORDER BY asset_id
                    """,
                    (dept,)
                )
            else:
                cursor.execute(
                    """
                    SELECT
                        asset_id,
                        criticality,
                        health_score,
                        failure_risk,
                        installation_date,
                        last_inspection_date
                    FROM assets
                    ORDER BY asset_id
                    """
                )

            asset_rows = cursor.fetchall()

        results = []

        # =====================================================
        # PROCESS EACH ASSET
        # =====================================================

        for row in asset_rows:

            asset = {
                "asset_id": row[0],
                "criticality": row[1],
                "health_score": row[2],
                "failure_risk": row[3],
                "installation_date": row[4],
                "last_inspection_date": row[5],
            }

            asset_id = row[0]

            # -------------------------------------------------
            # DEFECTS
            # -------------------------------------------------

            with connection.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        severity,
                        safety_impact,
                        repeat_failure
                    FROM defects
                    WHERE asset_id = %s
                    """,
                    (asset_id,)
                )

                defect_rows = cursor.fetchall()

            defects = [
                {
                    "severity": defect[0],
                    "safety_impact": defect[1],
                    "repeat_failure": defect[2],
                }
                for defect in defect_rows
            ]

            # -------------------------------------------------
            # MAINTENANCE HISTORY
            # -------------------------------------------------

            with connection.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        maintenance_type,
                        failure_after_maintenance
                    FROM maintenance_history
                    WHERE asset_id = %s
                    """,
                    (asset_id,)
                )

                history_rows = cursor.fetchall()

            maintenance_history = [
                {
                    "maintenance_type": history[0],
                    "failure_after_maintenance": history[1],
                }
                for history in history_rows
            ]

            # -------------------------------------------------
            # ML PREDICTION
            # -------------------------------------------------

            prediction = predict_asset_risk(
                asset=asset,
                defects=defects,
                maintenance_history=maintenance_history,
            )

            results.append(prediction)

        # =====================================================
        # SORT BY RISK
        # =====================================================

        results.sort(
            key=lambda x: x["risk_score"],
            reverse=True
        )

        # =====================================================
        # ADD RANK
        # =====================================================

        for index, result in enumerate(
            results,
            start=1
        ):
            result["priority_rank"] = index

        return {
            "total_assets": len(results),
            "assets": results,
        }

    finally:

        if connection:
            connection.close()


@router.get("/tasks/priority-ranking", dependencies=[Depends(require_permission("ai.risk.view"))])
def get_task_priority_ranking(user: CurrentUser = Depends(get_current_user)):

    connection = None

    try:
        connection = psycopg.connect(**DB_CONFIG)

        dept = department_of(user.role_id)
        is_dept = not is_network_scope(user.role_id) and bool(dept)

        with connection.cursor() as cursor:

            if is_dept:
                cursor.execute(
                    """
                    SELECT
                        task_id,
                        asset_id,
                        department,
                        task_type,
                        description,
                        due_date,
                        estimated_duration_min,
                        overdue_days,
                        safety_risk,
                        priority_score,
                        priority_category,
                        task_status
                    FROM maintenance_tasks
                    WHERE task_status NOT IN (
                        'COMPLETED',
                        'CANCELLED'
                    )
                    AND department = %s
                    ORDER BY task_id
                    """,
                    (dept,)
                )
            else:
                cursor.execute(
                    """
                    SELECT
                        task_id,
                        asset_id,
                        department,
                        task_type,
                        description,
                        due_date,
                        estimated_duration_min,
                        overdue_days,
                        safety_risk,
                        priority_score,
                        priority_category,
                        task_status
                    FROM maintenance_tasks
                    WHERE task_status NOT IN (
                        'COMPLETED',
                        'CANCELLED'
                    )
                    ORDER BY task_id
                    """
                )

            task_rows = cursor.fetchall()

        results = []

        for row in task_rows:

            task_id = row[0]
            asset_id = row[1]

            # -------------------------------------------------
            # GET AI RISK FOR THIS ASSET
            # -------------------------------------------------

            with connection.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        asset_id,
                        criticality,
                        health_score,
                        failure_risk,
                        installation_date,
                        last_inspection_date
                    FROM assets
                    WHERE asset_id = %s
                    """,
                    (asset_id,)
                )

                asset_row = cursor.fetchone()

            if asset_row is None:
                continue

            asset = {
                "asset_id": asset_row[0],
                "criticality": asset_row[1],
                "health_score": asset_row[2],
                "failure_risk": asset_row[3],
                "installation_date": asset_row[4],
                "last_inspection_date": asset_row[5],
            }

            # -------------------------------------------------
            # DEFECTS
            # -------------------------------------------------

            with connection.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        severity,
                        safety_impact,
                        repeat_failure
                    FROM defects
                    WHERE asset_id = %s
                    """,
                    (asset_id,)
                )

                defect_rows = cursor.fetchall()

            defects = [
                {
                    "severity": d[0],
                    "safety_impact": d[1],
                    "repeat_failure": d[2],
                }
                for d in defect_rows
            ]

            # -------------------------------------------------
            # MAINTENANCE HISTORY
            # -------------------------------------------------

            with connection.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        maintenance_type,
                        failure_after_maintenance
                    FROM maintenance_history
                    WHERE asset_id = %s
                    """,
                    (asset_id,)
                )

                history_rows = cursor.fetchall()

            maintenance_history = [
                {
                    "maintenance_type": h[0],
                    "failure_after_maintenance": h[1],
                }
                for h in history_rows
            ]

            # -------------------------------------------------
            # ML PREDICTION
            # -------------------------------------------------

            prediction = predict_asset_risk(
                asset=asset,
                defects=defects,
                maintenance_history=maintenance_history,
            )

            # -------------------------------------------------
            # COMBINE TASK + AI RISK
            # -------------------------------------------------

            base_priority = float(
                row[9] or 0
            )

            ai_risk = float(
                prediction["risk_score"]
            )

            ai_priority_score = round(
                (
                    base_priority * 0.40
                    + ai_risk * 0.60
                ),
                2
            )

            # -------------------------------------------------
            # CATEGORY
            # -------------------------------------------------

            if ai_priority_score >= 85:
                category = "CRITICAL"
            elif ai_priority_score >= 70:
                category = "HIGH"
            elif ai_priority_score >= 50:
                category = "MEDIUM"
            else:
                category = "LOW"

            results.append(
                {
                    "task_id": task_id,
                    "asset_id": asset_id,
                    "department": row[2],
                    "task_type": row[3],
                    "description": row[4],
                    "due_date": (
                        str(row[5])
                        if row[5]
                        else None
                    ),
                    "estimated_duration_min": row[6],
                    "overdue_days": row[7],
                    "safety_risk": row[8],
                    "original_priority_score": base_priority,
                    "ml_risk_score": ai_risk,
                    "ai_priority_score": ai_priority_score,
                    "priority_category": category,
                    "task_status": row[11],
                }
            )

        # -----------------------------------------------------
        # SORT
        # -----------------------------------------------------

        results.sort(
            key=lambda x: x["ai_priority_score"],
            reverse=True
        )

        for index, result in enumerate(
            results,
            start=1
        ):
            result["priority_rank"] = index

        return {
            "total_tasks": len(results),
            "tasks": results,
        }

    finally:

        if connection:
            connection.close()


@router.post("/tasks/apply-priorities", dependencies=[Depends(require_permission("ai.priorities.apply"))])
def apply_ai_task_priorities(user: CurrentUser = Depends(get_current_user)):

    connection = None

    try:
        connection = psycopg.connect(**DB_CONFIG)

        # Get current AI rankings
        ranking_response = get_task_priority_ranking(user=user)

        tasks = ranking_response["tasks"]

        updated = 0

        with connection.cursor() as cursor:

            for task in tasks:

                cursor.execute(
                    """
                    UPDATE maintenance_tasks
                    SET
                        priority_score = %s,
                        priority_category = %s
                    WHERE task_id = %s
                    """,
                    (
                        task["ai_priority_score"],
                        task["priority_category"],
                        task["task_id"],
                    )
                )

                updated += cursor.rowcount

        connection.commit()

        record_audit(
            user=user,
            method="POST",
            path="/ai/tasks/apply-priorities",
            action="ai.priorities.apply",
            target_type="tasks",
            target_id="all",
            outcome="SUCCESS",
            detail={"tasks_updated": updated}
        )

        return {
            "status": "success",
            "message": "AI priorities applied to maintenance tasks",
            "tasks_analyzed": len(tasks),
            "tasks_updated": updated,
        }

    except Exception as exc:

        if connection:
            connection.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )

    finally:

        if connection:
            connection.close()

@router.post("/traffic-impact", dependencies=[Depends(require_permission("optimizer.simulate"))])
def traffic_impact_prediction(payload: dict):
    """
    Predict traffic/disruption impact for a proposed railway block.
    """

    result = predict_traffic_impact(
        block_duration_min=int(payload["block_duration_min"]),
        start_hour=int(payload["start_hour"]),
        passenger_trains=int(payload["passenger_trains"]),
        goods_trains=int(payload["goods_trains"]),
        special_trains=int(payload["special_trains"]),
        express_trains=int(payload["express_trains"]),
        corridor_congestion=float(payload["corridor_congestion"]),
        criticality=int(payload["criticality"]),
        maintenance_priority=float(payload["maintenance_priority"])
    )

    return {
        "status": "success",
        "traffic_prediction": result
    }


@router.get("/blocks/{block_id}/traffic-impact", dependencies=[Depends(require_permission("ai.risk.view"))])
def get_block_traffic_impact(block_id: str):


    connection = None

    try:
        connection = psycopg.connect(**DB_CONFIG)

        # --------------------------------------------------
        # GET OPTIMIZED BLOCK
        # --------------------------------------------------

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    block_id,
                    corridor_id,
                    block_date,
                    start_time,
                    end_time,
                    duration_min
                FROM optimized_blocks
                WHERE block_id = %s
                """,
                (block_id,)
            )

            block = cursor.fetchone()

        if block is None:
            raise HTTPException(
                status_code=404,
                detail=f"Optimized block '{block_id}' not found"
            )

        (
            block_id,
            corridor_id,
            block_date,
            start_time,
            end_time,
            duration_min
        ) = block

        # --------------------------------------------------
        # GET TRAINS AFFECTED BY THIS BLOCK WINDOW (UNIFIED)
        # --------------------------------------------------

        with connection.cursor() as cursor:
            overlapping_items = load_traffic_in_window(
                cursor,
                corridor_id,
                block_date,
                start_time,
                end_time
            )
            counts = classify_counts(overlapping_items)

        passenger_trains = counts["passenger_trains"]
        goods_trains = counts["goods_trains"]
        special_trains = counts["special_trains"]
        express_trains = counts["express_trains"]

        # --------------------------------------------------
        # GET CORRIDOR CONGESTION
        # --------------------------------------------------

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT traffic_level
                FROM corridors
                WHERE corridor_id = %s
                """,
                (corridor_id,)
            )

            corridor_row = cursor.fetchone()

        traffic_level = (
            str(corridor_row[0]).upper()
            if corridor_row and corridor_row[0]
            else "MEDIUM"
        )

        congestion_map = {
            "LOW": 25,
            "MEDIUM": 50,
            "HIGH": 75,
            "VERY HIGH": 90,
            "CRITICAL": 100
        }

        corridor_congestion = congestion_map.get(
            traffic_level,
            50
        )

        # --------------------------------------------------
        # START HOUR
        # --------------------------------------------------

        start_hour = start_time.hour

        # --------------------------------------------------
        # GET MAINTENANCE PRIORITY
        # --------------------------------------------------

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COALESCE(MAX(mt.priority_score), 50),
                    COALESCE(MAX(a.criticality), 3)
                FROM block_tasks bt
                JOIN maintenance_tasks mt
                    ON bt.task_id = mt.task_id
                LEFT JOIN assets a
                    ON mt.asset_id = a.asset_id
                WHERE bt.block_id = %s
                """,
                (block_id,)
            )

            priority_row = cursor.fetchone()

        maintenance_priority = float(
            priority_row[0] if priority_row else 50
        )

        criticality = int(
            priority_row[1] if priority_row else 3
        )

        # --------------------------------------------------
        # ML PREDICTION
        # --------------------------------------------------

        prediction = predict_traffic_impact(
            block_duration_min=int(duration_min),
            start_hour=int(start_hour),
            passenger_trains=passenger_trains,
            goods_trains=goods_trains,
            special_trains=special_trains,
            express_trains=express_trains,
            corridor_congestion=float(corridor_congestion),
            criticality=criticality,
            maintenance_priority=maintenance_priority
        )

        return {
            "status": "success",
            "block_id": block_id,
            "corridor_id": corridor_id,
            "block_date": str(block_date),
            "start_time": str(start_time),
            "end_time": str(end_time),

            "traffic_summary": {
                "passenger_trains": passenger_trains,
                "goods_trains": goods_trains,
                "special_trains": special_trains,
                "express_trains": express_trains,
                "corridor_congestion": corridor_congestion
            },

            "traffic_prediction": prediction
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )

    finally:
        if connection:
            connection.close()


@router.post("/goods-demand", dependencies=[Depends(require_permission("optimizer.simulate"))])
def goods_demand_prediction(payload: dict):
    """
    Predict future goods-train demand for a corridor.
    """

    result = predict_goods_train_demand(
        day_of_week=int(payload["day_of_week"]),
        month=int(payload["month"]),
        is_weekend=int(payload["is_weekend"]),
        festival_period=int(payload["festival_period"]),
        operational_pressure=float(payload["operational_pressure"]),
        industrial_demand=float(payload["industrial_demand"]),
        previous_day_demand=float(payload["previous_day_demand"]),
        corridor_id=str(payload["corridor_id"]),
        commodity=str(payload["commodity"])
    )

    return {
        "status": "success",
        "goods_demand_prediction": result
    }


@router.get("/goods-demand/{corridor_id}", dependencies=[Depends(require_permission("ai.risk.view"))])
def get_goods_demand_forecast(
    corridor_id: str,
    forecast_date: str
):
    """
    Generate a goods-train demand forecast for a corridor/date
    and save it to PostgreSQL (duplicate-safe: updates if existing).
    """
    from logic.freight_pressure import get_daily_goods_forecast

    connection = None
    try:
        connection = psycopg.connect(**DB_CONFIG)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT corridor_id
                FROM corridors
                WHERE corridor_id = %s
                """,
                (corridor_id,)
            )
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=404,
                    detail=f"Corridor '{corridor_id}' not found"
                )

            res = get_daily_goods_forecast(cursor, corridor_id, forecast_date, persist=True)

        connection.commit()
        return res

    except HTTPException:
        raise
    except Exception as exc:
        if connection:
            connection.rollback()
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )
    finally:
        if connection:
            connection.close()


@router.get("/blocks/{block_id}/intelligence", dependencies=[Depends(require_permission("ai.risk.view"))])
def get_block_intelligence(block_id: str):

    """
    Unified AI intelligence for an optimized block.

    Combines:
    - Asset risk
    - Traffic impact
    - Goods train demand
    - Overall pressure assessment
    """

    conn = psycopg.connect(**DB_CONFIG)

    try:
        cur = conn.cursor()

        # Get optimized block
        cur.execute("""
        SELECT
            ob.block_id,
            ob.corridor_id,
            ob.block_date,
            ob.start_time,
            ob.end_time,
            ob.duration_min,
            ob.utilization_percent,
            ob.train_impact_score,
            ob.optimization_score,
            ob.number_of_tasks,
            ob.number_of_departments,
            ob.ai_decision_confidence,
            ob.ai_reasons,
            ob.ai_explanation
        FROM optimized_blocks ob
        WHERE ob.block_id = %s
    """, (block_id,))

        block = cur.fetchone()

        if not block:
            raise HTTPException(
                status_code=404,
                detail=f"Optimized block {block_id} not found"
            )

        (
            block_id_db,
            corridor_id,
            block_date,
            start_time,
            end_time,
            duration_min,
            utilization_percent,
            train_impact_score,
            optimization_score,
            number_of_tasks,
            number_of_departments,
                    ai_decision_confidence,
                    ai_reasons,
                    persisted_ai_explanation,
        ) = block

        # ==========================================
        # AI EXPLANATION
        # ==========================================

        # This is populated after the overlapping-train classification below.
        # It is returned to the frontend as the explanation for why the block
        # was selected.
        why_selected = []

        # Get tasks/assets associated with this block
        cur.execute("""
            SELECT
                mt.task_id,
                mt.asset_id,
                mt.priority_score,
                a.criticality,
                a.health_score,
                a.failure_risk,
                a.installation_date,
                a.last_inspection_date
            FROM block_tasks bt
            JOIN maintenance_tasks mt
                ON mt.task_id = bt.task_id
            LEFT JOIN assets a
                ON a.asset_id = mt.asset_id
            WHERE bt.block_id = %s
        """, (block_id,))

        tasks = cur.fetchall()

        if not tasks:
            raise HTTPException(
                status_code=404,
                detail=f"No maintenance tasks found for block {block_id}"
            )

        cur.execute("""
            SELECT
                MIN(br.requested_start),
                MAX(br.requested_end)
            FROM block_tasks bt
            JOIN block_requests br
                ON br.task_id = bt.task_id
            WHERE bt.block_id = %s
              AND br.corridor_id = %s
              AND br.requested_date = %s
              AND br.requested_start < %s
              AND br.requested_end > %s
        """, (
            block_id,
            corridor_id,
            block_date,
            end_time,
            start_time,
        ))

        requested_window_row = cur.fetchone()
        requested_start = (
            requested_window_row[0]
            if requested_window_row and requested_window_row[0]
            else None
        )
        requested_end = (
            requested_window_row[1]
            if requested_window_row and requested_window_row[1]
            else None
        )

        # Use first associated asset for asset-risk analysis
        task = tasks[0]

        asset = {
            "asset_id": task[1],
            "criticality": task[3] or 3,
            "health_score": task[4] or 70,
            "failure_risk": task[5] or 30,
            "installation_date": task[6],
            "last_inspection_date": task[7],
        }

        # Empty lists are valid for the current unified model.
        # ==========================================
        # GET REAL DEFECTS FOR THE ASSET
        # ==========================================

        cur.execute("""
            SELECT
                severity,
                safety_impact,
                repeat_failure
            FROM defects
            WHERE asset_id = %s
        """, (task[1],))

        defect_rows = cur.fetchall()

        defects = [
            {
                "severity": row[0],
                "safety_impact": row[1],
                "repeat_failure": row[2],
            }
            for row in defect_rows
        ]


        # ==========================================
        # GET REAL MAINTENANCE HISTORY
        # ==========================================

        cur.execute("""
            SELECT
                maintenance_type,
                failure_after_maintenance
            FROM maintenance_history
            WHERE asset_id = %s
        """, (task[1],))

        history_rows = cur.fetchall()

        maintenance_history = [
            {
                "maintenance_type": row[0],
                "failure_after_maintenance": row[1],
            }
            for row in history_rows
        ]

        # Block duration
        from datetime import datetime

        duration_min = int(
            (
                datetime.combine(block_date, end_time)
                - datetime.combine(block_date, start_time)
            ).total_seconds() / 60
        )

        # Corridor traffic level and priorities
        cur.execute("""
            SELECT traffic_level
            FROM corridors
            WHERE corridor_id = %s
        """, (corridor_id,))

        corridor_row = cur.fetchone()

        traffic_map = {
            "LOW": 25,
            "MEDIUM": 50,
            "HIGH": 75,
            "VERY HIGH": 90,
            "VERY_HIGH": 90,
            "CRITICAL": 100
        }

        traffic_level = (
            str(corridor_row[0]).upper()
            if corridor_row and corridor_row[0]
            else "MEDIUM"
        )

        corridor_congestion = traffic_map.get(
            traffic_level,
            50
        )

        maintenance_priority = max(
            [float(t[2] or 0) for t in tasks],
            default=0.0
        )

        criticality = max(
            [int(t[3] or 3) for t in tasks],
            default=3
        )

        # Unified Traffic Assessment via evaluate_window
        assessment = evaluate_window(
            cursor=cur,
            corridor_id=corridor_id,
            travel_date=block_date,
            start_time=start_time,
            end_time=end_time,
            criticality=criticality,
            maintenance_priority=maintenance_priority
        )

        counts = assessment["counts"]
        conflicts = assessment["conflicts"]
        f_pressure = assessment["freight_pressure"]

        passenger_trains = counts["passenger_trains"]
        goods_trains = counts["goods_trains"]
        special_trains = counts["special_trains"]
        express_trains = counts["express_trains"]
        regular_passenger_trains = counts["regular_passenger_trains"]

        # Shared daily goods forecast
        daily_forecast = get_daily_goods_forecast(
            cursor=cur,
            corridor_id=corridor_id,
            forecast_date=block_date,
            persist=False
        )

        # ==========================================
        # BUILD AI EXPLANATION AFTER TRAFFIC COUNTS
        # ==========================================

        total_trains = (
            passenger_trains
            + goods_trains
            + special_trains
            + express_trains
        )

        if total_trains == 0:
            why_selected.append(
                "No passenger, goods, special or express trains overlap the selected window"
            )
        else:
            traffic_parts = []

            if passenger_trains > 0:
                traffic_parts.append(
                    f"{passenger_trains} passenger"
                )

            if goods_trains > 0:
                traffic_parts.append(
                    f"{goods_trains} goods"
                )

            if special_trains > 0:
                traffic_parts.append(
                    f"{special_trains} special"
                )

            if express_trains > 0:
                traffic_parts.append(
                    f"{express_trains} express"
                )

            why_selected.append(
                "Traffic considered in selected window: "
                + ", ".join(traffic_parts)
            )

        # Special train conflict details
        special_conflicts = [c for c in conflicts if c.get("traffic_class") == "SPECIAL"]
        if special_conflicts:
            why_selected.append(
                f"{len(special_conflicts)} Special train conflict(s) detected in window"
            )

        # Freight pressure details (labelled as forecast-based)
        freight_level = f_pressure.get("level", "LOW")
        why_selected.append(
            f"Freight pressure level: {freight_level} (forecast-based)"
        )

        unscheduled_freight = f_pressure.get("unscheduled_expected", 0.0)
        if unscheduled_freight > 0:
            why_selected.append(
                f"{unscheduled_freight:.1f} unscheduled freight trains expected in window"
            )

        # --------------------------------------------------
        # Train impact
        # --------------------------------------------------

        if train_impact_score == 0:
            why_selected.append(
                "Zero predicted train-impact score"
            )
        else:
            why_selected.append(
                f"Train impact score considered ({train_impact_score:.2f})"
            )

        # --------------------------------------------------
        # Utilization
        # --------------------------------------------------

        if utilization_percent >= 90:
            why_selected.append(
                f"High block utilization ({utilization_percent:.2f}%)"
            )
        elif utilization_percent >= 70:
            why_selected.append(
                f"Good block utilization ({utilization_percent:.2f}%)"
            )
        else:
            why_selected.append(
                f"Block utilization ({utilization_percent:.2f}%)"
            )

        # --------------------------------------------------
        # Maintenance consolidation
        # --------------------------------------------------

        if number_of_tasks > 1:
            why_selected.append(
                f"{number_of_tasks} maintenance tasks consolidated"
            )
        else:
            why_selected.append(
                "Maintenance task scheduled within the optimized window"
            )

        # --------------------------------------------------
        # Department coordination
        # --------------------------------------------------

        if number_of_departments > 1:
            why_selected.append(
                f"{number_of_departments} departments coordinated"
            )

        # --------------------------------------------------
        # Final optimization score
        # --------------------------------------------------
        optimization_score = float(optimization_score or 0)
        why_selected.append(
            f"Optimization score: {optimization_score:.2f}"
        )

        # Run unified AI
        result = analyze_block(
            asset=asset,
            defects=defects,
            maintenance_history=maintenance_history,
            traffic_inputs={
                "block_duration_min": duration_min,
                "start_hour": start_time.hour,
                "passenger_trains": passenger_trains,
                "goods_trains": goods_trains,
                "special_trains": special_trains,
                "express_trains": express_trains,
                "regular_passenger_trains": regular_passenger_trains,
                "corridor_congestion": corridor_congestion,
                "criticality": criticality,
                "maintenance_priority": maintenance_priority,
            },
            goods_inputs={
                "day_of_week": block_date.weekday(),
                "month": block_date.month,
                "is_weekend": int(block_date.weekday() >= 5),
                "festival_period": daily_forecast.get("festival_period", 0),
                "operational_pressure": daily_forecast.get("operational_pressure", corridor_congestion),
                "industrial_demand": daily_forecast.get("industrial_demand", min(corridor_congestion + 10, 100)),
                "previous_day_demand": daily_forecast.get("previous_day_demand", 20.0),
                "corridor_id": corridor_id,
                "commodity": "COAL",
            }
        )

        return {
            "success": True,
            "block_id": block_id_db,
            "corridor_id": corridor_id,
            "block_date": str(block_date),
            "start_time": str(start_time),
            "end_time": str(end_time),
            "requested_window": (
                {
                    "start": str(requested_start),
                    "end": str(requested_end),
                }
                if requested_start and requested_end
                else None
            ),
            "selected_window": {
                "start": str(start_time),
                "end": str(end_time),
            },
            "conflict_count": len(conflicts),
            "train_conflicts": len(conflicts),
            "train_impact_score": float(train_impact_score or 0),
            "estimated_delay": int(assessment.get("estimated_delay_min", 0) or 0),
                        "ai_decision_confidence": ai_decision_confidence or {},
                        "ai_reasons": ai_reasons or [],
                        "persisted_ai_explanation": persisted_ai_explanation or {},
            "tasks_analyzed": len(tasks),
            "trains_in_window": len(conflicts),
            "traffic_summary": {
                "passenger_trains": passenger_trains,
                "goods_trains": goods_trains,
                "special_trains": special_trains,
                "express_trains": express_trains,
            },
            "intelligence": result,
            "traffic_intelligence": {
                "assessment": assessment,
                "freight_pressure": f_pressure,
                "adjustments": assessment.get("adjustments", []),
            },

            # ==========================================
            # AI EXPLANATION
            # ==========================================

            "ai_explanation": {
                "score": float(optimization_score or 0),

                "why_selected": why_selected,

                "metrics": {
                    "duration_min": int(
                        duration_min or 0
                    ),

                    "utilization_percent": float(
                        utilization_percent or 0
                    ),

                    "train_impact_score": float(
                        assessment.get("train_impact_score", 0)


                    ),

                    "number_of_tasks": int(
                        number_of_tasks or 0
                    ),

                    "number_of_departments": int(
                        number_of_departments or 0
                    )
                }
            }
        }

    finally:
        conn.close()

