"""
Tests for Transition Request Receiver — Component 2/12.

DB integration tests. Validates source rejection, idempotency contract
(P3 #28), State Store read failures, and forward-to-validator path.

Assertions: TRR-01 through TRR-10
"""

from __future__ import annotations

from uuid import uuid4

from app.state_machine.state_store import StateWriteRequest, write_state
from app.state_machine.transition_request_receiver import (
    ReceiverResult,
    TransitionSignal,
    receive_transition_signal,
)


# ── Helper ──────────────────────────────────────────────────────────

def _setup_state(conn, sid, state, **kwargs):
    """Write a specific application_state for a session."""
    if state == "UPLOADED":
        write_state(conn, StateWriteRequest(
            new_state="UPLOADED", analysis_status="IDLE",
            trigger="INGESTION_COMPLETE", session_id=sid,
        ))
    elif state == "ANALYZED":
        _setup_state(conn, sid, "UPLOADED")
        write_state(conn, StateWriteRequest(
            new_state="ANALYZED", trigger="ENGINES_COMPLETE",
            session_id=sid,
        ))
    elif state == "APPROVED":
        _setup_state(conn, sid, "ANALYZED")
        write_state(conn, StateWriteRequest(
            new_state="APPROVED", trigger="CFO_APPROVAL",
            session_id=sid, write_result="SUCCESS",
        ))


# ── TRR-01: Unrecognized source rejected ────────────────────────────

def test_unrecognized_source_rejected(db_connection, test_session_id):
    sid = test_session_id
    _setup_state(db_connection, sid, "UPLOADED")
    signal = TransitionSignal(
        requested_transition="UPLOADED→ANALYZED",
        source="UNKNOWN_SOURCE",
        session_id=sid,
    )
    result = receive_transition_signal(db_connection, signal)
    assert result.result == "REJECTED"                         # TRR-01a
    assert "Unrecognized transition source" in result.error    # TRR-01b


# ── TRR-02: Missing session_id rejected ──────────────────────────────

def test_missing_session_id_rejected(db_connection):
    signal = TransitionSignal(
        requested_transition="EMPTY→UPLOADED",
        source="INGESTION",
        session_id=None,
    )
    result = receive_transition_signal(db_connection, signal)
    assert result.result == "REJECTED"                         # TRR-02a
    assert "session_id is required" in result.error            # TRR-02b


# ── TRR-03: No state_store row treated as EMPTY (forwards) ─────────
#
# When no state_store row exists, the receiver treats the session as
# being in EMPTY state. This is the expected path for the initial
# EMPTY → UPLOADED transition (session just committed to ingestion_log).
# Protection against truly unknown sessions is enforced by the FK
# constraint on dbo.state_store (session_id → raw.ingestion_log).

def test_no_state_row_treated_as_empty(db_connection):
    signal = TransitionSignal(
        requested_transition="EMPTY→UPLOADED",
        source="INGESTION",
        session_id=uuid4(),
    )
    result = receive_transition_signal(db_connection, signal)
    assert result.result == "FORWARD"                          # TRR-03a
    assert result.transition_request is not None               # TRR-03b
    assert result.transition_request.current_state == "EMPTY"  # TRR-03c


# ── TRR-04: Valid EMPTY→UPLOADED forwarded ───────────────────────────

def test_forward_empty_to_uploaded(db_connection, test_session_id):
    sid = test_session_id
    # Create state_store row at EMPTY state
    write_state(db_connection, StateWriteRequest(
        new_state="EMPTY", analysis_status="IDLE",
        trigger="SYSTEM_RECOVERY", session_id=sid,
    ))
    signal = TransitionSignal(
        requested_transition="EMPTY→UPLOADED",
        source="INGESTION",
        session_id=sid,
    )
    result = receive_transition_signal(db_connection, signal)
    assert result.result == "FORWARD"                          # TRR-04a
    assert result.transition_request is not None               # TRR-04b
    assert result.transition_request.current_state == "EMPTY"  # TRR-04c
    assert result.transition_request.requested_transition == "EMPTY→UPLOADED"  # TRR-04d
    assert result.transition_request.source == "INGESTION"     # TRR-04e
    assert result.transition_request.session_id == sid         # TRR-04f


