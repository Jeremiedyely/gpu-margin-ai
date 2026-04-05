"""
Tests for Cost Rate Reader — Component 3/10.

CRR-01  Valid session → SUCCESS
CRR-02  All fields read correctly
CRR-03  Decimal precision preserved (reserved_gpu_hours)
CRR-04  Decimal precision preserved (cost_per_gpu_hour)
CRR-05  Multiple rows returned
CRR-06  Empty session → FAIL
CRR-07  FAIL error contains session_id
"""

from decimal import Decimal

from sqlalchemy import text

from app.allocation.cost_rate_reader import read_cost_rates


def _insert_cost(conn, sid, region, pool, date_str, reserved, cost):
    conn.execute(
        text("""
            INSERT INTO raw.cost_management
                (session_id, region, gpu_pool_id, date,
                 reserved_gpu_hours, cost_per_gpu_hour)
            VALUES (:sid, :region, :pool, :date, :reserved, :cost)
        """),
        {
            "sid": str(sid),
            "region": region,
            "pool": pool,
            "date": date_str,
            "reserved": reserved,
            "cost": cost,
        },
    )


# ── CRR-01: Valid session → SUCCESS ──
def test_valid_session_returns_success(db_connection, test_session_id):
    _insert_cost(db_connection, test_session_id,
                 "us-east", "pool-a", "2026-03-15", "100.000000", "2.500000")
    result = read_cost_rates(db_connection, test_session_id)
    assert result.result == "SUCCESS"


# ── CRR-02: All fields read correctly ──
def test_fields_read_correctly(db_connection, test_session_id):
    _insert_cost(db_connection, test_session_id,
                 "us-east", "pool-a", "2026-03-15", "100.000000", "2.500000")
    result = read_cost_rates(db_connection, test_session_id)
    rec = result.records[0]
    assert rec.region == "us-east"
    assert rec.gpu_pool_id == "pool-a"


# ── CRR-03: Decimal precision preserved (reserved_gpu_hours) ──
def test_reserved_gpu_hours_decimal(db_connection, test_session_id):
    _insert_cost(db_connection, test_session_id,
                 "us-east", "pool-a", "2026-03-15", "123.456789", "2.500000")
    result = read_cost_rates(db_connection, test_session_id)
    assert result.records[0].reserved_gpu_hours == Decimal("123.456789")


# ── CRR-04: Decimal precision preserved (cost_per_gpu_hour) ──
def test_cost_per_gpu_hour_decimal(db_connection, test_session_id):
    _insert_cost(db_connection, test_session_id,
                 "us-east", "pool-a", "2026-03-15", "100.000000", "3.141592")
    result = read_cost_rates(db_connection, test_session_id)
    assert result.records[0].cost_per_gpu_hour == Decimal("3.141592")


# ── CRR-05: Multiple rows returned ──
def test_multiple_rows(db_connection, test_session_id):
    _insert_cost(db_connection, test_session_id,
                 "us-east", "pool-a", "2026-03-15", "100.000000", "2.500000")
    _insert_cost(db_connection, test_session_id,
                 "us-east", "pool-b", "2026-03-15", "50.000000", "3.000000")
    result = read_cost_rates(db_connection, test_session_id)
    assert len(result.records) == 2


# ── CRR-06: Empty session → FAIL ──
def test_empty_session_returns_fail(db_connection, test_session_id):
    result = read_cost_rates(db_connection, test_session_id)
    assert result.result == "FAIL"


# ── CRR-07: FAIL error contains session_id ──
def test_fail_error_contains_session_id(db_connection, test_session_id):
    result = read_cost_rates(db_connection, test_session_id)
    assert str(test_session_id) in result.error
