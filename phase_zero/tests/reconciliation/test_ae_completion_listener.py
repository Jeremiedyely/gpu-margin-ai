"""
Tests for AE Completion Listener — Component 3/7.

Pure logic tests — no DB. Validates signal→result transformation,
timestamp capture, and Contract 3 boundary behavior.

Assertions: AECL-01 through AECL-10
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.allocation.completion_emitter import AllocationEngineResult
from app.reconciliation.ae_completion_listener import (
    ListenerResult,
    listen_for_ae_completion,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _ae_success(session_id=None):
    sid = session_id or uuid4()
    return AllocationEngineResult.success(session_id=sid), sid


def _ae_fail(session_id=None, error="AE grain write failed"):
    sid = session_id or uuid4()
    return AllocationEngineResult.failed(session_id=sid, error=error), sid


# ── AECL-01: SUCCESS signal → READY ─────────────────────────────────

def test_success_signal_produces_ready():
    ae, sid = _ae_success()
    result = listen_for_ae_completion(ae)
    assert result.result == "READY"                          # AECL-01


# ── AECL-02: READY carries correct session_id ───────────────────────

def test_ready_carries_session_id():
    ae, sid = _ae_success()
    result = listen_for_ae_completion(ae)
    assert result.session_id == sid                          # AECL-02


# ── AECL-03: READY carries t_ae_complete timestamp ──────────────────

def test_ready_carries_timestamp():
    before = datetime.now(timezone.utc)
    ae, _ = _ae_success()
    result = listen_for_ae_completion(ae)
    after = datetime.now(timezone.utc)
    assert before <= result.t_ae_complete <= after           # AECL-03


# ── AECL-04: READY has no error ─────────────────────────────────────

def test_ready_has_no_error():
    ae, _ = _ae_success()
    result = listen_for_ae_completion(ae)
    assert result.error is None                              # AECL-04


# ── AECL-05: FAIL signal → BLOCKED ──────────────────────────────────

def test_fail_signal_produces_blocked():
    ae, _ = _ae_fail()
    result = listen_for_ae_completion(ae)
    assert result.result == "BLOCKED"                        # AECL-05


# ── AECL-06: BLOCKED carries correct session_id ─────────────────────

def test_blocked_carries_session_id():
    ae, sid = _ae_fail()
    result = listen_for_ae_completion(ae)
    assert result.session_id == sid                          # AECL-06


# ── AECL-07: BLOCKED carries t_ae_complete timestamp ────────────────

def test_blocked_carries_timestamp():
    before = datetime.now(timezone.utc)
    ae, _ = _ae_fail()
    result = listen_for_ae_completion(ae)
    after = datetime.now(timezone.utc)
    assert before <= result.t_ae_complete <= after           # AECL-07


# ── AECL-08: BLOCKED carries error from AE signal ───────────────────

def test_blocked_carries_ae_error():
    ae, _ = _ae_fail(error="grain write rolled back")
    result = listen_for_ae_completion(ae)
    assert result.error == "grain write rolled back"         # AECL-08


# ── AECL-09: FAIL with no error detail → default message ────────────

def test_blocked_default_error_when_none():
    sid = uuid4()
    ae = AllocationEngineResult(result="FAIL", session_id=sid, error=None)
    result = listen_for_ae_completion(ae)
    assert "Allocation Engine failed" in result.error        # AECL-09


# ── AECL-10: Missing session_id in AE signal → BLOCKED + source label

def test_missing_session_id_blocked_with_source_label():
    ae = AllocationEngineResult(result="FAIL", session_id=None, error="unknown")
    result = listen_for_ae_completion(ae)
    assert result.result == "BLOCKED"                        # AECL-10a
    assert "[Reconciliation Engine — AE Completion Listener]" in result.error  # AECL-10b
