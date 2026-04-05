"""
Tests for State Store — Component 1/12.

DB integration tests. Validates atomic state + history writes,
trigger validation, read_state, retry_count operations, and
constraint enforcement.

Assertions: SS-01 through SS-16
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text

from app.state_machine.state_store import (
    StateSnapshot,
    StateWriteRequest,
    StoreWriteResult,
    increment_retry_count,
    read_state,
    reset_retry_count,
    write_state,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _read_history(conn, sid):
    """Read state_history rows for a session, ordered by id."""
    return conn.execute(
        text("""
            SELECT from_state, to_state, transition_trigger, transitioned_at
            FROM dbo.state_history
            WHERE session_id = :sid
            ORDER BY id
        """),
        {"sid": str(sid)},
    ).fetchall()


def _read_store(conn, sid):
    """Read state_store row for a session."""
    return conn.execute(
        text("""
            SELECT application_state, session_status, analysis_status,
                   write_result, retry_count
            FROM dbo.state_store
            WHERE session_id = :sid
        """),
        {"sid": str(sid)},
    ).fetchone()


# ── SS-01: First write creates state_store row ──────────────────────

def test_first_write_creates_row(db_connection, test_session_id):
    sid = test_session_id
    req = StateWriteRequest(
        new_state="UPLOADED",
        analysis_status="IDLE",
        trigger="INGESTION_COMPLETE",
        session_id=sid,
    )
    result = write_state(db_connection, req)
    assert result.result == "SUCCESS"                          # SS-01a
    row = _read_store(db_connection, sid)
    assert row is not None                                     # SS-01b
    assert row.application_state == "UPLOADED"                 # SS-01c


# ── SS-02: State_history appended atomically ─────────────────────────

def test_history_appended(db_connection, test_session_id):
    sid = test_session_id
    req = StateWriteRequest(
        new_state="UPLOADED",
        analysis_status="IDLE",
        trigger="INGESTION_COMPLETE",
        session_id=sid,
    )
    write_state(db_connection, req)
    history = _read_history(db_connection, sid)
    assert len(history) == 1                                   # SS-02a
    assert history[0].from_state == "EMPTY"                    # SS-02b
    assert history[0].to_state == "UPLOADED"                   # SS-02c
    assert history[0].transition_trigger == "INGESTION_COMPLETE"  # SS-02d


# ── SS-03: read_state returns snapshot after write ───────────────────

def test_read_state_after_write(db_connection, test_session_id):
    sid = test_session_id
    req = StateWriteRequest(
        new_state="UPLOADED",
        analysis_status="IDLE",
        trigger="INGESTION_COMPLETE",
        session_id=sid,
    )
    write_state(db_connection, req)
    snap = read_state(db_connection, sid)
    assert snap is not None                                    # SS-03a
    assert snap.application_state == "UPLOADED"                # SS-03b
    assert snap.session_status == "ACTIVE"                     # SS-03c
    assert snap.analysis_status == "IDLE"                      # SS-03d
    assert snap.write_result is None                           # SS-03e
    assert snap.retry_count == 0                               # SS-03f


# ── SS-04: read_state returns None for unknown session ───────────────

def test_read_state_unknown_session(db_connection):
    snap = read_state(db_connection, uuid4())
    assert snap is None                                        # SS-04


# ── SS-05: Invalid trigger rejected ─────────────────────────────────

def test_invalid_trigger_rejected(db_connection, test_session_id):
    sid = test_session_id
    req = StateWriteRequest(
        new_state="UPLOADED",
        analysis_status="IDLE",
        trigger="INVALID_TRIGGER",
        session_id=sid,
    )
    result = write_state(db_connection, req)
    assert result.result == "FAIL"                             # SS-05a
    assert "not in enumerated set" in result.error             # SS-05b
    # No row written
    row = _read_store(db_connection, sid)
    assert row is None                                         # SS-05c


# ── SS-06: Empty trigger rejected ───────────────────────────────────

def test_empty_trigger_rejected(db_connection, test_session_id):
    sid = test_session_id
    req = StateWriteRequest(
        new_state="UPLOADED",
        analysis_status="IDLE",
        trigger="",
        session_id=sid,
    )
    result = write_state(db_connection, req)
    assert result.result == "FAIL"                             # SS-06a
    assert "not in enumerated set" in result.error             # SS-06b


# ── SS-07: Sequential transitions build history ──────────────────────

def test_sequential_transitions(db_connection, test_session_id):
    sid = test_session_id
    # EMPTY → UPLOADED
    write_state(db_connection, StateWriteRequest(
        new_state="UPLOADED", analysis_status="IDLE",
        trigger="INGESTION_COMPLETE", session_id=sid,
    ))
    # UPLOADED → ANALYZED
    write_state(db_connection, StateWriteRequest(
        new_state="ANALYZED", analysis_status=None,
        trigger="ENGINES_COMPLETE", session_id=sid,
    ))
    history = _read_history(db_connection, sid)
    assert len(history) == 2                                   # SS-07a
    assert history[0].from_state == "EMPTY"                    # SS-07b
    assert history[0].to_state == "UPLOADED"                   # SS-07c
    assert history[1].from_state == "UPLOADED"                 # SS-07d
    assert history[1].to_state == "ANALYZED"                   # SS-07e


# ── SS-08: APPROVED + write_result atomic write ──────────────────────

def test_approved_atomic_write(db_connection, test_session_id):
    sid = test_session_id
    # Setup: EMPTY → UPLOADED → ANALYZED
    write_state(db_connection, StateWriteRequest(
        new_state="UPLOADED", analysis_status="IDLE",
        trigger="INGESTION_COMPLETE", session_id=sid,
    ))
    write_state(db_connection, StateWriteRequest(
        new_state="ANALYZED", analysis_status=None,
        trigger="ENGINES_COMPLETE", session_id=sid,
    ))
    # ANALYZED → APPROVED with write_result (P1 #26)
    write_state(db_connection, StateWriteRequest(
        new_state="APPROVED", analysis_status=None,
        trigger="CFO_APPROVAL", session_id=sid,
        write_result="SUCCESS",
    ))
    row = _read_store(db_connection, sid)
    assert row.application_state == "APPROVED"                 # SS-08a
    assert row.write_result == "SUCCESS"                       # SS-08b


# ── SS-09: session_status = TERMINAL write ───────────────────────────

def test_terminal_write(db_connection, test_session_id):
    sid = test_session_id
    # Setup: full lifecycle to APPROVED
    write_state(db_connection, StateWriteRequest(
        new_state="UPLOADED", analysis_status="IDLE",
        trigger="INGESTION_COMPLETE", session_id=sid,
    ))
    write_state(db_connection, StateWriteRequest(
        new_state="ANALYZED", analysis_status=None,
        trigger="ENGINES_COMPLETE", session_id=sid,
    ))
    write_state(db_connection, StateWriteRequest(
        new_state="APPROVED", analysis_status=None,
        trigger="CFO_APPROVAL", session_id=sid,
        write_result="SUCCESS",
    ))
    # Close session
    write_state(db_connection, StateWriteRequest(
        new_state="APPROVED", analysis_status=None,
        trigger="SESSION_CLOSED", session_id=sid,
        session_status="TERMINAL",
        write_result="SUCCESS",
    ))
    row = _read_store(db_connection, sid)
    assert row.session_status == "TERMINAL"                    # SS-09a
    assert row.application_state == "APPROVED"                 # SS-09b


# ── SS-10: increment_retry_count ─────────────────────────────────────

def test_increment_retry_count(db_connection, test_session_id):
    sid = test_session_id
    # Setup: create state row
    write_state(db_connection, StateWriteRequest(
        new_state="UPLOADED", analysis_status="IDLE",
        trigger="INGESTION_COMPLETE", session_id=sid,
    ))
    assert _read_store(db_connection, sid).retry_count == 0    # SS-10a
    increment_retry_count(db_connection, sid)
    assert _read_store(db_connection, sid).retry_count == 1    # SS-10b
    increment_retry_count(db_connection, sid)
    assert _read_store(db_connection, sid).retry_count == 2    # SS-10c


# ── SS-11: reset_retry_count ────────────────────────────────────────

def test_reset_retry_count(db_connection, test_session_id):
    sid = test_session_id
    write_state(db_connection, StateWriteRequest(
        new_state="UPLOADED", analysis_status="IDLE",
        trigger="INGESTION_COMPLETE", session_id=sid,
    ))
    increment_retry_count(db_connection, sid)
    increment_retry_count(db_connection, sid)
    assert _read_store(db_connection, sid).retry_count == 2    # SS-11a
    reset_retry_count(db_connection, sid)
    assert _read_store(db_connection, sid).retry_count == 0    # SS-11b


# ── SS-12: analysis_status = ANALYZING only valid for UPLOADED ───────

def test_analyzing_requires_uploaded(db_connection, test_session_id):
    sid = test_session_id
    # Setup: advance to ANALYZED (analysis_status = None)
    write_state(db_connection, StateWriteRequest(
        new_state="UPLOADED", analysis_status="IDLE",
        trigger="INGESTION_COMPLETE", session_id=sid,
    ))
    write_state(db_connection, StateWriteRequest(
        new_state="ANALYZED", analysis_status=None,
        trigger="ENGINES_COMPLETE", session_id=sid,
    ))
    # Try to set ANALYZING on ANALYZED state — should FAIL (CHK_state_analysis_status_scope)
    result = write_state(db_connection, StateWriteRequest(
        new_state="ANALYZED", analysis_status="ANALYZING",
        trigger="SYSTEM_RECOVERY", session_id=sid,
    ))
    assert result.result == "FAIL"                             # SS-12a
    assert "State persist failed" in result.error              # SS-12b


# ── SS-13: APPROVED without write_result rejected ────────────────────

def test_approved_without_write_result_rejected(db_connection, test_session_id):
    sid = test_session_id
    write_state(db_connection, StateWriteRequest(
        new_state="UPLOADED", analysis_status="IDLE",
        trigger="INGESTION_COMPLETE", session_id=sid,
    ))
    write_state(db_connection, StateWriteRequest(
        new_state="ANALYZED", analysis_status=None,
        trigger="ENGINES_COMPLETE", session_id=sid,
    ))
    # APPROVED without write_result → CHK_state_approved_requires_write_result
    result = write_state(db_connection, StateWriteRequest(
        new_state="APPROVED", analysis_status=None,
        trigger="CFO_APPROVAL", session_id=sid,
    ))
    assert result.result == "FAIL"                             # SS-13a
    assert "State persist failed" in result.error              # SS-13b


# ── SS-14: Self-transition skips history (except SYSTEM_RECOVERY) ────

def test_self_transition_skips_history(db_connection, test_session_id):
    sid = test_session_id
    write_state(db_connection, StateWriteRequest(
        new_state="UPLOADED", analysis_status="IDLE",
        trigger="INGESTION_COMPLETE", session_id=sid,
    ))
    # UPLOADED → UPLOADED with non-recovery trigger — metadata-only update
    # State Store MERGE executes, but history append is skipped to respect
    # CHK_history_no_self_transition.
    result = write_state(db_connection, StateWriteRequest(
        new_state="UPLOADED", analysis_status="IDLE",
        trigger="ANALYSIS_DISPATCHED", session_id=sid,
    ))
    assert result.result == "SUCCESS"                          # SS-14a
    # Only one history entry (the original INGESTION_COMPLETE), not two
    history = _read_history(db_connection, sid)
    assert len(history) == 1                                   # SS-14b
    assert history[0].transition_trigger == "INGESTION_COMPLETE"  # SS-14c


# ── SS-15: analysis_status write without state change ────────────────

def test_analysis_status_update(db_connection, test_session_id):
    sid = test_session_id
    write_state(db_connection, StateWriteRequest(
        new_state="UPLOADED", analysis_status="IDLE",
        trigger="INGESTION_COMPLETE", session_id=sid,
    ))
    # UPLOADED → UPLOADED with ANALYZING via SYSTEM_RECOVERY
    # (analysis_status updates use SYSTEM_RECOVERY to bypass self-transition check)
    write_state(db_connection, StateWriteRequest(
        new_state="UPLOADED", analysis_status="ANALYZING",
        trigger="SYSTEM_RECOVERY", session_id=sid,
    ))
    snap = read_state(db_connection, sid)
    assert snap.analysis_status == "ANALYZING"                 # SS-15a
    assert snap.application_state == "UPLOADED"                # SS-15b


# ── SS-16: Savepoint rollback — no partial writes ────────────────────

def test_no_partial_writes_on_constraint_violation(db_connection, test_session_id):
    sid = test_session_id
    # Write valid first state
    write_state(db_connection, StateWriteRequest(
        new_state="UPLOADED", analysis_status="IDLE",
        trigger="INGESTION_COMPLETE", session_id=sid,
    ))
    # Attempt invalid transition: UPLOADED → APPROVED without write_result
    result = write_state(db_connection, StateWriteRequest(
        new_state="APPROVED", analysis_status=None,
        trigger="CFO_APPROVAL", session_id=sid,
    ))
    assert result.result == "FAIL"                             # SS-16a
    # State unchanged — still UPLOADED
    row = _read_store(db_connection, sid)
    assert row.application_state == "UPLOADED"                 # SS-16b
    # History not appended for failed transition
    history = _read_history(db_connection, sid)
    assert len(history) == 1                                   # SS-16c (only the INGESTION_COMPLETE entry)
