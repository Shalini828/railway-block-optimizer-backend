import psycopg
import os
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# DATABASE CONNECTION
# ==========================================

connection = psycopg.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)

cursor = connection.cursor()


# ==========================================
# GET PENDING TASKS
# ==========================================

cursor.execute("""
    SELECT
        t.task_id,
        t.asset_id,
        t.department,
        t.overdue_days,
        t.safety_risk,
        a.criticality,
        a.health_score,
        a.failure_risk,

        EXISTS (
            SELECT 1
            FROM defects d
            WHERE d.asset_id = t.asset_id
            AND d.repeat_failure = TRUE
        ) AS repeat_failure

    FROM maintenance_tasks t

    JOIN assets a
        ON t.asset_id = a.asset_id

    WHERE t.task_status = 'PENDING'
""")

tasks = cursor.fetchall()


if not tasks:
    print("❌ No pending tasks found!")
    connection.close()
    exit()


# ==========================================
# PRIORITY ENGINE
# ==========================================

results = []


for task in tasks:

    (
        task_id,
        asset_id,
        department,
        overdue_days,
        safety_risk,
        criticality,
        health_score,
        failure_risk,
        repeat_failure
    ) = task


    # Convert values

    criticality = float(criticality)
    health_score = float(health_score)
    failure_risk = float(failure_risk)

    overdue_days = int(overdue_days)
    safety_risk = int(safety_risk)


    # ======================================
    # NORMALIZED FEATURES
    # ======================================

    criticality_score = (
        criticality / 5
    ) * 100

    safety_score = (
        safety_risk / 5
    ) * 100

    failure_score = failure_risk

    health_urgency = 100 - health_score

    overdue_score = min(
        overdue_days / 30,
        1
    ) * 100

    repeat_score = (
        100 if repeat_failure else 0
    )


    # ======================================
    # WEIGHTED SCORE
    # ======================================

    priority_score = (
        safety_score * 0.25
        + criticality_score * 0.20
        + failure_score * 0.20
        + health_urgency * 0.15
        + overdue_score * 0.10
        + repeat_score * 0.10
    )

    priority_score = round(
        priority_score,
        2
    )


    # ======================================
    # CATEGORY
    # ======================================

    if priority_score >= 85:
        category = "CRITICAL"

    elif priority_score >= 70:
        category = "HIGH"

    elif priority_score >= 50:
        category = "MEDIUM"

    else:
        category = "LOW"


    # ======================================
    # SAVE TO DATABASE
    # ======================================

    cursor.execute(
        """
        UPDATE maintenance_tasks

        SET
            priority_score = %s,
            priority_category = %s

        WHERE task_id = %s
        """,
        (
            priority_score,
            category,
            task_id
        )
    )


    results.append(
        (
            task_id,
            asset_id,
            department,
            priority_score,
            category
        )
    )


# ==========================================
# COMMIT CHANGES
# ==========================================

connection.commit()


# ==========================================
# SORT RESULTS
# ==========================================

results.sort(
    key=lambda x: x[3],
    reverse=True
)


# ==========================================
# DISPLAY
# ==========================================

print()
print("==============================================")
print("       PRIORITY ENGINE V3")
print("==============================================")
print()

print(
    f"{'TASK':<18}"
    f"{'ASSET':<12}"
    f"{'DEPARTMENT':<15}"
    f"{'SCORE':<10}"
    f"CATEGORY"
)

print("-" * 70)


for result in results[:20]:

    (
        task_id,
        asset_id,
        department,
        score,
        category
    ) = result

    print(
        f"{task_id:<18}"
        f"{asset_id:<12}"
        f"{department:<15}"
        f"{score:<10}"
        f"{category}"
    )


print()
print("==============================================")
print(f"Tasks updated in PostgreSQL: {len(results)}")
print("==============================================")


cursor.close()
connection.close()