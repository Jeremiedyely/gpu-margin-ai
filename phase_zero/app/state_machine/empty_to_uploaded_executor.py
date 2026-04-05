"""
EMPTY → UPLOADED Executor — Component 4/12.

Layer: State.

Receives a VALID validation result for the EMPTY→UPLOADED transition
and writes the new state to the State Store. Sets analysis_status=IDLE
(analysis has not started yet) and trigger=INGESTION_COMPLETE.

Spec: state-machine-design.md — Component 4 — EMPTY → UPLOADED Executor
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Connection

from app.state_machine.state_store import StateWriteRequest, write_state
from app.state_machine.transition_validator import ValidationResult


# ── Models ──────────────────────────────────────────────────────────

class TransitionResult(BaseModel):
    """Output of a transition executor."""

    result: Literal["SUCCESS", "FAIL"]
    new_state: str
    session_id: UUID | None = None
    error: str | None = None

    @classmethod
    def success(cls, new_state: str, session_id: UUID) -> TransitionResult:
        return cls(result="SUCCESS", new_state=new_state, session_id=session_id)

    @classmethod
    def failed(
        cls, new_state: str, session_id: UUID | None, error: str,
    ) -> TransitionResult:
        return cls(
            result="FAIL", new_state=new_state,
            session_id=session_id, error=error,
        )


# ── Public API ──────────────────────────────────────────────────────

def execute_empty_to_uploaded(
    conn: Connection,
    validation: ValidationResult,
) -> TransitionResult:
    """
    Execute the EMPTY → UPLOADED transition.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection (caller owns outer transaction).
    validation : ValidationResult
        Must be VALID with requested_transition = "EMPTY→UPLOADED".

    Returns
    -------
    TransitionResult
        SUCCESS if State Store write completes, FAIL on error.
    """
    # Guard: only execute on VALID result for this transition
    if validation.result != "VALID":
        return TransitionResult.failed(
            new_state="UPLOADED",
            session_id=validation.session_id,
            error=(
                "EMPTY→UPLOADED executor received non-VALID validation: "
                f"{validation.result}"
            ),
        )

    if validation.requested_transition != "EMPTY→UPLOADED":
        return TransitionResult.failed(
            new_state="UPLOADED",
            session_id=validation.session_id,
            error=(
                "EMPTY→UPLOADED executor received wrong transition: "
                f"{validation.requested_transition!r}"
            ),
        )

    if validation.session_id is None:
        return TransitionResult.failed(
            new_state="UPLOADED",
            session_id=None,
            error="EMPTY→UPLOADED transition requires session_id",
        )

    # Write to State Store
    store_result = write_state(
        conn,
        StateWriteRequest(
            new_state="UPLOADED",
            analysis_status="IDLE",
            trigger="INGESTION_COMPLETE",
            session_id=validation.session_id,
        ),
        from_state="EMPTY",
    )

    if store_result.result == "SUCCESS":
        return TransitionResult.success(
            new_state="UPLOADED",
            session_id=validation.session_id,
        )

    return TransitionResult.failed(
        new_state="UPLOADED",
        session_id=validation.session_id,
        error=(
            "EMPTY→UPLOADED transition failed — state not persisted: "
            f"{store_result.error}"
        ),
    )
