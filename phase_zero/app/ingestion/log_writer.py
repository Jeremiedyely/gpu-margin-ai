"""
Ingestion Log Writer — Component 18/19.

Layer 5 — Log Write (pass-through under Option A).

In the Option A architecture, raw.ingestion_log is written INSIDE the atomic
commit transaction (commit.py STEP 2) with status = 'COMMITTED'. This is
required because the 5 raw tables have FK constraints referencing
raw.ingestion_log.session_id — the parent row must exist before children.

Therefore, Component 18 does NOT perform a duplicate DB write. It checks
the CommitResult and produces a LogWriteResult that feeds Component 19
(State Transition Emitter). The log row already exists in the database
when CommitResult = SUCCESS.

Spec: ingestion-module-design.md — Layer 5 — Ingestion Log Writer
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.ingestion.commit import CommitResult


class LogWriteResult(BaseModel):
    """Result of the Ingestion Log Writer check."""

    result: Literal["SUCCESS", "FAIL"]
    session_id: UUID | None = None
    error: str | None = None

    @classmethod
    def success(cls, session_id: UUID) -> LogWriteResult:
        return cls(result="SUCCESS", session_id=session_id)

    @classmethod
    def failed(cls, error: str) -> LogWriteResult:
        return cls(result="FAIL", error=error)


def run_log_writer(commit_result: CommitResult) -> LogWriteResult:
    """
    Check the commit result and produce a LogWriteResult.

    Under Option A, the ingestion_log row was already written atomically
    inside the commit transaction. This function confirms the write
    by checking CommitResult.

    Parameters
    ----------
    commit_result : CommitResult
        Result from run_ingestion_commit().

    Returns
    -------
    LogWriteResult
        SUCCESS with session_id if commit succeeded (log row exists).
        FAIL with error if commit failed (log row was rolled back).
    """
    if commit_result.result == "SUCCESS":
        return LogWriteResult.success(session_id=commit_result.session_id)

    return LogWriteResult.failed(
        error=f"Ingestion log write failed — commit was not successful: "
              f"{commit_result.reason}"
    )
