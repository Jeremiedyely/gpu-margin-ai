"""
Integration tests for the telemetry raw-table writer.

6 assertions: TW-01 through TW-06.
Requires a running SQL Server with the gpu_margin database and migrations applied.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.ingestion.parsers.telemetry import TelemetryRecord
from app.ingestion.writers.telemetry import write_telemetry


# ---------------------------------------------------------------------------
# TW-01  Single record insert returns SUCCESS
# ---------------------------------------------------------------------------
def test_single_record_success(db_connection, test_session_id):
    records = [
        TelemetryRecord(
            tenant_id="tenant-a",
            region="us-east-1",
            gpu_pool_id="pool-1",
            date=date(2025, 1, 15),
            gpu_hours_consumed=Decimal("10.5"),
        )
    ]
    result = write_telemetry(db_connection, test_session_id, records)

    assert result.result == "SUCCESS"                           # TW-01


# ---------------------------------------------------------------------------
# TW-02  Row count matches input
# ---------------------------------------------------------------------------
def test_row_count_matches(db_connection, test_session_id):
    records = [
        TelemetryRecord(
            tenant_id=f"tenant-{i}",
            region="us-east-1",
            gpu_pool_id="pool-1",
            date=date(2025, 1, 15),
            gpu_hours_consumed=Decimal("1.0"),
        )
        for i in range(5)
    ]
    result = write_telemetry(db_connection, test_session_id, records)

    assert result.row_count == 5                                # TW-02


# ---------------------------------------------------------------------------
# TW-03  session_id echoed back in result
# ---------------------------------------------------------------------------
def test_session_id_returned(db_connection, test_session_id):
    records = [
        TelemetryRecord(
            tenant_id="tenant-a",
            region="us-east-1",
            gpu_pool_id="pool-1",
            date=date(2025, 1, 15),
            gpu_hours_consumed=Decimal("1.0"),
        )
    ]
    result = write_telemetry(db_connection, test_session_id, records)

    assert result.session_id == test_session_id                 # TW-03


# ---------------------------------------------------------------------------
# TW-04  Data round-trips correctly through the database
# ---------------------------------------------------------------------------
def test_data_round_trip(db_connection, test_session_id):
    records = [
        TelemetryRecord(
            tenant_id="tenant-a",
            region="us-east-1",
            gpu_pool_id="pool-1",
            date=date(2025, 1, 15),
            gpu_hours_consumed=Decimal("10.5"),
        )
    ]
    write_telemetry(db_connection, test_session_id, records)

    row = db_connection.execute(
        text("SELECT tenant_id, region, gpu_pool_id, date, gpu_hours_consumed "
             "FROM raw.telemetry WHERE session_id = :sid"),
        {"sid": str(test_session_id)},
    ).fetchone()

    assert row[0] == "tenant-a"                                 # TW-04a
    assert row[1] == "us-east-1"                                # TW-04b
    assert row[2] == "pool-1"                                   # TW-04c
    assert row[3] == date(2025, 1, 15)                          # TW-04d
    assert row[4] == Decimal("10.500000")                       # TW-04e


# ---------------------------------------------------------------------------
# TW-05  Empty list returns SUCCESS with row_count 0
# ---------------------------------------------------------------------------
def test_empty_list_returns_success(db_connection, test_session_id):
    result = write_telemetry(db_connection, test_session_id, [])

    assert result.result == "SUCCESS"                           # TW-05a
    assert result.row_count == 0                                # TW-05b


# ---------------------------------------------------------------------------
# TW-06  Invalid session_id returns FAIL (FK violation)
# ---------------------------------------------------------------------------
def test_invalid_session_id_returns_fail(db_connection):
    bad_sid = __import__("uuid").uuid4()
    records = [
        TelemetryRecord(
            tenant_id="tenant-a",
            region="us-east-1",
            gpu_pool_id="pool-1",
            date=date(2025, 1, 15),
            gpu_hours_consumed=Decimal("1.0"),
        )
    ]
    result = write_telemetry(db_connection, bad_sid, records)

    assert result.result == "FAIL"                              # TW-06a
    assert result.error is not None                             # TW-06b
