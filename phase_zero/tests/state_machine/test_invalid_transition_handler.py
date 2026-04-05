"""
Tests for Invalid Transition Rejection Handler — Component 10/12.

Pure logic tests. No DB dependency.

Assertions: ITH-01 through ITH-08
"""

from __future__ import annotations

from uuid import uuid4

from app.state_machine.engine_completion_collector import (
    CollectionResult,
)
from app.state_machine.invalid_transition_handler import (
    RejectionResponse,
    handle_engine_failure,
    handle_invalid_transition,
)
from app.state_machine.transition_validator import ValidationResult

_DUMMY_SID = uuid4()


# ── ITH-01: INVALID transition → INVALID_TRANSITION type ────────────

def test_invalid_transition_type():
    vr = ValidationResult(
        result="INVALID",
        requested_transition="ANALYZED→APPROVED",
        reason="Terminal state — no transitions permitted",
        current_state="APPROVED",
    )
    resp = handle_invalid_transition(vr)
    assert resp.type == "INVALID_TRANSITION"                   # ITH-01


# ── ITH-02: INVALID transition message includes reason ───────────────

def test_invalid_transition_message():
    vr = ValidationResult(
        result="INVALID",
        requested_transition="ANALYZED→APPROVED",
        reason="Terminal state — no transitions permitted",
        current_state="APPROVED",
    )
    resp = handle_invalid_transition(vr)
    assert "Transition not permitted" in resp.message          # ITH-02a
    assert "Terminal state" in resp.message                    # ITH-02b


# ── ITH-03: INVALID transition preserves current state ───────────────

def test_invalid_transition_state_preserved():
    vr = ValidationResult(
        result="INVALID",
        requested_transition="UPLOADED→ANALYZED",
        reason="Not a valid transition",
        current_state="UPLOADED",
    )
    resp = handle_invalid_transition(vr)
    assert resp.state == "UPLOADED"                            # ITH-03


# ── ITH-04: Non-INVALID validation result guarded ────────────────────

def test_non_invalid_guarded():
    vr = ValidationResult(
        result="VALID",
        requested_transition="EMPTY→UPLOADED",
        current_state="EMPTY",
    )
    resp = handle_invalid_transition(vr)
    assert "non-INVALID" in resp.message                       # ITH-04


# ── ITH-05: ENGINE_FAILURE type from collector FAIL ──────────────────

def test_engine_failure_type():
    cr = CollectionResult(
        result="FAIL",
        session_id=_DUMMY_SID,
        errors=["margin_engine: timeout"],
    )
    resp = handle_engine_failure(cr, "UPLOADED")
    assert resp.type == "ENGINE_FAILURE"                       # ITH-05


# ── ITH-06: Engine failure message includes all named errors ─────────

def test_engine_failure_message():
    cr = CollectionResult(
        result="FAIL",
        session_id=_DUMMY_SID,
        errors=["margin_engine: timeout", "allocation_engine: data error"],
    )
    resp = handle_engine_failure(cr, "UPLOADED")
    assert "margin_engine: timeout" in resp.message            # ITH-06a
    assert "allocation_engine: data error" in resp.message     # ITH-06b


# ── ITH-07: Engine failure preserves UPLOADED state ──────────────────

def test_engine_failure_state_preserved():
    cr = CollectionResult(
        result="FAIL",
        session_id=_DUMMY_SID,
        errors=["engine: failed"],
    )
    resp = handle_engine_failure(cr, "UPLOADED")
    assert resp.state == "UPLOADED"                            # ITH-07


# ── ITH-08: Non-FAIL collection result guarded ──────────────────────

def test_non_fail_collection_guarded():
    cr = CollectionResult(result="SUCCESS", session_id=_DUMMY_SID)
    resp = handle_engine_failure(cr, "UPLOADED")
    assert "non-FAIL" in resp.message                          # ITH-08
