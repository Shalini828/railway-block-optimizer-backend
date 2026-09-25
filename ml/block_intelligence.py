import os
import sys
from typing import Dict, Any


# ============================================================
# PATH CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(BASE_DIR)

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


# ============================================================
# IMPORT EXISTING ML SERVICES
# ============================================================

from ml.predict_service import predict_asset_risk
from ml.traffic_predict_service import predict_traffic_impact
from ml.goods_forecast_service import predict_goods_train_demand


# ============================================================
# HELPER
# ============================================================

def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert a value to float.
    Prevents None/string values from breaking the ML pipeline.
    """
    try:
        if value is None:
            return default

        return float(value)

    except (TypeError, ValueError):
        return default


# ============================================================
# OVERALL AI ASSESSMENT
# ============================================================

def get_overall_assessment(
    asset_risk_score: float,
    traffic_impact_score: float,
    goods_demand: float
) -> Dict[str, Any]:

    asset_risk_score = max(
        0.0,
        min(100.0, safe_float(asset_risk_score))
    )

    traffic_impact_score = max(
        0.0,
        min(100.0, safe_float(traffic_impact_score))
    )

    goods_demand = max(
        0.0,
        safe_float(goods_demand)
    )

    # --------------------------------------------------------
    # Asset risk classification
    # --------------------------------------------------------

    if asset_risk_score >= 85:
        asset_assessment = "CRITICAL"

    elif asset_risk_score >= 70:
        asset_assessment = "HIGH"

    elif asset_risk_score >= 50:
        asset_assessment = "MEDIUM"

    else:
        asset_assessment = "LOW"

    # --------------------------------------------------------
    # Traffic impact classification
    # --------------------------------------------------------

    if traffic_impact_score >= 80:
        traffic_assessment = "CRITICAL"

    elif traffic_impact_score >= 60:
        traffic_assessment = "HIGH"

    elif traffic_impact_score >= 35:
        traffic_assessment = "MEDIUM"

    else:
        traffic_assessment = "LOW"

    # --------------------------------------------------------
    # Goods demand classification
    # --------------------------------------------------------

    if goods_demand >= 40:
        goods_assessment = "VERY_HIGH"

    elif goods_demand >= 30:
        goods_assessment = "HIGH"

    elif goods_demand >= 15:
        goods_assessment = "MEDIUM"

    else:
        goods_assessment = "LOW"

    # --------------------------------------------------------
    # Combined pressure score
    #
    # Asset risk       -> 35%
    # Traffic impact   -> 40%
    # Goods demand     -> 25%
    #
    # Goods demand is normalized to 0-100.
    # --------------------------------------------------------

    normalized_goods_demand = min(
        goods_demand * 2,
        100.0
    )

    pressure_score = (
        asset_risk_score * 0.35
        + traffic_impact_score * 0.40
        + normalized_goods_demand * 0.25
    )

    pressure_score = round(
        min(100.0, max(0.0, pressure_score)),
        2
    )

    # --------------------------------------------------------
    # Overall classification
    # --------------------------------------------------------

    if pressure_score >= 80:
        overall_level = "CRITICAL"

    elif pressure_score >= 60:
        overall_level = "HIGH"

    elif pressure_score >= 35:
        overall_level = "MEDIUM"

    else:
        overall_level = "LOW"

    # IMPORTANT:
    # Return BOTH names for compatibility.
    #
    # Frontend currently expects:
    # overall_assessment.pressure_score
    #
    # Existing backend code may expect:
    # overall_assessment.overall_pressure_score
    # --------------------------------------------------------

    return {
        "pressure_score": pressure_score,
        "overall_pressure_score": pressure_score,

        "overall_level": overall_level,

        "asset_assessment": asset_assessment,
        "traffic_assessment": traffic_assessment,
        "goods_assessment": goods_assessment
    }



def calculate_block_priority(
    asset_risk_score: float,
    traffic_impact_score: float,
    goods_demand: float
) -> dict:
    """
    Convert ML predictions into a unified block priority score.

    Higher score = higher scheduling priority.
    """

    # Normalize goods demand to 0-100 scale
    goods_score = min(
        100.0,
        max(0.0, goods_demand * 2)
    )

    # Weighted AI priority
    priority_score = (
        asset_risk_score * 0.35
        + traffic_impact_score * 0.40
        + goods_score * 0.25
    )

    priority_score = round(
        min(100.0, max(0.0, priority_score)),
        2
    )

    if priority_score >= 80:
        priority_level = "CRITICAL"
    elif priority_score >= 60:
        priority_level = "HIGH"
    elif priority_score >= 35:
        priority_level = "MEDIUM"
    else:
        priority_level = "LOW"

    return {
        "priority_score": priority_score,
        "priority_level": priority_level,
        "asset_weight": 0.35,
        "traffic_weight": 0.40,
        "goods_weight": 0.25,
    }


# ============================================================
# UNIFIED BLOCK INTELLIGENCE
# ============================================================

def analyze_block(
    asset: Dict[str, Any],
    defects: list,
    maintenance_history: list,
    traffic_inputs: Dict[str, Any],
    goods_inputs: Dict[str, Any]
) -> Dict[str, Any]:

    # ========================================================
    # 1. ASSET RISK
    # ========================================================

    asset_result = predict_asset_risk(
        asset=asset,
        defects=defects,
        maintenance_history=maintenance_history
    )

    asset_risk_score = safe_float(
        asset_result.get("risk_score", 0)
    )

    # ========================================================
    # 2. TRAFFIC IMPACT
    # ========================================================

    traffic_result = predict_traffic_impact(
        block_duration_min=int(
            traffic_inputs.get("block_duration_min", 0)
        ),

        start_hour=int(
            traffic_inputs.get("start_hour", 0)
        ),

        passenger_trains=int(
            traffic_inputs.get("passenger_trains", 0)
        ),

        goods_trains=int(
            traffic_inputs.get("goods_trains", 0)
        ),

        special_trains=int(
            traffic_inputs.get("special_trains", 0)
        ),

        express_trains=int(
            traffic_inputs.get("express_trains", 0)
        ),

        corridor_congestion=safe_float(
            traffic_inputs.get("corridor_congestion", 0)
        ),

        criticality=int(
            traffic_inputs.get("criticality", 0)
        ),

        maintenance_priority=safe_float(
            traffic_inputs.get("maintenance_priority", 0)
        )
    )

    traffic_score = safe_float(
        traffic_result.get(
            "traffic_impact_score",
            traffic_result.get("impact_score", 0)
        )
    )

    # ========================================================
    # 3. GOODS TRAIN DEMAND
    # ========================================================

    goods_result = predict_goods_train_demand(
        day_of_week=int(
            goods_inputs.get("day_of_week", 0)
        ),

        month=int(
            goods_inputs.get("month", 1)
        ),

        is_weekend=int(
            goods_inputs.get("is_weekend", 0)
        ),

        festival_period=int(
            goods_inputs.get("festival_period", 0)
        ),

        operational_pressure=safe_float(
            goods_inputs.get("operational_pressure", 0)
        ),

        industrial_demand=safe_float(
            goods_inputs.get("industrial_demand", 0)
        ),

        previous_day_demand=safe_float(
            goods_inputs.get("previous_day_demand", 0)
        ),

        corridor_id=str(
            goods_inputs.get("corridor_id", "")
        ),

        commodity=str(
            goods_inputs.get("commodity", "UNKNOWN")
        )
    )

    goods_demand = safe_float(
        goods_result.get(
            "predicted_goods_train_demand",
            goods_result.get("predicted_demand", 0)
        )
    )

    # ========================================================
    # 4. OVERALL AI ASSESSMENT
    # ========================================================

    overall = get_overall_assessment(
        asset_risk_score=asset_risk_score,
        traffic_impact_score=traffic_score,
        goods_demand=goods_demand
    )

    priority = calculate_block_priority(
    asset_risk_score,
    traffic_score,
    goods_demand
    )

    # ========================================================
    # 5. FINAL UNIFIED RESPONSE
    # ========================================================

    return {
        "asset_risk": asset_result,

        "traffic_impact": traffic_result,

        "goods_demand": goods_result,
        "overall_assessment": overall,
        "block_priority": priority
        
    }

# ============================================================
# TEST UNIFIED BLOCK INTELLIGENCE
# ============================================================

if __name__ == "__main__":

    print("=" * 70)
    print("UNIFIED BLOCK AI INTELLIGENCE TEST")
    print("=" * 70)

    # --------------------------------------------------------
    # TEST ASSET
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # TRAFFIC INPUTS
    # --------------------------------------------------------

    traffic_inputs = {
        "block_duration_min": 120,
        "start_hour": 18,
        "passenger_trains": 8,
        "goods_trains": 4,
        "special_trains": 1,
        "express_trains": 3,
        "corridor_congestion": 70,
        "criticality": 4,
        "maintenance_priority": 80
    }

    # --------------------------------------------------------
    # GOODS FORECAST INPUTS
    # --------------------------------------------------------

    goods_inputs = {
        "day_of_week": 2,
        "month": 10,
        "is_weekend": 0,
        "festival_period": 1,
        "operational_pressure": 70,
        "industrial_demand": 85,
        "previous_day_demand": 25,
        "corridor_id": "C09",
        "commodity": "COAL"
    }

    # --------------------------------------------------------
    # RUN UNIFIED AI
    # --------------------------------------------------------

    result = analyze_block(
        asset=test_asset,
        defects=test_defects,
        maintenance_history=test_maintenance_history,
        traffic_inputs=traffic_inputs,
        goods_inputs=goods_inputs
    )

    # --------------------------------------------------------
    # DISPLAY ASSET RISK
    # --------------------------------------------------------

    print("\nASSET RISK")
    print("-" * 40)

    print(
        "Risk Score:",
        result["asset_risk"]["risk_score"]
    )

    print(
        "Risk Probability:",
        result["asset_risk"]["risk_probability"]
    )

    print(
        "Priority:",
        result["asset_risk"]["priority_category"]
    )

    print(
        "Urgent Maintenance:",
        result["asset_risk"]["urgent_maintenance_prediction"]
    )

    # --------------------------------------------------------
    # DISPLAY TRAFFIC IMPACT
    # --------------------------------------------------------

    print("\nTRAFFIC IMPACT")
    print("-" * 40)

    print(
        "Impact Score:",
        result["traffic_impact"]["traffic_impact_score"]
    )

    print(
        "Disruption Level:",
        result["traffic_impact"]["disruption_level"]
    )

    # --------------------------------------------------------
    # DISPLAY GOODS DEMAND
    # --------------------------------------------------------

    print("\nGOODS TRAIN DEMAND")
    print("-" * 40)

    print(
        "Predicted Demand:",
        result["goods_demand"]["predicted_goods_train_demand"]
    )

    print(
        "Demand Level:",
        result["goods_demand"]["demand_level"]
    )

    # --------------------------------------------------------
    # DISPLAY OVERALL ASSESSMENT
    # --------------------------------------------------------

    print("\nOVERALL ASSESSMENT")
    print("-" * 40)

    print(
        "Pressure Score:",
        result["overall_assessment"]["overall_pressure_score"]
    )

    print(
        "Overall Level:",
        result["overall_assessment"]["overall_level"]
    )

    print(
        "Asset:",
        result["overall_assessment"]["asset_assessment"]
    )

    print(
        "Traffic:",
        result["overall_assessment"]["traffic_assessment"]
    )

    print(
        "Goods:",
        result["overall_assessment"]["goods_assessment"]
    )

    print("\n" + "=" * 70)
    print("UNIFIED BLOCK AI INTELLIGENCE TEST SUCCESSFUL")
    print("=" * 70)