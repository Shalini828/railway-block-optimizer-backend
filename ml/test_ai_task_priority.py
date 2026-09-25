from ai_task_priority import calculate_priority


task = {
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
    "previous_failure_count": 3
}


result = calculate_priority(task)


print()
print("=" * 60)
print("       AI TASK PRIORITY")
print("=" * 60)

print(
    f"Risk probability : "
    f"{result['risk_probability'] * 100:.2f}%"
)

print(
    f"ML risk score    : "
    f"{result['risk_score']:.2f}"
)

print(
    f"Rule score       : "
    f"{result['rule_based_score']:.2f}"
)

print(
    f"AI priority      : "
    f"{result['ai_priority_score']:.2f}"
)

print(
    f"Category         : "
    f"{result['priority_category']}"
)

print("=" * 60)