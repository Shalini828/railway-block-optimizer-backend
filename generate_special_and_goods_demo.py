"""
Idempotent generator for Special Train Services, Goods trains, and Freight Forecast demo data.
Seeds relative to real active corridor windows in optimized_blocks.
"""

import psycopg
from datetime import datetime, timedelta, time
import logging
from db_config import DB_CONFIG
from logic.freight_pressure import get_daily_goods_forecast

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("demo_seeder")


def seed_demo_data():
    conn = psycopg.connect(**DB_CONFIG)
    cursor = conn.cursor()

    try:
        # 1. Inspect existing optimized blocks to anchor relative dates & times
        cursor.execute("""
            SELECT block_id, corridor_id, block_date, start_time, end_time
            FROM optimized_blocks
            ORDER BY block_date DESC, start_time ASC
            LIMIT 5
        """)
        existing_blocks = cursor.fetchall()

        if existing_blocks:
            anchor_block = existing_blocks[0]
            ref_block_id = anchor_block[0]
            ref_corridor = anchor_block[1]
            ref_date = anchor_block[2]
            ref_start = anchor_block[3]
            ref_end = anchor_block[4]
            logger.info(f"Anchoring demo traffic to real block {ref_block_id} on {ref_corridor} ({ref_date} {ref_start}-{ref_end})")
        else:
            # Fallback anchor if DB is clean
            cursor.execute("SELECT corridor_id FROM corridors LIMIT 3")
            corrs = [r[0] for r in cursor.fetchall()]
            ref_corridor = corrs[0] if corrs else "CORR-001"
            ref_date = datetime.now().date() + timedelta(days=1)
            ref_start = time(10, 0)
            ref_end = time(13, 0)
            logger.info(f"No existing blocks found. Using default anchor {ref_corridor} on {ref_date}")

        # Get list of valid corridor IDs
        cursor.execute("SELECT corridor_id FROM corridors")
        all_corridors = [r[0] for r in cursor.fetchall()]
        if not all_corridors:
            all_corridors = [ref_corridor]

        c1 = ref_corridor
        c2 = all_corridors[1 % len(all_corridors)]
        c3 = all_corridors[2 % len(all_corridors)]

        # Calculate an overlapping arrival/departure for the first special train
        if isinstance(ref_start, time) and isinstance(ref_end, time):
            s_min = ref_start.hour * 60 + ref_start.minute
            e_min = ref_end.hour * 60 + ref_end.minute
            if e_min <= s_min:
                e_min += 1440
            mid_min = (s_min + e_min) // 2
            overlap_arr = f"{(mid_min - 20) // 60 % 24:02d}:{(mid_min - 20) % 60:02d}:00"
            overlap_dep = f"{(mid_min + 20) // 60 % 24:02d}:{(mid_min + 20) % 60:02d}:00"
        else:
            overlap_arr = "10:30:00"
            overlap_dep = "11:15:00"

        # ----------------------------------------------------
        # 2. Seed ~6 Special Train Services (Idempotent)
        # ----------------------------------------------------
        special_trains = [
            (
                "SPL-0001",
                "04011",
                "Kumbh Mela Mahakumbh Special",
                c1,
                ref_date,
                overlap_arr,
                overlap_dep,
                "UP",
                5,
                "FESTIVAL",
                1450,
                f"Deliberate operational overlap with block window {ref_block_id if existing_blocks else 'BL-001'}",
                True,
                "New Delhi",
                "Prayagraj Jn",
                "DRM Planning"
            ),
            (
                "SPL-0002",
                "04022",
                "Armed Forces Strategic Military Special",
                c1,
                ref_date,
                "04:15:00",
                "05:00:00",
                "DOWN",
                5,
                "MILITARY",
                450,
                "Priority defense logistical movement",
                True,
                "Ambala Cantt",
                "Kanpur Central",
                "Army Liaison Cell"
            ),
            (
                "SPL-0003",
                "04033",
                "Diwali / Chhath Puja Superfast Special",
                c2,
                ref_date,
                "14:30:00",
                "15:15:00",
                "UP",
                4,
                "FESTIVAL",
                1200,
                "Peak festival holiday clearance",
                True,
                "Anand Vihar Terminus",
                "Patna Jn",
                "Commercial Dept"
            ),
            (
                "SPL-0004",
                "04044",
                "NDRF Disaster Relief & Medical Special",
                c2,
                ref_date,
                "18:00:00",
                "18:45:00",
                "DOWN",
                4,
                "RELIEF",
                200,
                "Emergency civil defense and medical materials",
                True,
                "Ghaziabad",
                "Lucknow",
                "Safety Directorate"
            ),
            (
                "SPL-0005",
                "04055",
                "Summer Vacation Tourist Special",
                c3,
                ref_date,
                "08:45:00",
                "09:30:00",
                "UP",
                3,
                "HOLIDAY",
                950,
                "Seasonal holiday capacity reinforcement",
                True,
                "Agra Cantt",
                "Varanasi Jn",
                "Commercial Dept"
            ),
            (
                "SPL-0006",
                "04066",
                "Pravasi Bharatiya Divas Delegate Express",
                c3,
                ref_date,
                "21:00:00",
                "21:45:00",
                "DOWN",
                3,
                "EVENT",
                600,
                "State international summit transport",
                True,
                "New Delhi",
                "Indore Jn",
                "Ministry of External Affairs"
            ),
        ]

        logger.info("Seeding special_train_services rows...")
        for st in special_trains:
            cursor.execute("""
                INSERT INTO special_train_services (
                    special_train_id,
                    train_number,
                    train_name,
                    corridor_id,
                    service_date,
                    arrival_time,
                    departure_time,
                    direction,
                    operational_priority,
                    special_type,
                    expected_passengers,
                    reason,
                    active,
                    origin_station,
                    destination_station,
                    created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (special_train_id) DO NOTHING
            """, st)

        # ----------------------------------------------------
        # 3. Seed Scheduled GOODS Trains in `trains` table
        # ----------------------------------------------------
        goods_trains = [
            (
                "GTR-001",
                "G-9021",
                "CONCOR Container Express",
                "GOODS",
                c1,
                ref_date,
                "02:00:00",
                "03:15:00",
                "DOWN",
                3
            ),
            (
                "GTR-002",
                "G-9022",
                "NTPC Thermal Coal Rake",
                "GOODS",
                c1,
                ref_date,
                "16:20:00",
                "17:35:00",
                "UP",
                3
            ),
            (
                "GTR-003",
                "G-9023",
                "IOCL Petroleum Tanker Freight",
                "GOODS",
                c2,
                ref_date,
                "06:30:00",
                "07:45:00",
                "DOWN",
                3
            ),
            (
                "GTR-004",
                "G-9024",
                "SAIL Steel Coil Freight",
                "GOODS",
                c2,
                ref_date,
                "13:00:00",
                "14:10:00",
                "UP",
                3
            ),
            (
                "GTR-005",
                "G-9025",
                "FCI Foodgrain Bulk Rake",
                "GOODS",
                c3,
                ref_date,
                "19:15:00",
                "20:30:00",
                "DOWN",
                2
            ),
        ]

        logger.info("Seeding GOODS rows in trains table...")
        for gt in goods_trains:
            cursor.execute("""
                INSERT INTO trains (
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
            """, gt)

        # ----------------------------------------------------
        # 4. Seed Goods Train Forecast via Shared Helper
        # ----------------------------------------------------
        logger.info("Seeding goods_train_forecast via shared helper...")
        for corridor in [c1, c2, c3]:
            try:
                forecast_record = get_daily_goods_forecast(
                    cursor=cursor,
                    corridor_id=corridor,
                    target_date=ref_date,
                    commodity="COAL",
                    persist=True
                )
                logger.info(f"Forecast for {corridor} on {ref_date}: {forecast_record.get('expected_goods_trains')} trains ({forecast_record.get('traffic_level')})")
            except Exception as fe:
                logger.warning(f"Could not generate forecast for {corridor}: {fe}")

        conn.commit()
        logger.info("✅ Demo special trains, goods trains, and freight forecasts seeded successfully!")

    except Exception as e:
        conn.rollback()
        logger.error(f"Seeding failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    seed_demo_data()
