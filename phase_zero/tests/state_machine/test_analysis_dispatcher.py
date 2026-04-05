"""
Tests for Analysis Dispatcher — Component 5/12.

DB integration tests. Validates session_id resolution, double-dispatch
guard, analysis_status write, guard clauses, and failure paths.

Assertions: AD-01 through AD-10
"""

from __future__ import annotations

from uuid import uuid4

from app.state_machine.state_store import (
    StateWriteRequest,
    read_state,
    write_state,
)
from app.state_machine.transition_validator import ValidationResult
from app.state_machine.analysis_dispatcher import (
    DispatchResult,
    dispatch_analysis,
)


# ── Helpers ─────────────────────────────────────────────────────────

def _valid_uploaded_to_analyzed(session_id):
    """Create a VALID ValidationResult for UPLOADED→ANALYZED."""
    return ValidationResult(
        result="VALID",
        requested_transition="UPLOADED→ANALYZED",
        current_state="UPLOADED",
        session_id=session_id,
    )


def _setup_uploaded(conn, sid):
    """Create a state_store row at UPLOADED state."""
    write_state(conn, StateWriteRequest(
        new_state="UPLOADED", analysis_status="IDLE",
        trigger="INGESTION_COMPLETE", session_id=sid,
    ))


# ── AD-01: Successful dispatch ───────────────────────────────────────

def test_successful_dispatch(db_connection, test_session_id):
    sid = test_session_id
    _setup_uploaded(db_connection, sid)
    result = dispatch_analysis(
        db_connection, _valid_uploaded_to_analyzed(sid),
    )
    assert result.result == "DISPATCHED"                       # AD-01a
    assert result.session_id == sid                            # AD-01b
    assert result.error is None                                # AD-01c


# ── AD-02: analysis_status set to ANALYZING after dispatch ───────────

def test_analysis_status_set_to_analyzing(db_connection, test_session_id):
    sid = test_session_id
    _setup_uploaded(db_connection, sid)
    dispatch_analysis(db_connection, _valid_uploaded_to_analyzed(sid))
    snap = read_state(db_connection, sid)
    assert snap.analysis_status == "ANALYZING"                 # AD-02a
    assert snap.application_state == "UPLOADED"                # AD-02b


# ── AD-03: Double-dispatch blocked ───────────────────────────────────

def test_double_dispatch_blocked(db_connection, test_session_id):
    sid = test_session_id
    _setup_uploaded(db_connection, sid)
    # First dispatch succeeds
    dispatch_analysis(db_connection, _valid_uploaded_to_analyzed(sid))
    # Second dispatch blocked — already ANALYZING
    result = dispatch_analysis(
        db_connection, _valid_uploaded_to_analyzed(sid),
    )
    assert result.result == "FAIL"                             # AD-03a
    assert "already in progress" in result.error               # AD-03b


# ── AD-04: Non-VALID validation rejected ─────────────────────────────

def test_non_valid_rejected(db_connection, test_session_id):
    sid = test_session_id
    invalid = ValidationResult(
        result="INVALID",
        requested_transition="UPLOADED→ANALYZED",
        current_state="UPLOADED",
        session_id=sid,
        reason="test",
    )
    result = dispatch_analysis(db_connection, invalid)
    assert result.result == "FAIL"                             # AD-04a
    assert "non-VALID" in result.error                         # AD-04b


# ── AD-05: Wrong transition name rejected ────────────────────────────

def test_wrong_transition_rejected(db_connection, test_session_id):
    sid = test_session_id
    wrong = ValidationResult(
        result="VALID",
        requested_transition="EMPTY→UPLOADED",
        current_state="EMPTY",
        session_id=sid,
    )
    result = dispatch_analysis(db_connection, wrong)
    assert result.result == "FAIL"                             # AD-05a
    assert "wrong transition" in result.error                  # AD-05b


# ── AD-06: Missing session_id rejected ───────────────────────────────

def test_missing_session_id_rejected(db_connection):
    no_sid = ValidationResult(
        result="VALID",
        requested_transition="UPLOADED→ANALYZED",
        current_state="UPLOADED",
        session_id=None,
    )
    result = dispatch_analysis(db_connection, no_sid)
    assert result.result == "FAIL"                             # AD-06a
    assert "Session ID not found" in result.error              # AD-06b


# ── AD-07: Unknown session_id (no state_store row) rejected ──────────

def test_unknown_session_rejected(db_connection, test_session_id):
    # Use a session_id that exists in ingestion_log but not state_store
    sid = test_session_id  # ingestion_log row exists via fixture
    # Don't call _setup_uploaded — no state_store row
    result = dispatch_analysis(
        db_connection, _valid_uploaded_to_analyzed(sid),
    )
    assert result.result == "FAIL"                             # AD-07a
    assert "Session ID not found" in result.error              # AD-07b


# ── AD-08: State remains UPLOADED (application_state unchanged) ──────

def test_state_remains_uploaded(db_connection, test_session_id):
    sid = test_session_id
    _setup_uploaded(db_connection, sid)
    dispatch_analysis(db_connection, _valid_uploaded_to_analyzed(sid))
    snap = read_state(db_connection, sid)
    assert snap.application_state == "UPLOADED"                # AD-08


# ── AD-09: Dispatch after IDLE reset (re-dispatch after failure) ─────

def test_redispatch_after_idle_reset(db_connection, test_session_id):
    sid = test_session_id
    _setup_uploaded(db_connection, sid)
    # First dispatch
    dispatch_analysis(db_connection, _valid_uploaded_to_analyzed(sid))
    assert read_state(db_connection, sid).analysis_status == "ANALYZING"
    # Simulate engine failure — collector resets to IDLE
    write_state(db_connection, StateWriteRequest(
        new_state="UPLOADED", analysis_status="IDLE",
        trigger="ANALYSIS_FAILED", session_id=sid,
    ))
    assert read_state(db_connection, sid).analysis_status == "IDLE"
    # Re-dispatch succeeds
    result = dispatch_analysis(
        db_connection, _valid_uploaded_to_analyzed(sid),
    )
    assert result.result == "DISPATCHED"                       # AD-09a
    assert read_state(db_connection, sid).analysis_status == "ANALYZING"  # AD-09b


# ── AD-10: session_status stays ACTIVE ───────────────────────────────

def test_session_status_stays_active(db_connection, test_session_id):
    sid = test_session_id
    _setup_uploaded(db_connection, sid)
    dispatch_analysis(db_connection, _valid_uploaded_to_analyzed(sid))
    snap = read_state(db_connection, sid)
    assert snap.session_status == "ACTIVE"                     # AD-10
