"""
Tests for Check 2 Executor — Usage vs Tenant Mapping — Component 2/7.

C2-01  All tenants resolved → PASS
C2-02  One tenant unresolved → FAIL
C2-03  Unresolved pair contains tenant_id and billing_period
C2-04  billing_period derived via shared module (Contract 1)
C2-05  Multiple tenants, one unresolved → failing_count = 1
C2-06  Multiple tenants, all unresolved → failing_count = N
C2-07  Same tenant, different billing_periods — both must resolve
C2-08  Empty telemetry → FAIL with detail
C2-09  session_id filter — only current session rows checked
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from app.reconciliation.check2_executor import execute_check2
from app.shared.billing_period import derive_billing_period


def _insert_telemetry(conn, sid, tenant="T1", d=date(2026, 3, 15),
                      region="us-east", pool="pool-a",
                      hours=Decimal("10.000000")):
    conn.execute(
        text("""
            INSERT INTO raw.telemetry
                (session_id, tenant_id, region, gpu_pool_id, date, gpu_hours_consumed)
            VALUES (:sid, :tid, :region, :pool, :d, :hours)
        """),
        {"sid": str(sid), "tid": tenant, "region": region,
         "pool": pool, "d": d, "hours": hours},
    )


def _insert_iam(conn, sid, tenant="T1", bp="2026-03",
                rate=Decimal("5.000000")):
    conn.execute(
        text("""
            INSERT INTO raw.iam
                (session_id, tenant_id, billing_period, contracted_rate)
            VALUES (:sid, :tid, :bp, :rate)
        """),
        {"sid": str(sid), "tid": tenant, "bp": bp, "rate": rate},
    )


# ── C2-01: All tenants resolved → PASS ──
def test_all_resolved_passes(db_connection, test_session_id):
    _insert_telemetry(db_connection, test_session_id, tenant="T1")
    _insert_iam(db_connection, test_session_id, tenant="T1", bp="2026-03")
    result = execute_check2(db_connection, test_session_id)
    assert result.verdict == "PASS"


# ── C2-02: One tenant unresolved → FAIL ──
def test_one_unresolved_fails(db_connection, test_session_id):
    _insert_telemetry(db_connection, test_session_id, tenant="T1")
    # No IAM row for T1
    result = execute_check2(db_connection, test_session_id)
    assert result.verdict == "FAIL"


# ── C2-03: Unresolved pair contains tenant_id and billing_period ──
def test_unresolved_pair_fields(db_connection, test_session_id):
    _insert_telemetry(db_connection, test_session_id, tenant="GHOST",
                      d=date(2026, 4, 10))
    result = execute_check2(db_connection, test_session_id)
    pair = result.unresolved_pairs[0]
    assert pair.tenant_id == "GHOST"
    assert pair.billing_period == "2026-04"


# ── C2-04: billing_period derived via shared module ──
def test_billing_period_from_shared_module(db_connection, test_session_id):
    d = date(2026, 11, 20)
    expected_bp = derive_billing_period(d)
    _insert_telemetry(db_connection, test_session_id, tenant="T1", d=d)
    _insert_iam(db_connection, test_session_id, tenant="T1", bp=expected_bp)
    result = execute_check2(db_connection, test_session_id)
    assert result.verdict == "PASS"


# ── C2-05: Multiple tenants, one unresolved → failing_count = 1 ──
def test_multiple_tenants_one_unresolved(db_connection, test_session_id):
    _insert_telemetry(db_connection, test_session_id, tenant="T1")
    _insert_telemetry(db_connection, test_session_id, tenant="T2")
    _insert_iam(db_connection, test_session_id, tenant="T1", bp="2026-03")
    # No IAM for T2
    result = execute_check2(db_connection, test_session_id)
    assert result.verdict == "FAIL"
    assert result.failing_count == 1
    assert result.unresolved_pairs[0].tenant_id == "T2"


# ── C2-06: Multiple tenants, all unresolved → failing_count = N ──
def test_multiple_tenants_all_unresolved(db_connection, test_session_id):
    _insert_telemetry(db_connection, test_session_id, tenant="T1")
    _insert_telemetry(db_connection, test_session_id, tenant="T2")
    result = execute_check2(db_connection, test_session_id)
    assert result.verdict == "FAIL"
    assert result.failing_count == 2


# ── C2-07: Same tenant, different billing_periods — both must resolve ──
def test_same_tenant_different_periods(db_connection, test_session_id):
    _insert_telemetry(db_connection, test_session_id, tenant="T1",
                      d=date(2026, 3, 15))
    _insert_telemetry(db_connection, test_session_id, tenant="T1",
                      d=date(2026, 4, 10))
    _insert_iam(db_connection, test_session_id, tenant="T1", bp="2026-03")
    # No IAM for T1 + 2026-04
    result = execute_check2(db_connection, test_session_id)
    assert result.verdict == "FAIL"
    assert result.failing_count == 1
    assert result.unresolved_pairs[0].billing_period == "2026-04"


# ── C2-08: Empty telemetry → FAIL with detail ──
def test_empty_telemetry_fails(db_connection, test_session_id):
    result = execute_check2(db_connection, test_session_id)
    assert result.verdict == "FAIL"
    assert "telemetry" in result.detail.lower()


# ── C2-09: session_id filter — only current session checked ──
def test_session_id_filter(db_connection, test_session_id):
    # Insert telemetry for current session
    _insert_telemetry(db_connection, test_session_id, tenant="T1")
    _insert_iam(db_connection, test_session_id, tenant="T1", bp="2026-03")

    # Insert unresolved telemetry for a DIFFERENT session
    other_sid = uuid.uuid4()
    db_connection.execute(
        text("""
            INSERT INTO raw.ingestion_log (session_id, source_files, status)
            VALUES (:sid, :sf, 'COMMITTED')
        """),
        {"sid": str(other_sid), "sf": '["other.csv"]'},
    )
    _insert_telemetry(db_connection, other_sid, tenant="GHOST")

    # Current session should PASS — other session's data ignored
    result = execute_check2(db_connection, test_session_id)
    assert result.verdict == "PASS"
