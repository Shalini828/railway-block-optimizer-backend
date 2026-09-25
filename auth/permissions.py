"""
Role-Based Access Control (RBAC) Permission Definitions & Source of Truth.
Defines role permissions, scopes, emergency incident group mappings, and pure helper functions.
"""
from typing import Dict, Optional, Set, Any

# ============================================================
# ROLE DEFINITIONS & PERMISSIONS
# ============================================================

ROLE_TABLE: Dict[str, Dict[str, Any]] = {
    "admin": {
        "role_id": "admin",
        "name": "Senior Officer / DRM Planning",
        "title": "ADMIN / SENIOR OFFICER",
        "system": "COA + BDMS (Full Authority)",
        "dept": "COA",
        "scope": "network",
        "permissions": {
            # Dashboard
            "dashboard.view",
            # Requests
            "requests.view",
            "requests.create",
            "requests.edit",
            "requests.cancel",
            "requests.reject",
            "requests.override_priority",  # reserved
            # Optimizer
            "optimizer.view",
            "optimizer.run",
            "optimizer.simulate",
            "optimizer.override",   # reserved
            "optimizer.configure",  # reserved
            # Planner
            "planner.view",
            "planner.review",
            "planner.rework",
            "planner.reject",
            "planner.approve",
            "planner.edit",         # reserved
            # Conflicts
            "conflicts.view",
            "conflicts.resolve",
            # Maintenance Tasks
            "tasks.view",
            "tasks.update",
            "tasks.create",         # reserved
            # Analytics
            "analytics.view",
            # Emergency
            "emergency.view",
            "emergency.report",
            "emergency.resolve",
            # Corridors
            "corridors.view",
            "corridors.configure",  # reserved
            # Trains
            "trains.view",
            "trains.edit",          # reserved
            # Special Trains
            "special_trains.view",
            "special_trains.manage",
            # AI
            "ai.risk.view",
            "ai.priorities.apply",
            # Admin management
            "admin.manage",
        },
    },
    "control": {
        "role_id": "control",
        "name": "Chief Controller",
        "title": "CONTROL OFFICE",
        "system": "COA Live Monitoring",
        "dept": "COA",
        "scope": "network",
        "permissions": {
            # Dashboard
            "dashboard.view",
            # Requests (read-only)
            "requests.view",
            # Optimizer
            "optimizer.view",
            "optimizer.run",
            "optimizer.simulate",
            # Planner (review & rework only, no final approve/reject)
            "planner.view",
            "planner.review",
            "planner.rework",
            # Conflicts
            "conflicts.view",
            "conflicts.resolve",
            # Maintenance Tasks (read-only)
            "tasks.view",
            # Analytics
            "analytics.view",
            # Emergency
            "emergency.view",
            "emergency.report",
            "emergency.resolve",
            # Corridors
            "corridors.view",
            # Trains
            "trains.view",
            "trains.edit",          # reserved
            # Special Trains
            "special_trains.view",
            "special_trains.manage",
            # AI
            "ai.risk.view",
        },
    },
    "engineering": {
        "role_id": "engineering",
        "name": "SSE / P.Way",
        "title": "ENGINEERING TEAM",
        "system": "TMS Requisition Portal",
        "dept": "TMS",
        "scope": "department",
        "permissions": {
            # Dashboard
            "dashboard.view",
            # Requests (own dept)
            "requests.view",
            "requests.create",
            "requests.edit",
            "requests.cancel",
            # Optimizer (view & what-if simulation)
            "optimizer.view",
            "optimizer.simulate",
            # Planner (own blocks, request change)
            "planner.view",
            "planner.request_change",
            # Conflicts (own blocks, acknowledge)
            "conflicts.view",
            "conflicts.acknowledge",
            # Maintenance Tasks (own dept)
            "tasks.view",
            "tasks.update",
            "tasks.create",         # reserved
            # Analytics
            "analytics.view",
            # Emergency
            "emergency.view",
            "emergency.report",
            # Corridors
            "corridors.view",
            # Trains
            "trains.view",
            # Special Trains
            "special_trains.view",
            # AI
            "ai.risk.view",
        },
    },
    "traction": {
        "role_id": "traction",
        "name": "SSE / TRD",
        "title": "TRACTION TEAM",
        "system": "TDMS Isolation & Power",
        "dept": "TDMS",
        "scope": "department",
        "permissions": {
            # Dashboard
            "dashboard.view",
            # Requests (own dept)
            "requests.view",
            "requests.create",
            "requests.edit",
            "requests.cancel",
            # Optimizer (read-only view)
            "optimizer.view",
            # Planner (own blocks, request change)
            "planner.view",
            "planner.request_change",
            # Conflicts (own blocks, acknowledge)
            "conflicts.view",
            "conflicts.acknowledge",
            # Maintenance Tasks (own dept)
            "tasks.view",
            "tasks.update",
            "tasks.create",         # reserved
            # Analytics
            "analytics.view",
            # Emergency
            "emergency.view",
            "emergency.report",
            # Corridors
            "corridors.view",
            # Trains
            "trains.view",
            # Special Trains
            "special_trains.view",
            # AI
            "ai.risk.view",
        },
    },
    "signal": {
        "role_id": "signal",
        "name": "SSE / S&T",
        "title": "SIGNAL TEAM",
        "system": "SMMS Requisition Portal",
        "dept": "SMMS",
        "scope": "department",
        "permissions": {
            # Dashboard
            "dashboard.view",
            # Requests (own dept)
            "requests.view",
            "requests.create",
            "requests.edit",
            "requests.cancel",
            # Optimizer (read-only view)
            "optimizer.view",
            # Planner (own blocks, request change)
            "planner.view",
            "planner.request_change",
            # Conflicts (own blocks, acknowledge)
            "conflicts.view",
            "conflicts.acknowledge",
            # Maintenance Tasks (own dept)
            "tasks.view",
            "tasks.update",
            "tasks.create",         # reserved
            # Analytics
            "analytics.view",
            # Emergency
            "emergency.view",
            "emergency.report",
            # Corridors
            "corridors.view",
            # Trains
            "trains.view",
            # Special Trains
            "special_trains.view",
            # AI
            "ai.risk.view",
        },
    },
}

