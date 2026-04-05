"""
Integration tests for the IAM raw-table writer.
6 assertions: IAMW-01 through IAMW-06.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.ingestion.parsers.iam import IAMRecord
from app.ingestion.writers.iam import write_iam


def test_single_record_success(db_connection, test_session_id):
    records = [
        IAMRecord(
            tenant_id="tenant-a",
            billing_period="2025-01",
            contracted_rate=Decimal("3.50"),
        )
    ]
    result = write_iam(db_connection, test_session_id, records)
    assert result.result == "SUCCESS"                           # IAMW-01


def test_row_count_matches(db_connection, test_session_id):
    records = [
        IAMRecord(
            tenant_id=f"tenant-{i}",
            billing_period="2025-01",
            contracted_rate=Decimal("3.50"),
        )
        for i in range(4)
    ]
    result = write_iam(db_connection, test_session_id, records)
    assert result.row_count == 4                                # IAMW-02


def test_data_round_trip(db_connection, test_session_id):
    records = [
        IAMRecord(
            tenant_id="tenant-a",
            billing_period="2025-01",
            contracted_rate=Decimal("3.75"),
        )
    ]
    write_iam(db_connection, test_session_id, records)

    row = db_connection.execute(
        text("SELECT tenant_id, billing_period, contracted_rate "
             "FROM raw.iam WHERE session_id = :sid"),
        {"sid": str(test_session_id)},
    ).fetchone()

    assert row[0] == "tenant-a"                                 # IAMW-03a
    assert row[1] == "2025-01"                                  # IAMW-03b
    assert row[2] == Decimal("3.750000")                        # IAMW-03c


def test_empty_list_returns_success(db_connection, test_session_id):
    result = write_iam(db_connection, test_session_id, [])
    assert result.result == "SUCCESS"                           # IAMW-04a
    assert result.row_count == 0                                # IAMW-04b


def test_session_id_returned(db_connection, test_session_id):
    records = [
        IAMRecord(
            tenant_id="tenant-a",
            billing_period="2025-01",
            contracted_rate=Decimal("3.50"),
        )
    ]
    result = write_iam(db_connection, test_session_id, records)
    assert result.session_id == test_session_id                 # IAMW-05


def test_invalid_session_id_returns_fail(db_connection):
    bad_sid = __import__("uuid").uuid4()
    records = [
        IAMRecord(
            tenant_id="tenant-a",
            billing_period="2025-01",
            contracted_rate=Decimal("3.50"),
        )
    ]
    result = write_iam(db_connection, bad_sid, records)
    assert result.result == "FAIL"                              # IAMW-06a
    assert result.error is not None                             # IAMW-06b
