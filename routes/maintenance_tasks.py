from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import psycopg
import os
from dotenv import load_dotenv

from auth.security import get_current_user, require_permission, CurrentUser, RBACForbiddenException

load_dotenv()

router = APIRouter(
    prefix="/maintenance-tasks",
    tags=["Maintenance Tasks"]
)


def get_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )


# ==========================================
# GET ALL MAINTENANCE TASKS
# ==========================================

@router.get("/", dependencies=[Depends(require_permission("tasks.view"))])
def get_maintenance_tasks(user: CurrentUser = Depends(get_current_user)):

    conn = get_connection()
    cursor = conn.cursor()

    try:
        if user.scope != "network":
            cursor.execute("""
                SELECT
                    task_id,
                    asset_id,
                    department,
                    task_type,
                    description,
                    created_date,
                    due_date,
                    estimated_duration_min,
                    overdue_days,
                    safety_risk,
                    task_status,
                    priority_score,
                    priority_category
                FROM maintenance_tasks
                WHERE UPPER(department) = %s
                ORDER BY priority_score DESC NULLS LAST, task_id
            """, (user.dept.upper(),))
        else:
            cursor.execute("""
                SELECT
                    task_id,
                    asset_id,
                    department,
                    task_type,
                    description,
                    created_date,
                    due_date,
                    estimated_duration_min,
                    overdue_days,
                    safety_risk,
                    task_status,
                    priority_score,
                    priority_category
                FROM maintenance_tasks
                ORDER BY priority_score DESC NULLS LAST, task_id
            """)

        rows = cursor.fetchall()

        tasks = []

        for row in rows:
            tasks.append({
                "task_id": row[0],
                "asset_id": row[1],
                "department": row[2],
                "task_type": row[3],
                "description": row[4],
                "created_date": str(row[5]) if row[5] else None,
                "due_date": str(row[6]) if row[6] else None,
                "estimated_duration_min": row[7],
                "overdue_days": row[8],
                "safety_risk": row[9],
                "task_status": row[10],
                "priority_score": float(row[11]) if row[11] is not None else None,
                "priority_category": row[12]
            })

        return {
            "status": "success",
            "task_count": len(tasks),
            "tasks": tasks
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:
        cursor.close()
        conn.close()


# ==========================================
# UPDATE TASK STATUS
# ==========================================

class TaskStatusUpdate(BaseModel):
    task_status: str


@router.put("/{task_id}/status", dependencies=[Depends(require_permission("tasks.update"))])
def update_task_status(
    task_id: str,
    request: TaskStatusUpdate,
    user: CurrentUser = Depends(get_current_user)
):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            SELECT task_id, department
            FROM maintenance_tasks
            WHERE task_id = %s
        """, (task_id,))

        task = cursor.fetchone()

        if not task:
            raise HTTPException(
                status_code=404,
                detail="Maintenance task not found"
            )

        if user.scope != "network":
            task_dept = (task[1] or "").strip().upper()
            user_dept = (user.dept or "").strip().upper()
            if task_dept != user_dept:
                raise RBACForbiddenException(
                    required=f"department.{user.dept}",
                    role=user.role_id,
                    detail=f"Cannot update task belonging to another department ({task_dept})",
                )

        cursor.execute("""
            UPDATE maintenance_tasks
            SET task_status = %s
            WHERE task_id = %s
        """, (
            request.task_status,
            task_id
        ))

        conn.commit()

        return {
            "status": "success",
            "message": "Maintenance task status updated successfully",
            "task_id": task_id,
            "task_status": request.task_status
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