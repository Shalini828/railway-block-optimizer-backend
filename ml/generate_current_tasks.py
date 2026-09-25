import pandas as pd

from ai_task_priority import calculate_priority


# --------------------------------------------------
# CURRENT MAINTENANCE TASKS
# --------------------------------------------------

tasks = [
    {
        "task_id": "T-AUTO-0001",
        "asset_id": "AST-0001",
        "department": "ENGINEERING",
        "asset_type": "Track",
        "criticality": 5,
        "health_score": 42,
        "failure_risk": 78,
        "asset_age_years": 18,
        "days_since_inspection": 145,
        "defect_count": 4,
        "urgent_defect_count": 2,
        "max_safety_impact": 5,
        "repeat_failure": 1,
        "maintenance_count": 8,
        "corrective_maintenance_count": 5,
        "previous_failure_count": 3,
    },

    {
        "task_id": "T-AUTO-0002",
        "asset_id": "AST-0002",
        "department": "S&T",
        "asset_type": "Signal",
        "criticality": 4,
        "health_score": 65,
        "failure_risk": 52,
        "asset_age_years": 11,
        "days_since_inspection": 75,
        "defect_count": 2,
        "urgent_defect_count": 1,
        "max_safety_impact": 4,
        "repeat_failure": 0,
        "maintenance_count": 6,
        "corrective_maintenance_count": 3,
        "previous_failure_count": 1,
    },

    {
        "task_id": "T-AUTO-0003",
        "asset_id": "AST-0003",
        "department": "TRD",
        "asset_type": "OHE",
        "criticality": 5,
        "health_score": 35,
        "failure_risk": 88,
        "asset_age_years": 20,
        "days_since_inspection": 210,
        "defect_count": 6,
        "urgent_defect_count": 3,
        "max_safety_impact": 5,
        "repeat_failure": 1,
        "maintenance_count": 10,
        "corrective_maintenance_count": 7,
        "previous_failure_count": 4,
    },

    {
        "task_id": "T-AUTO-0004",
        "asset_id": "AST-0004",
        "department": "ENGINEERING",
        "asset_type": "Bridge",
        "criticality": 3,
        "health_score": 78,
        "failure_risk": 30,
        "asset_age_years": 7,
        "days_since_inspection": 40,
        "defect_count": 1,
        "urgent_defect_count": 0,
        "max_safety_impact": 3,
        "repeat_failure": 0,
        "maintenance_count": 3,
        "corrective_maintenance_count": 1,
        "previous_failure_count": 0,
    },

    {
        "task_id": "T-AUTO-0005",
        "asset_id": "AST-0005",
        "department": "S&T",
        "asset_type": "Point Machine",
        "criticality": 5,
        "health_score": 50,
        "failure_risk": 70,
        "asset_age_years": 15,
        "days_since_inspection": 120,
        "defect_count": 3,
        "urgent_defect_count": 2,
        "max_safety_impact": 5,
        "repeat_failure": 1,
        "maintenance_count": 9,
        "corrective_maintenance_count": 6,
        "previous_failure_count": 2,
    }
]


# --------------------------------------------------
# RUN AI PRIORITY
# --------------------------------------------------

results = []

for task in tasks:

    ai_result = calculate_priority(task)

    result = {
        "task_id": task["task_id"],
        "asset_id": task["asset_id"],
        "department": task["department"],
        "asset_type": task["asset_type"],
        **ai_result
    }

    results.append(result)


# --------------------------------------------------
# CREATE RESULT TABLE
# --------------------------------------------------

df = pd.DataFrame(results)

df = df.sort_values(
    "ai_priority_score",
    ascending=False
).reset_index(drop=True)

df["priority_rank"] = range(1, len(df) + 1)

df = df[
    [
        "priority_rank",
        "task_id",
        "asset_id",
        "department",
        "asset_type",
        "risk_probability",
        "risk_score",
        "rule_based_score",
        "ai_priority_score",
        "priority_category"
    ]
]


# --------------------------------------------------
# SAVE RESULTS
# --------------------------------------------------

output_file = "backend/ml/current_task_priorities.csv"

df.to_csv(
    output_file,
    index=False
)


# --------------------------------------------------
# DISPLAY
# --------------------------------------------------

print()
print("=" * 75)
print("       AI MAINTENANCE TASK PRIORITIZATION")
print("=" * 75)

print(df.to_string(index=False))

print("=" * 75)
print(f"Saved results to: {output_file}")
print("=" * 75)