import psycopg
import os
from dotenv import load_dotenv

load_dotenv()

connection = psycopg.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)

cursor = connection.cursor()

trains = [
    (
        "TR-106",
        "12952",
        "Mumbai Rajdhani",
        "Express",
        "C02",
        "2026-08-30",
        "20:30",
        "20:35",
        "DOWN",
        5
    ),
    (
        "TR-107",
        "12001",
        "Bhopal Shatabdi",
        "Express",
        "C03",
        "2026-08-30",
        "21:15",
        "21:20",
        "UP",
        4
    ),
    (
        "TR-108",
        "12432",
        "Rajdhani Express",
        "Express",
        "C04",
        "2026-08-30",
        "22:00",
        "22:05",
        "DOWN",
        5
    ),
    (
        "TR-109",
        "12012",
        "Kalka Shatabdi",
        "Express",
        "C05",
        "2026-08-30",
        "23:00",
        "23:05",
        "UP",
        3
    ),
    (
        "TR-110",
        "12138",
        "Punjab Mail",
        "Passenger",
        "C06",
        "2026-08-30",
        "23:30",
        "23:35",
        "DOWN",
        2
    )
]

for train in trains:
    cursor.execute(
        """
        INSERT INTO trains
        (
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
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (train_id) DO NOTHING
        """,
        train
    )

connection.commit()

cursor.close()
connection.close()

print("✅ Train data generated successfully!")