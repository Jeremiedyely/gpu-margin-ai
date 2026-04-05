"""
Writer for raw.erp table.

Receives a list of ERPRecord objects and a SQLAlchemy Connection.
Inserts all rows in a single executemany call. Does NOT commit.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text

from app.ingestion.parsers.erp import ERPRecord
from app.ingestion.writers.base import WriteResult


INSERT_SQL = text("""
    INSERT INTO raw.erp
        (session_id, tenant_id, billing_period, amount_posted)
    VALUES
        (:session_id, :tenant_id, :billing_period, :amount_posted)
""")


def write_erp(
    conn: Connection,
    session_id: UUID,
    records: list[ERPRecord],
) -> WriteResult:
    if not records:
        return WriteResult.success(session_id=session_id, row_count=0)

    try:
        params = [
            {
                "session_id": str(session_id),
                "tenant_id": rec.tenant_id,
                "billing_period": rec.billing_period,
                "amount_posted": rec.amount_posted,
            }
            for rec in records
        ]
        conn.execute(INSERT_SQL, params)
        return WriteResult.success(session_id=session_id, row_count=len(records))

    except Exception as exc:
        return WriteResult.failed(session_id=session_id, error=str(exc))
