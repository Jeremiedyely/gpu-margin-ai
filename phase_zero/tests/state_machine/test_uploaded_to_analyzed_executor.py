"""
Tests for UPLOADED → ANALYZED Executor — Component 7/12.

DB integration tests. Validates successful transition, State Store
persistence, retry_count reset, guard clauses, and failure path.

Assertions: UA-01 through UA-07
"""

from __future__ import annotations

from sqlalchemy import text

from app.state_machine.state_store import (
    StateWriteRequest,
    increment_retry_count,
    read_state,
    write_state,
)
from app.state_machine.engine_completion_collector import CollectionResult
from app.state_machine.uploaded_to_analyzed_executor import (
    execute_uploaded_to_analyzed,
)


# ── Helpers ─────────────────────────────────────────────────────────

def _setup_uploaded(conn, sid):
    write_state(conn, StateWriteRequest(
        new_state="UPLOADED", analysis_status="IDLE",
        trigger="INGESTION_COMPLETE", session_id=sid,
    ))


def _success_collection(sid):
    return CollectionResult(result="SUCCESS", session_id=sid)


def _fail_collection(sid):
    return CollectionResult(
        result="FAIL", session_id=sid,
        errors=["test engine failure"],
    )


# ── UA-01: Successful UPLOADED→ANALYZED transition ───────────────────

def test_successful_transition(db_connection, test_session_id):
    sid = test_session_id
    _setup_uploaded(db_connection, sid)
    result = execute_uploaded_to_analyzed(
        db_connection, _success_collection(sid),
    )
    assert result.result == "SUCCESS"                          # UA-01a
    assert result.new_state == "ANALYZED"                      # UA-01b
    assert result.session_id == sid                            # UA-01c


# ── UA-02: State Store updated to ANALYZED ───────────────────────────

def test_state_store_updated(db_connection, test_session_id):
    sid = test_session_id
    _setup_uploaded(db_connection, sid)
    execute_uploaded_to_analyzed(db_connection, _success_collection(sid))
    snap = read_state(db_connection, sid)
    assert snap.application_state == "ANALYZED"                # UA-02a
    assert snap.analysis_status == "IDLE"                      # UA-02b
    assert snap.session_status == "ACTIVE"                     # UA-02c


# ── UA-03: retry_count reset to 0 on success ────────────────────────

def test_retry_count_reset(db_connection, test_session_id):
    sid = test_session_id
    _setup_uploaded(db_connection, sid)
    # Simulate prior failures
    increment_retry_count(db_connection, sid)
    increment_retry_count(db_connection, sid)
    assert read_state(db_connection, sid).retry_count == 2
    # Successful transition resets
    execute_uploaded_to_analyzed(db_connection, _success_collection(sid))
    assert read_state(db_connection, sid).retry_count == 0     # UA-03


# ── UA-04: Non-SUCCESS collection rejected ───────────────────────────

def test_non_success_rejected(db_connection, test_session_id):
    sid = test_session_id
    result = execute_uploaded_to_analyzed(
        db_connection, _fail_collection(sid),
    )
    assert result.result == "FAIL"                             # UA-04a
    assert "non-SUCCESS" in result.error                       # UA-04b


# ── UA-05: State history appended ────────────────────────────────────

def test_history_appended(db_connection, test_session_id):
    sid = test_session_id
    _setup_uploaded(db_connection, sid)
    execute_uploaded_to_analyzed(db_connection, _success_collection(sid))
    rows = db_connection.execute(
        text("""
            SELECT from_state, to_state, transition_trigger
            FROM dbo.state_history
            WHERE session_id = :sid
            ORDER BY id
        """),
        {"sid": str(sid)},
    ).fetchall()
    engines_row = [r for r in rows if r.transition_trigger == "ENGINES_COMPLETE"]
    assert len(engines_row) == 1                               # UA-05a
    assert engines_row[0].from_state == "UPLOADED"             # UA-05b
    assert engines_row[0].to_state == "ANALYZED"               # UA-05c


# ── UA-06: Error is None on success ──────────────────────────────────

def test_error_none_on_success(db_connection, test_session_id):
    sid = test_session_id
    _setup_uploaded(db_connection, sid)
    result = execute_uploaded_to_analyzed(
        db_connection, _success_collection(sid),
    )
    assert result.error is None                                # UA-06


# ── UA-07: write_result stays None after ANALYZED ────────────────────

def test_write_result_stays_none(db_connection, test_session_id):
    sid = test_session_id
    _setup_uploaded(db_connection, sid)
    execute_uploaded_to_analyzed(db_connection, _success_collection(sid))
    snap = read_state(db_connection, sid)
    assert snap.write_result is None                           # UA-07
