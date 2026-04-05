"""
Tests for ANALYZED → APPROVED Executor — Component 8/12.

Pure logic tests — no DB required. This component does NOT write
to State Store (C-3 FIX). It validates the transition and passes
trigger + session_id to the Approved Result Writer (Component 9).

Assertions: AA-01 through AA-08
"""

from __future__ import annotations

from uuid import uuid4

from app.state_machine.transition_validator import ValidationResult
from app.state_machine.analyzed_to_approved_executor import (
    ApprovalTransitionResult,
    execute_analyzed_to_approved,
)


# ── Helper ──────────────────────────────────────────────────────────

def _valid_approval(session_id):
    return ValidationResult(
        result="VALID",
        requested_transition="ANALYZED→APPROVED",
        current_state="ANALYZED",
        session_id=session_id,
    )


# ── AA-01: Successful validation → SUCCESS with trigger ──────────────

def test_successful_validation(db_connection, test_session_id):
    sid = test_session_id
    result = execute_analyzed_to_approved(_valid_approval(sid))
    assert result.result == "SUCCESS"                          # AA-01a
    assert result.new_state == "APPROVED"                      # AA-01b
    assert result.session_id == sid                            # AA-01c


# ── AA-02: trigger = CFO_APPROVAL ────────────────────────────────────

def test_trigger_is_cfo_approval():
    sid = uuid4()
    result = execute_analyzed_to_approved(_valid_approval(sid))
    assert result.trigger == "CFO_APPROVAL"                    # AA-02


# ── AA-03: Error is None on success ──────────────────────────────────

def test_error_none_on_success():
    sid = uuid4()
    result = execute_analyzed_to_approved(_valid_approval(sid))
    assert result.error is None                                # AA-03


# ── AA-04: Non-VALID validation rejected ─────────────────────────────

def test_non_valid_rejected():
    sid = uuid4()
    invalid = ValidationResult(
        result="INVALID",
        requested_transition="ANALYZED→APPROVED",
        current_state="ANALYZED",
        session_id=sid,
        reason="test",
    )
    result = execute_analyzed_to_approved(invalid)
    assert result.result == "FAIL"                             # AA-04a
    assert "non-VALID" in result.error                         # AA-04b


# ── AA-05: Wrong transition name rejected ────────────────────────────

def test_wrong_transition_rejected():
    sid = uuid4()
    wrong = ValidationResult(
        result="VALID",
        requested_transition="EMPTY→UPLOADED",
        current_state="EMPTY",
        session_id=sid,
    )
    result = execute_analyzed_to_approved(wrong)
    assert result.result == "FAIL"                             # AA-05a
    assert "wrong transition" in result.error                  # AA-05b


# ── AA-06: Missing session_id rejected ───────────────────────────────

def test_missing_session_id_rejected():
    no_sid = ValidationResult(
        result="VALID",
        requested_transition="ANALYZED→APPROVED",
        current_state="ANALYZED",
        session_id=None,
    )
    result = execute_analyzed_to_approved(no_sid)
    assert result.result == "FAIL"                             # AA-06a
    assert "requires session_id" in result.error               # AA-06b


# ── AA-07: Does NOT write to State Store (C-3 FIX verification) ─────

def test_no_state_store_write(db_connection, test_session_id):
    """Component 8 must NOT write APPROVED — Component 9 owns that."""
    from app.state_machine.state_store import (
        StateWriteRequest,
        read_state,
        write_state,
    )
    sid = test_session_id
    # Setup: advance to ANALYZED
    write_state(db_connection, StateWriteRequest(
        new_state="UPLOADED", analysis_status="IDLE",
        trigger="INGESTION_COMPLETE", session_id=sid,
    ))
    write_state(db_connection, StateWriteRequest(
        new_state="ANALYZED", trigger="ENGINES_COMPLETE",
        session_id=sid,
    ))
    # Execute Component 8
    execute_analyzed_to_approved(_valid_approval(sid))
    # State must still be ANALYZED — not APPROVED
    snap = read_state(db_connection, sid)
    assert snap.application_state == "ANALYZED"                # AA-07


# ── AA-08: session_id preserved in result ────────────────────────────

def test_session_id_preserved():
    sid = uuid4()
    result = execute_analyzed_to_approved(_valid_approval(sid))
    assert result.session_id == sid                            # AA-08
