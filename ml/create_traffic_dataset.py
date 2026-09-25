import random
import pandas as pd
import numpy as np

random.seed(42)
np.random.seed(42)

NUM_RECORDS = 100000

rows = []

for i in range(NUM_RECORDS):

    # Block characteristics
    block_duration_min = random.randint(30, 240)
    start_hour = random.randint(5, 22)

    # Traffic volume
    passenger_trains = random.randint(0, 15)
    goods_trains = random.randint(0, 10)
    special_trains = random.randint(0, 4)

    # Train importance
    express_trains = random.randint(0, min(passenger_trains, 6))
    passenger_trains_regular = max(
        0,
        passenger_trains - express_trains
    )

    # Operational conditions
    corridor_congestion = random.randint(0, 100)
    peak_hour = 1 if start_hour in [7, 8, 9, 17, 18, 19, 20] else 0

    # Block characteristics
    criticality = random.randint(1, 5)
    maintenance_priority = random.randint(1, 100)

    # Calculate synthetic impact
    impact = (
        passenger_trains * 4
        + goods_trains * 2.5
        + special_trains * 6
        + express_trains * 5
        + block_duration_min * 0.08
        + corridor_congestion * 0.20
        + peak_hour * 12
        + criticality * 3
        + maintenance_priority * 0.08
    )

    # Small realistic noise
    impact += np.random.normal(0, 5)

    # Keep score between 0 and 100
    impact = max(0, min(100, impact))

    rows.append({
        "block_duration_min": block_duration_min,
        "start_hour": start_hour,
        "passenger_trains": passenger_trains,
        "goods_trains": goods_trains,
        "special_trains": special_trains,
        "express_trains": express_trains,
        "regular_passenger_trains": passenger_trains_regular,
        "corridor_congestion": corridor_congestion,
        "peak_hour": peak_hour,
        "criticality": criticality,
        "maintenance_priority": maintenance_priority,
        "traffic_impact_score": round(impact, 2)
    })


df = pd.DataFrame(rows)

output_path = "ml/traffic_training_data.csv"

df.to_csv(output_path, index=False)

print("=" * 60)
print("TRAFFIC DATASET CREATED")
print("=" * 60)
print(f"Records: {len(df)}")
print(f"Columns: {len(df.columns)}")
print()
print(df.head())
print()
print("Target statistics:")
print(df["traffic_impact_score"].describe())
print()
print(f"Saved to: {output_path}")