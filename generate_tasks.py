import psycopg
import os
from dotenv import load_dotenv
from datetime import date

load_dotenv()

connection = psycopg.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)

cursor = connection.cursor()

cursor.execute("""
    SELECT
        d.defect_id,
        d.asset_id,
        d.defect_type,
        d.severity,
        d.detected_date,
        d.safety_impact,
        d.repeat_failure,
        d.target_resolution_date,
        a.department,
        a.criticality,
        a.failure_risk
    FROM defects d
    JOIN assets a
        ON d.asset_id = a.asset_id
    WHERE d.status != 'RESOLVED'
""")

defects = cursor.fetchall()

if not defects:
    print("❌ No unresolved defects found!")
    connection.close()
    exit()

cursor.execute("""
    SELECT task_id
    FROM maintenance_tasks
""")

existing_tasks = {row[0] for row in cursor.fetchall()}

today = date(2026, 8, 27)

created = 0
task_number = 1

for defect in defects:

    (
        defect_id,
        asset_id,
        defect_type,
        severity,
        detected_date,
        safety_impact,
        repeat_failure,
        target_resolution_date,
        department,
        criticality,
        failure_risk
    ) = defect

    # Find an unused task ID
    while f"T-AUTO-{task_number:04d}" in existing_tasks:
        task_number += 1

    task_id = f"T-AUTO-{task_number:04d}"
    task_number += 1

    # Maintenance duration
    if department == "ENGINEERING":
        duration = 120
    elif department == "S&T":
        duration = 90
    else:
        duration = 100

    # Calculate overdue days
    overdue_days = max(
        0,
        (today - target_resolution_date).days
    )

    # Priority score
    priority_score = (
        criticality * 20
        + float(failure_risk) * 0.30
        + int(safety_impact) * 10
        + min(overdue_days, 30) * 1.5
        + (10 if repeat_failure else 0)
    )

    priority_score = round(
        min(100, priority_score),
        2
    )

    # Priority category
    if priority_score >= 85:
        priority_category = "CRITICAL"
    elif priority_score >= 70:
        priority_category = "HIGH"
    elif priority_score >= 50:
        priority_category = "MEDIUM"
    else:
        priority_category = "LOW"

    # Task type
    if severity in ["CRITICAL", "HIGH"]:
        task_type = "Corrective Maintenance"
    else:
        task_type = "Preventive Maintenance"

    description = (
        f"Resolve {defect_type} on asset {asset_id}"
    )

    cursor.execute(
        """
        INSERT INTO maintenance_tasks
        (
            task_id,
            asset_id,
            department,
            task_type,
            description,
            created_date,
            due_date,
            estimated_duration_min,
            overdue_days,
            safety_risk,
            task_status,
            priority_score,
            priority_category
        )
        VALUES
        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            task_id,
            asset_id,
            department,
            task_type,
            description,
            today,
            target_resolution_date,
            duration,
            overdue_days,
            safety_impact,
            "PENDING",
            priority_score,
            priority_category
        )
    )

    created += 1

connection.commit()

cursor.close()
connection.close()

print(f"✅ {created} maintenance tasks generated successfully!")