# ── TRR-05: Valid UPLOADED→ANALYZED forwarded ────────────────────────

def test_forward_uploaded_to_analyzed(db_connection, test_session_id):
    sid = test_session_id
    _setup_state(db_connection, sid, "UPLOADED")
    signal = TransitionSignal(
        requested_transition="UPLOADED→ANALYZED",
        source="UI_ANALYZE",
        session_id=sid,
    )
    result = receive_transition_signal(db_connection, signal)
    assert result.result == "FORWARD"                          # TRR-05a
    assert result.transition_request.current_state == "UPLOADED"  # TRR-05b


# ── TRR-06: Valid ANALYZED→APPROVED forwarded ────────────────────────

def test_forward_analyzed_to_approved(db_connection, test_session_id):
    sid = test_session_id
    _setup_state(db_connection, sid, "ANALYZED")
    signal = TransitionSignal(
        requested_transition="ANALYZED→APPROVED",
        source="APPROVAL_DIALOG",
        session_id=sid,
    )
    result = receive_transition_signal(db_connection, signal)
    assert result.result == "FORWARD"                          # TRR-06a
    assert result.transition_request.current_state == "ANALYZED"  # TRR-06b


# ── TRR-07: Idempotent — EMPTY→UPLOADED when already UPLOADED ───────

def test_idempotent_already_uploaded(db_connection, test_session_id):
    sid = test_session_id
    _setup_state(db_connection, sid, "UPLOADED")
    signal = TransitionSignal(
        requested_transition="EMPTY→UPLOADED",
        source="INGESTION",
        session_id=sid,
    )
    result = receive_transition_signal(db_connection, signal)
    assert result.result == "ALREADY_COMPLETE"                 # TRR-07a
    assert result.idempotent_response is not None              # TRR-07b
    assert result.idempotent_response.current_state == "UPLOADED"  # TRR-07c
    assert "already completed" in result.idempotent_response.message  # TRR-07d


# ── TRR-08: Idempotent — UPLOADED→ANALYZED when already ANALYZED ────

def test_idempotent_already_analyzed(db_connection, test_session_id):
    sid = test_session_id
    _setup_state(db_connection, sid, "ANALYZED")
    signal = TransitionSignal(
        requested_transition="UPLOADED→ANALYZED",
        source="UI_ANALYZE",
        session_id=sid,
    )
    result = receive_transition_signal(db_connection, signal)
    assert result.result == "ALREADY_COMPLETE"                 # TRR-08a
    assert result.idempotent_response.current_state == "ANALYZED"  # TRR-08b


# ── TRR-09: Idempotent — ANALYZED→APPROVED when already APPROVED ────

def test_idempotent_already_approved(db_connection, test_session_id):
    sid = test_session_id
    _setup_state(db_connection, sid, "APPROVED")
    signal = TransitionSignal(
        requested_transition="ANALYZED→APPROVED",
        source="APPROVAL_DIALOG",
        session_id=sid,
    )
    result = receive_transition_signal(db_connection, signal)
    assert result.result == "ALREADY_COMPLETE"                 # TRR-09a
    assert result.idempotent_response.current_state == "APPROVED"  # TRR-09b


# ── TRR-10: All three recognized sources accepted ────────────────────

def test_all_recognized_sources(db_connection, test_session_id):
    sid = test_session_id
    _setup_state(db_connection, sid, "UPLOADED")
    for source in ("INGESTION", "UI_ANALYZE", "APPROVAL_DIALOG"):
        signal = TransitionSignal(
            requested_transition="UPLOADED→ANALYZED",
            source=source,
            session_id=sid,
        )
        result = receive_transition_signal(db_connection, signal)
        assert result.result != "REJECTED", f"{source} was rejected"  # TRR-10
