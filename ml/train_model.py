import pandas as pd
import joblib

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier

from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    precision_recall_curve
)


# =========================================================
# 1. LOAD DATA
# =========================================================

DATA_FILE = "ml/ml_training_data.csv"

df = pd.read_csv(DATA_FILE)

print("=" * 60)
print("          RAILWAY MAINTENANCE ML MODEL")
print("=" * 60)
print()

print("Dataset shape:", df.shape)


# =========================================================
# 2. SELECT FEATURES
# =========================================================

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

target = "urgent_maintenance"


X = df[features]
y = df[target]


# =========================================================
# 3. TRAIN / TEST SPLIT
# =========================================================

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.20,
    random_state=42,
    stratify=y
)

print()
print("Training records:", len(X_train))
print("Testing records :", len(X_test))


# =========================================================
# 4. CREATE MODEL
# =========================================================

model = RandomForestClassifier(
    n_estimators=200,
    max_depth=12,
    min_samples_split=5,
    random_state=42,
    class_weight="balanced"
)


# =========================================================
# 5. TRAIN MODEL
# =========================================================

print()
print("Training model...")

model.fit(
    X_train,
    y_train
)

print("Training completed!")


# =========================================================
# 6. NORMAL PREDICTION
# =========================================================

y_pred = model.predict(X_test)


# =========================================================
# 7. NORMAL MODEL EVALUATION
# =========================================================

accuracy = accuracy_score(
    y_test,
    y_pred
)

print()
print("=" * 60)
print("MODEL PERFORMANCE - DEFAULT THRESHOLD")
print("=" * 60)

print(
    f"Accuracy: {accuracy:.4f}"
)

print()
print("Classification Report:")

print(
    classification_report(
        y_test,
        y_pred
    )
)

print()
print("Confusion Matrix:")

print(
    confusion_matrix(
        y_test,
        y_pred
    )
)


# =========================================================
# 8. PROBABILITY PREDICTIONS
# =========================================================

y_prob = model.predict_proba(X_test)[:, 1]


# =========================================================
# 9. FIND BEST PROBABILITY THRESHOLD
# =========================================================

precision, recall, thresholds = precision_recall_curve(
    y_test,
    y_prob
)

# Calculate F1 for every threshold
f1_scores = (
    2 * precision * recall
    / (precision + recall + 1e-8)
)

# The final precision/recall value does not have
# a corresponding threshold.
valid_f1_scores = f1_scores[:-1]

best_index = valid_f1_scores.argmax()

best_threshold = thresholds[best_index]
best_f1 = valid_f1_scores[best_index]


print()
print("=" * 60)
print("BEST THRESHOLD ANALYSIS")
print("=" * 60)

print(
    f"Best threshold : {best_threshold:.4f}"
)

print(
    f"Best F1 score  : {best_f1:.4f}"
)


# =========================================================
# 10. PREDICTION USING BEST THRESHOLD
# =========================================================

optimized_predictions = (
    y_prob >= best_threshold
).astype(int)


print()
print("Classification Report at Best Threshold:")

print(
    classification_report(
        y_test,
        optimized_predictions
    )
)


print()
print("Confusion Matrix at Best Threshold:")

print(
    confusion_matrix(
        y_test,
        optimized_predictions
    )
)


# =========================================================
# 11. FEATURE IMPORTANCE
# =========================================================

importance = pd.DataFrame({
    "feature": features,
    "importance": model.feature_importances_
})

importance = importance.sort_values(
    by="importance",
    ascending=False
)

print()
print("=" * 60)
print("FEATURE IMPORTANCE")
print("=" * 60)

print(
    importance.to_string(
        index=False
    )
)


# =========================================================
# 12. SAVE MODEL
# =========================================================

MODEL_FILE = "ml/railway_risk_model.pkl"

joblib.dump(
    model,
    MODEL_FILE
)


# =========================================================
# 13. SAVE OPTIMAL THRESHOLD
# =========================================================

THRESHOLD_FILE = "ml/optimal_threshold.txt"

with open(
    THRESHOLD_FILE,
    "w"
) as f:

    f.write(
        str(best_threshold)
    )


# =========================================================
# 14. FINAL OUTPUT
# =========================================================

print()
print("=" * 60)
print("MODEL ARTIFACTS SAVED")
print("=" * 60)

print(
    f"Model saved to: {MODEL_FILE}"
)

print(
    f"Optimal threshold saved to: {THRESHOLD_FILE}"
)

print(
    f"Final selected threshold: {best_threshold:.4f}"
)

print(
    f"Best positive-class F1: {best_f1:.4f}"
)

print("=" * 60)