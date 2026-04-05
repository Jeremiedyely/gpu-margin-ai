"""
Engine Completion Collector — Component 6/12.

Layer: State.

Collects results from both Allocation Engine and Reconciliation Engine.
Both must arrive and both must be SUCCESS before emitting SUCCESS.
Writes analysis_status = IDLE on completion (success or fail).
Increments retry_count on FAIL. Enforces ANALYSIS_MAX_RETRIES.

Spec: state-machine-design.md — Component 6 — Engine Completion Collector
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import Connection

from app.state_machine.state_store import (
    StateWriteRequest,
    increment_retry_count,
    read_state,
    write_state,
)


# ── Constants ───────────────────────────────────────────────────────

ANALYSIS_MAX_RETRIES: int = 3


# ── Models ──────────────────────────────────────────────────────────

class EngineResult(BaseModel):
    """Result signal from a single engine."""

    engine: Literal["ALLOCATION", "RECONCILIATION"]
    result: Literal["SUCCESS", "FAIL"]
    session_id: UUID
    error: str | None = None


class CollectionResult(BaseModel):
    """Output of the Engine Completion Collector."""

    result: Literal["SUCCESS", "FAIL"]
    session_id: UUID
    errors: list[str] = Field(default_factory=list)
    retry_count: int = 0
    retry_exhausted: bool = False

    @classmethod
    def success(cls, session_id: UUID) -> CollectionResult:
        return cls(result="SUCCESS", session_id=session_id)

    @classmethod
    def failed(
        cls,
        session_id: UUID,
        errors: list[str],
        retry_count: int = 0,
        retry_exhausted: bool = False,
    ) -> CollectionResult:
        return cls(
            result="FAIL",
            session_id=session_id,
            errors=errors,
            retry_count=retry_count,
            retry_exhausted=retry_exhausted,
        )


# ── Public API ──────────────────────────────────────────────────────

def collect_engine_results(
    conn: Connection,
    ae_result: EngineResult,
    re_result: EngineResult,
) -> CollectionResult:
    """
    Collect results from both engines and emit a collection result.

    Both engines must report SUCCESS for the collector to emit SUCCESS.
    On any FAIL, analysis_status is reset to IDLE and retry_count is
    incremented. If retry_count >= ANALYSIS_MAX_RETRIES, the session
    is flagged for operator intervention.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection (caller owns outer transaction).
    ae_result : EngineResult
        Allocation Engine result (engine="ALLOCATION").
    re_result : EngineResult
        Reconciliation Engine result (engine="RECONCILIATION").

    Returns
    -------
    CollectionResult
        SUCCESS if both engines succeeded, FAIL with named errors
        otherwise.
    """
    session_id = ae_result.session_id

    # ── Validate session_id consistency ──────────────────────────────
    if ae_result.session_id != re_result.session_id:
        return CollectionResult.failed(
            session_id=session_id,
            errors=[
                "Engine session_id mismatch: "
                f"AE={ae_result.session_id}, RE={re_result.session_id}"
            ],
        )

    # ── Both SUCCESS ────────────────────────────────────────────────
    if ae_result.result == "SUCCESS" and re_result.result == "SUCCESS":
        # Write analysis_status = IDLE
        write_state(
            conn,
            StateWriteRequest(
                new_state="UPLOADED",
                analysis_status="IDLE",
                trigger="ENGINES_COMPLETE",
                session_id=session_id,
            ),
        )
        return CollectionResult.success(session_id=session_id)

    # ── At least one FAIL ───────────────────────────────────────────
    errors: list[str] = []
    if ae_result.result == "FAIL":
        errors.append(
            f"Allocation Engine failed: {ae_result.error or 'no error detail'}"
        )
    if re_result.result == "FAIL":
        errors.append(
            f"Reconciliation Engine failed: {re_result.error or 'no error detail'}"
        )

    # Write analysis_status = IDLE (clear ANALYZING)
    write_state(
        conn,
        StateWriteRequest(
            new_state="UPLOADED",
            analysis_status="IDLE",
            trigger="ANALYSIS_FAILED",
            session_id=session_id,
        ),
    )

    # Increment retry_count
    increment_retry_count(conn, session_id)

    # Read updated retry_count
    snapshot = read_state(conn, session_id)
    current_retry = snapshot.retry_count if snapshot else 0
    retry_exhausted = current_retry >= ANALYSIS_MAX_RETRIES

    if retry_exhausted:
        errors.append(
            f"Analysis has failed {current_retry} times for this session. "
            f"Contact your operator with Session ID: {session_id} "
            f"before retrying."
        )

    return CollectionResult.failed(
        session_id=session_id,
        errors=errors,
        retry_count=current_retry,
        retry_exhausted=retry_exhausted,
    )
