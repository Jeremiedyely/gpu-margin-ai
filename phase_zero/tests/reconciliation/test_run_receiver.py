"""
Tests for Reconciliation Engine Run Receiver — Component 0/7.

RERR-01  Valid signal → READY
RERR-02  session_id matches input
RERR-03  No error on valid signal
RERR-04  Wrong trigger → Pydantic ValidationError
RERR-05  Missing trigger → Pydantic ValidationError
RERR-06  Invalid session_id → Pydantic ValidationError
"""

import uuid

import pytest
from pydantic import ValidationError

from app.reconciliation.run_receiver import RERunSignal, receive_re_run_signal


# ── RERR-01: Valid signal → READY ──
def test_valid_signal_returns_ready():
    signal = RERunSignal(trigger="ANALYZE", session_id=uuid.uuid4())
    result = receive_re_run_signal(signal)
    assert result.result == "READY"


# ── RERR-02: session_id matches input ──
def test_valid_signal_session_id_matches():
    sid = uuid.uuid4()
    signal = RERunSignal(trigger="ANALYZE", session_id=sid)
    result = receive_re_run_signal(signal)
    assert result.session_id == sid


# ── RERR-03: No error on valid signal ──
def test_valid_signal_no_error():
    signal = RERunSignal(trigger="ANALYZE", session_id=uuid.uuid4())
    result = receive_re_run_signal(signal)
    assert result.error is None


# ── RERR-04: Wrong trigger → ValidationError ──
def test_wrong_trigger_raises_validation_error():
    with pytest.raises(ValidationError):
        RERunSignal(trigger="UNKNOWN", session_id=uuid.uuid4())


# ── RERR-05: Missing trigger → ValidationError ──
def test_missing_trigger_raises_validation_error():
    with pytest.raises(ValidationError):
        RERunSignal(session_id=uuid.uuid4())


# ── RERR-06: Invalid session_id → ValidationError ──
def test_invalid_session_id_raises_validation_error():
    with pytest.raises(ValidationError):
        RERunSignal(trigger="ANALYZE", session_id="not-a-uuid")
