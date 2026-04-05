"""
Tests for State Transition Emitter — Component 19/19.

EMIT-01  SUCCESS log → signal is not None
EMIT-02  SUCCESS log → signal.signal = 'FIRE'
EMIT-03  SUCCESS log → requested_transition = 'EMPTY→UPLOADED'
EMIT-04  SUCCESS log → source = 'INGESTION'
EMIT-05  SUCCESS log → session_id matches
EMIT-06  FAIL log → signal is None (State Machine not contacted)
EMIT-07  FAIL log → no exception raised
EMIT-08  SUCCESS log with None session_id → signal is None (guard)
"""

import uuid

from app.ingestion.log_writer import LogWriteResult
from app.ingestion.emitter import emit_state_transition


def _success_log() -> LogWriteResult:
    return LogWriteResult.success(session_id=uuid.uuid4())


def _failed_log() -> LogWriteResult:
    return LogWriteResult.failed(error="Ingestion log write failed")


# ── EMIT-01: SUCCESS log → signal emitted ──
def test_success_log_emits_signal():
    log = _success_log()
    signal = emit_state_transition(log)
    assert signal is not None


# ── EMIT-02: Signal field = FIRE ──
def test_signal_is_fire():
    log = _success_log()
    signal = emit_state_transition(log)
    assert signal.signal == "FIRE"


# ── EMIT-03: Requested transition = EMPTY→UPLOADED ──
def test_requested_transition():
    log = _success_log()
    signal = emit_state_transition(log)
    assert signal.requested_transition == "EMPTY→UPLOADED"


# ── EMIT-04: Source = INGESTION ──
def test_source_is_ingestion():
    log = _success_log()
    signal = emit_state_transition(log)
    assert signal.source == "INGESTION"


# ── EMIT-05: session_id matches ──
def test_session_id_matches():
    log = _success_log()
    signal = emit_state_transition(log)
    assert signal.session_id == log.session_id


# ── EMIT-06: FAIL log → None (no signal) ──
def test_failed_log_returns_none():
    log = _failed_log()
    signal = emit_state_transition(log)
    assert signal is None


# ── EMIT-07: FAIL log → no exception ──
def test_failed_log_no_exception():
    log = _failed_log()
    try:
        emit_state_transition(log)
    except Exception:
        raise AssertionError("emit_state_transition raised on FAIL log")


# ── EMIT-08: SUCCESS result but None session_id → guard returns None ──
def test_none_session_id_guard():
    log = LogWriteResult(result="SUCCESS", session_id=None)
    signal = emit_state_transition(log)
    assert signal is None
