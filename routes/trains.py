from fastapi import APIRouter, Depends
import psycopg
import os
from dotenv import load_dotenv

from auth.security import get_current_user, require_permission, CurrentUser
from auth.scoping import get_relevant_corridor_ids

load_dotenv()

router = APIRouter(
    prefix="/trains",
    tags=["Trains"]
)


def get_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )


@router.get("/", dependencies=[Depends(require_permission("trains.view"))])
def get_trains(user: CurrentUser = Depends(get_current_user)):

    conn = get_connection()
    cursor = conn.cursor()

    if user.scope != "network":
        relevant_corridors = get_relevant_corridor_ids(cursor, user.dept)
        if not relevant_corridors:
            cursor.close()
            conn.close()
            return {
                "status": "success",
                "train_count": 0,
                "trains": [],
                "scope": user.scope,
                "department": user.dept,
            }

        cursor.execute("""
            SELECT
                train_id,
                train_number,
                train_name,
                train_type,
                corridor_id,
                travel_date,
                arrival_time,
                departure_time,
                direction,
                operational_priority
            FROM trains
            WHERE corridor_id = ANY(%s)
            ORDER BY travel_date, departure_time
        """, (relevant_corridors,))
    else:
        cursor.execute("""
            SELECT
                train_id,
                train_number,
                train_name,
                train_type,
                corridor_id,
                travel_date,
                arrival_time,
                departure_time,
                direction,
                operational_priority
            FROM trains
            ORDER BY travel_date, departure_time
        """)

    rows = cursor.fetchall()

    columns = [desc[0] for desc in cursor.description]

    cursor.close()
    conn.close()

    trains = []

    for row in rows:
        train = {}

        for column, value in zip(columns, row):
            train[column] = str(value) if value is not None else None

        trains.append(train)

    return {
        "status": "success",
        "train_count": len(trains),
        "trains": trains
    }