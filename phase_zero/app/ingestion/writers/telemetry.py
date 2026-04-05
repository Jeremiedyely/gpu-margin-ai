"""
Writer for raw_telemetry table.

Receives a list of TelemetryRecord objects (from the parser) and a
SQLAlchemy Connection. Inserts all rows in a single executemany call.
Does NOT commit — the Ingestion Commit layer controls the transaction.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text

from app.ingestion.parsers.telemetry import TelemetryRecord
from app.ingestion.writers.base import WriteResult


INSERT_SQL = text("""
    INSERT INTO raw.telemetry
        (session_id, tenant_id, region, gpu_pool_id, date, gpu_hours_consumed)
    VALUES
        (:session_id, :tenant_id, :region, :gpu_pool_id, :date, :gpu_hours_consumed)
""")


def write_telemetry(
    conn: Connection,
    session_id: UUID,
    records: list[TelemetryRecord],
) -> WriteResult:
    """
    Bulk-insert telemetry records into raw_telemetry.

    Parameters
    ----------
    conn : Connection
        An active SQLAlchemy connection (transaction managed externally).
    session_id : UUID
        The ingestion session ID (must already exist in ingestion_log).
    records : list[TelemetryRecord]
        Parsed telemetry records to insert.

    Returns
    -------
    WriteResult
        SUCCESS with row_count, or FAIL with error message.
    """
    if not records:
        return WriteResult.success(session_id=session_id, row_count=0)

    try:
        params = [
            {
                "session_id": str(session_id),
                "tenant_id": rec.tenant_id,
                "region": rec.region,
                "gpu_pool_id": rec.gpu_pool_id,
                "date": rec.date,
                "gpu_hours_consumed": rec.gpu_hours_consumed,
            }
            for rec in records
        ]
        conn.execute(INSERT_SQL, params)
        return WriteResult.success(session_id=session_id, row_count=len(records))

    except Exception as exc:
        return WriteResult.failed(session_id=session_id, error=str(exc))
