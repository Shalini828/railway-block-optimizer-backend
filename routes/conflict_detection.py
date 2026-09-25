from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime
import psycopg
import os
from dotenv import load_dotenv

from auth.security import require_permission, get_current_user, CurrentUser
from auth.permissions import is_network_scope, department_of
from auth.audit import record_audit

load_dotenv()

router = APIRouter(
    prefix="/conflicts",
    tags=["Conflict Detection"]
)


def get_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )


@router.get("/", dependencies=[Depends(require_permission("conflicts.view"))])
def detect_conflicts(user: CurrentUser = Depends(get_current_user)):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        # ==========================================
        # FIND OVERLAPPING BLOCK REQUESTS
        # ==========================================

        dept_code = department_of(user.role_id)
        if not is_network_scope(user.role_id) and dept_code:
            dept_id = f"DEPT-{dept_code}"
            cursor.execute("""
                SELECT
                    a.request_id AS request_1,
                    b.request_id AS request_2,
                    a.corridor_id,
                    a.requested_date,
                    a.requested_start AS start_1,
                    a.requested_end AS end_1,
                    b.requested_start AS start_2,
                    b.requested_end AS end_2
                FROM block_requests a
                JOIN block_requests b
                    ON a.corridor_id = b.corridor_id
                    AND a.requested_date = b.requested_date
                    AND a.request_id < b.request_id
                WHERE
                    a.requested_start IS NOT NULL
                    AND a.requested_end IS NOT NULL
                    AND b.requested_start IS NOT NULL
                    AND b.requested_end IS NOT NULL
                    AND a.requested_start < b.requested_end
                    AND b.requested_start < a.requested_end
                    AND (a.department_id = %s OR b.department_id = %s)
                ORDER BY
                    a.requested_date,
                    a.corridor_id
            """, (dept_id, dept_id))
        else:
            cursor.execute("""
                SELECT
                    a.request_id AS request_1,
                    b.request_id AS request_2,
                    a.corridor_id,
                    a.requested_date,
                    a.requested_start AS start_1,
                    a.requested_end AS end_1,
                    b.requested_start AS start_2,
                    b.requested_end AS end_2
                FROM block_requests a
                JOIN block_requests b
                    ON a.corridor_id = b.corridor_id
                    AND a.requested_date = b.requested_date
                    AND a.request_id < b.request_id
                WHERE
                    a.requested_start IS NOT NULL
                    AND a.requested_end IS NOT NULL
                    AND b.requested_start IS NOT NULL
                    AND b.requested_end IS NOT NULL
                    AND a.requested_start < b.requested_end
                    AND b.requested_start < a.requested_end
                ORDER BY
                    a.requested_date,
                    a.corridor_id
            """)

        rows = cursor.fetchall()

        conflicts = []

        for row in rows:

            request_1 = row[0]
            request_2 = row[1]

            # ======================================
            # CHECK IF CONFLICT ALREADY EXISTS
            # ======================================

            cursor.execute("""
                SELECT
                    conflict_id,
                    conflict_status,
                    resolution_note,
                    resolved_by,
                    resolved_at
                FROM block_conflicts
                WHERE request_1 = %s
                  AND request_2 = %s
            """, (
                request_1,
                request_2
            ))

            existing = cursor.fetchone()

            # ======================================
            # CREATE CONFLICT IF NEW
            # ======================================

            if existing:

                conflict_id = existing[0]
                conflict_status = existing[1]
                resolution_note = existing[2]
                resolved_by = existing[3]
                resolved_at = existing[4]

            else:

                cursor.execute("""
                    INSERT INTO block_conflicts
                    (
                        request_1,
                        request_2,
                        corridor_id,
                        conflict_date,
                        request_1_start,
                        request_1_end,
                        request_2_start,
                        request_2_end,
                        conflict_type,
                        conflict_status
                    )
                    VALUES
                    (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        'TIME_OVERLAP',
                        'OPEN'
                    )
                    RETURNING conflict_id
                """, (
                    request_1,
                    request_2,
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                    row[6],
                    row[7]
                ))

                conflict_id = cursor.fetchone()[0]

                conflict_status = "OPEN"
                resolution_note = None
                resolved_by = None
                resolved_at = None

        # ==========================================
        # COMMIT NEW CONFLICTS
        # ==========================================

        conn.commit()

        # ==========================================
        # RETURN CONFLICTS
        # ==========================================

        for row in rows:

            request_1 = row[0]
            request_2 = row[1]

            cursor.execute("""
                SELECT
                    conflict_id,
                    conflict_status,
                    resolution_note,
                    resolved_by,
                    resolved_at
                FROM block_conflicts
                WHERE request_1 = %s
                  AND request_2 = %s
            """, (
                request_1,
                request_2
            ))

            conflict = cursor.fetchone()

            conflicts.append({
                "conflict_id": conflict[0],
                "request_1": request_1,
                "request_2": request_2,
                "corridor_id": row[2],
                "requested_date": (
                    str(row[3])
                    if row[3]
                    else None
                ),
                "request_1_start": (
                    str(row[4])
                    if row[4]
                    else None
                ),
                "request_1_end": (
                    str(row[5])
                    if row[5]
                    else None
                ),
                "request_2_start": (
                    str(row[6])
                    if row[6]
                    else None
                ),
                "request_2_end": (
                    str(row[7])
                    if row[7]
                    else None
                ),
                "conflict_type": "TIME_OVERLAP",
                "conflict_status": conflict[1],
                "resolution_note": conflict[2],
                "resolved_by": conflict[3],
                "resolved_at": (
                    str(conflict[4])
                    if conflict[4]
                    else None
                )
            })

        return {
            "status": "success",
            "conflict_count": len(conflicts),
            "conflicts": conflicts
        }

    except Exception as e:

        conn.rollback()

        return {
            "status": "error",
            "message": str(e)
        }

    finally:

        cursor.close()
        conn.close()

        
