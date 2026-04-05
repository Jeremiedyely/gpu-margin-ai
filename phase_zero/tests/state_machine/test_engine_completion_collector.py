"""
Tests for Engine Completion Collector — Component 6/12.

DB integration tests. Validates both-SUCCESS path, single-FAIL path,
both-FAIL path, analysis_status reset, retry_count management,
ANALYSIS_MAX_RETRIES enforcement, and session_id mismatch guard.

Assertions: ECC-01 through ECC-12
"""

from __future__ import annotations

from uuid import uuid4

from app.state_machine.state_store import (
    StateWriteRequest,
    read_state,
    write_state,
)
from app.state_machine.engine_completion_collector import (
    ANALYSIS_MAX_RETRIES,
    CollectionResult,
    EngineResult,
    collect_engine_results,
)


# ── Helpers ─────────────────────────────────────────────────────────

def _setup_analyzing(conn, sid):
    """Create a state_store row at UPLOADED/ANALYZING."""
    write_state(conn, StateWriteRequest(
        new_state="UPLOADED", analysis_status="IDLE",
        trigger="INGESTION_COMPLETE", session_id=sid,
    ))
    write_state(conn, StateWriteRequest(
        new_state="UPLOADED", analysis_status="ANALYZING",
        trigger="ANALYSIS_DISPATCHED", session_id=sid,
    ))


def _ae_success(sid):
    return EngineResult(engine="ALLOCATION", result="SUCCESS", session_id=sid)


def _ae_fail(sid, error="AE timeout"):
    return EngineResult(engine="ALLOCATION", result="FAIL", session_id=sid, error=error)


def _re_success(sid):
    return EngineResult(engine="RECONCILIATION", result="SUCCESS", session_id=sid)


def _re_fail(sid, error="RE check failed"):
    return EngineResult(engine="RECONCILIATION", result="FAIL", session_id=sid, error=error)


# ── ECC-01: Both SUCCESS → collection SUCCESS ───────────────────────

def test_both_success(db_connection, test_session_id):
    sid = test_session_id
    _setup_analyzing(db_connection, sid)
    result = collect_engine_results(
        db_connection, _ae_success(sid), _re_success(sid),
    )
    assert result.result == "SUCCESS"                          # ECC-01a
    assert result.session_id == sid                            # ECC-01b
    assert result.errors == []                                 # ECC-01c


# ── ECC-02: analysis_status reset to IDLE on SUCCESS ─────────────────

def test_analysis_status_idle_on_success(db_connection, test_session_id):
    sid = test_session_id
    _setup_analyzing(db_connection, sid)
    collect_engine_results(db_connection, _ae_success(sid), _re_success(sid))
    snap = read_state(db_connection, sid)
    assert snap.analysis_status == "IDLE"                      # ECC-02


# ── ECC-03: AE FAIL → collection FAIL ───────────────────────────────

def test_ae_fail(db_connection, test_session_id):
    sid = test_session_id
    _setup_analyzing(db_connection, sid)
    result = collect_engine_results(
        db_connection, _ae_fail(sid), _re_success(sid),
    )
    assert result.result == "FAIL"                             # ECC-03a
    assert any("Allocation Engine" in e for e in result.errors)  # ECC-03b


# ── ECC-04: RE FAIL → collection FAIL ───────────────────────────────

def test_re_fail(db_connection, test_session_id):
    sid = test_session_id
    _setup_analyzing(db_connection, sid)
    result = collect_engine_results(
        db_connection, _ae_success(sid), _re_fail(sid),
    )
    assert result.result == "FAIL"                             # ECC-04a
    assert any("Reconciliation Engine" in e for e in result.errors)  # ECC-04b


# ── ECC-05: Both FAIL → both errors collected ───────────────────────

def test_both_fail(db_connection, test_session_id):
    sid = test_session_id
    _setup_analyzing(db_connection, sid)
    result = collect_engine_results(
        db_connection, _ae_fail(sid), _re_fail(sid),
    )
    assert result.result == "FAIL"                             # ECC-05a
    assert len(result.errors) >= 2                             # ECC-05b
    assert any("Allocation" in e for e in result.errors)       # ECC-05c
    assert any("Reconciliation" in e for e in result.errors)   # ECC-05d


