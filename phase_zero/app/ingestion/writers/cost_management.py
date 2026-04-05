"""
Writer for raw.cost_management table.

Receives a list of CostManagementRecord objects and a SQLAlchemy Connection.
Inserts all rows in a single executemany call. Does NOT commit.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text

from app.ingestion.parsers.cost_management import CostManagementRecord
from app.ingestion.writers.base import WriteResult


INSERT_SQL = text("""
    INSERT INTO raw.cost_management
        (session_id, region, gpu_pool_id, date, reserved_gpu_hours, cost_per_gpu_hour)
    VALUES
        (:session_id, :region, :gpu_pool_id, :date, :reserved_gpu_hours, :cost_per_gpu_hour)
""")


def write_cost_management(
    conn: Connection,
    session_id: UUID,
    records: list[CostManagementRecord],
) -> WriteResult:
    if not records:
        return WriteResult.success(session_id=session_id, row_count=0)

    try:
        params = [
            {
                "session_id": str(session_id),
                "region": rec.region,
                "gpu_pool_id": rec.gpu_pool_id,
                "date": rec.date,
                "reserved_gpu_hours": rec.reserved_gpu_hours,
                "cost_per_gpu_hour": rec.cost_per_gpu_hour,
            }
            for rec in records
        ]
        conn.execute(INSERT_SQL, params)
        return WriteResult.success(session_id=session_id, row_count=len(records))

    except Exception as exc:
        return WriteResult.failed(session_id=session_id, error=str(exc))
