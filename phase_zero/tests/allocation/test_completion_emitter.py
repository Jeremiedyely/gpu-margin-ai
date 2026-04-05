"""
Tests for Allocation Engine Completion Emitter — Component 10/10.

CE-01  write_result SUCCESS → AllocationEngineResult SUCCESS
CE-02  SUCCESS result contains session_id
CE-03  SUCCESS result error is None
CE-04  write_result FAIL → AllocationEngineResult FAIL
CE-05  FAIL result contains session_id
CE-06  FAIL result contains error from write_result
CE-07  FAIL with no error message → default error provided
CE-08  FAIL with None session_id → session_id is None in result
"""

import uuid

from app.allocation.grain_writer import GrainWriteResult
from app.allocation.completion_emitter import emit_completion


def _success_write(sid=None):
    sid = sid or uuid.uuid4()
    return GrainWriteResult(result="SUCCESS", session_id=sid, row_count=5)


def _fail_write(sid=None, error="grain write failed"):
    sid = sid or uuid.uuid4()
    return GrainWriteResult(result="FAIL", session_id=sid, error=error)


# ── CE-01: write_result SUCCESS → AllocationEngineResult SUCCESS ──
def test_success_write_emits_success():
    result = emit_completion(_success_write())
    assert result.result == "SUCCESS"


# ── CE-02: SUCCESS result contains session_id ──
def test_success_contains_session_id():
    sid = uuid.uuid4()
    result = emit_completion(_success_write(sid=sid))
    assert result.session_id == sid


# ── CE-03: SUCCESS result error is None ──
def test_success_error_is_none():
    result = emit_completion(_success_write())
    assert result.error is None


# ── CE-04: write_result FAIL → AllocationEngineResult FAIL ──
def test_fail_write_emits_fail():
    result = emit_completion(_fail_write())
    assert result.result == "FAIL"


# ── CE-05: FAIL result contains session_id ──
def test_fail_contains_session_id():
    sid = uuid.uuid4()
    result = emit_completion(_fail_write(sid=sid))
    assert result.session_id == sid


# ── CE-06: FAIL result contains error from write_result ──
def test_fail_contains_error():
    result = emit_completion(_fail_write(error="timeout on grain write"))
    assert "timeout on grain write" in result.error


# ── CE-07: FAIL with no error → default error provided ──
def test_fail_no_error_gets_default():
    wr = GrainWriteResult(result="FAIL", session_id=uuid.uuid4(), error=None)
    result = emit_completion(wr)
    assert result.result == "FAIL"
    assert result.error is not None
    assert "no error detail" in result.error.lower()


# ── CE-08: FAIL with None session_id → session_id is None ──
def test_fail_none_session_id():
    wr = GrainWriteResult(result="FAIL", session_id=None, error="critical failure")
    result = emit_completion(wr)
    assert result.result == "FAIL"
    assert result.session_id is None
