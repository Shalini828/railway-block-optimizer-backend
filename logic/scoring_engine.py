"""
IR-ABPS Scoring Engine

Phase 1:
Transparent deterministic scoring for maintenance
requisition prioritization.

All scores are normalized to 0-100.
"""

from typing import Any, Dict


# ============================================================
# WEIGHTS
# ============================================================

CRITICALITY_WEIGHT = 0.30
SAFETY_RISK_WEIGHT = 0.25
TSR_RISK_WEIGHT = 0.20
OVERDUE_WEIGHT = 0.15
OPERATIONAL_IMPACT_WEIGHT = 0.10


# ============================================================
# NORMALIZATION HELPERS
# ============================================================

def clamp(value: float, minimum: float = 0, maximum: float = 100) -> float:
    """
    Keep a score within the specified range.
    """

    return max(
        minimum,
        min(maximum, float(value)),
    )


def normalize_criticality(value: Any) -> float:
    """
    Convert maintenance criticality into 0-100.

    Supported examples:
        CRITICAL = 100
        HIGH     = 80
        MEDIUM   = 60
        LOW      = 30

    Numeric values are also supported.
    """

    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        return clamp(float(value))

    value = str(value).strip().upper()

    mapping = {
        "CRITICAL": 100,
        "HIGH": 80,
        "MEDIUM": 60,
        "LOW": 30,
    }

    return float(mapping.get(value, 0))


def normalize_safety_risk(value: Any) -> float:
    """
    Convert safety risk from a 1-5 scale to 0-100.

    1 = lowest risk
    5 = highest risk
    """

    if value is None:
        return 0.0

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return 0.0

    numeric_value = max(
        1,
        min(5, numeric_value),
    )

    return ((numeric_value - 1) / 4) * 100


def normalize_tsr_risk(value: Any) -> float:
    """
    TSR risk is represented as a boolean.

    True  = 100
    False = 0
    """

    if isinstance(value, bool):
        return 100.0 if value else 0.0

    value = str(value).strip().upper()

    if value in {
        "TRUE",
        "YES",
        "Y",
        "1",
    }:
        return 100.0

    return 0.0


def normalize_overdue(days_overdue: Any) -> float:
    """
    Convert overdue duration into a 0-100 score.

    0 days   = 0
    30+ days = 100

    Values above 30 days are capped.
    """

    if days_overdue is None:
        return 0.0

    try:
        days = max(
            0,
            float(days_overdue),
        )
    except (TypeError, ValueError):
        return 0.0

    return clamp(
        (days / 30) * 100
    )


def normalize_operational_impact(value: Any) -> float:
    """
    Convert operational impact into 0-100.

    Supports:
        0-100 numeric values
        CRITICAL / HIGH / MEDIUM / LOW labels
    """

    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        return clamp(float(value))

    value = str(value).strip().upper()

    mapping = {
        "CRITICAL": 100,
        "HIGH": 80,
        "MEDIUM": 60,
        "LOW": 30,
    }

    return float(mapping.get(value, 0))


# ============================================================
# PRIORITY SCORE
# ============================================================

def calculate_priority_score(
    criticality: Any = None,
    safety_risk: Any = None,
    tsr_risk: Any = None,
    days_overdue: Any = None,
    operational_impact: Any = None,
) -> Dict[str, Any]:
    """
    Calculate a transparent maintenance priority score.

    Returns:
        score
        level
        component scores
        weighted contributions
    """

    criticality_score = normalize_criticality(
        criticality
    )

    safety_score = normalize_safety_risk(
        safety_risk
    )

    tsr_score = normalize_tsr_risk(
        tsr_risk
    )

    overdue_score = normalize_overdue(
        days_overdue
    )

    operational_score = normalize_operational_impact(
        operational_impact
    )

    # --------------------------------------------------------
    # Weighted contributions
    # --------------------------------------------------------

    criticality_contribution = (
        criticality_score
        * CRITICALITY_WEIGHT
    )

    safety_contribution = (
        safety_score
        * SAFETY_RISK_WEIGHT
    )

    tsr_contribution = (
        tsr_score
        * TSR_RISK_WEIGHT
    )

    overdue_contribution = (
        overdue_score
        * OVERDUE_WEIGHT
    )

    operational_contribution = (
        operational_score
        * OPERATIONAL_IMPACT_WEIGHT
    )

    # --------------------------------------------------------
    # Final score
    # --------------------------------------------------------

    final_score = clamp(
        criticality_contribution
        + safety_contribution
        + tsr_contribution
        + overdue_contribution
        + operational_contribution
    )

    final_score = round(
        final_score,
        2,
    )

    # --------------------------------------------------------
    # Priority level
    # --------------------------------------------------------

    if final_score >= 80:
        priority_level = "CRITICAL"

    elif final_score >= 60:
        priority_level = "HIGH"

    elif final_score >= 40:
        priority_level = "MEDIUM"

    else:
        priority_level = "LOW"

    return {
        "score": final_score,
        "level": priority_level,

        "components": {
            "criticality": round(
                criticality_score,
                2,
            ),
            "safety_risk": round(
                safety_score,
                2,
            ),
            "tsr_risk": round(
                tsr_score,
                2,
            ),
            "overdue": round(
                overdue_score,
                2,
            ),
            "operational_impact": round(
                operational_score,
                2,
            ),
        },

        "contributions": {
            "criticality": round(
                criticality_contribution,
                2,
            ),
            "safety_risk": round(
                safety_contribution,
                2,
            ),
            "tsr_risk": round(
                tsr_contribution,
                2,
            ),
            "overdue": round(
                overdue_contribution,
                2,
            ),
            "operational_impact": round(
                operational_contribution,
                2,
            ),
        },
    }