# ── ECC-06: analysis_status reset to IDLE on FAIL ────────────────────

def test_analysis_status_idle_on_fail(db_connection, test_session_id):
    sid = test_session_id
    _setup_analyzing(db_connection, sid)
    collect_engine_results(db_connection, _ae_fail(sid), _re_success(sid))
    snap = read_state(db_connection, sid)
    assert snap.analysis_status == "IDLE"                      # ECC-06


# ── ECC-07: retry_count incremented on FAIL ──────────────────────────

def test_retry_count_incremented(db_connection, test_session_id):
    sid = test_session_id
    _setup_analyzing(db_connection, sid)
    result = collect_engine_results(
        db_connection, _ae_fail(sid), _re_success(sid),
    )
    assert result.retry_count == 1                             # ECC-07a
    snap = read_state(db_connection, sid)
    assert snap.retry_count == 1                               # ECC-07b


# ── ECC-08: retry_count NOT incremented on SUCCESS ───────────────────

def test_retry_count_unchanged_on_success(db_connection, test_session_id):
    sid = test_session_id
    _setup_analyzing(db_connection, sid)
    collect_engine_results(db_connection, _ae_success(sid), _re_success(sid))
    snap = read_state(db_connection, sid)
    assert snap.retry_count == 0                               # ECC-08


# ── ECC-09: ANALYSIS_MAX_RETRIES exhausted ───────────────────────────

def test_max_retries_exhausted(db_connection, test_session_id):
    sid = test_session_id
    _setup_analyzing(db_connection, sid)
    # Exhaust retries
    for i in range(ANALYSIS_MAX_RETRIES):
        collect_engine_results(
            db_connection, _ae_fail(sid), _re_success(sid),
        )
        # Reset to ANALYZING for next attempt (simulating re-dispatch)
        if i < ANALYSIS_MAX_RETRIES - 1:
            write_state(db_connection, StateWriteRequest(
                new_state="UPLOADED", analysis_status="ANALYZING",
                trigger="ANALYSIS_DISPATCHED", session_id=sid,
            ))
    # Last result should flag retry_exhausted
    # Need one more attempt after exhaustion
    write_state(db_connection, StateWriteRequest(
        new_state="UPLOADED", analysis_status="ANALYZING",
        trigger="ANALYSIS_DISPATCHED", session_id=sid,
    ))
    result = collect_engine_results(
        db_connection, _ae_fail(sid), _re_success(sid),
    )
    assert result.retry_exhausted is True                      # ECC-09a
    assert result.retry_count >= ANALYSIS_MAX_RETRIES          # ECC-09b
    assert any("Contact your operator" in e for e in result.errors)  # ECC-09c


# ── ECC-10: retry_exhausted = False when under limit ─────────────────

def test_retry_not_exhausted(db_connection, test_session_id):
    sid = test_session_id
    _setup_analyzing(db_connection, sid)
    result = collect_engine_results(
        db_connection, _ae_fail(sid), _re_success(sid),
    )
    assert result.retry_exhausted is False                     # ECC-10


# ── ECC-11: session_id mismatch rejected ─────────────────────────────

def test_session_id_mismatch(db_connection, test_session_id):
    sid = test_session_id
    other_sid = uuid4()
    result = collect_engine_results(
        db_connection,
        EngineResult(engine="ALLOCATION", result="SUCCESS", session_id=sid),
        EngineResult(engine="RECONCILIATION", result="SUCCESS", session_id=other_sid),
    )
    assert result.result == "FAIL"                             # ECC-11a
    assert any("mismatch" in e for e in result.errors)         # ECC-11b


# ── ECC-12: application_state stays UPLOADED on both paths ───────────

def test_state_stays_uploaded(db_connection, test_session_id):
    sid = test_session_id
    _setup_analyzing(db_connection, sid)
    # SUCCESS path
    collect_engine_results(db_connection, _ae_success(sid), _re_success(sid))
    snap = read_state(db_connection, sid)
    assert snap.application_state == "UPLOADED"                # ECC-12
