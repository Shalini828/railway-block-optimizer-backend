import random
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


random.seed(42)
np.random.seed(42)


# ============================================================
# CONFIG
# ============================================================

NUM_RECORDS = 100000

START_DATE = datetime(2024, 1, 1)

CORRIDORS = [
    "C01", "C02", "C03", "C04", "C05",
    "C06", "C07", "C08", "C09", "C10"
]

COMMODITIES = [
    "COAL",
    "IRON_ORE",
    "CEMENT",
    "FOOD_GRAINS",
    "FERTILIZER",
    "CONTAINER",
    "PETROLEUM"
]


# ============================================================
# GENERATE DATA
# ============================================================

rows = []


for i in range(NUM_RECORDS):

    date = START_DATE + timedelta(days=i % 1095)

    corridor = random.choice(CORRIDORS)
    commodity = random.choice(COMMODITIES)

    day_of_week = date.weekday()
    month = date.month

    is_weekend = 1 if day_of_week >= 5 else 0

    # Festival / seasonal demand indicator
    festival_period = (
        1
        if month in [9, 10, 11]
        else 0
    )

    # Weather / operational pressure
    operational_pressure = random.randint(0, 100)

    # Industrial demand
    industrial_demand = random.randint(20, 100)

    # Previous demand proxy
    previous_day_demand = random.randint(5, 35)

    # Commodity-specific demand factor
    commodity_factor = {
        "COAL": 1.30,
        "IRON_ORE": 1.15,
        "CEMENT": 1.10,
        "FOOD_GRAINS": 0.95,
        "FERTILIZER": 1.05,
        "CONTAINER": 1.20,
        "PETROLEUM": 1.00
    }[commodity]

    # Corridor-specific demand factor
    corridor_factor = {
        "C01": 1.00,
        "C02": 1.10,
        "C03": 0.95,
        "C04": 1.20,
        "C05": 1.05,
        "C06": 0.90,
        "C07": 1.15,
        "C08": 1.00,
        "C09": 1.25,
        "C10": 1.10
    }[corridor]

    # Synthetic demand target
    goods_train_demand = (
        previous_day_demand * 0.30
        + industrial_demand * 0.18
        + operational_pressure * 0.05
        + festival_period * 5
        - is_weekend * 2
    )

    goods_train_demand *= commodity_factor
    goods_train_demand *= corridor_factor

    # Add realistic noise
    goods_train_demand += np.random.normal(0, 2.5)

    # Keep within realistic range
    goods_train_demand = max(
        0,
        min(60, goods_train_demand)
    )

    rows.append({
        "date": date.strftime("%Y-%m-%d"),
        "corridor_id": corridor,
        "commodity": commodity,
        "day_of_week": day_of_week,
        "month": month,
        "is_weekend": is_weekend,
        "festival_period": festival_period,
        "operational_pressure": operational_pressure,
        "industrial_demand": industrial_demand,
        "previous_day_demand": previous_day_demand,
        "goods_train_demand": round(
            goods_train_demand,
            2
        )
    })


# ============================================================
# DATAFRAME
# ============================================================

df = pd.DataFrame(rows)

# IMPORTANT:
# Forecasting data must be ordered chronologically.
df["date"] = pd.to_datetime(df["date"])

df = df.sort_values(
    ["date", "corridor_id"]
).reset_index(drop=True)


# ============================================================
# SAVE
# ============================================================

output_path = "ml/goods_train_forecast_data.csv"

df.to_csv(
    output_path,
    index=False
)


# ============================================================
# OUTPUT
# ============================================================

print("=" * 60)
print("GOODS TRAIN FORECAST DATASET CREATED")
print("=" * 60)

print(f"Records : {len(df)}")
print(f"Columns : {len(df.columns)}")

print("\nFirst 5 records:")
print(df.head())

print("\nTarget statistics:")
print(
    df["goods_train_demand"].describe()
)

print("\nDate range:")
print(df["date"].min(), "to", df["date"].max())

print("\nCorridors:")
print(
    df["corridor_id"].nunique()
)

print("\nSaved to:")
print(output_path)

print("=" * 60)