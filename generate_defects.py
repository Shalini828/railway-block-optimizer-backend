import psycopg
import os
from dotenv import load_dotenv
import random
from datetime import date, timedelta

load_dotenv()


# -----------------------------
# SETTINGS
# -----------------------------

NUM_DEFECTS = 80

today = date(2026, 8, 27)


# -----------------------------
# DEFECT TYPES BY DEPARTMENT
# -----------------------------

defect_types = {
    "ENGINEERING": [
        "Rail Crack",
        "Track Geometry Deviation",
        "Sleeper Damage",
        "Point & Crossing Wear"
    ],
    "S&T": [
        "Signal Malfunction",
        "Axle Counter Failure",
        "Point Machine Failure",
        "Relay Fault"
    ],
    "TRD": [
        "Insulator Damage",
        "OHE Wire Wear",
        "Transformer Issue",
        "Pantograph Interaction Issue"
    ]
}


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
# GET ASSET DATA
# -----------------------------

cursor.execute("""
    SELECT
        asset_id,
        department,
        criticality,
        health_score,
        failure_risk
    FROM assets
""")

assets = cursor.fetchall()

if not assets:
    print("❌ No assets found!")
    connection.close()
    exit()


# -----------------------------
# GET EXISTING DEFECT IDS
# -----------------------------

cursor.execute("""
    SELECT defect_id
    FROM defects
""")

existing_defects = {row[0] for row in cursor.fetchall()}


# -----------------------------
# GENERATE DEFECTS
# -----------------------------

created = 0
defect_number = 1


while created < NUM_DEFECTS:

    defect_id = f"DEF-{defect_number:04d}"
    defect_number += 1

    if defect_id in existing_defects:
        continue

    # Select an asset
    asset = random.choice(assets)

    asset_id = asset[0]
    department = asset[1]
    criticality = asset[2]
    health_score = float(asset[3])
    failure_risk = float(asset[4])

    # -----------------------------------
    # Defect probability
    # -----------------------------------

    risk_factor = (
        (100 - health_score) * 0.4
        + failure_risk * 0.4
        + criticality * 4
    )

    # Convert to probability
    defect_probability = min(0.95, risk_factor / 120)

    # Sometimes skip healthy assets
    if random.random() > defect_probability:
        continue

    defect_type = random.choice(defect_types[department])

    # Severity based on risk
    if risk_factor >= 75:
        severity = "CRITICAL"
        safety_impact = random.choice([4, 5])

    elif risk_factor >= 55:
        severity = "HIGH"
        safety_impact = random.choice([3, 4, 5])

    elif risk_factor >= 35:
        severity = "MEDIUM"
        safety_impact = random.choice([2, 3])

    else:
        severity = "LOW"
        safety_impact = random.choice([1, 2])

    # Detection date
    detected_date = today - timedelta(
        days=random.randint(1, 90)
    )

    # Repeat failures more likely for high-risk assets
    repeat_failure = (
        True
        if random.random() < min(0.8, failure_risk / 130)
        else False
    )

    # Status
    status = random.choices(
        ["OPEN", "IN_PROGRESS", "RESOLVED"],
        weights=[65, 20, 15]
    )[0]

    # Critical defects should generally be open/in progress
    if severity == "CRITICAL":
        status = random.choice(["OPEN", "IN_PROGRESS"])

    # Target resolution date
    if severity == "CRITICAL":
        days_to_resolve = random.randint(1, 3)

    elif severity == "HIGH":
        days_to_resolve = random.randint(2, 7)

    elif severity == "MEDIUM":
        days_to_resolve = random.randint(5, 14)

    else:
        days_to_resolve = random.randint(10, 30)

    target_resolution_date = (
        detected_date + timedelta(days=days_to_resolve)
    )

    description = (
        f"{defect_type} detected on "
        f"{department} asset during inspection"
    )

    # Insert defect
    cursor.execute(
        """
        INSERT INTO defects
        (
            defect_id,
            asset_id,
            defect_type,
            severity,
            detected_date,
            description,
            safety_impact,
            repeat_failure,
            status,
            target_resolution_date
        )
        VALUES
        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            defect_id,
            asset_id,
            defect_type,
            severity,
            detected_date,
            description,
            safety_impact,
            repeat_failure,
            status,
            target_resolution_date
        )
    )

    created += 1


# -----------------------------
# SAVE
# -----------------------------

connection.commit()

cursor.close()
connection.close()


print(
    f"✅ {created} new defects generated "
    f"and inserted successfully!"
)