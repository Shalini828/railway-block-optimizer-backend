import psycopg
import os
from dotenv import load_dotenv

from db_config import DB_CONFIG
from logic.traffic_intelligence import (
    windows_overlap,
    normalize_train_type,
    conflict_severity,
)

load_dotenv()


def get_connection():
    return psycopg.connect(**DB_CONFIG)


def detect_conflicts(connection=None):
    """
    Detect maintenance vs maintenance and maintenance vs train conflicts.
    Safe to call at runtime; does not connect at import time.
    """
    close_at_end = False
    if connection is None:
        connection = get_connection()
        close_at_end = True

    cursor = connection.cursor()

    try:
        # ==========================================
        # GET BLOCK REQUESTS
        # ==========================================
        cursor.execute("""
            SELECT
                request_id,
                task_id,
                team_id,
                corridor_id,
                requested_date,
                requested_start,
                requested_end
            FROM block_requests
            WHERE request_status = 'PENDING'
            ORDER BY corridor_id, requested_date, requested_start
        """)
        blocks = cursor.fetchall()

        # ==========================================
        # GET TRAINS
        # ==========================================
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
        """)
        trains = cursor.fetchall()

        conflicts = []

        # ==========================================
        # 1. MAINTENANCE vs MAINTENANCE
        # ==========================================
        for i in range(len(blocks)):
            block_a = blocks[i]
            (
                request_a,
                task_a,
                team_a,
                corridor_a,
                date_a,
                start_a,
                end_a,
            ) = block_a

            for j in range(i + 1, len(blocks)):
                block_b = blocks[j]
                (
                    request_b,
                    task_b,
                    team_b,
                    corridor_b,
                    date_b,
                    start_b,
                    end_b,
                ) = block_b

                if corridor_a != corridor_b:
                    continue
                if date_a != date_b:
                    continue

                overlap, _ = windows_overlap(start_a, end_a, start_b, end_b)
                if overlap:
                    conflicts.append({
                        "type": "MAINTENANCE_MAINTENANCE",
                        "severity": "HIGH",
                        "corridor": corridor_a,
                        "date": date_a,
                        "request_a": request_a,
                        "task_a": task_a,
                        "request_b": request_b,
                        "task_b": task_b,
                        "time_a": f"{start_a} - {end_a}",
                        "time_b": f"{start_b} - {end_b}",
                    })

        # ==========================================
        # 2. MAINTENANCE vs TRAIN
        # ==========================================
        for block in blocks:
            (
                request_id,
                task_id,
                team_id,
                block_corridor,
                block_date,
                block_start,
                block_end,
            ) = block

            for train in trains:
                (
                    train_id,
                    train_number,
                    train_name,
                    raw_train_type,
                    train_corridor,
                    train_date,
                    train_arrival,
                    train_departure,
                    train_dir,
                    train_prio,
                ) = train

                if block_corridor != train_corridor:
                    continue
                if block_date != train_date:
                    continue

                overlap, _ = windows_overlap(
                    block_start, block_end, train_arrival, train_departure
                )
                if overlap:
                    canonical_type, _, _ = normalize_train_type(raw_train_type)
                    train_item = {
                        "train_type": canonical_type,
                        "raw_train_type": raw_train_type,
                        "operational_priority": train_prio or 3,
                    }
                    severity = conflict_severity(train_item)

                    conflicts.append({
                        "type": "MAINTENANCE_TRAIN",
                        "severity": severity,
                        "corridor": block_corridor,
                        "date": block_date,
                        "request_id": request_id,
                        "task_id": task_id,
                        "train_id": train_id,
                        "train_number": train_number,
                        "train_name": train_name,
                        "train_type": canonical_type,
                        "block_time": f"{block_start} - {block_end}",
                        "train_time": f"{train_arrival} - {train_departure}",
                    })

        return blocks, trains, conflicts

    finally:
        cursor.close()
        if close_at_end:
            connection.close()


if __name__ == "__main__":
    blocks, trains, conflicts = detect_conflicts()

    maintenance_conflicts = sum(1 for c in conflicts if c["type"] == "MAINTENANCE_MAINTENANCE")
    train_conflicts = sum(1 for c in conflicts if c["type"] == "MAINTENANCE_TRAIN")

    print()
    print("================================================")
    print("          UNIFIED CONFLICT DETECTOR V3")
    print("================================================")
    print()
    print(f"Block requests checked : {len(blocks)}")
    print(f"Trains checked         : {len(trains)}")
    print()
    print(f"Maintenance conflicts  : {maintenance_conflicts}")
    print(f"Train conflicts        : {train_conflicts}")
    print(f"Total conflicts        : {len(conflicts)}")
    print()

    severity_count = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for conflict in conflicts:
        severity_count[conflict["severity"]] += 1

    for severity, count in severity_count.items():
        if count > 0:
            print(f"{severity:<10} {count} conflicts")
    print()
    print("================================================")
    print("Unified conflict detection complete.")
    print("================================================")