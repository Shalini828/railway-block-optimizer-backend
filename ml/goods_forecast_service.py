import os

try:
    import joblib
except ImportError:
    joblib = None

try:
    import pandas as pd
except ImportError:
    pd = None


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
        if joblib is None or not os.path.exists(MODEL_PATH):
            return None

        try:
            _model_package = joblib.load(MODEL_PATH)
        except Exception:
            _model_package = None

    return _model_package


def heuristic_goods_demand(
    day_of_week: int,
    month: int,
    is_weekend: int,
    festival_period: int,
    operational_pressure: float,
    industrial_demand: float,
    previous_day_demand: float,
    corridor_id: str,
    commodity: str,
    features: dict = None,
) -> dict:
    base = previous_day_demand if previous_day_demand > 0 else 18.0
    weekend_mod = -3.0 if is_weekend else 1.0
    festival_mod = -4.0 if festival_period else 0.0
    pressure_mod = (operational_pressure - 0.5) * 5.0
    industrial_mod = (industrial_demand - 0.5) * 6.0

    predicted = max(5.0, min(60.0, base + weekend_mod + festival_mod + pressure_mod + industrial_mod))
    predicted = round(predicted, 2)

    if predicted >= 40:
        demand_level = "VERY_HIGH"
    elif predicted >= 30:
        demand_level = "HIGH"
    elif predicted >= 15:
        demand_level = "MEDIUM"
    else:
        demand_level = "LOW"

    if not features:
        features = {
            "day_of_week": day_of_week,
            "month": month,
            "is_weekend": is_weekend,
            "festival_period": festival_period,
            "operational_pressure": operational_pressure,
            "industrial_demand": industrial_demand,
            "previous_day_demand": previous_day_demand,
        }

    return {
        "predicted_goods_train_demand": predicted,
        "predicted_demand": predicted,
        "forecasted_goods_trains": predicted,
        "demand_level": demand_level,
        "corridor_id": corridor_id,
        "commodity": commodity,
        "features": features,
    }


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
    if package is None or pd is None:
        return heuristic_goods_demand(
            day_of_week=day_of_week,
            month=month,
            is_weekend=is_weekend,
            festival_period=festival_period,
            operational_pressure=operational_pressure,
            industrial_demand=industrial_demand,
            previous_day_demand=previous_day_demand,
            corridor_id=corridor_id,
            commodity=commodity
        )

    model = package.get("model")
    feature_columns = package.get("feature_columns", [])
    if model is None or not feature_columns:
        return heuristic_goods_demand(
            day_of_week=day_of_week,
            month=month,
            is_weekend=is_weekend,
            festival_period=festival_period,
            operational_pressure=operational_pressure,
            industrial_demand=industrial_demand,
            previous_day_demand=previous_day_demand,
            corridor_id=corridor_id,
            commodity=commodity
        )

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

    try:
        input_df = pd.DataFrame([features])
        input_df = input_df.reindex(columns=feature_columns, fill_value=0)
        prediction = model.predict(input_df)[0]
        predicted_demand = max(0.0, min(60.0, float(prediction)))
        predicted_demand = round(predicted_demand, 2)

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
            "predicted_demand": predicted_demand,
            "forecasted_goods_trains": predicted_demand,
            "demand_level": demand_level,
            "corridor_id": corridor_id,
            "commodity": commodity,
            "features": features,
        }
    except Exception:
        return heuristic_goods_demand(
            day_of_week=day_of_week,
            month=month,
            is_weekend=is_weekend,
            festival_period=festival_period,
            operational_pressure=operational_pressure,
            industrial_demand=industrial_demand,
            previous_day_demand=previous_day_demand,
            corridor_id=corridor_id,
            commodity=commodity,
            features=features
        )


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