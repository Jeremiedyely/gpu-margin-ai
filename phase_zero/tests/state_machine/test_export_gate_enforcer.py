"""
Tests for Export Gate Enforcer — Component 11/12.

DB integration tests. Validates the four-path gate evaluation
and the P1 #27 NULL-before-not-SUCCESS ordering.

Assertions: EGE-01 through EGE-12
"""

from __future__ import annotations

from uuid import uuid4

from app.state_machine.export_gate_enforcer import (
    GateResponse,
    check_export_gate,
)
from app.state_machine.state_store import StateWriteRequest, write_state


# ── Helpers ─────────────────────────────────────────────────────────

def _to_uploaded(conn, sid):
    write_state(conn, StateWriteRequest(
        new_state="UPLOADED", analysis_status="IDLE",
        trigger="INGESTION_COMPLETE", session_id=sid,
    ))


def _to_analyzed(conn, sid):
    _to_uploaded(conn, sid)
    write_state(conn, StateWriteRequest(
        new_state="ANALYZED", trigger="ENGINES_COMPLETE",
        session_id=sid,
    ))


def _to_approved_success(conn, sid):
    _to_analyzed(conn, sid)
    write_state(conn, StateWriteRequest(
        new_state="APPROVED", trigger="CFO_APPROVAL",
        session_id=sid, write_result="SUCCESS",
    ))


def _to_approved_fail(conn, sid):
    _to_analyzed(conn, sid)
    write_state(conn, StateWriteRequest(
        new_state="APPROVED", trigger="CFO_APPROVAL",
        session_id=sid, write_result="FAIL",
    ))


# ── EGE-01: APPROVED + SUCCESS → OPEN ───────────────────────────────

def test_approved_success_opens_gate(db_connection, test_session_id):
    sid = test_session_id
    _to_approved_success(db_connection, sid)
    resp = check_export_gate(db_connection, sid)
    assert resp.result == "OPEN"                               # EGE-01a
    assert resp.reason_code == "GATE_OPEN"                     # EGE-01b


# ── EGE-02: EMPTY state → BLOCKED NOT_APPROVED ──────────────────────

def test_empty_state_blocked(db_connection, test_session_id):
    sid = test_session_id
    # State Store row doesn't exist yet — write EMPTY first
    write_state(db_connection, StateWriteRequest(
        new_state="EMPTY", trigger="SYSTEM_RECOVERY",
        session_id=sid,
    ))
    resp = check_export_gate(db_connection, sid)
    assert resp.result == "BLOCKED"                            # EGE-02a
    assert resp.reason_code == "GATE_BLOCKED_NOT_APPROVED"     # EGE-02b


# ── EGE-03: UPLOADED state → BLOCKED NOT_APPROVED ───────────────────

def test_uploaded_state_blocked(db_connection, test_session_id):
    sid = test_session_id
    _to_uploaded(db_connection, sid)
    resp = check_export_gate(db_connection, sid)
    assert resp.result == "BLOCKED"                            # EGE-03a
    assert resp.reason_code == "GATE_BLOCKED_NOT_APPROVED"     # EGE-03b


# ── EGE-04: ANALYZED state → BLOCKED NOT_APPROVED ───────────────────

def test_analyzed_state_blocked(db_connection, test_session_id):
    sid = test_session_id
    _to_analyzed(db_connection, sid)
    resp = check_export_gate(db_connection, sid)
    assert resp.result == "BLOCKED"                            # EGE-04a
    assert resp.reason_code == "GATE_BLOCKED_NOT_APPROVED"     # EGE-04b


# ── EGE-05: APPROVED + write_result=FAIL → BLOCKED WRITE_FAILED ─────

def test_approved_fail_blocked(db_connection, test_session_id):
    sid = test_session_id
    _to_approved_fail(db_connection, sid)
    resp = check_export_gate(db_connection, sid)
    assert resp.result == "BLOCKED"                            # EGE-05a
    assert resp.reason_code == "GATE_BLOCKED_WRITE_FAILED"     # EGE-05b


# ── EGE-06: No state row → BLOCKED STATE_UNREADABLE ─────────────────

def test_no_state_row_blocked(db_connection, test_session_id):
    sid = test_session_id
    # Don't write any state — read_state returns None
    resp = check_export_gate(db_connection, sid)
    assert resp.result == "BLOCKED"                            # EGE-06a
    assert resp.reason_code == "GATE_BLOCKED_STATE_UNREADABLE" # EGE-06b


# ── EGE-07: OPEN gate preserves session_id ───────────────────────────

def test_open_gate_session_id(db_connection, test_session_id):
    sid = test_session_id
    _to_approved_success(db_connection, sid)
    resp = check_export_gate(db_connection, sid)
    assert resp.session_id == sid                              # EGE-07


# ── EGE-08: BLOCKED gate preserves session_id ────────────────────────

def test_blocked_gate_session_id(db_connection, test_session_id):
    sid = test_session_id
    _to_uploaded(db_connection, sid)
    resp = check_export_gate(db_connection, sid)
    assert resp.session_id == sid                              # EGE-08


# ── EGE-09: NOT_APPROVED reason includes current state ───────────────

def test_not_approved_reason_includes_state(db_connection, test_session_id):
    sid = test_session_id
    _to_uploaded(db_connection, sid)
    resp = check_export_gate(db_connection, sid)
    assert "UPLOADED" in resp.reason                           # EGE-09


# ── EGE-10: OPEN gate has no reason text ─────────────────────────────

def test_open_gate_no_reason(db_connection, test_session_id):
    sid = test_session_id
    _to_approved_success(db_connection, sid)
    resp = check_export_gate(db_connection, sid)
    assert resp.reason is None                                 # EGE-10


# ── EGE-11: WRITE_FAILED reason text correct ────────────────────────

def test_write_failed_reason(db_connection, test_session_id):
    sid = test_session_id
    _to_approved_fail(db_connection, sid)
    resp = check_export_gate(db_connection, sid)
    assert "not confirmed" in resp.reason                      # EGE-11


# ── EGE-12: Gate evaluation is idempotent ────────────────────────────

def test_gate_idempotent(db_connection, test_session_id):
    sid = test_session_id
    _to_approved_success(db_connection, sid)
    r1 = check_export_gate(db_connection, sid)
    r2 = check_export_gate(db_connection, sid)
    assert r1.result == r2.result == "OPEN"                    # EGE-12
