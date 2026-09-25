import psycopg
import os
from dotenv import load_dotenv
import random
from datetime import date, timedelta

load_dotenv()

# -----------------------------
# SETTINGS
# -----------------------------

EVENTS_PER_ASSET_MIN = 1
EVENTS_PER_ASSET_MAX = 5

today = date(2026, 8, 27)


# -----------------------------
# CONNECT TO POSTGRESQL
# -----------------------------

connection = psycopg.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)


cursor = connection.cursor()


# -----------------------------
# GET ASSETS
# -----------------------------

cursor.execute("""
    SELECT
        asset_id,
        department,
        failure_risk
    FROM assets
""")

assets = cursor.fetchall()

if not assets:
    print("❌ No assets found!")
    connection.close()
    exit()


# -----------------------------
# GET EXISTING HISTORY
# -----------------------------

cursor.execute("""
    SELECT
        asset_id,
        maintenance_date
    FROM maintenance_history
""")

existing_history = set(cursor.fetchall())


# -----------------------------
# TEAM MAPPING
# -----------------------------

team_mapping = {
    "ENGINEERING": "ENG-01",
    "S&T": "SNT-01",
    "TRD": "TRD-01"
}


# -----------------------------
# MAINTENANCE TYPES
# -----------------------------

maintenance_types = {
    "ENGINEERING": [
        "Preventive Inspection",
        "Track Maintenance",
        "Corrective Repair"
    ],
    "S&T": [
        "Signal Inspection",
        "Preventive Maintenance",
        "Corrective Repair"
    ],
    "TRD": [
        "OHE Inspection",
        "Preventive Maintenance",
        "Corrective Repair"
    ]
}


# -----------------------------
# GENERATE HISTORY
# -----------------------------

history_created = 0

for asset_id, department, failure_risk in assets:

    number_of_events = random.randint(
        EVENTS_PER_ASSET_MIN,
        EVENTS_PER_ASSET_MAX
    )

    for _ in range(number_of_events):

        maintenance_date = today - timedelta(
            days=random.randint(30, 700)
        )

        # Avoid exact duplicate asset/date combinations
        if (asset_id, maintenance_date) in existing_history:
            continue

        maintenance_type = random.choice(
            maintenance_types[department]
        )

        # Corrective work generally takes longer
        if maintenance_type == "Corrective Repair":
            duration_min = random.randint(60, 180)
        else:
            duration_min = random.randint(30, 120)

        team_id = team_mapping[department]

        # High-risk assets are more likely to experience
        # another failure after maintenance
        failure_probability = min(
            0.75,
            float(failure_risk) / 140
        )

        failure_after_maintenance = (
            random.random() < failure_probability
        )

        if failure_after_maintenance:
            remarks = "Repeat issue observed after maintenance"
        else:
            remarks = "Maintenance completed successfully"

        cursor.execute(
            """
            INSERT INTO maintenance_history
            (
                asset_id,
                maintenance_type,
                maintenance_date,
                duration_min,
                team_id,
                failure_after_maintenance,
                remarks
            )
            VALUES
            (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                asset_id,
                maintenance_type,
                maintenance_date,
                duration_min,
                team_id,
                failure_after_maintenance,
                remarks
            )
        )

        history_created += 1


# -----------------------------
# SAVE
# -----------------------------

connection.commit()

cursor.close()
connection.close()


print(
    f"✅ {history_created} maintenance history "
    f"records generated successfully!"
)