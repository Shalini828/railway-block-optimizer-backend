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
        if joblib is None or not os.path.exists(MODEL_PATH):
            return None

        try:
            _model = joblib.load(MODEL_PATH)
        except Exception:
            _model = None

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


def heuristic_asset_risk(
    asset: dict,
    defects: list,
    maintenance_history: list,
    features: dict = None,
) -> dict:
    crit = float(asset.get("criticality", 3) or 3)
    health = float(asset.get("health_score", 70) or 70)
    fail_risk = float(asset.get("failure_risk", 30) or 30)
    defects_list = defects or []
    urgent_defects = sum(
        1 for d in defects_list
        if float(d.get("severity", 0) or 0) >= 4 or float(d.get("safety_impact", 0) or 0) >= 4
    )
    repeat_failures = sum(1 for d in defects_list if d.get("repeat_failure"))

    base_score = (
        (crit / 5.0) * 30.0
        + ((100.0 - health) / 100.0) * 35.0
        + (fail_risk / 100.0) * 20.0
        + min(urgent_defects * 7.5, 15.0)
    )
    if repeat_failures > 0:
        base_score += 5.0

    risk_score = round(max(0.0, min(100.0, base_score)), 2)
    prob = round(risk_score / 100.0, 6)
    threshold = get_threshold()
    category = get_priority_category(risk_score)
    urgent_pred = int(prob >= threshold)

    return {
        "asset_id": asset.get("asset_id"),
        "risk_probability": prob,
        "risk_score": risk_score,
        "priority_category": category,
        "urgent_maintenance_prediction": urgent_pred,
        "decision_threshold": round(float(threshold), 6),
        "features": features or {},
    }


# ============================================================
# PREDICT ASSET RISK
# ============================================================

def predict_asset_risk(
    asset: dict,
    defects: list,
    maintenance_history: list
) -> dict:
    threshold = get_threshold()

    try:
        from .features import build_asset_features
        features = build_asset_features(
            asset=asset,
            defects=defects or [],
            maintenance_history=maintenance_history or []
        )
    except Exception:
        features = {}

    model = get_model()
    if model is None or pd is None:
        return heuristic_asset_risk(asset, defects, maintenance_history, features)

    try:
        feature_data = {}
        for column in FEATURE_COLUMNS:
            value = features.get(column, 0)
            try:
                value = float(value)
            except (TypeError, ValueError):
                value = 0.0
            feature_data[column] = [value]

        X = pd.DataFrame(feature_data, columns=FEATURE_COLUMNS)
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
                positive_index = len(classes) - 1
        else:
            positive_index = 1

        urgent_probability = float(probabilities[0][positive_index])
        urgent_probability = max(0.0, min(1.0, urgent_probability))
        urgent_prediction = int(urgent_probability >= threshold)
        risk_score = round(urgent_probability * 100, 2)
        priority_category = get_priority_category(risk_score)

        return {
            "asset_id": asset.get("asset_id"),
            "risk_probability": round(urgent_probability, 6),
            "risk_score": risk_score,
            "priority_category": priority_category,
            "urgent_maintenance_prediction": urgent_prediction,
            "decision_threshold": round(float(threshold), 6),
            "features": features,
        }
    except Exception:
        return heuristic_asset_risk(asset, defects, maintenance_history, features)


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