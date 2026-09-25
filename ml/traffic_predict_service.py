import os
import joblib
import pandas as pd


# ============================================================
# MODEL PATH
# ============================================================

MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "traffic_impact_model.pkl"
)


# ============================================================
# FEATURE COLUMNS
# Must match the training model exactly
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


# ============================================================
# LOAD MODEL
# ============================================================

_model = None


def get_model():
    global _model

    if _model is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"Traffic impact model not found: {MODEL_PATH}"
            )

        _model = joblib.load(MODEL_PATH)

    return _model


# ============================================================
# DISRUPTION CATEGORY
# ============================================================

def get_disruption_level(score: float) -> str:

    if score >= 80:
        return "CRITICAL"

    if score >= 60:
        return "HIGH"

    if score >= 35:
        return "MEDIUM"

    return "LOW"


# ============================================================
# BUILD MODEL INPUT
# ============================================================

def build_traffic_features(
    block_duration_min: int,
    start_hour: int,
    passenger_trains: int,
    goods_trains: int,
    special_trains: int,
    express_trains: int,
    corridor_congestion: float,
    criticality: int,
    maintenance_priority: float
):

    regular_passenger_trains = max(
        0,
        passenger_trains - express_trains
    )

    peak_hour = (
        1
        if start_hour in [7, 8, 9, 17, 18, 19, 20]
        else 0
    )

    return {
        "block_duration_min": block_duration_min,
        "start_hour": start_hour,
        "passenger_trains": passenger_trains,
        "goods_trains": goods_trains,
        "special_trains": special_trains,
        "express_trains": express_trains,
        "regular_passenger_trains": regular_passenger_trains,
        "corridor_congestion": corridor_congestion,
        "peak_hour": peak_hour,
        "criticality": criticality,
        "maintenance_priority": maintenance_priority
    }


# ============================================================
# PREDICT TRAFFIC IMPACT
# ============================================================

def predict_traffic_impact(
    block_duration_min: int,
    start_hour: int,
    passenger_trains: int,
    goods_trains: int,
    special_trains: int,
    express_trains: int,
    corridor_congestion: float,
    criticality: int,
    maintenance_priority: float
):

    model = get_model()

    features = build_traffic_features(
        block_duration_min=block_duration_min,
        start_hour=start_hour,
        passenger_trains=passenger_trains,
        goods_trains=goods_trains,
        special_trains=special_trains,
        express_trains=express_trains,
        corridor_congestion=corridor_congestion,
        criticality=criticality,
        maintenance_priority=maintenance_priority
    )

    # Keep the exact training feature order
    input_df = pd.DataFrame(
        [features],
        columns=FEATURE_COLUMNS
    )

    # RandomForestRegressor returns a continuous prediction
    prediction = model.predict(input_df)[0]

    # Keep the score within our defined 0–100 range
    traffic_impact_score = round(
        max(0.0, min(100.0, float(prediction))),
        2
    )

    disruption_level = get_disruption_level(
        traffic_impact_score
    )

    return {
        "traffic_impact_score": traffic_impact_score,
        "disruption_level": disruption_level,
        "features": features
    }


# ============================================================
# SIMPLE TEST
# ============================================================

if __name__ == "__main__":

    result = predict_traffic_impact(
        block_duration_min=120,
        start_hour=18,
        passenger_trains=8,
        goods_trains=4,
        special_trains=1,
        express_trains=3,
        corridor_congestion=70,
        criticality=4,
        maintenance_priority=80
    )

    print("=" * 60)
    print("TRAFFIC IMPACT PREDICTION")
    print("=" * 60)

    print(f"Traffic Impact Score : {result['traffic_impact_score']}")
    print(f"Disruption Level      : {result['disruption_level']}")

    print("\nFeatures:")
    for key, value in result["features"].items():
        print(f"  {key}: {value}")