# ==========================================
# RESOLVE CONFLICT
# ==========================================

class ConflictResolveRequest(BaseModel):
    resolved_by: str = ""
    resolution_note: str


@router.post("/{conflict_id}/resolve", dependencies=[Depends(require_permission("conflicts.resolve"))])
def resolve_conflict(
    conflict_id: int,
    request: ConflictResolveRequest,
    user: CurrentUser = Depends(get_current_user)
):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        # ======================================
        # CHECK CONFLICT EXISTS
        # ======================================

        cursor.execute("""
            SELECT conflict_id, conflict_status
            FROM block_conflicts
            WHERE conflict_id = %s
        """, (conflict_id,))

        conflict = cursor.fetchone()

        if not conflict:

            raise HTTPException(
                status_code=404,
                detail="Conflict not found"
            )


        # ======================================
        # CHECK IF ALREADY RESOLVED
        # ======================================

        if conflict[1] == "RESOLVED":

            raise HTTPException(
                status_code=400,
                detail="Conflict is already resolved"
            )


        # ======================================
        # UPDATE CONFLICT
        # ======================================

        resolver = user.name if user and user.name else (request.resolved_by or "Control Office")

        cursor.execute("""
            UPDATE block_conflicts
            SET
                conflict_status = 'RESOLVED',
                resolution_note = %s,
                resolved_by = %s,
                resolved_at = %s
            WHERE conflict_id = %s
        """, (
            request.resolution_note,
            resolver,
            datetime.now(),
            conflict_id
        ))


        conn.commit()

        record_audit(
            user=user,
            method="POST",
            path=f"/conflicts/{conflict_id}/resolve",
            action="conflicts.resolve",
            target_type="conflict",
            target_id=str(conflict_id),
            outcome="SUCCESS",
            detail={"note": request.resolution_note}
        )

        # ======================================
        # SUCCESS RESPONSE
        # ======================================

        return {
            "status": "success",
            "message": "Conflict resolved successfully",
            "conflict_id": conflict_id,
            "conflict_status": "RESOLVED",
            "resolved_by": resolver,
            "resolution_note": request.resolution_note
        }


    except HTTPException:

        conn.rollback()
        raise


    except Exception as e:

        conn.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


    finally:

        cursor.close()
        conn.close()