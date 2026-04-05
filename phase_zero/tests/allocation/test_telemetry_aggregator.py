"""
Tests for Telemetry Aggregator — Component 1/10.

TA-01  Valid session → SUCCESS
TA-02  Aggregation groups by tenant + region + pool + date
TA-03  SUM(gpu_hours_consumed) correct across multiple rows
TA-04  Decimal precision preserved (no float loss)
TA-05  Empty session (no rows) → FAIL
TA-06  FAIL error message contains session_id
TA-07  Multiple tenants in same pool → separate records
TA-08  Same tenant across multiple dates → separate records
"""

from decimal import Decimal

from sqlalchemy import text

from app.allocation.telemetry_aggregator import aggregate_telemetry


def _insert_telemetry(conn, sid, tenant, region, pool, date_str, hours):
    conn.execute(
        text("""
            INSERT INTO raw.telemetry
                (session_id, tenant_id, region, gpu_pool_id, date, gpu_hours_consumed)
            VALUES (:sid, :tenant, :region, :pool, :date, :hours)
        """),
        {
            "sid": str(sid),
            "tenant": tenant,
            "region": region,
            "pool": pool,
            "date": date_str,
            "hours": hours,
        },
    )


# ── TA-01: Valid session → SUCCESS ──
def test_valid_session_returns_success(db_connection, test_session_id):
    _insert_telemetry(db_connection, test_session_id,
                      "T1", "us-east", "pool-a", "2026-03-15", "10.500000")
    result = aggregate_telemetry(db_connection, test_session_id)
    assert result.result == "SUCCESS"


# ── TA-02: Aggregation groups by tenant + region + pool + date ──
def test_grouping_produces_one_record_per_grain(db_connection, test_session_id):
    _insert_telemetry(db_connection, test_session_id,
                      "T1", "us-east", "pool-a", "2026-03-15", "5.000000")
    _insert_telemetry(db_connection, test_session_id,
                      "T1", "us-east", "pool-a", "2026-03-15", "3.000000")
    result = aggregate_telemetry(db_connection, test_session_id)
    assert len(result.records) == 1


# ── TA-03: SUM(gpu_hours_consumed) correct across multiple rows ──
def test_sum_gpu_hours_correct(db_connection, test_session_id):
    _insert_telemetry(db_connection, test_session_id,
                      "T1", "us-east", "pool-a", "2026-03-15", "5.000000")
    _insert_telemetry(db_connection, test_session_id,
                      "T1", "us-east", "pool-a", "2026-03-15", "3.500000")
    result = aggregate_telemetry(db_connection, test_session_id)
    assert result.records[0].gpu_hours == Decimal("8.500000")


# ── TA-04: Decimal precision preserved ──
def test_decimal_precision_preserved(db_connection, test_session_id):
    _insert_telemetry(db_connection, test_session_id,
                      "T1", "us-east", "pool-a", "2026-03-15", "1.123456")
    result = aggregate_telemetry(db_connection, test_session_id)
    assert result.records[0].gpu_hours == Decimal("1.123456")


# ── TA-05: Empty session → FAIL ──
def test_empty_session_returns_fail(db_connection, test_session_id):
    result = aggregate_telemetry(db_connection, test_session_id)
    assert result.result == "FAIL"


# ── TA-06: FAIL error message contains session_id ──
def test_fail_error_contains_session_id(db_connection, test_session_id):
    result = aggregate_telemetry(db_connection, test_session_id)
    assert str(test_session_id) in result.error


# ── TA-07: Multiple tenants in same pool → separate records ──
def test_multiple_tenants_separate_records(db_connection, test_session_id):
    _insert_telemetry(db_connection, test_session_id,
                      "T1", "us-east", "pool-a", "2026-03-15", "10.000000")
    _insert_telemetry(db_connection, test_session_id,
                      "T2", "us-east", "pool-a", "2026-03-15", "7.000000")
    result = aggregate_telemetry(db_connection, test_session_id)
    assert len(result.records) == 2


# ── TA-08: Same tenant across multiple dates → separate records ──
def test_same_tenant_different_dates_separate(db_connection, test_session_id):
    _insert_telemetry(db_connection, test_session_id,
                      "T1", "us-east", "pool-a", "2026-03-15", "10.000000")
    _insert_telemetry(db_connection, test_session_id,
                      "T1", "us-east", "pool-a", "2026-03-16", "5.000000")
    result = aggregate_telemetry(db_connection, test_session_id)
    assert len(result.records) == 2
