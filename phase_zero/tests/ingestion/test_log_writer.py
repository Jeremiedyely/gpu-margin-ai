"""
Tests for Ingestion Log Writer — Component 18/19.

LW-01  SUCCESS commit → LogWriteResult = SUCCESS
LW-02  SUCCESS commit → session_id matches
LW-03  SUCCESS commit → error is None
LW-04  FAIL commit → LogWriteResult = FAIL
LW-05  FAIL commit → session_id is None
LW-06  FAIL commit → error contains reason
"""

import uuid

from app.ingestion.commit import CommitResult
from app.ingestion.log_writer import run_log_writer


def _success_commit() -> CommitResult:
    return CommitResult.success(session_id=uuid.uuid4())


def _failed_commit() -> CommitResult:
    return CommitResult.failed(
        session_id=uuid.uuid4(),
        reason="Session dropped",
    )


# ── LW-01: SUCCESS commit → SUCCESS result ──
def test_success_commit_returns_success():
    commit = _success_commit()
    result = run_log_writer(commit)
    assert result.result == "SUCCESS"


# ── LW-02: SUCCESS commit → session_id matches ──
def test_success_commit_session_id_matches():
    commit = _success_commit()
    result = run_log_writer(commit)
    assert result.session_id == commit.session_id


# ── LW-03: SUCCESS commit → error is None ──
def test_success_commit_no_error():
    commit = _success_commit()
    result = run_log_writer(commit)
    assert result.error is None


# ── LW-04: FAIL commit → FAIL result ──
def test_failed_commit_returns_fail():
    commit = _failed_commit()
    result = run_log_writer(commit)
    assert result.result == "FAIL"


# ── LW-05: FAIL commit → session_id is None ──
def test_failed_commit_session_id_is_none():
    commit = _failed_commit()
    result = run_log_writer(commit)
    assert result.session_id is None


# ── LW-06: FAIL commit → error contains reason ──
def test_failed_commit_error_contains_reason():
    commit = _failed_commit()
    result = run_log_writer(commit)
    assert "Session dropped" in result.error
