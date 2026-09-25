import pandas as pd
import joblib


MODEL_FILE = "backend/ml/railway_risk_model.pkl"

FEATURES = [
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


# ==========================================
# LOAD MODEL
# ==========================================

model = joblib.load(MODEL_FILE)


# ==========================================
# PREDICT ONE ASSET
# ==========================================

def predict_asset(asset_data):

    data = pd.DataFrame(
        [asset_data],
        columns=FEATURES
    )

    probability = model.predict_proba(
        data
    )[0][1]

    risk_score = probability * 100


    # Priority category

    if risk_score >= 85:
        category = "CRITICAL"

    elif risk_score >= 70:
        category = "HIGH"

    elif risk_score >= 50:
        category = "MEDIUM"

    else:
        category = "LOW"


    return {
        "risk_probability": round(probability, 4),
        "risk_score": round(risk_score, 2),
        "priority_category": category
    }


# ==========================================
# TEST
# ==========================================

if __name__ == "__main__":

    sample_asset = {
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

    result = predict_asset(sample_asset)

    print()
    print("=" * 60)
    print("             AI PREDICTOR TEST")
    print("=" * 60)

    print(f"Risk probability : {result['risk_probability'] * 100:.2f}%")
    print(f"Risk score       : {result['risk_score']:.2f}")
    print(f"Priority         : {result['priority_category']}")

    print("=" * 60)