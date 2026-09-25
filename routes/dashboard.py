from fastapi import APIRouter, Depends
import importlib
import sys
import os
import psycopg
from dotenv import load_dotenv

from auth.security import require_permission

load_dotenv()

router = APIRouter(
    prefix="/optimization",
    tags=["Optimization"]
)


# ==========================================
# DATABASE CONNECTION
# ==========================================

def get_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )


# ==========================================
# RUN OPTIMIZATION
# ==========================================

@router.post("/", dependencies=[Depends(require_permission("optimizer.run"))])
def run_optimization():

    try:

        # ==========================================
        # 1. LOAD / RELOAD OPTIMIZER
        # ==========================================

        module_name = "logic.block_optimizer"

        if module_name in sys.modules:
            optimizer = importlib.reload(
                sys.modules[module_name]
            )
        else:
            optimizer = importlib.import_module(
                module_name
            )

        # ==========================================
        # 2. GET OPTIMIZATION RESULTS
        # ==========================================

        optimized_blocks = getattr(
            optimizer,
            "optimized_blocks",
            []
        )

        requests = getattr(
            optimizer,
            "requests",
            []
        )

        # ==========================================
        # 3. CALCULATE RUN METRICS
        # ==========================================

        total_block_minutes = sum(
            block.get("duration", 0) or 0
            for block in optimized_blocks
        )

        average_utilization = (
            sum(
                block.get("utilization", 0) or 0
                for block in optimized_blocks
            ) / len(optimized_blocks)
            if optimized_blocks
            else 0
        )

        average_optimization_score = (
            sum(
                block.get("optimization_score", 0) or 0
                for block in optimized_blocks
            ) / len(optimized_blocks)
            if optimized_blocks
            else 0
        )

        total_train_impact = sum(
            block.get("train_impact", 0) or 0
            for block in optimized_blocks
        )

        total_train_conflicts = sum(
            len(block.get("train_conflicts", []))
            for block in optimized_blocks
        )

        # ==========================================
        # 4. SAVE OPTIMIZATION HISTORY
        # ==========================================

        conn = get_connection()
        cursor = conn.cursor()

        try:

            cursor.execute(
                """
                INSERT INTO optimization_history (
                    blocks_generated,
                    requests_processed,
                    total_block_minutes,
                    average_utilization,
                    average_optimization_score,
                    total_train_impact,
                    total_train_conflicts,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    len(optimized_blocks),
                    len(requests),
                    total_block_minutes,
                    round(average_utilization, 2),
                    round(average_optimization_score, 2),
                    total_train_impact,
                    total_train_conflicts,
                    "SUCCESS"
                )
            )

            conn.commit()

        finally:

            cursor.close()
            conn.close()

        # ==========================================
        # 5. RETURN OPTIMIZATION RESULT
        # ==========================================

        return {
            "status": "success",
            "message": "Optimization completed successfully",

            "requests_processed":
                len(requests),

            "blocks_generated":
                len(optimized_blocks),

            "run_metrics": {
                "total_block_minutes":
                    total_block_minutes,

                "average_utilization":
                    round(average_utilization, 2),

                "average_optimization_score":
                    round(average_optimization_score, 2),

                "total_train_impact":
                    total_train_impact,

                "total_train_conflicts":
                    total_train_conflicts
            },

            "blocks": [
                {
                    "block_id":
                        block["block_id"],

                    "corridor":
                        block["corridor"],

                    "date":
                        str(block["date"]),

                    "start":
                        str(block["start"]),

                    "end":
                        str(block["end"]),

                    "duration":
                        block["duration"],

                    "utilization":
                        block["utilization"],

                    "train_impact":
                        block.get(
                            "train_impact",
                            0
                        ),

                    "number_of_tasks":
                        len(
                            block.get(
                                "tasks",
                                []
                            )
                        ),

                    "train_conflicts":
                        len(
                            block.get(
                                "train_conflicts",
                                []
                            )
                        )
                }

                for block in optimized_blocks
            ]
        }

    except Exception as e:

        return {
            "status": "error",
            "message": str(e)
        }