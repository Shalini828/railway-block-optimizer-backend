import pandas as pd
import joblib


# ==========================================
# LOAD TRAINED MODEL
# ==========================================

MODEL_FILE = "ml/railway_risk_model.pkl"

model = joblib.load(MODEL_FILE)


# ==========================================
# NEW RAILWAY ASSET
# ==========================================

asset = {
    "criticality": 5,
    "health_score": 42,
    "failure_risk": 78,
    "asset_age_years": 18,
    "days_since_inspection": 145,
    "defect_count": 4,
    "urgent_defect_count": 2,
    "max_safety_impact": 5,
    "repeat_failure": 1,
    "maintenance_count": 8,
    "corrective_maintenance_count": 5,
    "previous_failure_count": 3
}


# ==========================================
# FEATURES
# ==========================================

features = [
    "criticality",
    "health_score",
    "failure_risk",
    "asset_age_years",
    "days_since_inspection",
    "defect_count",
    "urgent_defect_count",
    "max_safety_impact",
    "repeat_failure",
    "maintenance_count",
    "corrective_maintenance_count",
    "previous_failure_count"
]


input_data = pd.DataFrame(
    [asset],
    columns=features
)


# ==========================================
# PREDICTION
# ==========================================

prediction = model.predict(input_data)[0]

probability = model.predict_proba(
    input_data
)[0][1]


# ==========================================
# PRIORITY
# ==========================================

risk_percentage = probability * 100


if risk_percentage >= 80:
    priority = "CRITICAL"

elif risk_percentage >= 60:
    priority = "HIGH"

elif risk_percentage >= 40:
    priority = "MEDIUM"

else:
    priority = "LOW"


# ==========================================
# DISPLAY RESULT
# ==========================================

print()
print("=" * 55)
print("       AI RAILWAY MAINTENANCE PREDICTION")
print("=" * 55)

print()
print("Asset Information")
print("-----------------")

for key, value in asset.items():
    print(f"{key:35} {value}")

print()
print("AI RESULT")
print("---------")

print(
    f"Urgent maintenance probability : "
    f"{risk_percentage:.2f}%"
)

print(
    f"AI priority category           : "
    f"{priority}"
)

print()

if prediction == 1:

    print(
        "⚠️ AI recommends prioritizing "
        "this asset for maintenance."
    )

else:

    print(
        "✅ AI does not currently classify "
        "this asset as urgently requiring maintenance."
    )

print("=" * 55)