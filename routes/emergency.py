from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
import psycopg
import os
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

from auth.security import (
    require_permission,
    get_current_user,
    CurrentUser,
)

load_dotenv()

router = APIRouter(
    prefix="/emergency",
    tags=["Emergency"]
)


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )


# ============================================================
# REQUEST MODELS
# ============================================================

class EmergencyCreate(BaseModel):
    """
    Create a new emergency incident.

    The model accepts both the new field names and some of the
    older frontend field names for compatibility.
    """

    incident_id: Optional[str] = None

    # New name
    emergency_type: Optional[str] = None

    # Old frontend name
    incident_type: Optional[str] = None

    # New names
    section: Optional[str] = None
    line: Optional[str] = None

    # Older frontend names
    section_id: Optional[str] = None
    corridor_id: Optional[str] = None

    severity: str = "HIGH"

    started_at: Optional[str] = None

    # Optional fields accepted from older frontend
    required_start: Optional[str] = None
    required_duration: Optional[int] = None
    reason: Optional[str] = None
    created_by: Optional[str] = None

    control_notified: bool = False

    traffic_protection_status: str = "PENDING"


class EmergencyResolve(BaseModel):
    confirmed: bool = True


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def generate_incident_id(cursor):
    """
    Generate a new SOS emergency incident ID.

    Example:
        SOS-EMG-007
        SOS-EMG-008
    """

    cursor.execute(
        """
        SELECT incident_id
        FROM emergency_incidents
        WHERE incident_id LIKE 'SOS-EMG-%'
        ORDER BY incident_id DESC
        LIMIT 1
        """
    )

    row = cursor.fetchone()

    if not row:
        return "SOS-EMG-001"

    last_id = row[0]

    try:
        number = int(last_id.split("-")[-1])
        return f"SOS-EMG-{number + 1:03d}"
    except (ValueError, IndexError):
        return f"SOS-EMG-{int(datetime.now().timestamp())}"


def serialize_incident(row):
    """
    Convert emergency_incidents database row to JSON.
    """

    return {
        "incident_id": row[0],
        "emergency_type": row[1],
        "incident_type": row[1],
        "section": row[2],
        "line": row[3],
        "severity": row[4],
        "started_at": str(row[5]) if row[5] else None,
        "status": row[6],
        "control_notified": row[7],
        "traffic_protection_status": row[8],
        "resolved_at": str(row[9]) if row[9] else None,
        "created_at": str(row[10]) if row[10] else None
    }


# ============================================================
# CREATE EMERGENCY INCIDENT
# ============================================================

