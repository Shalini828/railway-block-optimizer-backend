import psycopg
import os
from dotenv import load_dotenv
import random
from datetime import date, time, timedelta

load_dotenv()

TODAY = date(2026, 8, 27)

connection = psycopg.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)

cursor = connection.cursor()


# ---------------------------------------
# GET EXISTING BLOCK REQUEST IDS
# ---------------------------------------

cursor.execute("""
    SELECT request_id
    FROM block_requests
""")

existing_requests = {
    row[0] for row in cursor.fetchall()
}


# ---------------------------------------
# GET MAINTENANCE TASKS
# + ASSET + CORRIDOR INFORMATION
# ---------------------------------------

cursor.execute("""
    SELECT
        t.task_id,
        t.department,
        t.estimated_duration_min,
        t.priority_score,
        a.corridor_id
    FROM maintenance_tasks t
    JOIN assets a
        ON t.asset_id = a.asset_id
    WHERE t.task_status = 'PENDING'
""")

tasks = cursor.fetchall()


if not tasks:
    print("❌ No pending maintenance tasks found!")
    connection.close()
    exit()


# ---------------------------------------
# TEAM MAPPING
# ---------------------------------------

team_mapping = {
    "ENGINEERING": "ENG-01",
    "S&T": "SNT-01",
    "TRD": "TRD-01"
}


# ---------------------------------------
# POSSIBLE BLOCK START TIMES
# ---------------------------------------

start_times = [
    time(0, 0),
    time(1, 0),
    time(2, 0),
    time(3, 0),
    time(4, 0),
    time(10, 0),
    time(11, 0),
    time(12, 0),
    time(14, 0),
    time(22, 0)
]


# ---------------------------------------
# GENERATE BLOCK REQUESTS
# ---------------------------------------

created = 0
request_number = 1

# We generate requests for all pending tasks
for task in tasks:

    (
        task_id,
        department,
        estimated_duration,
        priority_score,
        corridor_id
    ) = task

    # Find unused request ID
    while f"BR-AUTO-{request_number:04d}" in existing_requests:
        request_number += 1

    request_id = f"BR-AUTO-{request_number:04d}"
    request_number += 1

    team_id = team_mapping[department]

    # Most maintenance requests are planned
    # within the next 7 days
    requested_date = TODAY + timedelta(
        days=random.randint(1, 7)
    )

    start = random.choice(start_times)

    # Add small randomness to duration
    duration = int(estimated_duration)

    # End time calculation
    start_minutes = start.hour * 60 + start.minute
    end_minutes = start_minutes + duration

    end_hour = (end_minutes // 60) % 24
    end_minute = end_minutes % 60

    end = time(end_hour, end_minute)

    # Block type
    if duration >= 120:
        block_type = "FULL_BLOCK"
    else:
        block_type = "PARTIAL_BLOCK"

    cursor.execute(
        """
        INSERT INTO block_requests
        (
            request_id,
            task_id,
            team_id,
            corridor_id,
            requested_date,
            requested_start,
            requested_end,
            requested_duration_min,
            block_type,
            request_status,
            submitted_date
        )
        VALUES
        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            request_id,
            task_id,
            team_id,
            corridor_id,
            requested_date,
            start,
            end,
            duration,
            block_type,
            "PENDING",
            TODAY
        )
    )

    created += 1


# ---------------------------------------
# CREATE EXTRA CONFLICT REQUESTS
# ---------------------------------------
#
# These deliberately overlap with existing
# requests on the same corridor.
#

cursor.execute("""
    SELECT
        request_id,
        task_id,
        team_id,
        corridor_id,
        requested_date,
        requested_start,
        requested_end,
        requested_duration_min,
        block_type
    FROM block_requests
    WHERE request_id LIKE 'BR-AUTO-%'
    LIMIT 20
""")

sample_requests = cursor.fetchall()


conflict_number = 1

for request in sample_requests:

    (
        original_id,
        task_id,
        team_id,
        corridor_id,
        requested_date,
        requested_start,
        requested_end,
        duration,
        block_type
    ) = request

    while f"BR-CONFLICT-{conflict_number:04d}" in existing_requests:
        conflict_number += 1

    conflict_id = f"BR-CONFLICT-{conflict_number:04d}"
    conflict_number += 1

    # Shift start time by 30 minutes
    original_minutes = (
        requested_start.hour * 60
        + requested_start.minute
    )

    new_minutes = original_minutes + 30

    new_hour = (new_minutes // 60) % 24
    new_minute = new_minutes % 60

    new_start = time(new_hour, new_minute)

    new_end_minutes = new_minutes + duration

    new_end = time(
        (new_end_minutes // 60) % 24,
        new_end_minutes % 60
    )

    cursor.execute(
        """
        INSERT INTO block_requests
        (
            request_id,
            task_id,
            team_id,
            corridor_id,
            requested_date,
            requested_start,
            requested_end,
            requested_duration_min,
            block_type,
            request_status,
            submitted_date
        )
        VALUES
        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            conflict_id,
            task_id,
            team_id,
            corridor_id,
            requested_date,
            new_start,
            new_end,
            duration,
            block_type,
            "PENDING",
            TODAY
        )
    )

    created += 1


connection.commit()

cursor.close()
connection.close()


print(
    f"✅ {created} block requests generated successfully!"
)