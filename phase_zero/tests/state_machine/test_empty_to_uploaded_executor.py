"""
Tests for EMPTY → UPLOADED Executor — Component 4/12.

DB integration tests. Validates successful transition, State Store
persistence, guard clauses, and failure path.

Assertions: EU-01 through EU-08
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text

from app.state_machine.state_store import (
    StateWriteRequest,
    read_state,
    write_state,
)
from app.state_machine.transition_validator import ValidationResult
from app.state_machine.empty_to_uploaded_executor import (
    TransitionResult,
    execute_empty_to_uploaded,
)


# ── Helper ──────────────────────────────────────────────────────────

def _valid_result(session_id):
    """Create a VALID ValidationResult for EMPTY→UPLOADED."""
    return ValidationResult(
        result="VALID",
        requested_transition="EMPTY→UPLOADED",
        current_state="EMPTY",
        session_id=session_id,
    )


def _setup_empty(conn, sid):
    """Create a state_store row at EMPTY state."""
    write_state(conn, StateWriteRequest(
        new_state="EMPTY", analysis_status="IDLE",
        trigger="SYSTEM_RECOVERY", session_id=sid,
    ))


# ── EU-01: Successful EMPTY→UPLOADED transition ─────────────────────

def test_successful_transition(db_connection, test_session_id):
    sid = test_session_id
    _setup_empty(db_connection, sid)
    result = execute_empty_to_uploaded(
        db_connection, _valid_result(sid),
    )
    assert result.result == "SUCCESS"                          # EU-01a
    assert result.new_state == "UPLOADED"                      # EU-01b
    assert result.session_id == sid                            # EU-01c


# ── EU-02: State Store updated after transition ──────────────────────

def test_state_store_updated(db_connection, test_session_id):
    sid = test_session_id
    _setup_empty(db_connection, sid)
    execute_empty_to_uploaded(db_connection, _valid_result(sid))
    snap = read_state(db_connection, sid)
    assert snap.application_state == "UPLOADED"                # EU-02a
    assert snap.analysis_status == "IDLE"                      # EU-02b
    assert snap.session_status == "ACTIVE"                     # EU-02c


# ── EU-03: State history appended ────────────────────────────────────

def test_history_appended(db_connection, test_session_id):
    sid = test_session_id
    _setup_empty(db_connection, sid)
    execute_empty_to_uploaded(db_connection, _valid_result(sid))
    rows = db_connection.execute(
        text("""
            SELECT from_state, to_state, transition_trigger
            FROM dbo.state_history
            WHERE session_id = :sid
            ORDER BY id
        """),
        {"sid": str(sid)},
    ).fetchall()
    # Two entries: SYSTEM_RECOVERY (setup) + INGESTION_COMPLETE
    ingestion_row = [r for r in rows if r.transition_trigger == "INGESTION_COMPLETE"]
    assert len(ingestion_row) == 1                             # EU-03a
    assert ingestion_row[0].from_state == "EMPTY"              # EU-03b
    assert ingestion_row[0].to_state == "UPLOADED"             # EU-03c


# ── EU-04: Non-VALID validation rejected ─────────────────────────────

def test_non_valid_rejected(db_connection, test_session_id):
    sid = test_session_id
    invalid = ValidationResult(
        result="INVALID",
        requested_transition="EMPTY→UPLOADED",
        current_state="EMPTY",
        session_id=sid,
        reason="test rejection",
    )
    result = execute_empty_to_uploaded(db_connection, invalid)
    assert result.result == "FAIL"                             # EU-04a
    assert "non-VALID" in result.error                         # EU-04b


# ── EU-05: Wrong transition name rejected ────────────────────────────

def test_wrong_transition_rejected(db_connection, test_session_id):
    sid = test_session_id
    wrong = ValidationResult(
        result="VALID",
        requested_transition="UPLOADED→ANALYZED",
        current_state="UPLOADED",
        session_id=sid,
    )
    result = execute_empty_to_uploaded(db_connection, wrong)
    assert result.result == "FAIL"                             # EU-05a
    assert "wrong transition" in result.error                  # EU-05b


# ── EU-06: Missing session_id rejected ───────────────────────────────

def test_missing_session_id_rejected(db_connection):
    no_sid = ValidationResult(
        result="VALID",
        requested_transition="EMPTY→UPLOADED",
        current_state="EMPTY",
        session_id=None,
    )
    result = execute_empty_to_uploaded(db_connection, no_sid)
    assert result.result == "FAIL"                             # EU-06a
    assert "requires session_id" in result.error               # EU-06b


# ── EU-07: First write (no prior state_store row) ────────────────────

def test_first_write_no_prior_row(db_connection, test_session_id):
    sid = test_session_id
    # No _setup_empty — the executor's write_state will INSERT via MERGE
    result = execute_empty_to_uploaded(
        db_connection, _valid_result(sid),
    )
    assert result.result == "SUCCESS"                          # EU-07a
    snap = read_state(db_connection, sid)
    assert snap.application_state == "UPLOADED"                # EU-07b


# ── EU-08: Error field is None on success ────────────────────────────

def test_error_none_on_success(db_connection, test_session_id):
    sid = test_session_id
    _setup_empty(db_connection, sid)
    result = execute_empty_to_uploaded(
        db_connection, _valid_result(sid),
    )
    assert result.error is None                                # EU-08
