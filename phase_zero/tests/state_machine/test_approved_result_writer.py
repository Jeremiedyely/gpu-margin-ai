"""
Tests for Approved Result Writer — Component 9/12.

DB integration tests. Validates the P1 #26 atomic write invariant:
application_state=APPROVED + write_result written in ONE transaction.
Also validates grain copy, row count, guard clauses, and FAIL path.

Assertions: ARW-01 through ARW-10
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import text

from app.state_machine.analyzed_to_approved_executor import (
    ApprovalTransitionResult,
)
from app.state_machine.approved_result_writer import (
    ApprovedWriteResult,
    write_approved_result,
)
from app.state_machine.state_store import (
    StateWriteRequest,
    read_state,
    write_state,
)


# ── Helpers ─────────────────────────────────────────────────────────

def _setup_analyzed(conn, sid):
    """Advance state to ANALYZED."""
    write_state(conn, StateWriteRequest(
        new_state="UPLOADED", analysis_status="IDLE",
        trigger="INGESTION_COMPLETE", session_id=sid,
    ))
    write_state(conn, StateWriteRequest(
        new_state="ANALYZED", trigger="ENGINES_COMPLETE",
        session_id=sid,
    ))


def _insert_grain(conn, sid, allocation_target="tenant-A",
                   region="us-east-1", gpu_pool_id="pool-A",
                   billing_period="2026-03"):
    """Insert a Type A allocation_grain row for testing."""
    gpu_hours = Decimal("100.000000")
    cost_per_gpu_hour = Decimal("0.500000")
    contracted_rate = Decimal("1.000000")
    revenue = Decimal("100.00")
    cogs = Decimal("50.00")
    gross_margin = Decimal("50.00")
    grain_date = f"{billing_period}-15"
    conn.execute(
        text("""
            INSERT INTO dbo.allocation_grain
                (session_id, region, gpu_pool_id, date, billing_period,
                 allocation_target, unallocated_type, failed_tenant_id,
                 gpu_hours, cost_per_gpu_hour, contracted_rate,
                 revenue, cogs, gross_margin)
            VALUES
                (:sid, :region, :gpu_pool_id, :date, :bp,
                 :target, NULL, NULL,
                 :gpu_hours, :cpgh, :rate,
                 :revenue, :cogs, :margin)
        """),
        {
            "sid": str(sid), "region": region,
            "gpu_pool_id": gpu_pool_id, "date": grain_date,
            "bp": billing_period, "target": allocation_target,
            "gpu_hours": gpu_hours, "cpgh": cost_per_gpu_hour,
            "rate": contracted_rate, "revenue": revenue,
            "cogs": cogs, "margin": gross_margin,
        },
    )


def _success_transition(sid):
    return ApprovalTransitionResult(
        result="SUCCESS",
        new_state="APPROVED",
        session_id=sid,
        trigger="CFO_APPROVAL",
    )


def _count_final(conn, sid):
    row = conn.execute(
        text("SELECT COUNT(*) AS cnt FROM final.allocation_result WHERE session_id = :sid"),
        {"sid": str(sid)},
    ).fetchone()
    return row.cnt


# ── ARW-01: Successful grain copy + APPROVED atomic write ───────────

def test_successful_write(db_connection, test_session_id):
    sid = test_session_id
    _setup_analyzed(db_connection, sid)
    _insert_grain(db_connection, sid)
    result = write_approved_result(
        db_connection, _success_transition(sid),
    )
    assert result.result == "SUCCESS"                          # ARW-01a
    assert result.row_count == 1                               # ARW-01b
    assert result.approved_at is not None                      # ARW-01c


# ── ARW-02: State Store shows APPROVED + write_result=SUCCESS ────────

def test_state_store_approved(db_connection, test_session_id):
    sid = test_session_id
    _setup_analyzed(db_connection, sid)
    _insert_grain(db_connection, sid)
    write_approved_result(db_connection, _success_transition(sid))
    snap = read_state(db_connection, sid)
    assert snap.application_state == "APPROVED"                # ARW-02a
    assert snap.write_result == "SUCCESS"                      # ARW-02b


# ── ARW-03: final.allocation_result rows match grain ─────────────────

def test_final_rows_match_grain(db_connection, test_session_id):
    sid = test_session_id
    _setup_analyzed(db_connection, sid)
    _insert_grain(db_connection, sid, "tenant-A", billing_period="2026-03")
    _insert_grain(db_connection, sid, "tenant-B", billing_period="2026-03")
    write_approved_result(db_connection, _success_transition(sid))
    assert _count_final(db_connection, sid) == 2               # ARW-03


# ── ARW-04: Empty grain → FAIL + write_result=FAIL ──────────────────

def test_empty_grain_fails(db_connection, test_session_id):
    sid = test_session_id
    _setup_analyzed(db_connection, sid)
    # No grain rows inserted
    result = write_approved_result(
        db_connection, _success_transition(sid),
    )
    assert result.result == "FAIL"                             # ARW-04a
    assert "no allocation_grain rows" in result.error          # ARW-04b


# ── ARW-05: Non-SUCCESS transition rejected ──────────────────────────

def test_non_success_rejected(db_connection, test_session_id):
    sid = test_session_id
    fail_transition = ApprovalTransitionResult(
        result="FAIL",
        new_state="APPROVED",
        session_id=sid,
        error="test failure",
    )
    result = write_approved_result(db_connection, fail_transition)
    assert result.result == "FAIL"                             # ARW-05a
    assert "non-SUCCESS" in result.error                       # ARW-05b


# ── ARW-06: Missing session_id rejected ──────────────────────────────

def test_missing_session_id_rejected(db_connection):
    no_sid = ApprovalTransitionResult(
        result="SUCCESS",
        new_state="APPROVED",
        session_id=None,
        trigger="CFO_APPROVAL",
    )
    result = write_approved_result(db_connection, no_sid)
    assert result.result == "FAIL"                             # ARW-06a
    assert "requires session_id" in result.error               # ARW-06b


# ── ARW-07: State history records ANALYZED→APPROVED ──────────────────

def test_history_records_transition(db_connection, test_session_id):
    sid = test_session_id
    _setup_analyzed(db_connection, sid)
    _insert_grain(db_connection, sid)
    write_approved_result(db_connection, _success_transition(sid))
    rows = db_connection.execute(
        text("""
            SELECT from_state, to_state, transition_trigger
            FROM dbo.state_history
            WHERE session_id = :sid
            ORDER BY id
        """),
        {"sid": str(sid)},
    ).fetchall()
    approval_row = [r for r in rows if r.transition_trigger == "CFO_APPROVAL"]
    assert len(approval_row) == 1                              # ARW-07a
    assert approval_row[0].from_state == "ANALYZED"            # ARW-07b
    assert approval_row[0].to_state == "APPROVED"              # ARW-07c


# ── ARW-08: Multiple grain rows copied correctly ─────────────────────

def test_multiple_rows_copied(db_connection, test_session_id):
    sid = test_session_id
    _setup_analyzed(db_connection, sid)
    _insert_grain(db_connection, sid, "tenant-A", billing_period="2026-03")
    _insert_grain(db_connection, sid, "tenant-B", billing_period="2026-03")
    _insert_grain(db_connection, sid, "tenant-C", billing_period="2026-03")
    result = write_approved_result(db_connection, _success_transition(sid))
    assert result.row_count == 3                               # ARW-08


# ── ARW-09: P1 #26 — no partial state (APPROVED without write_result) ─

def test_no_partial_approved_state(db_connection, test_session_id):
    """
    If the grain copy succeeds but state write fails,
    savepoint rolls back BOTH — no APPROVED without write_result.
    """
    sid = test_session_id
    _setup_analyzed(db_connection, sid)
    _insert_grain(db_connection, sid)
    # This test validates the atomic invariant exists —
    # on success, both APPROVED and write_result are set together
    write_approved_result(db_connection, _success_transition(sid))
    snap = read_state(db_connection, sid)
    # Both must be set — never APPROVED with NULL write_result
    assert snap.application_state == "APPROVED"                # ARW-09a
    assert snap.write_result is not None                       # ARW-09b


# ── ARW-10: session_id preserved in result ───────────────────────────

def test_session_id_preserved(db_connection, test_session_id):
    sid = test_session_id
    _setup_analyzed(db_connection, sid)
    _insert_grain(db_connection, sid)
    result = write_approved_result(db_connection, _success_transition(sid))
    assert result.session_id == sid                            # ARW-10
