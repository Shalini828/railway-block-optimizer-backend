from fastapi import APIRouter, Depends

import importlib
import sys
import time
import psycopg
import os
import io
from contextlib import redirect_stdout
from dotenv import load_dotenv

from auth.security import require_permission

load_dotenv()


router = APIRouter(
    prefix="/optimization",
    tags=["Optimization"]
)


def get_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )


def format_block(block):
    tasks = block.get("tasks", []) or []
    conflicts = block.get("train_conflicts", []) or []
    conflict_count = (
        conflicts
        if isinstance(conflicts, int)
        else len(conflicts)
    )

    def safe_float(value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    return {
        "block_id": str(block.get("block_id", "")),
        "corridor": str(
            block.get("corridor", block.get("corridor_id", ""))
        ),
        "date": str(
            block.get("date", block.get("block_date", ""))
        ),
        "start": str(
            block.get("start", block.get("start_time", ""))
        ),
        "end": str(
            block.get("end", block.get("end_time", ""))
        ),
        "duration": safe_float(
            block.get("duration", block.get("duration_min", 0))
        ),
        "utilization": safe_float(
            block.get("utilization", block.get("utilization_percent", 0))
        ),
        "train_impact": safe_float(
            block.get("train_impact", block.get("train_impact_score", 0))
        ),
        "train_impact_score": safe_float(
            block.get("train_impact_score", block.get("train_impact", 0))
        ),
        "estimated_delay": safe_float(
            block.get("estimated_delay", block.get("estimated_delay_min", 0))
        ),
        "number_of_tasks": int(
            block.get("number_of_tasks", len(tasks)) or 0
        ),
        "train_conflicts": int(
            block.get("train_conflicts_count", conflict_count) or 0
        ),
        "conflict_count": int(
            block.get("conflict_count", conflict_count) or 0
        ),

        # Preserve the optimizer's decision evidence.
        "optimization_score": safe_float(block.get("optimization_score", 0)),
        "maintenance_priority": safe_float(block.get("maintenance_priority", 0)),
        "asset_risk_score": safe_float(block.get("asset_risk_score", 0)),
        "traffic_impact_score": safe_float(block.get("traffic_impact_score", 0)),
        "goods_impact_score": safe_float(block.get("goods_impact_score", 0)),
        "consolidation_score": safe_float(block.get("consolidation_score", 0)),
        "ai_decision_confidence": block.get("ai_decision_confidence"),
        "ai_reasons": block.get("ai_reasons") or [],
        "ai_explanation": block.get("ai_explanation"),
        "reason": block.get("reason") or block.get("optimization_reason"),
    }



def get_saved_blocks():
    """
    Read the latest optimized blocks directly from PostgreSQL.

    This is a read-only reconstruction of the saved engine result.
    It preserves the AI decision fields so the frontend can explain
    why each block was selected.
    """

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT
                ob.block_id,
                ob.corridor_id,
                ob.block_date,
                ob.start_time,
                ob.end_time,
                ob.duration_min,
                ob.utilization_percent,
                ob.train_impact_score,
                COALESCE(SUM(bti.estimated_delay_min), 0) AS estimated_delay_min,
                ob.optimization_score,
                ob.number_of_tasks,
                ob.maintenance_priority,
                ob.asset_risk_score,
                ob.traffic_impact_score,
                ob.goods_impact_score,
                ob.consolidation_score,
                ob.ai_decision_confidence,
                ob.ai_reasons,
                ob.ai_explanation,
                ob.optimization_reason,
                COUNT(DISTINCT bti.train_id) AS train_conflict_count
            FROM optimized_blocks ob
            LEFT JOIN block_train_impact bti
                ON bti.block_id = ob.block_id
            GROUP BY
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
                ob.maintenance_priority,
                ob.asset_risk_score,
                ob.traffic_impact_score,
                ob.goods_impact_score,
                ob.consolidation_score,
                ob.ai_decision_confidence,
                ob.ai_reasons,
                ob.ai_explanation,
                ob.optimization_reason
            ORDER BY
                ob.block_date,
                ob.start_time
        """)

        rows = cursor.fetchall()

        blocks = []

        for row in rows:
            blocks.append({
                "block_id": row[0],
                "corridor": row[1],
                "date": str(row[2]),
                "start": str(row[3]),
                "end": str(row[4]),
                "duration": float(row[5] or 0),
                "utilization": float(row[6] or 0),
                "train_impact": float(row[7] or 0),
                "train_impact_score": float(row[7] or 0),
                "estimated_delay": float(row[8] or 0),
                "number_of_tasks": int(row[10] or 0),
                "train_conflicts": int(row[20] or 0),
                "conflict_count": int(row[20] or 0),

                # AI decision fields
                "optimization_score": float(row[9] or 0),
                "maintenance_priority": float(row[11] or 0),
                "asset_risk_score": float(row[12] or 0),
                "traffic_impact_score": float(row[13] or 0),
                "goods_impact_score": float(row[14] or 0),
                "consolidation_score": float(row[15] or 0),
                "ai_decision_confidence": row[16],
                "ai_reasons": row[17],
                "ai_explanation": row[18],
                "reason": row[19],
            })

        return blocks

    finally:
        cursor.close()
        conn.close()


def get_saved_request_count():
    """
    Count distinct BDMS requests represented in the persisted optimized plan.
    This is the authoritative demand/request metric for the saved-plan path.
    """

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT COUNT(DISTINCT br.request_id)
            FROM block_requests br
            JOIN block_tasks bt
                ON bt.task_id = br.task_id
            JOIN optimized_blocks ob
                ON ob.block_id = bt.block_id
        """)

        row = cursor.fetchone()
        return int((row[0] if row else 0) or 0)

    finally:
        cursor.close()
        conn.close()



