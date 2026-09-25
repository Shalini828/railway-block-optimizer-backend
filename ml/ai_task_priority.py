import pandas as pd
import joblib
from pathlib import Path


MODEL_FILE = (
    Path(__file__).resolve().parent
    / "railway_risk_model.pkl"
)


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


model = joblib.load(MODEL_FILE)


def calculate_priority(data):

    # --------------------------------------
    # ML PREDICTION
    # --------------------------------------

    input_data = pd.DataFrame(
        [data],
        columns=FEATURES
    )

    probability = model.predict_proba(
        input_data
    )[0][1]

    risk_score = probability * 100


    # --------------------------------------
    # RULE-BASED SCORE
    # --------------------------------------

    criticality_score = (
        data["criticality"] / 5
    ) * 100

    safety_score = (
        data["max_safety_impact"] / 5
    ) * 100

    failure_score = data["failure_risk"]

    health_urgency = (
        100 - data["health_score"]
    )

    inspection_score = min(
        data["days_since_inspection"] / 30,
        1
    ) * 100

    repeat_score = (
        100
        if data["repeat_failure"]
        else 0
    )


    rule_score = (
        safety_score * 0.25
        + criticality_score * 0.20
        + failure_score * 0.20
        + health_urgency * 0.15
        + inspection_score * 0.10
        + repeat_score * 0.10
    )


    # --------------------------------------
    # COMBINED AI PRIORITY
    # --------------------------------------

    ai_priority = (
        rule_score * 0.40
        + risk_score * 0.60
    )

    ai_priority = round(
        min(ai_priority, 100),
        2
    )


    # --------------------------------------
    # CATEGORY
    # --------------------------------------

    if ai_priority >= 85:
        category = "CRITICAL"

    elif ai_priority >= 70:
        category = "HIGH"

    elif ai_priority >= 50:
        category = "MEDIUM"

    else:
        category = "LOW"


    return {
        "risk_probability": round(
            probability,
            4
        ),
        "risk_score": round(
            risk_score,
            2
        ),
        "rule_based_score": round(
            rule_score,
            2
        ),
        "ai_priority_score": ai_priority,
        "priority_category": category
    }