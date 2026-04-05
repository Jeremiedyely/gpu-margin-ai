"""
Tests for Transition Validator — Component 3/12.

Pure logic tests — no DB required. Validates the three-rule
transition table, terminal state rejection, source mismatch
rejection, and wrong-state rejection.

Assertions: TV-01 through TV-12
"""

from __future__ import annotations

from uuid import uuid4

from app.state_machine.transition_request_receiver import TransitionRequest
from app.state_machine.transition_validator import (
    ValidationResult,
    validate_transition,
)


# ── Helper ──────────────────────────────────────────────────────────

def _req(current_state, requested_transition, source, session_id=None):
    return TransitionRequest(
        current_state=current_state,
        requested_transition=requested_transition,
        source=source,
        session_id=session_id or uuid4(),
    )


# ── TV-01: EMPTY → UPLOADED with INGESTION = VALID ──────────────────

def test_empty_to_uploaded_valid():
    result = validate_transition(
        _req("EMPTY", "EMPTY→UPLOADED", "INGESTION"),
    )
    assert result.result == "VALID"                            # TV-01a
    assert result.reason is None                               # TV-01b


# ── TV-02: UPLOADED → ANALYZED with UI_ANALYZE = VALID ───────────────

def test_uploaded_to_analyzed_valid():
    result = validate_transition(
        _req("UPLOADED", "UPLOADED→ANALYZED", "UI_ANALYZE"),
    )
    assert result.result == "VALID"                            # TV-02a
    assert result.reason is None                               # TV-02b


# ── TV-03: ANALYZED → APPROVED with APPROVAL_DIALOG = VALID ─────────

def test_analyzed_to_approved_valid():
    result = validate_transition(
        _req("ANALYZED", "ANALYZED→APPROVED", "APPROVAL_DIALOG"),
    )
    assert result.result == "VALID"                            # TV-03a
    assert result.reason is None                               # TV-03b


# ── TV-04: APPROVED + any transition = INVALID (terminal) ───────────

def test_approved_is_terminal():
    result = validate_transition(
        _req("APPROVED", "APPROVED→SOMETHING", "INGESTION"),
    )
    assert result.result == "INVALID"                          # TV-04a
    assert "terminal" in result.reason                         # TV-04b


# ── TV-05: APPROVED + valid transition name still INVALID ────────────

def test_approved_rejects_valid_transition_name():
    result = validate_transition(
        _req("APPROVED", "ANALYZED→APPROVED", "APPROVAL_DIALOG"),
    )
    assert result.result == "INVALID"                          # TV-05a
    assert "terminal" in result.reason                         # TV-05b


# ── TV-06: Wrong source for EMPTY→UPLOADED = INVALID ─────────────────

def test_wrong_source_empty_to_uploaded():
    result = validate_transition(
        _req("EMPTY", "EMPTY→UPLOADED", "UI_ANALYZE"),
    )
    assert result.result == "INVALID"                          # TV-06a
    assert "not valid" in result.reason                        # TV-06b


# ── TV-07: Wrong source for UPLOADED→ANALYZED = INVALID ──────────────

def test_wrong_source_uploaded_to_analyzed():
    result = validate_transition(
        _req("UPLOADED", "UPLOADED→ANALYZED", "INGESTION"),
    )
    assert result.result == "INVALID"                          # TV-07a
    assert "not valid" in result.reason                        # TV-07b


# ── TV-08: Wrong source for ANALYZED→APPROVED = INVALID ──────────────

def test_wrong_source_analyzed_to_approved():
    result = validate_transition(
        _req("ANALYZED", "ANALYZED→APPROVED", "UI_ANALYZE"),
    )
    assert result.result == "INVALID"                          # TV-08a
    assert "not valid" in result.reason                        # TV-08b


# ── TV-09: Wrong current state for transition = INVALID ──────────────

def test_wrong_state_for_transition():
    # EMPTY state but requesting UPLOADED→ANALYZED
    result = validate_transition(
        _req("EMPTY", "UPLOADED→ANALYZED", "UI_ANALYZE"),
    )
    assert result.result == "INVALID"                          # TV-09a
    assert "not valid" in result.reason                        # TV-09b


# ── TV-10: Backward transition = INVALID ─────────────────────────────

def test_backward_transition_invalid():
    # ANALYZED trying to go back to UPLOADED
    result = validate_transition(
        _req("ANALYZED", "EMPTY→UPLOADED", "INGESTION"),
    )
    assert result.result == "INVALID"                          # TV-10a
    assert "not valid" in result.reason                        # TV-10b


# ── TV-11: session_id preserved in result ────────────────────────────

def test_session_id_preserved():
    sid = uuid4()
    result = validate_transition(
        _req("EMPTY", "EMPTY→UPLOADED", "INGESTION", session_id=sid),
    )
    assert result.session_id == sid                            # TV-11


# ── TV-12: Unrecognized transition name = INVALID ────────────────────

def test_unrecognized_transition_name():
    result = validate_transition(
        _req("UPLOADED", "UPLOADED→SOMETHING", "UI_ANALYZE"),
    )
    assert result.result == "INVALID"                          # TV-12a
    assert "not valid" in result.reason                        # TV-12b
