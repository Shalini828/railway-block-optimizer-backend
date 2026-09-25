from fastapi import APIRouter, HTTPException, Depends
import psycopg
import os
from dotenv import load_dotenv
from auth.security import get_current_user

load_dotenv()

router = APIRouter(
    prefix="/users",
    tags=["Users"],
    dependencies=[Depends(get_current_user)]
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
# GET ALL USERS
# ==========================================

@router.get("/")
def get_users():

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT
                u.user_id,
                u.name,
                u.email,
                u.role,
                u.department_id,
                d.name AS department_name,
                u.division_id,
                u.active
            FROM users u
            LEFT JOIN departments d
                ON u.department_id = d.department_id
            ORDER BY u.user_id
        """)

        rows = cursor.fetchall()

        return [
            {
                "user_id": row[0],
                "name": row[1],
                "email": row[2],
                "role": row[3],
                "department_id": row[4],
                "department_name": row[5],
                "division_id": row[6],
                "active": row[7]
            }
            for row in rows
        ]

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:
        cursor.close()
        conn.close()


# ==========================================
# GET SINGLE USER
# ==========================================

@router.get("/{user_id}")
def get_user(user_id: str):

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT
                u.user_id,
                u.name,
                u.email,
                u.role,
                u.department_id,
                d.name AS department_name,
                u.division_id,
                u.active
            FROM users u
            LEFT JOIN departments d
                ON u.department_id = d.department_id
            WHERE u.user_id = %s
        """, (user_id,))

        row = cursor.fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )

        return {
            "user_id": row[0],
            "name": row[1],
            "email": row[2],
            "role": row[3],
            "department_id": row[4],
            "department_name": row[5],
            "division_id": row[6],
            "active": row[7]
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:
        cursor.close()
        conn.close()