import joblib
import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


# ============================================================
# PATHS
# ============================================================

DATA_PATH = "ml/traffic_training_data.csv"
MODEL_PATH = "ml/traffic_impact_model.pkl"


# ============================================================
# LOAD DATASET
# ============================================================

df = pd.read_csv(DATA_PATH)

print("=" * 60)
print("TRAFFIC / DISRUPTION MODEL TRAINING")
print("=" * 60)

print(f"Dataset shape: {df.shape}")


# ============================================================
# FEATURES
# ============================================================

FEATURE_COLUMNS = [
    "block_duration_min",
    "start_hour",
    "passenger_trains",
    "goods_trains",
    "special_trains",
    "express_trains",
    "regular_passenger_trains",
    "corridor_congestion",
    "peak_hour",
    "criticality",
    "maintenance_priority"
]

TARGET = "traffic_impact_score"


X = df[FEATURE_COLUMNS]
y = df[TARGET]


# ============================================================
# TRAIN / TEST SPLIT
# ============================================================

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.20,
    random_state=42
)

print(f"Training records: {len(X_train)}")
print(f"Testing records:  {len(X_test)}")


# ============================================================
# RANDOM FOREST REGRESSOR
# ============================================================

model = RandomForestRegressor(
    n_estimators=200,
    max_depth=15,
    min_samples_split=5,
    random_state=42,
    n_jobs=-1
)

print("\nTraining model...")

model.fit(X_train, y_train)


# ============================================================
# PREDICTIONS
# ============================================================

y_pred = model.predict(X_test)


# ============================================================
# EVALUATION
# ============================================================

mae = mean_absolute_error(y_test, y_pred)

mse = mean_squared_error(y_test, y_pred)
rmse = mse ** 0.5

r2 = r2_score(y_test, y_pred)


print("\n" + "=" * 60)
print("MODEL EVALUATION")
print("=" * 60)

print(f"MAE  : {mae:.4f}")
print(f"RMSE : {rmse:.4f}")
print(f"R²   : {r2:.4f}")


# ============================================================
# FEATURE IMPORTANCE
# ============================================================

importance = pd.DataFrame({
    "feature": FEATURE_COLUMNS,
    "importance": model.feature_importances_
})

importance = importance.sort_values(
    "importance",
    ascending=False
)


print("\nFeature Importance:")
print("-" * 60)
print(importance.to_string(index=False))


# ============================================================
# SAVE MODEL
# ============================================================

joblib.dump(model, MODEL_PATH)

print("\n" + "=" * 60)
print(f"Model saved to: {MODEL_PATH}")
print("=" * 60)