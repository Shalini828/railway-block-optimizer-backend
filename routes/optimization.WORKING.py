from fastapi import APIRouter, Depends

import importlib
import sys
import time
import psycopg
import os
import io
import json
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


def ensure_shadow_table(conn):
    """Create the persistent shadow-opportunity store if it does not exist."""
    with conn.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shadow_block_opportunities (
                opportunity_id BIGSERIAL PRIMARY KEY,
                opportunity_data JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
    conn.commit()


def save_shadow_opportunities(opportunities):
    """Replace the previous shadow result with the latest optimization run."""
    conn = get_connection()
    try:
        ensure_shadow_table(conn)
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM shadow_block_opportunities")
            for opportunity in opportunities or []:
                cursor.execute(
                    """
                    INSERT INTO shadow_block_opportunities (opportunity_data)
                    VALUES (%s::jsonb)
                    """,
                    (json.dumps(opportunity, default=str),)
                )
        conn.commit()
    finally:
        conn.close()


def get_saved_shadow_opportunities():
    """Read the exact shadow opportunities persisted by the latest AI run."""
    conn = get_connection()
    try:
        ensure_shadow_table(conn)
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT opportunity_data
                FROM shadow_block_opportunities
                ORDER BY opportunity_id
            """)
            rows = cursor.fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def format_block(block):
    tasks = block.get("tasks", []) or []
    conflicts = block.get("train_conflicts", []) or []

    return {
        "block_id": str(
            block.get("block_id", "")
        ),

        "corridor": str(
            block.get(
                "corridor",
                block.get("corridor_id", "")
            )
        ),

        "date": str(
            block.get(
                "date",
                block.get("block_date", "")
            )
        ),

        "start": str(
            block.get(
                "start",
                block.get("start_time", "")
            )
        ),

        "end": str(
            block.get(
                "end",
                block.get("end_time", "")
            )
        ),

        "duration": float(
            block.get(
                "duration",
                block.get("duration_min", 0)
            ) or 0
        ),

        "utilization": float(
            block.get(
                "utilization",
                block.get("utilization_percent", 0)
            ) or 0
        ),

        "train_impact": float(
            block.get(
                "train_impact",
                block.get("train_impact_score", 0)
            ) or 0
        ),

        "number_of_tasks": len(tasks),

        "train_conflicts": len(conflicts)
    }


def get_saved_blocks():
    """
    Read the latest optimized blocks directly from PostgreSQL.
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
                ob.train_impact_score
            FROM optimized_blocks ob
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
                "number_of_tasks": 0,
                "train_conflicts": 0
            })

        return blocks

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

            shadow_block_opportunities = get_saved_shadow_opportunities()

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

            return {
                "status": "success",

                "message": (
                    "Showing the latest saved optimization plan."
                ),

                "requests_processed": 0,

                "blocks_generated": len(
                    saved_blocks
                ),

                "execution_time": execution_time,

                "total_duration": total_duration,

                "average_utilization": round(
                    average_utilization,
                    2
                ),

                "train_impact": sum(
                    block["train_impact"]
                    for block in saved_blocks
                ),

                "conflicts_avoided": 0,

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

        # Persist the exact shadow opportunities produced by this run.
        # /optimized-plan reads these rows and never recalculates them.
        save_shadow_opportunities(shadow_block_opportunities)


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