@router.post(
    "/",
    dependencies=[Depends(require_permission("emergency.view"))]
)
def create_emergency(
    payload: EmergencyCreate,
    user: CurrentUser = Depends(get_current_user)
):
    """
    Create a new emergency incident.

    This endpoint is intentionally compatible with both:
        emergency_type / section / line

    and older frontend fields:
        incident_type / section_id / corridor_id
    """

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # ----------------------------------------------------
        # Resolve emergency type
        # ----------------------------------------------------

        emergency_type = (
            payload.emergency_type
            or payload.incident_type
        )

        if not emergency_type:
            raise HTTPException(
                status_code=400,
                detail="Emergency type is required"
            )

        # ----------------------------------------------------
        # Resolve section
        # ----------------------------------------------------

        section = (
            payload.section
            or payload.section_id
        )

        if not section:
            raise HTTPException(
                status_code=400,
                detail="Section is required"
            )

        # ----------------------------------------------------
        # Resolve line
        # ----------------------------------------------------

        line = (
            payload.line
            or payload.corridor_id
            or "Main Line"
        )

        # ----------------------------------------------------
        # Generate incident ID
        # ----------------------------------------------------

        incident_id = payload.incident_id

        if not incident_id:
            incident_id = generate_incident_id(cursor)

        # ----------------------------------------------------
        # Prevent duplicate incident ID
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT incident_id
            FROM emergency_incidents
            WHERE incident_id = %s
            """,
            (incident_id,)
        )

        if cursor.fetchone():
            raise HTTPException(
                status_code=409,
                detail=f"Emergency incident '{incident_id}' already exists"
            )

        # ----------------------------------------------------
        # Parse started_at
        # ----------------------------------------------------

        started_at = None

        if payload.started_at:
            try:
                started_at = datetime.fromisoformat(
                    payload.started_at.replace("Z", "+00:00")
                )

                # Database column is timestamp without time zone.
                if started_at.tzinfo is not None:
                    started_at = started_at.replace(tzinfo=None)

            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid started_at format. Use ISO datetime."
                )

        else:
            started_at = datetime.now()

        # ----------------------------------------------------
        # Insert emergency
        # ----------------------------------------------------

        cursor.execute(
            """
            INSERT INTO emergency_incidents
            (
                incident_id,
                emergency_type,
                section,
                line,
                severity,
                started_at,
                status,
                control_notified,
                traffic_protection_status,
                resolved_at,
                created_at
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                'ACTIVE',
                %s,
                %s,
                NULL,
                CURRENT_TIMESTAMP
            )
            RETURNING
                incident_id,
                emergency_type,
                section,
                line,
                severity,
                started_at,
                status,
                control_notified,
                traffic_protection_status,
                resolved_at,
                created_at
            """,
            (
                incident_id,
                emergency_type,
                section,
                line,
                payload.severity,
                started_at,
                payload.control_notified,
                payload.traffic_protection_status
            )
        )

        created = cursor.fetchone()

        conn.commit()

        # ----------------------------------------------------
        # Return created emergency
        # ----------------------------------------------------

        result = serialize_incident(created)

        result["status"] = "success"
        result["message"] = "Emergency incident created successfully"

        return result

    except HTTPException:
        conn.rollback()
        raise

    except Exception as e:
        conn.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Emergency creation failed: {str(e)}"
        )

    finally:
        cursor.close()
        conn.close()


# ============================================================
# CREATE EMERGENCY - COMPATIBILITY ROUTE
# ============================================================

@router.post(
    "/create",
    dependencies=[Depends(require_permission("emergency.view"))]
)
def create_emergency_compat(
    payload: EmergencyCreate,
    user: CurrentUser = Depends(get_current_user)
):
    """
    Compatibility endpoint.

    Supports frontend calls to:
        POST /emergency/create
    """

    return create_emergency(payload, user)


# ============================================================
# GET ALL EMERGENCY INCIDENTS
# ============================================================

@router.get(
    "/",
    dependencies=[Depends(require_permission("emergency.view"))]
)
def get_emergency_incidents(
    user: CurrentUser = Depends(get_current_user)
):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT
                incident_id,
                emergency_type,
                section,
                line,
                severity,
                started_at,
                status,
                control_notified,
                traffic_protection_status,
                resolved_at,
                created_at
            FROM emergency_incidents
            ORDER BY created_at DESC
            """
        )

        rows = cursor.fetchall()

        return [
            serialize_incident(row)
            for row in rows
        ]

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch emergency incidents: {str(e)}"
        )

    finally:
        cursor.close()
        conn.close()


# ============================================================
# GET SINGLE EMERGENCY INCIDENT
# ============================================================

