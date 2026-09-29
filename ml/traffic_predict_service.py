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
        if joblib is None or not os.path.exists(MODEL_PATH):
            return None

        try:
            _model = joblib.load(MODEL_PATH)
        except Exception:
            _model = None

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


def heuristic_traffic_impact(
    block_duration_min: int,
    start_hour: int,
    passenger_trains: int,
    goods_trains: int,
    special_trains: int,
    express_trains: int,
    corridor_congestion: float,
    criticality: int,
    maintenance_priority: float,
    features: dict = None,
) -> dict:
    regular_passenger_trains = max(0, passenger_trains - express_trains)
    peak_hour = 1 if start_hour in [7, 8, 9, 17, 18, 19, 20] else 0

    duration_score = min(block_duration_min / 240.0, 1.5) * 30.0
    passenger_impact = (express_trains * 5.0 + regular_passenger_trains * 3.0 + special_trains * 4.0)
    train_impact = min(passenger_impact + goods_trains * 1.5, 45.0)
    congestion_score = (corridor_congestion / 100.0) * 15.0 if corridor_congestion > 1 else corridor_congestion * 15.0
    peak_score = peak_hour * 10.0

    raw_score = duration_score + train_impact + congestion_score + peak_score
    impact_score = round(max(0.0, min(100.0, raw_score)), 2)
    level = get_disruption_level(impact_score)

    if not features:
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

    return {
        "traffic_impact_score": impact_score,
        "disruption_level": level,
        "features": features
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

    model = get_model()
    if model is None or pd is None:
        return heuristic_traffic_impact(
            block_duration_min=block_duration_min,
            start_hour=start_hour,
            passenger_trains=passenger_trains,
            goods_trains=goods_trains,
            special_trains=special_trains,
            express_trains=express_trains,
            corridor_congestion=corridor_congestion,
            criticality=criticality,
            maintenance_priority=maintenance_priority,
            features=features
        )

    try:
        input_df = pd.DataFrame([features], columns=FEATURE_COLUMNS)
        prediction = model.predict(input_df)[0]
        traffic_impact_score = round(
            max(0.0, min(100.0, float(prediction))),
            2
        )
        disruption_level = get_disruption_level(traffic_impact_score)
        return {
            "traffic_impact_score": traffic_impact_score,
            "disruption_level": disruption_level,
            "features": features
        }
    except Exception:
        return heuristic_traffic_impact(
            block_duration_min=block_duration_min,
            start_hour=start_hour,
            passenger_trains=passenger_trains,
            goods_trains=goods_trains,
            special_trains=special_trains,
            express_trains=express_trains,
            corridor_congestion=corridor_congestion,
            criticality=criticality,
            maintenance_priority=maintenance_priority,
            features=features
        )


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