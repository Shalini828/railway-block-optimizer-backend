import os
import joblib
import pandas as pd


# ============================================================
# MODEL PATH
# ============================================================

MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "goods_train_forecast_model.pkl"
)


# ============================================================
# LOAD MODEL
# ============================================================

_model_package = None


def get_model_package():

    global _model_package

    if _model_package is None:

        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"Goods forecast model not found: {MODEL_PATH}"
            )

        _model_package = joblib.load(MODEL_PATH)

    return _model_package


# ============================================================
# PREDICTION
# ============================================================

def predict_goods_train_demand(
    day_of_week: int,
    month: int,
    is_weekend: int,
    festival_period: int,
    operational_pressure: float,
    industrial_demand: float,
    previous_day_demand: float,
    corridor_id: str,
    commodity: str
):

    package = get_model_package()

    model = package["model"]
    feature_columns = package["feature_columns"]

    # --------------------------------------------------------
    # Create base input
    # --------------------------------------------------------

    features = {
        "day_of_week": day_of_week,
        "month": month,
        "is_weekend": is_weekend,
        "festival_period": festival_period,
        "operational_pressure": operational_pressure,
        "industrial_demand": industrial_demand,
        "previous_day_demand": previous_day_demand
    }

    # --------------------------------------------------------
    # Add one-hot corridor features
    # --------------------------------------------------------

    for column in feature_columns:

        if column.startswith("corridor_id_"):

            expected_corridor = column.replace(
                "corridor_id_",
                ""
            )

            features[column] = (
                1
                if corridor_id == expected_corridor
                else 0
            )

    # --------------------------------------------------------
    # Add one-hot commodity features
    # --------------------------------------------------------

    for column in feature_columns:

        if column.startswith("commodity_"):

            expected_commodity = column.replace(
                "commodity_",
                ""
            )

            features[column] = (
                1
                if commodity == expected_commodity
                else 0
            )

    # --------------------------------------------------------
    # Build DataFrame in EXACT training order
    # --------------------------------------------------------

    input_df = pd.DataFrame(
        [features]
    )

    input_df = input_df.reindex(
        columns=feature_columns,
        fill_value=0
    )

    # --------------------------------------------------------
    # Prediction
    # --------------------------------------------------------

    prediction = model.predict(input_df)[0]

    predicted_demand = max(
        0.0,
        min(
            60.0,
            float(prediction)
        )
    )

    predicted_demand = round(
        predicted_demand,
        2
    )

    # --------------------------------------------------------
    # Demand category
    # --------------------------------------------------------

    if predicted_demand >= 40:
        demand_level = "VERY_HIGH"

    elif predicted_demand >= 30:
        demand_level = "HIGH"

    elif predicted_demand >= 15:
        demand_level = "MEDIUM"

    else:
        demand_level = "LOW"

    return {
        "predicted_goods_train_demand": predicted_demand,
        "demand_level": demand_level,
        "corridor_id": corridor_id,
        "commodity": commodity,
        "features": features
    }


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    result = predict_goods_train_demand(
        day_of_week=2,
        month=10,
        is_weekend=0,
        festival_period=1,
        operational_pressure=70,
        industrial_demand=85,
        previous_day_demand=25,
        corridor_id="C09",
        commodity="COAL"
    )

    print("=" * 60)
    print("GOODS TRAIN DEMAND PREDICTION")
    print("=" * 60)

    print(
        "Predicted Demand :",
        result["predicted_goods_train_demand"]
    )

    print(
        "Demand Level     :",
        result["demand_level"]
    )

    print(
        "Corridor         :",
        result["corridor_id"]
    )

    print(
        "Commodity        :",
        result["commodity"]
    )

    print("\nFeatures:")

    for key, value in result["features"].items():
        print(f"  {key}: {value}")