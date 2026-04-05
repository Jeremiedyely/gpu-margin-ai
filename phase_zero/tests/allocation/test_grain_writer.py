"""
Tests for Allocation Grain Writer — Component 9/10.

GW-01  Write single record → SUCCESS with row_count = 1
GW-02  Write multiple records → SUCCESS with row_count = N
GW-03  session_id appended to every written row
GW-04  All 14 columns written correctly (spot check)
GW-05  Empty records list → FAIL
GW-06  Result contains session_id on SUCCESS
GW-07  Result contains session_id on FAIL
GW-08  Savepoint rollback on write failure — no partial rows
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from app.allocation.cost_revenue_calculator import ComputedRecord
from app.allocation.grain_writer import write_allocation_grain


def _computed(region="us-east", pool="pool-a", d=date(2026, 3, 15),
              bp="2026-03", target="T1", utype=None, ftid=None,
              hours=Decimal("10.000000"), cph=Decimal("2.000000"),
              rate=Decimal("5.000000"), revenue=Decimal("50.00"),
              cogs=Decimal("20.00"), gm=Decimal("30.00")):
    return ComputedRecord(
        region=region, gpu_pool_id=pool, date=d,
        billing_period=bp, allocation_target=target,
        unallocated_type=utype, failed_tenant_id=ftid,
        gpu_hours=hours, cost_per_gpu_hour=cph,
        contracted_rate=rate, revenue=revenue,
        cogs=cogs, gross_margin=gm,
    )


# ── GW-01: Single record → SUCCESS with row_count = 1 ──
def test_single_record_success(db_connection, test_session_id):
    result = write_allocation_grain(
        db_connection, test_session_id, [_computed()]
    )
    assert result.result == "SUCCESS"
    assert result.row_count == 1


# ── GW-02: Multiple records → SUCCESS with row_count = N ──
def test_multiple_records_success(db_connection, test_session_id):
    records = [
        _computed(target="T1"),
        _computed(target="T2"),
        _computed(target="unallocated", utype="capacity_idle",
                  ftid=None, rate=None, revenue=Decimal("0"),
                  cogs=Decimal("20.00"), gm=Decimal("-20.00")),
    ]
    result = write_allocation_grain(
        db_connection, test_session_id, records
    )
    assert result.result == "SUCCESS"
    assert result.row_count == 3


# ── GW-03: session_id appended to every written row ──
def test_session_id_appended(db_connection, test_session_id):
    write_allocation_grain(
        db_connection, test_session_id, [_computed(), _computed(target="T2")]
    )
    rows = db_connection.execute(
        text("SELECT session_id FROM dbo.allocation_grain WHERE session_id = :sid"),
        {"sid": str(test_session_id)},
    ).fetchall()
    assert len(rows) == 2
    assert all(str(r.session_id).lower() == str(test_session_id).lower() for r in rows)


# ── GW-04: All 14 columns written correctly ──
def test_columns_written_correctly(db_connection, test_session_id):
    rec = _computed(
        region="eu-west", pool="pool-b", d=date(2026, 4, 1),
        bp="2026-04", target="ACME", utype=None, ftid=None,
        hours=Decimal("25.000000"), cph=Decimal("3.000000"),
        rate=Decimal("8.000000"), revenue=Decimal("200.00"),
        cogs=Decimal("75.00"), gm=Decimal("125.00"),
    )
    write_allocation_grain(db_connection, test_session_id, [rec])
    row = db_connection.execute(
        text("""
            SELECT region, gpu_pool_id, date, billing_period,
                   allocation_target, unallocated_type, failed_tenant_id,
                   gpu_hours, cost_per_gpu_hour, contracted_rate,
                   revenue, cogs, gross_margin
            FROM dbo.allocation_grain
            WHERE session_id = :sid
        """),
        {"sid": str(test_session_id)},
    ).fetchone()
    assert row.region == "eu-west"
    assert row.gpu_pool_id == "pool-b"
    assert str(row.date) == "2026-04-01"
    assert row.billing_period == "2026-04"
    assert row.allocation_target == "ACME"
    assert row.unallocated_type is None
    assert row.failed_tenant_id is None
    assert row.gpu_hours == Decimal("25.000000")
    assert row.cost_per_gpu_hour == Decimal("3.000000")
    assert row.contracted_rate == Decimal("8.000000")
    assert row.revenue == Decimal("200.00")
    assert row.cogs == Decimal("75.00")
    assert row.gross_margin == Decimal("125.00")


# ── GW-05: Empty records list → FAIL ──
def test_empty_records_fails(db_connection, test_session_id):
    result = write_allocation_grain(db_connection, test_session_id, [])
    assert result.result == "FAIL"
    assert "empty" in result.error.lower()


# ── GW-06: Result contains session_id on SUCCESS ──
def test_success_contains_session_id(db_connection, test_session_id):
    result = write_allocation_grain(
        db_connection, test_session_id, [_computed()]
    )
    assert result.session_id == test_session_id


# ── GW-07: Result contains session_id on FAIL ──
def test_fail_contains_session_id(db_connection, test_session_id):
    result = write_allocation_grain(db_connection, test_session_id, [])
    assert result.session_id == test_session_id


# ── GW-08: Savepoint rollback — no partial rows on failure ──
def test_savepoint_rollback_no_partial_rows(db_connection, test_session_id):
    good = _computed(target="T1")
    # Force a failure: billing_period too long for NVARCHAR(7)
    bad = _computed(target="T2", bp="2026-03-TOOLONG")
    result = write_allocation_grain(
        db_connection, test_session_id, [good, bad]
    )
    assert result.result == "FAIL"
    # Verify no rows were written
    count = db_connection.execute(
        text("SELECT COUNT(*) AS cnt FROM dbo.allocation_grain WHERE session_id = :sid"),
        {"sid": str(test_session_id)},
    ).fetchone().cnt
    assert count == 0
