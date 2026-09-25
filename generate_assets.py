import psycopg
import os
from dotenv import load_dotenv
import random
from datetime import date, timedelta

load_dotenv()

# -----------------------------
# SETTINGS
# -----------------------------

NUM_ASSETS = 100


# -----------------------------
# ASSET TYPES
# -----------------------------

asset_types = {
    "ENGINEERING": [
        "Track",
        "Bridge",
        "Point & Crossing"
    ],
    "S&T": [
        "Signal",
        "Axle Counter",
        "Point Machine"
    ],
    "TRD": [
        "OHE",
        "Transformer",
        "Section Insulator"
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
# GET EXISTING CORRIDORS
# -----------------------------

cursor.execute("""
    SELECT corridor_id, distance_km
    FROM corridors
""")

corridors = cursor.fetchall()

if not corridors:
    print("❌ No corridors found!")
    connection.close()
    exit()


# -----------------------------
# GET EXISTING ASSET IDS
# -----------------------------

cursor.execute("""
    SELECT asset_id
    FROM assets
""")

existing_assets = {row[0] for row in cursor.fetchall()}


# -----------------------------
# GENERATE ASSETS
# -----------------------------

departments = list(asset_types.keys())

today = date(2026, 8, 27)

created = 0
asset_number = 1


while created < NUM_ASSETS:

    asset_id = f"AST-{asset_number:04d}"
    asset_number += 1

    # Skip if this ID already exists
    if asset_id in existing_assets:
        continue

    # Select a corridor
    corridor_id, corridor_distance = random.choice(corridors)

    # Select department
    department = random.choice(departments)

    # Select asset type according to department
    asset_type = random.choice(asset_types[department])

    # Location somewhere along the corridor
    location_km = round(
        random.uniform(0, float(corridor_distance)),
        3
    )

    # Criticality: 1 = low, 5 = critical
    criticality = random.choices(
        [1, 2, 3, 4, 5],
        weights=[10, 15, 30, 30, 15]
    )[0]

    # Health score between 30 and 100
    health_score = round(
        random.uniform(40, 100),
        2
    )

    # Older / unhealthy assets tend to have higher failure risk
    failure_risk = (
        100
        - health_score
        + (criticality * 5)
        + random.uniform(-10, 10)
    )

    failure_risk = round(
        max(1, min(99, failure_risk)),
        2
    )

    # Installation date
    installation_date = date(
        random.randint(2005, 2024),
        random.randint(1, 12),
        random.randint(1, 28)
    )

    # Last inspection within roughly the last year
    last_inspection_date = today - timedelta(
        days=random.randint(1, 365)
    )

    # Operational status
    operational_status = random.choices(
        [
            "OPERATIONAL",
            "DEGRADED",
            "UNDER_MAINTENANCE"
        ],
        weights=[90, 7, 3]
    )[0]

    # Insert into PostgreSQL
    cursor.execute(
        """
        INSERT INTO assets
        (
            asset_id,
            corridor_id,
            department,
            asset_type,
            location_km,
            criticality,
            health_score,
            failure_risk,
            installation_date,
            last_inspection_date,
            operational_status
        )
        VALUES
        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            asset_id,
            corridor_id,
            department,
            asset_type,
            location_km,
            criticality,
            health_score,
            failure_risk,
            installation_date,
            last_inspection_date,
            operational_status
        )
    )

    created += 1


# -----------------------------
# SAVE CHANGES
# -----------------------------

connection.commit()

cursor.close()
connection.close()


print(f"✅ {created} new assets generated and inserted successfully!")