@router.get(
    "/{incident_id}",
    dependencies=[Depends(require_permission("emergency.view"))]
)
def get_emergency_incident(
    incident_id: str,
    user: CurrentUser = Depends(get_current_user)
):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT
                incident_id,
                emergency_type,
                section,
                line,
                severity,
                started_at,
                status,
                control_notified,
                traffic_protection_status,
                resolved_at,
                created_at
            FROM emergency_incidents
            WHERE incident_id = %s
            """,
            (incident_id,)
        )

        row = cursor.fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail="Emergency incident not found"
            )

        return serialize_incident(row)

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch emergency incident: {str(e)}"
        )

    finally:
        cursor.close()
        conn.close()


# ============================================================
# CHECK EMERGENCY CONFLICTS
# ============================================================

@router.post(
    "/{incident_id}/check-conflicts",
    dependencies=[Depends(require_permission("emergency.view"))]
)
def check_emergency_conflicts(
    incident_id: str,
    user: CurrentUser = Depends(get_current_user)
):
    conn = get_connection()
    cursor = conn.cursor()

    try:

        # ----------------------------------------------------
        # Get emergency
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT
                incident_id,
                section,
                started_at,
                status
            FROM emergency_incidents
            WHERE incident_id = %s
            """,
            (incident_id,)
        )

        emergency = cursor.fetchone()

        if not emergency:
            raise HTTPException(
                status_code=404,
                detail="Emergency incident not found"
            )

        section = emergency[1]
        started_at = emergency[2]
        status = emergency[3]

        conflicts = []

        # ----------------------------------------------------
        # Find corridor for emergency section
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT corridor_id
            FROM corridor_sections
            WHERE section_id = %s
               OR section_name = %s
            LIMIT 1
            """,
            (section, section)
        )

        corridor = cursor.fetchone()

        # ----------------------------------------------------
        # Find overlapping block requests
        # ----------------------------------------------------

        if corridor and started_at:

            corridor_id = corridor[0]

            cursor.execute(
                """
                SELECT
                    request_id,
                    requested_date,
                    requested_start,
                    requested_end
                FROM block_requests
                WHERE corridor_id = %s
                  AND requested_date = %s
                  AND request_status IN ('PENDING', 'OPTIMIZED')
                  AND requested_start <= %s::time
                  AND requested_end > %s::time
                """,
                (
                    corridor_id,
                    started_at.date(),
                    started_at.time(),
                    started_at.time()
                )
            )

            conflicts = cursor.fetchall()

        # ----------------------------------------------------
        # IMPORTANT:
        # Do NOT insert into emergency_conflicts here.
        #
        # That table does not exist in the current database.
        # We simply return the detected conflicts.
        # ----------------------------------------------------

        conn.commit()

        return {
            "status": "success",
            "incident_id": incident_id,
            "emergency_status": status,
            "conflicts_found": len(conflicts),
            "conflicting_requests": [
                {
                    "request_id": row[0],
                    "requested_date": str(row[1]),
                    "requested_start": str(row[2]),
                    "requested_end": str(row[3])
                }
                for row in conflicts
            ]
        }

    except HTTPException:
        conn.rollback()
        raise

    except Exception as e:
        conn.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Conflict check failed: {str(e)}"
        )

    finally:
        cursor.close()
        conn.close()


# ============================================================
# RESOLVE / CLEAR EMERGENCY BLOCK
# ============================================================

@router.post(
    "/{incident_id}/resolve",
    dependencies=[Depends(require_permission("emergency.view"))]
)
@router.patch(
    "/{incident_id}/resolve",
    dependencies=[Depends(require_permission("emergency.view"))]
)
def resolve_emergency(
    incident_id: str,
    payload: EmergencyResolve = EmergencyResolve(),
    user: CurrentUser = Depends(get_current_user)
):
    """
    Resolve an ACTIVE emergency.

    Supports both:
        POST  /emergency/{incident_id}/resolve
        PATCH /emergency/{incident_id}/resolve

    The PATCH route is kept for compatibility with the older frontend.
    """

    conn = get_connection()
    cursor = conn.cursor()

    try:

        # ----------------------------------------------------
        # Clearance confirmation
        # ----------------------------------------------------

        if not payload.confirmed:
            raise HTTPException(
                status_code=400,
                detail="Emergency clearance was not confirmed"
            )

        # ----------------------------------------------------
        # Lock and fetch incident
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT
                incident_id,
                status,
                traffic_protection_status,
                resolved_at,
                emergency_type,
                section
            FROM emergency_incidents
            WHERE incident_id = %s
            FOR UPDATE
            """,
            (incident_id,)
        )

        incident = cursor.fetchone()

        if not incident:
            raise HTTPException(
                status_code=404,
                detail="Emergency incident not found"
            )

        current_status = incident[1]
        traffic_protection_status = incident[2]
        existing_resolved_at = incident[3]
        emergency_type = incident[4]
        section = incident[5]

        # ----------------------------------------------------
        # Already resolved
        # ----------------------------------------------------

        if current_status == "RESOLVED":
            conn.commit()

            return {
                "status": "success",
                "message": "Emergency incident is already resolved",
                "incident_id": incident_id,
                "incident_status": "RESOLVED",
                "resolved_at": (
                    str(existing_resolved_at)
                    if existing_resolved_at
                    else None
                ),
                "traffic_protection_status": traffic_protection_status
            }

        # ----------------------------------------------------
        # Only ACTIVE incidents can be resolved
        # ----------------------------------------------------

        if current_status != "ACTIVE":
            raise HTTPException(
                status_code=409,
                detail=(
                    "Emergency incident cannot be resolved "
                    f"from status: {current_status}"
                )
            )

        # ----------------------------------------------------
        # Resolve emergency
        # ----------------------------------------------------

        cursor.execute(
            """
            UPDATE emergency_incidents
            SET
                status = 'RESOLVED',
                resolved_at = CURRENT_TIMESTAMP
            WHERE incident_id = %s
              AND status = 'ACTIVE'
            RETURNING
                incident_id,
                status,
                resolved_at
            """,
            (incident_id,)
        )

        updated = cursor.fetchone()

        if not updated:
            raise HTTPException(
                status_code=409,
                detail="Emergency incident could not be resolved"
            )

        # ----------------------------------------------------
        # Commit
        # ----------------------------------------------------

        conn.commit()

        return {
            "status": "success",
            "message": "Emergency block resolved successfully",
            "incident_id": updated[0],
            "incident_status": updated[1],
            "resolved_at": str(updated[2]),
            "traffic_protection_status": traffic_protection_status,
            "emergency_type": emergency_type,
            "section": section
        }

    except HTTPException:
        conn.rollback()
        raise

    except Exception as e:
        conn.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Emergency resolution failed: {str(e)}"
        )

    finally:
        cursor.close()
        conn.close()


