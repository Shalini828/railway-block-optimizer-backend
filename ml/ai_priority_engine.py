import pandas as pd
import joblib


# ==========================================
# FILES
# ==========================================

DATA_FILE = "backend/ml/ml_training_data.csv"
MODEL_FILE = "backend/ml/railway_risk_model.pkl"
OUTPUT_FILE = "backend/ml/ai_priority_results.csv"


# ==========================================
# LOAD DATA + MODEL
# ==========================================

df = pd.read_csv(DATA_FILE)

model = joblib.load(MODEL_FILE)


# ==========================================
# FEATURES USED BY MODEL
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


# ==========================================
# ML PREDICTION
# ==========================================

X = df[features]

df["risk_probability"] = (
    model.predict_proba(X)[:, 1]
)

df["risk_score"] = (
    df["risk_probability"] * 100
)


# ==========================================
# RULE-BASED SCORE
# ==========================================

criticality_score = (
    df["criticality"] / 5
) * 100

safety_score = (
    df["max_safety_impact"] / 5
) * 100

failure_score = df["failure_risk"]

health_urgency = (
    100 - df["health_score"]
)

overdue_score = (
    df["days_since_inspection"] / 30
).clip(upper=1) * 100

repeat_score = (
    df["repeat_failure"] * 100
)


df["rule_based_score"] = (
    safety_score * 0.25
    + criticality_score * 0.20
    + failure_score * 0.20
    + health_urgency * 0.15
    + overdue_score * 0.10
    + repeat_score * 0.10
)


# ==========================================
# AI-ENHANCED PRIORITY
# ==========================================

df["ai_priority_score"] = (
    df["rule_based_score"] * 0.40
    + df["risk_score"] * 0.60
)


df["ai_priority_score"] = (
    df["ai_priority_score"]
    .clip(upper=100)
    .round(2)
)


# ==========================================
# PRIORITY CATEGORY
# ==========================================

def get_category(score):

    if score >= 85:
        return "CRITICAL"

    elif score >= 70:
        return "HIGH"

    elif score >= 50:
        return "MEDIUM"

    else:
        return "LOW"


df["priority_category"] = (
    df["ai_priority_score"]
    .apply(get_category)
)


# ==========================================
# RANK TASKS
# ==========================================

df = df.sort_values(
    by="ai_priority_score",
    ascending=False
).reset_index(drop=True)


df["priority_rank"] = (
    df.index + 1
)


# ==========================================
# SAVE RESULTS
# ==========================================

output_columns = [
    "priority_rank",
    "asset_id",
    "department",
    "asset_type",
    "risk_probability",
    "risk_score",
    "rule_based_score",
    "ai_priority_score",
    "priority_category"
]


results = df[output_columns]


results.to_csv(
    OUTPUT_FILE,
    index=False
)


# ==========================================
# DISPLAY
# ==========================================

print()
print("=" * 80)
print("           AI MAINTENANCE PRIORITY RANKING")
print("=" * 80)

print()

print(
    f"Total assets analyzed : {len(results)}"
)

print()

print("TOP 20 PRIORITY ASSETS")
print("-" * 80)

print(
    results.head(20).to_string(
        index=False
    )
)

print()
print("=" * 80)

print(
    f"Results saved to: {OUTPUT_FILE}"
)

print("=" * 80)