# ============================================================
# EMERGENCY INCIDENT GROUPS & REPORTABLE MAPPING
# ============================================================

EMERGENCY_TYPE_GROUPS: Dict[str, str] = {
    "Track Fracture": "Track",
    "OHE Snapping": "Traction",
    "Signal Failure": "S&T",
    "Point Machine Failure": "S&T",
    "Bridge/Structure Risk": "Engineering",
    "Obstruction on Track": "Operations",
    "Other Critical Hazard": "General",
}

ALL_EMERGENCY_GROUPS: Set[str] = {
    "Track",
    "Traction",
    "S&T",
    "Engineering",
    "Operations",
    "General",
}

REPORTABLE_GROUPS: Dict[str, Set[str]] = {
    "admin": ALL_EMERGENCY_GROUPS,
    "control": ALL_EMERGENCY_GROUPS,
    "engineering": {"Track", "Engineering", "General"},
    "traction": {"Traction", "General"},
    "signal": {"S&T", "General"},
}

# ============================================================
# PURE HELPER FUNCTIONS
# ============================================================

def has_permission(role_id: str, perm: str) -> bool:
    """Returns True if the role possesses the specified permission key."""
    role = ROLE_TABLE.get(role_id)
    if not role:
        return False
    return perm in role["permissions"]


def is_network_scope(role_id: str) -> bool:
    """Returns True if the role has network-wide scope."""
    role = ROLE_TABLE.get(role_id)
    if not role:
        return False
    return role.get("scope") == "network"


def department_of(role_id: str) -> Optional[str]:
    """
    Returns department code ('TMS', 'TDMS') for department roles.
    Returns None for network-scoped roles ('admin', 'control').
    """
    role = ROLE_TABLE.get(role_id)
    if not role or role.get("scope") == "network":
        return None
    return role.get("dept")


def dept_id_of(role_id: str) -> Optional[str]:
    """
    Returns database department_id (e.g. 'DEPT-TMS', 'DEPT-TDMS') for department roles.
    Returns None for network-scoped roles.
    """
    dept = department_of(role_id)
    return f"DEPT-{dept}" if dept else None


def can_report_emergency_type(role_id: str, emergency_type: str) -> bool:
    """
    Checks if a role is authorized to report a specific emergency incident type.
    """
    group = EMERGENCY_TYPE_GROUPS.get(emergency_type)
    if not group:
        return False
    allowed_groups = REPORTABLE_GROUPS.get(role_id, set())
    return group in allowed_groups
