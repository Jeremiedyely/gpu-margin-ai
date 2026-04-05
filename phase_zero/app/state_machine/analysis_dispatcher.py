"""
Analysis Dispatcher — Component 5/12.

Layer: State.

Receives a VALID validation result for UPLOADED→ANALYZED. Resolves
session_id from State Store, guards against double-dispatch
(analysis_status = ANALYZING), writes analysis_status = ANALYZING
to State Store, and emits run signals to both engines.

Spec: state-machine-design.md — Component 5 — Analysis Dispatcher
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Connection

from app.state_machine.state_store import (
    StateWriteRequest,
    read_state,
    write_state,
)
from app.state_machine.transition_validator import ValidationResult


# ── Models ──────────────────────────────────────────────────────────

class DispatchResult(BaseModel):
    """Output of the Analysis Dispatcher."""

    result: Literal["DISPATCHED", "FAIL"]
    session_id: UUID | None = None
    error: str | None = None

    @classmethod
    def dispatched(cls, session_id: UUID) -> DispatchResult:
        return cls(result="DISPATCHED", session_id=session_id)

    @classmethod
    def failed(cls, session_id: UUID | None, error: str) -> DispatchResult:
        return cls(result="FAIL", session_id=session_id, error=error)


# ── Public API ──────────────────────────────────────────────────────

def dispatch_analysis(
    conn: Connection,
    validation: ValidationResult,
) -> DispatchResult:
    """
    Dispatch analysis engines for the UPLOADED→ANALYZED transition.

    Steps:
    1. Guard: VALID + correct transition.
    2. Resolve session_id from State Store.
    3. Guard: analysis_status ≠ ANALYZING (double-dispatch prevention).
    4. Write analysis_status = ANALYZING to State Store.
    5. Return DISPATCHED (engine signals emitted by caller).

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection (caller owns outer transaction).
    validation : ValidationResult
        Must be VALID with requested_transition = "UPLOADED→ANALYZED".

    Returns
    -------
    DispatchResult
        DISPATCHED if analysis_status set and engines ready,
        FAIL on guard violation or write failure.
    """
    # ── 1. Guard: VALID + correct transition ────────────────────────
    if validation.result != "VALID":
        return DispatchResult.failed(
            session_id=validation.session_id,
            error=(
                "Analysis Dispatcher received non-VALID validation: "
                f"{validation.result}"
            ),
        )

    if validation.requested_transition != "UPLOADED→ANALYZED":
        return DispatchResult.failed(
            session_id=validation.session_id,
            error=(
                "Analysis Dispatcher received wrong transition: "
                f"{validation.requested_transition!r}"
            ),
        )

    # ── 2. Resolve session_id from State Store ──────────────────────
    #   The UI [Analyze] click may not carry session_id. The Dispatcher
    #   resolves it from State Store (set at EMPTY→UPLOADED).
    session_id = validation.session_id
    if session_id is None:
        return DispatchResult.failed(
            session_id=None,
            error=(
                "Session ID not found in State Store — "
                "cannot dispatch engines"
            ),
        )

    snapshot = read_state(conn, session_id)
    if snapshot is None:
        return DispatchResult.failed(
            session_id=session_id,
            error=(
                "Session ID not found in State Store — "
                f"cannot dispatch engines: {session_id}"
            ),
        )

    # ── 3. Double-dispatch guard (C-1/W-3 FIX) ─────────────────────
    if snapshot.analysis_status == "ANALYZING":
        return DispatchResult.failed(
            session_id=session_id,
            error=(
                "Analysis already in progress for this session — "
                "wait for the current run to complete or time out. "
                f"Session ID: {session_id}"
            ),
        )

    # ── 4. Write analysis_status = ANALYZING ────────────────────────
    store_result = write_state(
        conn,
        StateWriteRequest(
            new_state="UPLOADED",
            analysis_status="ANALYZING",
            trigger="ANALYSIS_DISPATCHED",
            session_id=session_id,
        ),
    )

    if store_result.result != "SUCCESS":
        # Rollback: ensure analysis_status stays IDLE
        write_state(
            conn,
            StateWriteRequest(
                new_state="UPLOADED",
                analysis_status="IDLE",
                trigger="SYSTEM_RECOVERY",
                session_id=session_id,
            ),
        )
        return DispatchResult.failed(
            session_id=session_id,
            error=(
                "Analysis dispatch failed — analysis_status write failed: "
                f"{store_result.error}"
            ),
        )

    # ── 5. DISPATCHED — caller emits engine run signals ─────────────
    return DispatchResult.dispatched(session_id=session_id)
