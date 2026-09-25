"""
Admin System Administration Routes.
Provides live permission matrix and audit log viewer for administrators.
Protected by admin.manage permission.
"""
from typing import Optional, List, Dict, Any
import psycopg
from fastapi import APIRouter, Depends, Query
from auth.security import require_permission, get_current_user, CurrentUser
from auth.permissions import ROLE_TABLE
from db_config import DB_CONFIG

router = APIRouter(
    prefix="/admin",
    tags=["Admin System"],
    dependencies=[Depends(require_permission("admin.manage"))],
)

@router.get("/permission-matrix")
def get_permission_matrix(user: CurrentUser = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Returns the active RBAC permission matrix for all configured roles.
    """
    matrix = {}
    for role_id, info in ROLE_TABLE.items():
        matrix[role_id] = {
            "role_id": info["role_id"],
            "name": info["name"],
            "title": info["title"],
            "system": info["system"],
            "dept": info["dept"],
            "scope": info["scope"],
            "permissions": sorted(list(info["permissions"])),
        }
    return {
        "status": "success",
        "roles": matrix,
    }

@router.get("/audit-log")
def get_audit_log(
    limit: int = Query(100, ge=1, le=500),
    role: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Returns recent audit log records, sorted newest first.
    """
    try:
        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                query = "SELECT audit_id, ts, actor_role, actor_name, method, path, action, target_type, target_id, outcome, detail FROM audit_log"
                conditions = []
                params = []
                if role:
                    conditions.append("actor_role = %s")
                    params.append(role)
                if action:
                    conditions.append("action = %s")
                    params.append(action)
                if conditions:
                    query += " WHERE " + " AND ".join(conditions)
                query += " ORDER BY ts DESC LIMIT %s"
                params.append(limit)

                cur.execute(query, tuple(params))
                rows = cur.fetchall()
                logs = [
                    {
                        "audit_id": r[0],
                        "ts": r[1].isoformat() if r[1] else None,
                        "actor_role": r[2],
                        "actor_name": r[3],
                        "method": r[4],
                        "path": r[5],
                        "action": r[6],
                        "target_type": r[7],
                        "target_id": r[8],
                        "outcome": r[9],
                        "detail": r[10],
                    }
                    for r in rows
                ]
                return {"status": "success", "logs": logs}
    except Exception as e:
        # Fallback if audit_log table does not exist or DB offline
        return {"status": "success", "logs": [], "note": "Audit log empty or database offline"}
