import numpy as np
import pandas as pd


# ==========================================
# SETTINGS
# ==========================================

NUM_RECORDS = 100000
RANDOM_SEED = 42

np.random.seed(RANDOM_SEED)


# ==========================================
# 1. BASIC ASSET INFORMATION
# ==========================================

departments = ["ENGINEERING", "S&T", "TRD"]

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


records = []


# ==========================================
# 2. GENERATE HISTORICAL RECORDS
# ==========================================

for i in range(NUM_RECORDS):

    department = np.random.choice(
        departments,
        p=[0.40, 0.30, 0.30]
    )

    asset_type = np.random.choice(
        asset_types[department]
    )

    # Criticality: 1 = low, 5 = critical
    criticality = np.random.choice(
        [1, 2, 3, 4, 5],
        p=[0.10, 0.15, 0.30, 0.30, 0.15]
    )

    # Asset age
    asset_age_years = round(
        np.random.gamma(
            shape=4,
            scale=3
        ),
        1
    )

    asset_age_years = min(
        asset_age_years,
        30
    )

    # Health score
    # Older and highly critical assets tend to have
    # slightly lower health.
    health_score = (
        100
        - asset_age_years * 1.5
        - criticality * 2
        + np.random.normal(0, 8)
    )

    health_score = round(
        np.clip(
            health_score,
            20,
            100
        ),
        2
    )

    # Failure risk
    failure_risk = (
        (100 - health_score) * 0.55
        + criticality * 6
        + asset_age_years * 0.8
        + np.random.normal(0, 5)
    )

    failure_risk = round(
        np.clip(
            failure_risk,
            1,
            99
        ),
        2
    )

    # Days since last inspection
    days_since_inspection = int(
        np.random.gamma(
            shape=3,
            scale=30
        )
    )

    days_since_inspection = min(
        days_since_inspection,
        365
    )

    # Number of defects
    defect_lambda = (
        0.4
        + (100 - health_score) / 45
        + criticality * 0.12
    )

    defect_count = np.random.poisson(
        defect_lambda
    )

    defect_count = min(
        defect_count,
        8
    )

    # Urgent defects
    urgent_defect_probability = (
        0.05
        + (100 - health_score) / 250
        + criticality * 0.04
    )

    urgent_defect_count = np.random.binomial(
        defect_count,
        np.clip(
            urgent_defect_probability,
            0.05,
            0.80
        )
    )

    # Safety impact
    if defect_count == 0:
        max_safety_impact = 0
    else:
        safety_probability = (
            0.05
            + criticality * 0.07
            + (100 - health_score) / 300
        )

        max_safety_impact = np.random.choice(
            [1, 2, 3, 4, 5],
            p=[
                0.10,
                0.20,
                0.30,
                0.25,
                0.15
            ]
        )

        if np.random.random() > safety_probability:
            max_safety_impact = min(
                max_safety_impact,
                3
            )

    # Repeat failures
    repeat_failure_probability = (
        0.05
        + failure_risk / 150
        + criticality * 0.02
    )

    repeat_failure = int(
        np.random.random()
        < min(
            repeat_failure_probability,
            0.80
        )
    )

    # Maintenance history
    maintenance_count = np.random.poisson(
        2 + failure_risk / 35
    )

    maintenance_count = min(
        maintenance_count,
        15
    )

    corrective_probability = (
        0.20
        + failure_risk / 180
    )

    corrective_maintenance_count = np.random.binomial(
        maintenance_count,
        min(
            corrective_probability,
            0.80
        )
    )

    previous_failure_probability = (
        0.03
        + failure_risk / 160
    )

    previous_failure_count = np.random.binomial(
        maintenance_count,
        min(
            previous_failure_probability,
            0.70
        )
    )

    # ==========================================
    # FUTURE URGENT MAINTENANCE TARGET
    # ==========================================
    #
    # IMPORTANT:
    # This represents a future event.
    # The model will learn to predict this from
    # the CURRENT asset condition.
    #

    future_risk = (
        0.025 * criticality
        + 0.010 * (100 - health_score)
        + 0.018 * failure_risk
        + 0.025 * urgent_defect_count
        + 0.035 * max_safety_impact
        + 0.040 * repeat_failure
        + 0.008 * corrective_maintenance_count
        + 0.002 * days_since_inspection
    )

    # Convert score into probability
    future_probability = (
        1 /
        (
            1 +
            np.exp(
                -(future_risk - 2.8)
            )
        )
    )

    urgent_maintenance = int(
        np.random.random()
        < future_probability
    )

    records.append(
        {
            "asset_id": f"ML-{i + 1:05d}",
            "department": department,
            "asset_type": asset_type,
            "criticality": criticality,
            "health_score": health_score,
            "failure_risk": failure_risk,
            "asset_age_years": asset_age_years,
            "days_since_inspection": days_since_inspection,
            "defect_count": defect_count,
            "urgent_defect_count": urgent_defect_count,
            "max_safety_impact": max_safety_impact,
            "repeat_failure": repeat_failure,
            "maintenance_count": maintenance_count,
            "corrective_maintenance_count":
                corrective_maintenance_count,
            "previous_failure_count":
                previous_failure_count,
            "urgent_maintenance":
                urgent_maintenance
        }
    )


# ==========================================
# 3. CREATE DATAFRAME
# ==========================================

dataset = pd.DataFrame(records)


# ==========================================
# 4. SAVE DATASET
# ==========================================

output_file = (
    "ml/ml_training_data.csv"
)

dataset.to_csv(
    output_file,
    index=False
)


# ==========================================
# 5. DISPLAY SUMMARY
# ==========================================

print()
print("=" * 55)
print("       RAILWAY ML DATASET CREATED")
print("=" * 55)

print(
    f"Total records : {len(dataset)}"
)

print(
    f"Total features: {len(dataset.columns)}"
)

print()
print("Target distribution:")

print(
    dataset[
        "urgent_maintenance"
    ].value_counts()
)

print()
print("Dataset preview:")

print(
    dataset.head()
)

print()
print(
    f"Saved to: {output_file}"
)

print("=" * 55)