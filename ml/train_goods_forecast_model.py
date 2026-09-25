import joblib
import pandas as pd

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


# ============================================================
# PATHS
# ============================================================

DATA_PATH = "ml/goods_train_forecast_data.csv"
MODEL_PATH = "ml/goods_train_forecast_model.pkl"


# ============================================================
# LOAD DATA
# ============================================================

df = pd.read_csv(DATA_PATH)

df["date"] = pd.to_datetime(df["date"])

print("=" * 60)
print("GOODS TRAIN DEMAND FORECAST MODEL")
print("=" * 60)

print(f"Dataset shape: {df.shape}")


# ============================================================
# ENCODE CATEGORICAL FEATURES
# ============================================================

# Convert corridor and commodity into numeric columns.
df = pd.get_dummies(
    df,
    columns=["corridor_id", "commodity"],
    dtype=int
)


# ============================================================
# FEATURES
# ============================================================

BASE_FEATURES = [
    "day_of_week",
    "month",
    "is_weekend",
    "festival_period",
    "operational_pressure",
    "industrial_demand",
    "previous_day_demand"
]

CATEGORICAL_FEATURES = [
    column
    for column in df.columns
    if column.startswith("corridor_id_")
    or column.startswith("commodity_")
]

FEATURE_COLUMNS = (
    BASE_FEATURES
    + CATEGORICAL_FEATURES
)

TARGET = "goods_train_demand"


# ============================================================
# SORT CHRONOLOGICALLY
# ============================================================

df = df.sort_values("date").reset_index(drop=True)


X = df[FEATURE_COLUMNS]
y = df[TARGET]


# ============================================================
# CHRONOLOGICAL TRAIN / TEST SPLIT
# ============================================================

split_index = int(len(df) * 0.80)

X_train = X.iloc[:split_index]
X_test = X.iloc[split_index:]

y_train = y.iloc[:split_index]
y_test = y.iloc[split_index:]


print(f"Training records: {len(X_train)}")
print(f"Testing records:  {len(X_test)}")

print(
    f"Training period: "
    f"{df['date'].iloc[0].date()} "
    f"to "
    f"{df['date'].iloc[split_index - 1].date()}"
)

print(
    f"Testing period:  "
    f"{df['date'].iloc[split_index].date()} "
    f"to "
    f"{df['date'].iloc[-1].date()}"
)


# ============================================================
# TRAIN MODEL
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
# PREDICTION
# ============================================================

y_pred = model.predict(X_test)


# ============================================================
# EVALUATION
# ============================================================

mae = mean_absolute_error(
    y_test,
    y_pred
)

rmse = mean_squared_error(
    y_test,
    y_pred
) ** 0.5

r2 = r2_score(
    y_test,
    y_pred
)


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

print(
    importance.to_string(index=False)
)


# ============================================================
# SAVE MODEL + FEATURE COLUMNS
# ============================================================

model_package = {
    "model": model,
    "feature_columns": FEATURE_COLUMNS
}

joblib.dump(
    model_package,
    MODEL_PATH
)


# ============================================================
# FINISHED
# ============================================================

print("\n" + "=" * 60)
print("GOODS TRAIN FORECAST MODEL SAVED")
print("=" * 60)

print(f"Model: {MODEL_PATH}")

print("=" * 60)