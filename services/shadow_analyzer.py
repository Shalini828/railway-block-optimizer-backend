"""
Shadow Block Analyzer

Independent advisory layer for identifying nearby maintenance
windows that may be candidates for future coordination.

IMPORTANT:
- Does NOT import block_optimizer.py
- Does NOT modify optimization results
- Does NOT change block_requests
- Does NOT change optimized_blocks
- Read-only analysis
"""

from datetime import date, time
from typing import Any

import psycopg

from db_config import DB_CONFIG


NORMAL_GAP_MINUTES = 15
SHADOW_MAX_GAP_MINUTES = 120
NORMAL_MAX_BLOCK_MINUTES = 240
SHADOW_MAX_BLOCK_MINUTES = 360


def time_to_minutes(value: time | str) -> int:
    """Convert HH:MM[:SS] or datetime.time to minutes from midnight."""

    if isinstance(value, str):
        parts = value.split(":")
        return int(parts[0]) * 60 + int(parts[1])

    return value.hour * 60 + value.minute


def analyze_shadow_opportunities() -> list[dict[str, Any]]:
    """
    Find advisory shadow-block opportunities directly from database data.

    This function is completely independent of the main optimizer.
    """

    connection = psycopg.connect(**DB_CONFIG)

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                br.request_id,
                br.task_id,
                br.corridor_id,
                br.requested_date,
                br.requested_start,
                br.requested_end,
                br.requested_duration_min,
                br.request_status
            FROM block_requests br
            WHERE br.request_status IN ('PENDING', 'OPTIMIZED')
            ORDER BY
                br.corridor_id,
                br.requested_date,
                br.requested_start
            """
        )

        requests = cursor.fetchall()

    finally:
        connection.close()

    opportunities: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for index, first in enumerate(requests):

        for second in requests[index + 1:]:

            first_id = str(first[0])
            second_id = str(second[0])

            first_task = str(first[1])
            second_task = str(second[1])

            first_corridor = first[2]
            second_corridor = second[2]

            first_date = first[3]
            second_date = second[3]

            # Same corridor required.
            if first_corridor != second_corridor:
                continue

            # Same operating date required.
            if first_date != second_date:
                continue

            # Same maintenance task is not a useful shadow opportunity.
            if first_task == second_task:
                continue

            first_start = time_to_minutes(first[4])
            first_end = time_to_minutes(first[5])

            second_start = time_to_minutes(second[4])
            second_end = time_to_minutes(second[5])

            combined_start = min(first_start, second_start)
            combined_end = max(first_end, second_end)

            combined_duration = combined_end - combined_start

            if combined_duration <= 0:
                continue

            if combined_duration > SHADOW_MAX_BLOCK_MINUTES:
                continue

            # Calculate actual gap.
            if first_end <= second_start:
                gap_minutes = second_start - first_end
            elif second_end <= first_start:
                gap_minutes = first_start - second_end
            else:
                # Windows overlap.
                gap_minutes = 0

            # Only nearby windows are interesting.
            if gap_minutes > SHADOW_MAX_GAP_MINUTES:
                continue

            # Identify whether this is a near-miss or a longer extension.
            if gap_minutes > NORMAL_GAP_MINUTES:
                opportunity_type = "gap_extension"

                reason = (
                    f"Two maintenance windows on {first_corridor} are "
                    f"{gap_minutes} minutes apart. They exceed the normal "
                    f"{NORMAL_GAP_MINUTES}-minute consolidation gap but "
                    f"remain within the {SHADOW_MAX_GAP_MINUTES}-minute "
                    f"advisory range."
                )

            elif combined_duration > NORMAL_MAX_BLOCK_MINUTES:
                opportunity_type = "duration_extension"

                reason = (
                    f"Two nearby maintenance windows could be coordinated "
                    f"within a combined {combined_duration}-minute window, "
                    f"but that exceeds the normal "
                    f"{NORMAL_MAX_BLOCK_MINUTES}-minute block limit."
                )

            else:
                opportunity_type = "near_miss"

                reason = (
                    "Two separate maintenance windows are close enough "
                    "to be reviewed as a potential coordination opportunity."
                )

            key = (
                str(first_corridor),
                str(first_date),
                "|".join(sorted([first_id, second_id])),
            )

            if key in seen:
                continue

            seen.add(key)

            opportunities.append(
                {
                    "corridor": str(first_corridor),
                    "date": str(first_date),

                    "base_request_id": first_id,
                    "candidate_request_id": second_id,

                    "base_tasks": [first_task],
                    "candidate_tasks": [second_task],

                    "base_window": {
                        "start": str(first[4]),
                        "end": str(first[5]),
                    },

                    "candidate_window": {
                        "start": str(second[4]),
                        "end": str(second[5]),
                    },

                    "gap_minutes": gap_minutes,

                    "combined_duration_minutes": combined_duration,

                    "opportunity_type": opportunity_type,

                    "reason": reason,
                }
            )

    opportunities.sort(
        key=lambda item: (
            item["date"],
            item["corridor"],
            item["base_window"]["start"],
        )
    )

    return opportunities


if __name__ == "__main__":

    results = analyze_shadow_opportunities()

    print()
    print("=" * 60)
    print("SHADOW BLOCK ANALYZER")
    print("=" * 60)
    print(f"Opportunities found: {len(results)}")
    print("=" * 60)

    for opportunity in results:
        print()
        print(
            f"{opportunity['corridor']} | "
            f"{opportunity['date']} | "
            f"{opportunity['opportunity_type']}"
        )

        print(
            f"  {opportunity['base_window']['start']} "
            f"-> {opportunity['base_window']['end']}"
        )

        print(
            f"  {opportunity['candidate_window']['start']} "
            f"-> {opportunity['candidate_window']['end']}"
        )

        print(
            f"  Gap: {opportunity['gap_minutes']} min"
        )

        print(
            f"  Combined: "
            f"{opportunity['combined_duration_minutes']} min"
        )