# ============================================================
# REOPEN EMERGENCY
# ============================================================

@router.post(
    "/{incident_id}/reopen",
    dependencies=[Depends(require_permission("emergency.view"))]
)
def reopen_emergency(
    incident_id: str,
    user: CurrentUser = Depends(get_current_user)
):
    conn = get_connection()
    cursor = conn.cursor()

    try:

        # ----------------------------------------------------
        # Check incident
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT
                incident_id,
                status
            FROM emergency_incidents
            WHERE incident_id = %s
            FOR UPDATE
            """,
            (incident_id,)
        )

        incident = cursor.fetchone()

        if not incident:
            raise HTTPException(
                status_code=404,
                detail="Emergency incident not found"
            )

        # ----------------------------------------------------
        # Reopen
        # ----------------------------------------------------

        cursor.execute(
            """
            UPDATE emergency_incidents
            SET
                status = 'ACTIVE',
                resolved_at = NULL
            WHERE incident_id = %s
            RETURNING
                incident_id,
                status,
                resolved_at
            """,
            (incident_id,)
        )

        updated = cursor.fetchone()

        if not updated:
            raise HTTPException(
                status_code=500,
                detail="Emergency incident could not be reopened"
            )

        conn.commit()

        return {
            "status": "success",
            "message": "Emergency incident reopened",
            "incident_id": updated[0],
            "incident_status": updated[1],
            "resolved_at": None
        }

    except HTTPException:
        conn.rollback()
        raise

    except Exception as e:
        conn.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Emergency reopen failed: {str(e)}"
        )

    finally:
        cursor.close()
        conn.close()