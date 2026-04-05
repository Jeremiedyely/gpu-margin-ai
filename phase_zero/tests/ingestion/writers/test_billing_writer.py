"""
Integration tests for the billing raw-table writer.
6 assertions: BILW-01 through BILW-06.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.ingestion.parsers.billing import BillingRecord
from app.ingestion.writers.billing import write_billing


def test_single_record_success(db_connection, test_session_id):
    records = [
        BillingRecord(
            tenant_id="tenant-a",
            billing_period="2025-01",
            billable_amount=Decimal("1500.00"),
        )
    ]
    result = write_billing(db_connection, test_session_id, records)
    assert result.result == "SUCCESS"                           # BILW-01


def test_row_count_matches(db_connection, test_session_id):
    records = [
        BillingRecord(
            tenant_id=f"tenant-{i}",
            billing_period="2025-01",
            billable_amount=Decimal("1500.00"),
        )
        for i in range(3)
    ]
    result = write_billing(db_connection, test_session_id, records)
    assert result.row_count == 3                                # BILW-02


def test_data_round_trip(db_connection, test_session_id):
    records = [
        BillingRecord(
            tenant_id="tenant-a",
            billing_period="2025-01",
            billable_amount=Decimal("-250.75"),
        )
    ]
    write_billing(db_connection, test_session_id, records)

    row = db_connection.execute(
        text("SELECT tenant_id, billing_period, billable_amount "
             "FROM raw.billing WHERE session_id = :sid"),
        {"sid": str(test_session_id)},
    ).fetchone()

    assert row[0] == "tenant-a"                                 # BILW-03a
    assert row[1] == "2025-01"                                  # BILW-03b
    assert row[2] == Decimal("-250.75")                         # BILW-03c


def test_negative_amount_allowed(db_connection, test_session_id):
    """R4-W-3: credit memos produce negative billable_amount."""
    records = [
        BillingRecord(
            tenant_id="tenant-credit",
            billing_period="2025-02",
            billable_amount=Decimal("-100.00"),
        )
    ]
    result = write_billing(db_connection, test_session_id, records)
    assert result.result == "SUCCESS"                           # BILW-04


def test_empty_list_returns_success(db_connection, test_session_id):
    result = write_billing(db_connection, test_session_id, [])
    assert result.result == "SUCCESS"                           # BILW-05a
    assert result.row_count == 0                                # BILW-05b


def test_invalid_session_id_returns_fail(db_connection):
    bad_sid = __import__("uuid").uuid4()
    records = [
        BillingRecord(
            tenant_id="tenant-a",
            billing_period="2025-01",
            billable_amount=Decimal("1500.00"),
        )
    ]
    result = write_billing(db_connection, bad_sid, records)
    assert result.result == "FAIL"                              # BILW-06a
    assert result.error is not None                             # BILW-06b
