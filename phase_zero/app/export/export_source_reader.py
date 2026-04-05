"""
Export Source Reader — Component 2/9.

Layer: Export.

Reads ALL rows from final.allocation_result for the approved session.
No joins with other tables. No rows from other sessions.
Returns a list of dicts keyed by grain column names.

Spec: build-checklist.md — Step 7.2
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Connection, text

from app.export.column_order import GRAIN_COLUMNS


_READ_SQL = text("""
    SELECT {cols}
    FROM final.allocation_result
    WHERE session_id = :sid
    ORDER BY region, gpu_pool_id, date, allocation_target
""".format(cols=", ".join(GRAIN_COLUMNS)))


def read_export_source(
    conn: Connection,
    session_id: UUID,
) -> list[dict[str, Any]]:
    """
    Read all rows from final.allocation_result for one session.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection (caller owns transaction).
    session_id : UUID
        The approved session to export.

    Returns
    -------
    list[dict]
        One dict per row, keyed by GRAIN_COLUMNS.
        Empty list if no rows found.
    """
    result = conn.execute(_READ_SQL, {"sid": str(session_id)})
    rows = result.fetchall()
    columns = list(GRAIN_COLUMNS)
    return [dict(zip(columns, row)) for row in rows]
