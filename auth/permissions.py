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
# ROLE ALIASES & NORMALIZATION
# ============================================================

ROLE_ALIASES: Dict[str, str] = {
    "role-planner": "admin",
    "planner": "admin",
    "role-admin": "admin",
    "admin": "admin",
    "drm": "admin",
    "senior officer": "admin",
    "role-controller": "control",
    "controller": "control",
    "control": "control",
    "role-control": "control",
    "chief controller": "control",
    "role-tms": "engineering",
    "tms": "engineering",
    "engineering": "engineering",
    "role-engineering": "engineering",
    "sse/p.way": "engineering",
    "p.way": "engineering",
    "pway": "engineering",
    "sse / p.way": "engineering",
    "role-tdms": "traction",
    "tdms": "traction",
    "traction": "traction",
    "role-traction": "traction",
    "sse/trd": "traction",
    "trd": "traction",
    "sse / trd": "traction",
    "role-smms": "signal",
    "smms": "signal",
    "signal": "signal",
    "role-signal": "signal",
    "sse/s&t": "signal",
    "s&t": "signal",
    "sse / s&t": "signal",
}

def resolve_role(role_id: Optional[str]) -> str:
    """Normalize role string to canonical role key (admin, control, engineering, traction, signal)."""
    if not role_id:
        return "admin"
    clean = str(role_id).strip().strip('"').strip("'").lower()
    return ROLE_ALIASES.get(clean, clean)


# Populate alias lookups into ROLE_TABLE and REPORTABLE_GROUPS
for _alias, _target in ROLE_ALIASES.items():
    if _target in ROLE_TABLE:
        if _alias not in ROLE_TABLE:
            ROLE_TABLE[_alias] = ROLE_TABLE[_target]
        if _alias.upper() not in ROLE_TABLE:
            ROLE_TABLE[_alias.upper()] = ROLE_TABLE[_target]
    if _target in REPORTABLE_GROUPS:
        REPORTABLE_GROUPS[_alias] = REPORTABLE_GROUPS[_target]
        REPORTABLE_GROUPS[_alias.upper()] = REPORTABLE_GROUPS[_target]


# ============================================================
# PURE HELPER FUNCTIONS
# ============================================================

def has_permission(role_id: str, perm: str) -> bool:
    """Returns True if the role possesses the specified permission key."""
    norm = resolve_role(role_id)
    role = ROLE_TABLE.get(norm) or ROLE_TABLE.get(role_id)
    if not role:
        # Default fallback for admin-level operations in demo
        if "admin" in ROLE_TABLE and ("planner" in str(role_id).lower() or "admin" in str(role_id).lower()):
            return perm in ROLE_TABLE["admin"]["permissions"]
        return False
    return perm in role["permissions"]


def is_network_scope(role_id: str) -> bool:
    """Returns True if the role has network-wide scope."""
    norm = resolve_role(role_id)
    role = ROLE_TABLE.get(norm) or ROLE_TABLE.get(role_id)
    if not role:
        return False
    return role.get("scope") == "network"


def department_of(role_id: str) -> Optional[str]:
    """
    Returns department code ('TMS', 'TDMS') for department roles.
    Returns None for network-scoped roles ('admin', 'control').
    """
    norm = resolve_role(role_id)
    role = ROLE_TABLE.get(norm) or ROLE_TABLE.get(role_id)
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
    norm = resolve_role(role_id)
    allowed_groups = REPORTABLE_GROUPS.get(norm) or REPORTABLE_GROUPS.get(role_id, set())
    return group in allowed_groups

