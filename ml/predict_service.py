import os
import joblib
import pandas as pd


# ============================================================
# MODEL PATHS
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_PATH = os.path.join(
    BASE_DIR,
    "railway_risk_model.pkl"
)

THRESHOLD_PATH = os.path.join(
    BASE_DIR,
    "optimal_threshold.txt"
)


# ============================================================
# FEATURE COLUMNS
# ============================================================

FEATURE_COLUMNS = [
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


# ============================================================
# MODEL CACHE
# ============================================================

_model = None
_threshold = None


# ============================================================
# LOAD MODEL
# ============================================================

def get_model():

    global _model

    if _model is None:

        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"Asset risk model not found: {MODEL_PATH}"
            )

        _model = joblib.load(MODEL_PATH)

    return _model


# ============================================================
# LOAD OPTIMAL THRESHOLD
# ============================================================

def get_threshold():

    global _threshold

    if _threshold is None:

        try:

            with open(
                THRESHOLD_PATH,
                "r"
            ) as file:

                _threshold = float(
                    file.read().strip()
                )

        except (
            FileNotFoundError,
            ValueError,
            TypeError
        ):

            # Safe default
            _threshold = 0.5

    return _threshold


# ============================================================
# PRIORITY CATEGORY
# ============================================================

def get_priority_category(
    risk_score: float
) -> str:

    risk_score = max(
        0.0,
        min(100.0, float(risk_score))
    )

    if risk_score >= 85:
        return "CRITICAL"

    elif risk_score >= 70:
        return "HIGH"

    elif risk_score >= 50:
        return "MEDIUM"

    return "LOW"


# ============================================================
# PREDICT ASSET RISK
# ============================================================

def predict_asset_risk(
    asset: dict,
    defects: list,
    maintenance_history: list
) -> dict:

    # --------------------------------------------------------
    # Load model and threshold
    # --------------------------------------------------------

    model = get_model()
    threshold = get_threshold()

    # --------------------------------------------------------
    # Build asset features
    # --------------------------------------------------------

    from .features import build_asset_features

    features = build_asset_features(
        asset=asset,
        defects=defects or [],
        maintenance_history=maintenance_history or []
    )

    # --------------------------------------------------------
    # Prepare feature dataframe
    #
    # IMPORTANT:
    # Keep the exact same feature order used during training.
    # --------------------------------------------------------

    feature_data = {}

    for column in FEATURE_COLUMNS:

        value = features.get(
            column,
            0
        )

        try:
            value = float(value)

        except (
            TypeError,
            ValueError
        ):

            value = 0.0

        feature_data[column] = [value]

    X = pd.DataFrame(
        feature_data,
        columns=FEATURE_COLUMNS
    )

    # --------------------------------------------------------
    # Probability prediction
    # --------------------------------------------------------

    probabilities = model.predict_proba(X)

    # --------------------------------------------------------
    # Determine positive/urgent class probability
    #
    # Normally classes are [0, 1].
    # This also handles models where class ordering
    # is explicitly available.
    # --------------------------------------------------------

    if hasattr(model, "classes_"):

        classes = list(model.classes_)

        if 1 in classes:

            positive_index = classes.index(1)

        else:

            # Fallback to the last probability column
            positive_index = len(classes) - 1

    else:

        positive_index = 1

    urgent_probability = float(
        probabilities[0][positive_index]
    )

    urgent_probability = max(
        0.0,
        min(1.0, urgent_probability)
    )

    # --------------------------------------------------------
    # Apply optimized threshold
    # --------------------------------------------------------

    urgent_prediction = int(
        urgent_probability >= threshold
    )

    # --------------------------------------------------------
    # Convert probability to 0-100 risk score
    # --------------------------------------------------------

    risk_score = round(
        urgent_probability * 100,
        2
    )

    # --------------------------------------------------------
    # Priority
    # --------------------------------------------------------

    priority_category = get_priority_category(
        risk_score
    )

    # --------------------------------------------------------
    # Final result
    # --------------------------------------------------------

    return {

        "asset_id":
            asset.get("asset_id"),

        "risk_probability":
            round(
                urgent_probability,
                6
            ),

        "risk_score":
            risk_score,

        "priority_category":
            priority_category,

        "urgent_maintenance_prediction":
            urgent_prediction,

        "decision_threshold":
            round(
                float(threshold),
                6
            ),

        "features":
            features
    }


# ============================================================
# LOCAL TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 70)
    print("ASSET RISK ML TEST")
    print("=" * 70)

    test_asset = {
        "asset_id": "AST-0001",
        "criticality": 3,
        "health_score": 88.81,
        "failure_risk": 29.2,
        "installation_date": "2016-01-01",
        "last_inspection_date": "2026-02-01"
    }

    test_defects = []

    test_maintenance_history = []

    try:

        result = predict_asset_risk(
            asset=test_asset,
            defects=test_defects,
            maintenance_history=test_maintenance_history
        )

        print()
        print("ASSET ID:")
        print(result["asset_id"])

        print()
        print("RISK PROBABILITY:")
        print(result["risk_probability"])

        print()
        print("RISK SCORE:")
        print(result["risk_score"])

        print()
        print("PRIORITY:")
        print(result["priority_category"])

        print()
        print("URGENT MAINTENANCE:")
        print(result["urgent_maintenance_prediction"])

        print()
        print("DECISION THRESHOLD:")
        print(result["decision_threshold"])

        print()
        print("FEATURES:")
        for key, value in result["features"].items():
            print(f"  {key}: {value}")

        print()
        print("=" * 70)
        print("ASSET RISK ML TEST SUCCESSFUL")
        print("=" * 70)

    except Exception as error:

        print()
        print("=" * 70)
        print("ASSET RISK ML TEST FAILED")
        print("=" * 70)

        print(
            f"{type(error).__name__}: {error}"
        )

        raise