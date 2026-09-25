"""
Data Scoping Utilities for IR-ABPS RBAC.
Provides helper functions to filter and scope database queries by department and corridor.
"""
from typing import List, Optional, Set
import logging

logger = logging.getLogger("auth.scoping")

def get_relevant_corridor_ids(cursor, dept: Optional[str]) -> List[str]:
    """
    Returns the list of corridor_ids relevant to a department:
    Union of corridors that have:
      (a) assets of that department
      (b) block requests of that department
      (c) optimized blocks containing a task of that department
    """
    if not dept:
        return []

    clean_dept = dept.replace("DEPT-", "").upper()
    dept_id = f"DEPT-{clean_dept}"

    try:
        cursor.execute(
            """
            SELECT DISTINCT corridor_id FROM (
                SELECT corridor_id FROM assets
                WHERE UPPER(department) = %s AND corridor_id IS NOT NULL

                UNION

                SELECT br.corridor_id FROM block_requests br
                JOIN maintenance_tasks mt ON mt.task_id = br.task_id
                WHERE UPPER(COALESCE(mt.department, '')) IN (%s, %s)
                  AND br.corridor_id IS NOT NULL

                UNION

                SELECT ob.corridor_id FROM optimized_blocks ob
                JOIN block_tasks bt ON ob.block_id = bt.block_id
                JOIN maintenance_tasks mt ON bt.task_id = mt.task_id
                WHERE UPPER(mt.department) = %s AND ob.corridor_id IS NOT NULL
            ) combined_corridors
            """,
            (clean_dept, dept_id, clean_dept, clean_dept),
        )
        rows = cursor.fetchall()
        corridor_ids = [r[0] for r in rows if r[0]]
        return corridor_ids
    except Exception as e:
        logger.warning(f"Error querying relevant corridors for dept {dept}: {e}")
        return []
