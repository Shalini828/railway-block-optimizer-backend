from datetime import date, datetime
import pandas as pd


# ============================================================
# FEATURES EXPECTED BY THE TRAINED ML MODEL
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
    "previous_failure_count",
]


# ============================================================
# HELPERS
# ============================================================

def _to_bool(value):
    """Convert common database values to True/False."""
    if isinstance(value, bool):
        return value

    if value is None:
        return False

    if isinstance(value, (int, float)):
        return value != 0

    return str(value).strip().lower() in {
        "true",
        "1",
        "yes",
        "y",
        "failure",
        "failed",
    }


def _days_between(start_date):
    """Return number of days from start_date until today."""
    if start_date is None:
        return 0

    if isinstance(start_date, datetime):
        start_date = start_date.date()

    if isinstance(start_date, str):
        start_date = pd.to_datetime(
            start_date,
            errors="coerce"
        )

        if pd.isna(start_date):
            return 0

        start_date = start_date.date()

    if isinstance(start_date, date):
        return max(
            0,
            (date.today() - start_date).days
        )

    return 0


def _asset_age_years(installation_date):
    """Calculate approximate asset age in years."""
    if installation_date is None:
        return 0.0

    if isinstance(installation_date, datetime):
        installation_date = installation_date.date()

    if isinstance(installation_date, str):
        installation_date = pd.to_datetime(
            installation_date,
            errors="coerce"
        )

        if pd.isna(installation_date):
            return 0.0

        installation_date = installation_date.date()

    if isinstance(installation_date, date):
        days = max(
            0,
            (date.today() - installation_date).days
        )

        return round(
            days / 365.25,
            1
        )

    return 0.0


# ============================================================
# BUILD FEATURES FOR ONE ASSET
# ============================================================

def build_asset_features(
    asset,
    defects=None,
    maintenance_history=None,
):
    """
    Convert database records for one asset into
    the 12 features required by the ML model.

    Parameters
    ----------
    asset : dict
        Asset record from the assets table.

    defects : list[dict]
        Defect records belonging to the asset.

    maintenance_history : list[dict]
        Maintenance history records belonging to the asset.

    Returns
    -------
    dict
        ML feature dictionary.
    """

    defects = defects or []
    maintenance_history = maintenance_history or []

    # --------------------------------------------------------
    # BASIC ASSET FEATURES
    # --------------------------------------------------------

    criticality = int(
        asset.get("criticality") or 1
    )

    health_score = float(
        asset.get("health_score") or 100
    )

    failure_risk = float(
        asset.get("failure_risk") or 0
    )

    asset_age_years = _asset_age_years(
        asset.get("installation_date")
    )

    days_since_inspection = _days_between(
        asset.get("last_inspection_date")
    )

    # --------------------------------------------------------
    # DEFECT FEATURES
    # --------------------------------------------------------

    defect_count = len(defects)

    urgent_defect_count = 0
    max_safety_impact = 0
    repeat_failure = 0

    for defect in defects:

        severity_value = defect.get("severity")

        if isinstance(severity_value, str):
            severity_map = {
                "LOW": 1,
                "MEDIUM": 2,
                "HIGH": 4,
                "CRITICAL": 5,
            }

            severity = severity_map.get(
                severity_value.strip().upper(),
                0
            )
        else:
            severity = int(
                severity_value or 0
            )


        safety_value = defect.get("safety_impact")

        if isinstance(safety_value, str):
            safety_map = {
                "LOW": 1,
                "MEDIUM": 2,
                "HIGH": 4,
                "CRITICAL": 5,
            }

            safety_impact = safety_map.get(
                safety_value.strip().upper(),
                0
            )
        else:
            safety_impact = int(
                safety_value or 0
            )

        max_safety_impact = max(
            max_safety_impact,
            safety_impact
        )

        # Treat severe/safety-critical defects as urgent.
        if severity >= 4 or safety_impact >= 4:
            urgent_defect_count += 1

        if _to_bool(
            defect.get("repeat_failure")
        ):
            repeat_failure = 1

    # --------------------------------------------------------
    # MAINTENANCE HISTORY
    # --------------------------------------------------------

    maintenance_count = len(
        maintenance_history
    )

    corrective_maintenance_count = 0
    previous_failure_count = 0

    for history in maintenance_history:

        maintenance_type = str(
            history.get("maintenance_type") or ""
        ).strip().lower()

        if "corrective" in maintenance_type:
            corrective_maintenance_count += 1

        if _to_bool(
            history.get("failure_after_maintenance")
        ):
            previous_failure_count += 1

    # --------------------------------------------------------
    # RETURN EXACT MODEL FEATURES
    # --------------------------------------------------------

    return {
        "criticality": criticality,
        "health_score": health_score,
        "failure_risk": failure_risk,
        "asset_age_years": asset_age_years,
        "days_since_inspection": days_since_inspection,
        "defect_count": defect_count,
        "urgent_defect_count": urgent_defect_count,
        "max_safety_impact": max_safety_impact,
        "repeat_failure": repeat_failure,
        "maintenance_count": maintenance_count,
        "corrective_maintenance_count": (
            corrective_maintenance_count
        ),
        "previous_failure_count": (
            previous_failure_count
        ),
    }


# ============================================================
# CONVERT FEATURES TO MODEL INPUT
# ============================================================

def features_to_dataframe(features):
    """
    Convert feature dictionary into a one-row
    pandas DataFrame in the exact order expected
    by the trained Random Forest model.
    """

    return pd.DataFrame(
        [features],
        columns=FEATURE_COLUMNS
    )