"""
Tests for APPROVED Session Closer — Component 12/12.

DB integration tests. Validates terminal write, guard clauses,
and session_status persistence.

Assertions: SC-01 through SC-10
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text

from app.state_machine.approved_result_writer import ApprovedWriteResult
from app.state_machine.session_closer import (
    CLOSER_MAX_RETRIES,
    CLOSER_RETRY_INTERVAL,
    CloserResult,
    close_session,
)
from app.state_machine.state_store import (
    StateWriteRequest,
    read_state,
    write_state,
)


# ── Helpers ─────────────────────────────────────────────────────────

def _to_approved_success(conn, sid):
    """Advance state to APPROVED with write_result=SUCCESS."""
    write_state(conn, StateWriteRequest(
        new_state="UPLOADED", analysis_status="IDLE",
        trigger="INGESTION_COMPLETE", session_id=sid,
    ))
    write_state(conn, StateWriteRequest(
        new_state="ANALYZED", trigger="ENGINES_COMPLETE",
        session_id=sid,
    ))
    write_state(conn, StateWriteRequest(
        new_state="APPROVED", trigger="CFO_APPROVAL",
        session_id=sid, write_result="SUCCESS",
    ))


def _success_write_result(sid):
    return ApprovedWriteResult(
        result="SUCCESS",
        session_id=sid,
        approved_at=datetime.now(timezone.utc),
        row_count=1,
    )


# ── SC-01: Successful session close ─────────────────────────────────

def test_successful_close(db_connection, test_session_id):
    sid = test_session_id
    _to_approved_success(db_connection, sid)
    result = close_session(db_connection, _success_write_result(sid))
    assert result.result == "SUCCESS"                          # SC-01a
    assert result.terminal_at is not None                      # SC-01b


# ── SC-02: session_status = TERMINAL in State Store ──────────────────

def test_session_status_terminal(db_connection, test_session_id):
    sid = test_session_id
    _to_approved_success(db_connection, sid)
    close_session(db_connection, _success_write_result(sid))
    snap = read_state(db_connection, sid)
    assert snap.session_status == "TERMINAL"                   # SC-02


# ── SC-03: State history records SESSION_CLOSED ──────────────────────

def test_history_records_session_closed(db_connection, test_session_id):
    sid = test_session_id
    _to_approved_success(db_connection, sid)
    close_session(db_connection, _success_write_result(sid))
    rows = db_connection.execute(
        text("""
            SELECT transition_trigger
            FROM dbo.state_history
            WHERE session_id = :sid
            ORDER BY id
        """),
        {"sid": str(sid)},
    ).fetchall()
    triggers = [r.transition_trigger for r in rows]
    assert "SESSION_CLOSED" in triggers                        # SC-03


# ── SC-04: Non-SUCCESS write_result rejected ─────────────────────────

def test_non_success_rejected(db_connection, test_session_id):
    sid = test_session_id
    fail_wr = ApprovedWriteResult(
        result="FAIL",
        session_id=sid,
        error="test failure",
    )
    result = close_session(db_connection, fail_wr)
    assert result.result == "FAIL"                             # SC-04a
    assert "non-SUCCESS" in result.error                       # SC-04b


# ── SC-05: Missing session_id rejected ───────────────────────────────

def test_missing_session_id_rejected(db_connection):
    no_sid = ApprovedWriteResult(
        result="SUCCESS",
        session_id=None,
        approved_at=datetime.now(timezone.utc),
        row_count=1,
    )
    result = close_session(db_connection, no_sid)
    assert result.result == "FAIL"                             # SC-05a
    assert "requires session_id" in result.error               # SC-05b


# ── SC-06: session_id preserved in result ────────────────────────────

def test_session_id_preserved(db_connection, test_session_id):
    sid = test_session_id
    _to_approved_success(db_connection, sid)
    result = close_session(db_connection, _success_write_result(sid))
    assert result.session_id == sid                            # SC-06


# ── SC-07: application_state remains APPROVED after close ────────────

def test_state_remains_approved(db_connection, test_session_id):
    sid = test_session_id
    _to_approved_success(db_connection, sid)
    close_session(db_connection, _success_write_result(sid))
    snap = read_state(db_connection, sid)
    assert snap.application_state == "APPROVED"                # SC-07


# ── SC-08: Retry constants have expected defaults ────────────────────

def test_retry_constants():
    assert CLOSER_RETRY_INTERVAL == 60                         # SC-08a
    assert CLOSER_MAX_RETRIES == 5                             # SC-08b
