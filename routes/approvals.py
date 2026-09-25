from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import psycopg
import os

from dotenv import load_dotenv

load_dotenv()


router = APIRouter(
    prefix="/approvals",
    tags=["Approvals"]
)


def get_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )

class ApprovalRequest(BaseModel):
    block_id: str
    action: str
    comments: str | None = None
    performed_by: str

@router.post("/")
def process_approval(request: ApprovalRequest):

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # 1. Check that the block exists
        cursor.execute(
            """
            SELECT block_id
            FROM optimized_blocks
            WHERE block_id = %s
            """,
            (request.block_id,)
        )

        block = cursor.fetchone()

        if not block:
            raise HTTPException(
                status_code=404,
                detail="Optimized block not found"
            )

        # 2. Validate action
        action = request.action.strip().upper()

        if action not in ["APPROVE", "REJECT"]:
            raise HTTPException(
                status_code=400,
                detail="Action must be APPROVE or REJECT"
            )

        # 3. Update block status
        new_status = "APPROVED" if action == "APPROVE" else "REJECTED"

        cursor.execute(
            """
            UPDATE optimized_blocks
            SET block_status = %s,
                approved_by = %s,
                approved_at = CURRENT_TIMESTAMP
            WHERE block_id = %s
            """,
            (
                new_status,
                request.performed_by,
                request.block_id
            )
        )

        # 4. Save approval history
        cursor.execute(
            """
            INSERT INTO block_approval_history
            (
                block_id,
                action,
                performed_by,
                comments
            )
            VALUES (%s, %s, %s, %s)
            """,
            (
                request.block_id,
                action,
                request.performed_by,
                request.comments
            )
        )

                # 5. Create notification for Control Officer
        cursor.execute(
            """
            INSERT INTO notifications
            (
                user_id,
                notification_type,
                title,
                message,
                entity_type,
                entity_id
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                "USR-006",
                "BLOCK_APPROVAL",
                f"Block {new_status}",
                f"Block {request.block_id} has been {new_status.lower()} by {request.performed_by}.",
                "OPTIMIZED_BLOCK",
                request.block_id
            )
        )


        conn.commit()

        return {
            "status": "success",
            "message": f"Block {new_status.lower()} successfully",
            "block_id": request.block_id,
            "block_status": new_status
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