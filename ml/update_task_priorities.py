# pyrefly: ignore [missing-import]

import psycopg
from datetime import date
import sys
from pathlib import Path


# ============================================================
# ADD BACKEND DIRECTORY TO PYTHON PATH
# ============================================================

BACKEND_DIR = Path(__file__).resolve().parent.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))


from db_config import DB_CONFIG
from ai_task_priority import calculate_priority


TODAY = date(2026, 8, 27)


# ============================================================
# CONNECT TO DATABASE
# ============================================================

connection = psycopg.connect(**DB_CONFIG)
cursor = connection.cursor()


# ============================================================
# GET PENDING MAINTENANCE TASKS + ASSET INFORMATION
# ============================================================

cursor.execute("""
    SELECT
        t.task_id,
        t.asset_id,

        a.criticality,
        a.health_score,
        a.failure_risk,
        a.installation_date,
        a.last_inspection_date,

        t.safety_risk

    FROM maintenance_tasks t

    JOIN assets a
        ON t.asset_id = a.asset_id

    WHERE t.task_status = 'PENDING'
""")

tasks = cursor.fetchall()


if not tasks:
    print("No pending maintenance tasks found!")
    cursor.close()
    connection.close()
    exit()


print()
print("=" * 70)
print("           AI MAINTENANCE PRIORITY UPDATE")
print("=" * 70)
print(f"Pending tasks found: {len(tasks)}")
print()


# ============================================================
# PROCESS EACH TASK
# ============================================================

updated = 0

for task in tasks:

    (
        task_id,
        asset_id,
        criticality,
        health_score,
        failure_risk,
        installation_date,
        last_inspection_date,
        safety_risk
    ) = task


    # --------------------------------------------------------
    # DEFECT INFORMATION
    # --------------------------------------------------------

    cursor.execute("""
        SELECT
            COUNT(*),
            COUNT(*) FILTER (
                WHERE severity IN ('CRITICAL', 'HIGH')
            ),
            COALESCE(MAX(safety_impact), 0),
            COALESCE(BOOL_OR(repeat_failure), FALSE)
        FROM defects
        WHERE asset_id = %s
    """, (asset_id,))

    (
        defect_count,
        urgent_defect_count,
        max_safety_impact,
        defect_repeat
    ) = cursor.fetchone()


    # --------------------------------------------------------
    # MAINTENANCE HISTORY
    # --------------------------------------------------------

    cursor.execute("""
        SELECT
            COUNT(*),
            COUNT(*) FILTER (
                WHERE maintenance_type = 'Corrective Repair'
            ),
            COUNT(*) FILTER (
                WHERE failure_after_maintenance = TRUE
            )
        FROM maintenance_history
        WHERE asset_id = %s
    """, (asset_id,))

    (
        maintenance_count,
        corrective_maintenance_count,
        previous_failure_count
    ) = cursor.fetchone()


    # --------------------------------------------------------
    # REPEAT FAILURE
    # --------------------------------------------------------

    repeat_failure = (
        1
        if defect_repeat or previous_failure_count > 0
        else 0
    )


    # --------------------------------------------------------
    # ASSET AGE
    # --------------------------------------------------------

    asset_age_years = max(
        0,
        TODAY.year - installation_date.year
    )


    # --------------------------------------------------------
    # DAYS SINCE INSPECTION
    # --------------------------------------------------------

    days_since_inspection = max(
        0,
        (TODAY - last_inspection_date).days
    )


    # --------------------------------------------------------
    # SAFETY IMPACT
    # --------------------------------------------------------

    max_safety_impact = max(
        int(max_safety_impact),
        int(safety_risk or 0)
    )

    max_safety_impact = min(
        max_safety_impact,
        5
    )


    # ========================================================
    # BUILD ML FEATURE VECTOR
    # ========================================================

    features = {
        "criticality": int(criticality),

        "health_score": float(health_score),

        "failure_risk": float(failure_risk),

        "asset_age_years": asset_age_years,

        "days_since_inspection": days_since_inspection,

        "defect_count": int(defect_count),

        "urgent_defect_count": int(urgent_defect_count),

        "max_safety_impact": max_safety_impact,

        "repeat_failure": repeat_failure,

        "maintenance_count": int(maintenance_count),

        "corrective_maintenance_count": int(
            corrective_maintenance_count
        ),

        "previous_failure_count": int(
            previous_failure_count
        )
    }


    # ========================================================
    # AI PRIORITY PREDICTION
    # ========================================================

    result = calculate_priority(features)


    # ========================================================
    # UPDATE DATABASE
    # ========================================================

    cursor.execute("""
        UPDATE maintenance_tasks

        SET
            priority_score = %s,
            priority_category = %s

        WHERE task_id = %s
    """, (
        result["ai_priority_score"],
        result["priority_category"],
        task_id
    ))


    updated += 1


    # ========================================================
    # DISPLAY RESULT
    # ========================================================

    print(
        f"{task_id:<15}"
        f"Risk: {result['risk_score']:>6.2f}  "
        f"AI Priority: {result['ai_priority_score']:>6.2f}  "
        f"{result['priority_category']}"
    )


# ============================================================
# COMMIT CHANGES
# ============================================================

connection.commit()

cursor.close()
connection.close()


print()
print("=" * 70)
print(f"Tasks updated: {updated}")
print("AI priorities successfully written to PostgreSQL.")
print("=" * 70)