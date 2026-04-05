"""
Writer for raw.iam table.

Receives a list of IAMRecord objects and a SQLAlchemy Connection.
Inserts all rows in a single executemany call. Does NOT commit.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text

from app.ingestion.parsers.iam import IAMRecord
from app.ingestion.writers.base import WriteResult


INSERT_SQL = text("""
    INSERT INTO raw.iam
        (session_id, tenant_id, billing_period, contracted_rate)
    VALUES
        (:session_id, :tenant_id, :billing_period, :contracted_rate)
""")


def write_iam(
    conn: Connection,
    session_id: UUID,
    records: list[IAMRecord],
) -> WriteResult:
    if not records:
        return WriteResult.success(session_id=session_id, row_count=0)

    try:
        params = [
            {
                "session_id": str(session_id),
                "tenant_id": rec.tenant_id,
                "billing_period": rec.billing_period,
                "contracted_rate": rec.contracted_rate,
            }
            for rec in records
        ]
        conn.execute(INSERT_SQL, params)
        return WriteResult.success(session_id=session_id, row_count=len(records))

    except Exception as exc:
        return WriteResult.failed(session_id=session_id, error=str(exc))
