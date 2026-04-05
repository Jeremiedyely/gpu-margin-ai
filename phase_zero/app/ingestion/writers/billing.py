"""
Writer for raw.billing table.

Receives a list of BillingRecord objects and a SQLAlchemy Connection.
Inserts all rows in a single executemany call. Does NOT commit.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text

from app.ingestion.parsers.billing import BillingRecord
from app.ingestion.writers.base import WriteResult


INSERT_SQL = text("""
    INSERT INTO raw.billing
        (session_id, tenant_id, billing_period, billable_amount)
    VALUES
        (:session_id, :tenant_id, :billing_period, :billable_amount)
""")


def write_billing(
    conn: Connection,
    session_id: UUID,
    records: list[BillingRecord],
) -> WriteResult:
    if not records:
        return WriteResult.success(session_id=session_id, row_count=0)

    try:
        params = [
            {
                "session_id": str(session_id),
                "tenant_id": rec.tenant_id,
                "billing_period": rec.billing_period,
                "billable_amount": rec.billable_amount,
            }
            for rec in records
        ]
        conn.execute(INSERT_SQL, params)
        return WriteResult.success(session_id=session_id, row_count=len(records))

    except Exception as exc:
        return WriteResult.failed(session_id=session_id, error=str(exc))
