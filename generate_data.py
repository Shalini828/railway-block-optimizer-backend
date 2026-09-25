import psycopg
import os
from dotenv import load_dotenv
from faker import Faker

load_dotenv()
fake = Faker()

# Connect to PostgreSQL
connection = psycopg.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)


cursor = connection.cursor()

zones = [
    "Northern Railway",
    "Western Railway",
    "Eastern Railway",
    "Southern Railway",
    "Central Railway"
]

for i, zone in enumerate(zones, start=1):
    
    division_name = f"Division {i}"
    headquarters = fake.city()

    cursor.execute(
        """
        INSERT INTO zones_divisions
        (division_id, zone_name, division_name, headquarters)
        VALUES (%s, %s, %s, %s)
        """,
        (i, zone, division_name, headquarters)
    )

connection.commit()

cursor.close()
connection.close()

print("✅ 5 divisions generated and inserted successfully!")