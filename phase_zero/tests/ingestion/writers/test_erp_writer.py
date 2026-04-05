"""
Integration tests for the ERP raw-table writer.
6 assertions: ERPW-01 through ERPW-06.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.ingestion.parsers.erp import ERPRecord
from app.ingestion.writers.erp import write_erp


def test_single_record_success(db_connection, test_session_id):
    records = [
        ERPRecord(
            tenant_id="tenant-a",
            billing_period="2025-01",
            amount_posted=Decimal("1500.00"),
        )
    ]
    result = write_erp(db_connection, test_session_id, records)
    assert result.result == "SUCCESS"                           # ERPW-01


def test_row_count_matches(db_connection, test_session_id):
    records = [
        ERPRecord(
            tenant_id=f"tenant-{i}",
            billing_period="2025-01",
            amount_posted=Decimal("1500.00"),
        )
        for i in range(3)
    ]
    result = write_erp(db_connection, test_session_id, records)
    assert result.row_count == 3                                # ERPW-02


def test_data_round_trip(db_connection, test_session_id):
    records = [
        ERPRecord(
            tenant_id="tenant-a",
            billing_period="2025-01",
            amount_posted=Decimal("-500.25"),
        )
    ]
    write_erp(db_connection, test_session_id, records)

    row = db_connection.execute(
        text("SELECT tenant_id, billing_period, amount_posted "
             "FROM raw.erp WHERE session_id = :sid"),
        {"sid": str(test_session_id)},
    ).fetchone()

    assert row[0] == "tenant-a"                                 # ERPW-03a
    assert row[1] == "2025-01"                                  # ERPW-03b
    assert row[2] == Decimal("-500.25")                         # ERPW-03c


def test_negative_amount_allowed(db_connection, test_session_id):
    """R4-W-3: GL reversals produce negative amount_posted."""
    records = [
        ERPRecord(
            tenant_id="tenant-reversal",
            billing_period="2025-02",
            amount_posted=Decimal("-200.00"),
        )
    ]
    result = write_erp(db_connection, test_session_id, records)
    assert result.result == "SUCCESS"                           # ERPW-04


def test_empty_list_returns_success(db_connection, test_session_id):
    result = write_erp(db_connection, test_session_id, [])
    assert result.result == "SUCCESS"                           # ERPW-05a
    assert result.row_count == 0                                # ERPW-05b


def test_invalid_session_id_returns_fail(db_connection):
    bad_sid = __import__("uuid").uuid4()
    records = [
        ERPRecord(
            tenant_id="tenant-a",
            billing_period="2025-01",
            amount_posted=Decimal("1500.00"),
        )
    ]
    result = write_erp(db_connection, bad_sid, records)
    assert result.result == "FAIL"                              # ERPW-06a
    assert result.error is not None                             # ERPW-06b
