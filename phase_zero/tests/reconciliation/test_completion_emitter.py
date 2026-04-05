"""
Tests for Reconciliation Engine Completion Emitter — Component 7/7.

Pure logic tests — no DB. Validates SUCCESS, FAIL, and FATAL signal emission.

Assertions: RECE-01 through RECE-08
"""

from __future__ import annotations

from uuid import uuid4

from app.reconciliation.completion_emitter import (
    ReconciliationEngineResult,
    emit_re_completion,
)
from app.reconciliation.result_aggregator import AggregatedResults
from app.reconciliation.result_writer import REWriteResult


# ── RECE-01: write SUCCESS → SUCCESS signal ──────────────────────────

def test_write_success_emits_success():
    sid = uuid4()
    wr = REWriteResult.success(session_id=sid)
    result = emit_re_completion(write_result=wr)
    assert result.result == "SUCCESS"                        # RECE-01


# ── RECE-02: SUCCESS carries session_id ──────────────────────────────

def test_success_carries_session_id():
    sid = uuid4()
    wr = REWriteResult.success(session_id=sid)
    result = emit_re_completion(write_result=wr)
    assert result.session_id == sid                          # RECE-02


# ── RECE-03: SUCCESS has no error ────────────────────────────────────

def test_success_has_no_error():
    sid = uuid4()
    wr = REWriteResult.success(session_id=sid)
    result = emit_re_completion(write_result=wr)
    assert result.error is None                              # RECE-03


# ── RECE-04: write FAIL → FAIL signal ───────────────────────────────

def test_write_fail_emits_fail():
    sid = uuid4()
    wr = REWriteResult.failed(session_id=sid, error="write rolled back")
    result = emit_re_completion(write_result=wr)
    assert result.result == "FAIL"                           # RECE-04


# ── RECE-05: FAIL carries error from writer ──────────────────────────

def test_fail_carries_writer_error():
    sid = uuid4()
    wr = REWriteResult.failed(session_id=sid, error="write rolled back")
    result = emit_re_completion(write_result=wr)
    assert result.error == "write rolled back"               # RECE-05


# ── RECE-06: FATAL aggregation → FAIL signal ────────────────────────

def test_fatal_aggregation_emits_fail():
    sid = uuid4()
    agg = AggregatedResults.fatal(error="Check 1 source unreadable")
    result = emit_re_completion(aggregated=agg, session_id=sid)
    assert result.result == "FAIL"                           # RECE-06a
    assert "Check 1" in result.error                         # RECE-06b


# ── RECE-07: FAIL with no error detail → default message ────────────

def test_fail_default_error():
    sid = uuid4()
    wr = REWriteResult(result="FAIL", session_id=sid, error=None)
    result = emit_re_completion(write_result=wr)
    assert "Reconciliation engine failed" in result.error    # RECE-07


# ── RECE-08: No inputs → defensive FAIL ─────────────────────────────

def test_no_inputs_defensive_fail():
    result = emit_re_completion()
    assert result.result == "FAIL"                           # RECE-08a
    assert "no write_result" in result.error                 # RECE-08b