def _time_to_minutes(value):
    """Convert PostgreSQL time/string values to minutes since midnight."""
    if value is None:
        return 0

    if hasattr(value, "hour") and hasattr(value, "minute"):
        return (
            int(value.hour) * 60
            + int(value.minute)
            + int(getattr(value, "second", 0)) / 60
        )

    text = str(value).strip()
    if not text:
        return 0

    parts = text.split(":")
    try:
        hours = int(parts[0])
        minutes = int(parts[1]) if len(parts) > 1 else 0
        seconds = float(parts[2]) if len(parts) > 2 else 0
        return hours * 60 + minutes + seconds / 60
    except (ValueError, TypeError):
        return 0


def _get_persistent_shadow_opportunities():
    """
    Rebuild shadow opportunities from the saved PostgreSQL optimization
    when the in-memory optimizer state is empty.

    This is only a shadow-analysis rebuild. It does NOT rerun the
    optimization engine or modify the saved schedule.
    """
    try:
        import logic.block_optimizer as block_optimizer

        finder = getattr(
            block_optimizer,
            "find_shadow_block_opportunities",
            None,
        )

        if not callable(finder):
            return []

        max_gap = int(
            getattr(
                block_optimizer,
                "MAX_CONSOLIDATION_GAP",
                15,
            )
        )
        max_duration = int(
            getattr(
                block_optimizer,
                "MAX_BLOCK_DURATION",
                240,
            )
        )

        conn = get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT DISTINCT
                    br.request_id,
                    br.task_id,
                    br.team_id,
                    br.corridor_id,
                    br.requested_date,
                    br.requested_start,
                    br.requested_end,
                    br.requested_duration_min
                FROM block_requests br
                JOIN block_tasks bt
                    ON bt.task_id = br.task_id
                JOIN optimized_blocks ob
                    ON ob.block_id = bt.block_id
                   AND ob.corridor_id = br.corridor_id
                   AND ob.block_date = br.requested_date
                ORDER BY
                    br.corridor_id,
                    br.requested_date,
                    br.requested_start
            """)

            rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

        if not rows:
            print("PERSISTENT SHADOW REBUILD: no saved request rows found")
            return []

        groups = []

        for row in rows:
            (
                request_id,
                task_id,
                team_id,
                corridor_id,
                request_date,
                request_start,
                request_end,
                requested_duration,
            ) = row

            start = _time_to_minutes(request_start)
            end = _time_to_minutes(request_end)
            placed = False

            for group in groups:
                if group["corridor"] != corridor_id:
                    continue

                if group["date"] != request_date:
                    continue

                group_start = _time_to_minutes(group["start"])
                group_end = _time_to_minutes(group["end"])

                if start > group_end:
                    gap = start - group_end
                elif group_start > end:
                    gap = group_start - end
                else:
                    gap = 0

                combined_start = min(group_start, start)
                combined_end = max(group_end, end)
                combined_duration = combined_end - combined_start

                if (
                    gap <= max_gap
                    and combined_duration <= max_duration
                ):
                    group["start"] = min(
                        group["start"],
                        request_start,
                    )
                    group["end"] = max(
                        group["end"],
                        request_end,
                    )
                    group["requests"].append(
                        (
                            request_id,
                            task_id,
                            team_id,
                            corridor_id,
                            request_date,
                            request_start,
                            request_end,
                            requested_duration,
                            0,
                        )
                    )
                    placed = True
                    break

            if not placed:
                groups.append(
                    {
                        "corridor": corridor_id,
                        "date": request_date,
                        "start": request_start,
                        "end": request_end,
                        "requests": [
                            (
                                request_id,
                                task_id,
                                team_id,
                                corridor_id,
                                request_date,
                                request_start,
                                request_end,
                                requested_duration,
                                0,
                            )
                        ],
                    }
                )

        opportunities = finder(groups) or []

        print(
            "PERSISTENT SHADOW OPPORTUNITIES:",
            len(opportunities),
        )

        return opportunities

    except Exception as shadow_error:
        print(
            "Persistent shadow rebuild failed:",
            shadow_error,
        )
        return []


@router.post(
    "/",
    dependencies=[
        Depends(require_permission("optimizer.run"))
    ]
)
def run_optimization():

    start_time = time.time()

    try:

        # --------------------------------------------------
        # STEP 1
        # Check database BEFORE running optimizer
        # --------------------------------------------------

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*)
            FROM block_requests
            WHERE request_status = 'PENDING'
        """)

        pending_requests = cursor.fetchone()[0]

        cursor.close()
        conn.close()


        # --------------------------------------------------
        # STEP 2
        # If there are NO pending requests,
        # return the existing saved plan.
        # --------------------------------------------------

        if pending_requests == 0:

            saved_blocks = get_saved_blocks()

            # Try to get the latest shadow opportunities
            # already generated by the optimizer module.
            shadow_block_opportunities = getattr(
                block_optimizer,
                "shadow_block_opportunities",
                []
            ) or []

            # The in-memory list disappears after a backend restart.
            # Rebuild the SAME shadow analysis from the saved PostgreSQL
            # plan so Execute AI Engine remains stable after refresh/re-run.
            if not shadow_block_opportunities:
                shadow_block_opportunities = (
                    _get_persistent_shadow_opportunities()
                )

            execution_time = round(
                time.time() - start_time,
                2
            )

            total_duration = sum(
                block["duration"]
                for block in saved_blocks
            )

            average_utilization = (
                sum(
                    block["utilization"]
                    for block in saved_blocks
                )
                / len(saved_blocks)
                if saved_blocks
                else 0
            )

            requests_processed = get_saved_request_count()
            blocks_generated = len(saved_blocks)

            average_optimization_score = (
                sum(
                    block["optimization_score"]
                    for block in saved_blocks
                ) / blocks_generated
                if blocks_generated
                else 0
            )

            conflicts_avoided = sum(
                block["train_conflicts"]
                for block in saved_blocks
            )

            return {
                "status": "success",

                "message": (
                    "Showing the latest saved optimization plan."
                ),

                "requests_processed": requests_processed,

                "blocks_generated": blocks_generated,

                "execution_time": execution_time,

                "total_duration": total_duration,

                "average_utilization": round(
                    average_utilization,
                    2
                ),

                "average_optimization_score": round(
                    average_optimization_score,
                    2
                ),

                "train_impact": sum(
                    block["train_impact"]
                    for block in saved_blocks
                ),

                "conflicts_avoided": conflicts_avoided,

                "run_metrics": {
                    "total_block_minutes": round(total_duration, 2),
                    "average_utilization": round(average_utilization, 2),
                    "average_optimization_score": round(
                        average_optimization_score,
                        2
                    ),
                    "total_train_impact": round(
                        sum(
                            block["train_impact"]
                            for block in saved_blocks
                        ),
                        2
                    ),
                    "total_train_conflicts": conflicts_avoided,
                    "compute_time_seconds": execution_time,
                    "execution_latency_seconds": execution_time,
                },

                "blocks": saved_blocks,

                "shadow_block_opportunities":
                    shadow_block_opportunities
            }


        # --------------------------------------------------
        # STEP 3
        # Pending requests exist.
        # NOW run the optimizer.
        # --------------------------------------------------

        module_name = "logic.block_optimizer"

        # Run the optimizer silently.
        # The optimizer still executes normally, but its internal
        # print() statements are hidden from the terminal.
        with redirect_stdout(io.StringIO()):

            if module_name in sys.modules:

                optimizer = importlib.reload(
                    sys.modules[module_name]
                )

            else:

                optimizer = importlib.import_module(
                    module_name
                )


        # --------------------------------------------------
        # STEP 4
        # Read optimizer output
        # --------------------------------------------------

        requests = getattr(
            optimizer,
            "requests",
            []
        ) or []

        optimized_blocks = getattr(
            optimizer,
            "optimized_blocks",
            []
        ) or []

        shadow_block_opportunities = getattr(
            optimizer,
            "shadow_block_opportunities",
            []
        ) or []

        # Normally this is populated by the current optimizer run.
        # Keep a persistent fallback in case the module state is empty.
        if not shadow_block_opportunities:
            shadow_block_opportunities = (
                _get_persistent_shadow_opportunities()
            )


        # --------------------------------------------------
        # STEP 5
        # Format blocks
        # --------------------------------------------------

        blocks = [
            format_block(block)
            for block in optimized_blocks
        ]

        requests_processed = len(requests)

        blocks_generated = len(blocks)


        # --------------------------------------------------
        # STEP 6
        # Metrics
        # --------------------------------------------------

        total_duration = sum(
            block["duration"]
            for block in blocks
        )

        average_utilization = (
            sum(
                block["utilization"]
                for block in blocks
            )
            / blocks_generated
            if blocks_generated
            else 0
        )

        train_impact = sum(
            block["train_impact"]
            for block in blocks
        )

        conflicts_avoided = sum(
            block["train_conflicts"]
            for block in blocks
        )

        execution_time = round(
            time.time() - start_time,
            2
        )


        # --------------------------------------------------
        # STEP 7
        # Return newly generated plan
        # --------------------------------------------------

        return {

            "status": "success",

            "message": (
                "Optimization completed successfully"
            ),

            "requests_processed":
                requests_processed,

            "blocks_generated":
                blocks_generated,

            "execution_time":
                execution_time,

            "total_duration":
                total_duration,

            "average_utilization":
                round(
                    average_utilization,
                    2
                ),

            "train_impact":
                train_impact,

            "conflicts_avoided":
                conflicts_avoided,

            "run_metrics": {
                "total_block_minutes": round(total_duration, 2),
                "average_utilization": round(average_utilization, 2),
                "average_optimization_score": round(
                    sum(
                        block.get("optimization_score", 0)
                        for block in optimized_blocks
                    ) / blocks_generated,
                    2
                ) if blocks_generated else 0,
                "total_train_impact": round(train_impact, 2),
                "total_train_conflicts": int(conflicts_avoided),
                "compute_time_seconds": execution_time,
                "execution_latency_seconds": execution_time,
            },

            "blocks":
                blocks,

            # ------------------------------------------
            # SHADOW BLOCK OPPORTUNITIES
            # ------------------------------------------

            "shadow_block_opportunities":
                shadow_block_opportunities
        }


    except Exception as e:

        return {

            "status": "error",

            "message":
                str(e),

            "requests_processed":
                0,

            "blocks_generated":
                0,

            "execution_time":
                round(
                    time.time() - start_time,
                    2
                ),

            "total_duration":
                0,

            "average_utilization":
                0,

            "train_impact":
                0,

            "conflicts_avoided":
                0,

            "blocks":
                [],

            "shadow_block_opportunities":
                []
        }