"""
Tests for Allocation Engine Run Receiver — Component 0/10.

RR-01  Valid ANALYZE signal → READY
RR-02  Valid signal → session_id matches
RR-03  Valid signal → error is None
RR-04  Wrong trigger → Pydantic rejects at construction
RR-05  Missing trigger → Pydantic rejects at construction
RR-06  Invalid session_id → Pydantic rejects at construction
"""

import uuid

import pytest
from pydantic import ValidationError

from app.allocation.run_receiver import RunSignal, receive_run_signal


def _valid_signal() -> RunSignal:
    return RunSignal(trigger="ANALYZE", session_id=uuid.uuid4())


# ── RR-01: Valid ANALYZE signal → READY ──
def test_valid_signal_returns_ready():
    signal = _valid_signal()
    result = receive_run_signal(signal)
    assert result.result == "READY"


# ── RR-02: Valid signal → session_id matches ──
def test_valid_signal_session_id_matches():
    signal = _valid_signal()
    result = receive_run_signal(signal)
    assert result.session_id == signal.session_id


# ── RR-03: Valid signal → error is None ──
def test_valid_signal_no_error():
    signal = _valid_signal()
    result = receive_run_signal(signal)
    assert result.error is None


# ── RR-04: Wrong trigger → Pydantic rejects at construction ──
def test_wrong_trigger_raises_validation_error():
    with pytest.raises(ValidationError):
        RunSignal(trigger="UNKNOWN", session_id=uuid.uuid4())


# ── RR-05: Missing trigger → Pydantic rejects at construction ──
def test_missing_trigger_raises_validation_error():
    with pytest.raises(ValidationError):
        RunSignal(session_id=uuid.uuid4())


# ── RR-06: Invalid session_id → Pydantic rejects at construction ──
def test_invalid_session_id_raises_validation_error():
    with pytest.raises(ValidationError):
        RunSignal(trigger="ANALYZE", session_id="not-a-uuid")
