"""
Tests for Check 1 Executor — Capacity vs Usage — Component 1/7.

C1-01  Consumed ≤ reserved for all grains → PASS
C1-02  Consumed > reserved for one grain → FAIL
C1-03  FAIL record contains region, pool, date, consumed, reserved, excess
C1-04  excess = consumed − reserved
C1-05  No cost_management row for a telemetry grain → FAIL
C1-06  Multiple grains, one failing → failing_count = 1
C1-07  Multiple grains, all passing → PASS
C1-08  Empty telemetry → FAIL with detail
C1-09  Empty cost_management → FAIL with detail
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from app.reconciliation.check1_executor import execute_check1


def _insert_telemetry(conn, sid, region="us-east", pool="pool-a",
                      d=date(2026, 3, 15), hours=Decimal("60.000000")):
    conn.execute(
        text("""
            INSERT INTO raw.telemetry
                (session_id, tenant_id, region, gpu_pool_id, date, gpu_hours_consumed)
            VALUES (:sid, :tid, :region, :pool, :d, :hours)
        """),
        {"sid": str(sid), "tid": "T1", "region": region,
         "pool": pool, "d": d, "hours": hours},
    )


def _insert_cost(conn, sid, region="us-east", pool="pool-a",
                 d=date(2026, 3, 15), reserved=Decimal("100.000000"),
                 cph=Decimal("2.500000")):
    conn.execute(
        text("""
            INSERT INTO raw.cost_management
                (session_id, region, gpu_pool_id, date,
                 reserved_gpu_hours, cost_per_gpu_hour)
            VALUES (:sid, :region, :pool, :d, :reserved, :cph)
        """),
        {"sid": str(sid), "region": region, "pool": pool,
         "d": d, "reserved": reserved, "cph": cph},
    )


# ── C1-01: Consumed ≤ reserved → PASS ──
def test_consumed_within_reserved_passes(db_connection, test_session_id):
    _insert_telemetry(db_connection, test_session_id, hours=Decimal("60.000000"))
    _insert_cost(db_connection, test_session_id, reserved=Decimal("100.000000"))
    result = execute_check1(db_connection, test_session_id)
    assert result.verdict == "PASS"


# ── C1-02: Consumed > reserved → FAIL ──
def test_consumed_exceeds_reserved_fails(db_connection, test_session_id):
    _insert_telemetry(db_connection, test_session_id, hours=Decimal("110.000000"))
    _insert_cost(db_connection, test_session_id, reserved=Decimal("100.000000"))
    result = execute_check1(db_connection, test_session_id)
    assert result.verdict == "FAIL"


# ── C1-03: FAIL record contains all fields ──
def test_fail_record_has_fields(db_connection, test_session_id):
    _insert_telemetry(db_connection, test_session_id, hours=Decimal("110.000000"))
    _insert_cost(db_connection, test_session_id, reserved=Decimal("100.000000"))
    result = execute_check1(db_connection, test_session_id)
    rec = result.failing_records[0]
    assert rec.region == "us-east"
    assert rec.gpu_pool_id == "pool-a"
    assert rec.date == date(2026, 3, 15)
    assert rec.consumed == Decimal("110.000000")
    assert rec.reserved == Decimal("100.000000")


# ── C1-04: excess = consumed − reserved ──
def test_excess_calculation(db_connection, test_session_id):
    _insert_telemetry(db_connection, test_session_id, hours=Decimal("115.000000"))
    _insert_cost(db_connection, test_session_id, reserved=Decimal("100.000000"))
    result = execute_check1(db_connection, test_session_id)
    assert result.failing_records[0].excess == Decimal("15.000000")


# ── C1-05: No cost_management row for telemetry grain → FAIL ──
def test_missing_cost_row_fails(db_connection, test_session_id):
    _insert_telemetry(db_connection, test_session_id, region="ap-south")
    _insert_cost(db_connection, test_session_id, region="us-east")
    result = execute_check1(db_connection, test_session_id)
    assert result.verdict == "FAIL"
    assert any(r.region == "ap-south" for r in result.failing_records)


# ── C1-06: Multiple grains, one failing → failing_count = 1 ──
def test_multiple_grains_one_failing(db_connection, test_session_id):
    _insert_telemetry(db_connection, test_session_id, pool="pool-a", hours=Decimal("60.000000"))
    _insert_cost(db_connection, test_session_id, pool="pool-a", reserved=Decimal("100.000000"))
    _insert_telemetry(db_connection, test_session_id, pool="pool-b", hours=Decimal("110.000000"))
    _insert_cost(db_connection, test_session_id, pool="pool-b", reserved=Decimal("100.000000"))
    result = execute_check1(db_connection, test_session_id)
    assert result.verdict == "FAIL"
    assert result.failing_count == 1
    assert result.failing_records[0].gpu_pool_id == "pool-b"


# ── C1-07: Multiple grains, all passing → PASS ──
def test_multiple_grains_all_pass(db_connection, test_session_id):
    _insert_telemetry(db_connection, test_session_id, pool="pool-a", hours=Decimal("60.000000"))
    _insert_cost(db_connection, test_session_id, pool="pool-a", reserved=Decimal("100.000000"))
    _insert_telemetry(db_connection, test_session_id, pool="pool-b", hours=Decimal("40.000000"))
    _insert_cost(db_connection, test_session_id, pool="pool-b", reserved=Decimal("100.000000"))
    result = execute_check1(db_connection, test_session_id)
    assert result.verdict == "PASS"


# ── C1-08: Empty telemetry → FAIL with detail ──
def test_empty_telemetry_fails(db_connection, test_session_id):
    _insert_cost(db_connection, test_session_id)
    result = execute_check1(db_connection, test_session_id)
    assert result.verdict == "FAIL"
    assert "telemetry" in result.detail.lower()


# ── C1-09: Empty cost_management → FAIL with detail ──
def test_empty_cost_management_fails(db_connection, test_session_id):
    _insert_telemetry(db_connection, test_session_id)
    result = execute_check1(db_connection, test_session_id)
    assert result.verdict == "FAIL"
    assert "cost_management" in result.detail.lower()
