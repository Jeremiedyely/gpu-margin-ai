"""
APPROVED Session Closer — Component 12/12.

Layer: State.

Marks session_status = TERMINAL after Approved Result Writer confirms
write_result = SUCCESS. Blocks all future transition signals for this
session_id by moving the session to terminal status.

On failure: returns FAIL with retry guidance. Retry scheduling is a
wiring concern — this component exposes CLOSER_RETRY_INTERVAL and
CLOSER_MAX_RETRIES as deployment-configurable constants.

Spec: state-machine-design.md — Component 12 — APPROVED Session Closer
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Connection

from app.state_machine.approved_result_writer import ApprovedWriteResult
from app.state_machine.state_store import StateWriteRequest, write_state


# ── Constants (deployment-configurable) ─────────────────────────────

CLOSER_RETRY_INTERVAL: int = 60       # seconds — recommended default
CLOSER_MAX_RETRIES: int = 5           # recommended default


# ── Models ──────────────────────────────────────────────────────────

class CloserResult(BaseModel):
    """Output of the APPROVED Session Closer."""

    result: Literal["SUCCESS", "FAIL"]
    session_id: UUID | None = None
    terminal_at: datetime | None = None
    error: str | None = None

    @classmethod
    def success(
        cls, session_id: UUID, terminal_at: datetime,
    ) -> CloserResult:
        return cls(
            result="SUCCESS",
            session_id=session_id,
            terminal_at=terminal_at,
        )

    @classmethod
    def failed(
        cls, session_id: UUID | None, error: str,
    ) -> CloserResult:
        return cls(result="FAIL", session_id=session_id, error=error)


# ── Public API ──────────────────────────────────────────────────────

def close_session(
    conn: Connection,
    write_result: ApprovedWriteResult,
) -> CloserResult:
    """
    Mark session as TERMINAL after confirmed result write.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection (caller owns outer transaction).
    write_result : ApprovedWriteResult
        Must be SUCCESS from Approved Result Writer.

    Returns
    -------
    CloserResult
        SUCCESS with terminal_at, or FAIL with error.
    """
    # ── Guard: write_result must be SUCCESS ─────────────────────────
    if write_result.result != "SUCCESS":
        return CloserResult.failed(
            session_id=write_result.session_id,
            error=(
                "Session Closer received non-SUCCESS write_result: "
                f"{write_result.result}"
            ),
        )

    if write_result.session_id is None:
        return CloserResult.failed(
            session_id=None,
            error="Session Closer requires session_id",
        )

    session_id = write_result.session_id
    terminal_at = datetime.now(timezone.utc)

    # ── Write session_status = TERMINAL ─────────────────────────────
    try:
        store_result = write_state(
            conn,
            StateWriteRequest(
                new_state="APPROVED",
                trigger="SESSION_CLOSED",
                session_id=session_id,
                session_status="TERMINAL",
            ),
            from_state="APPROVED",
        )

        if store_result.result != "SUCCESS":
            return CloserResult.failed(
                session_id=session_id,
                error=(
                    "Session close failed — session may accept "
                    f"further transitions: {store_result.error}"
                ),
            )

        return CloserResult.success(
            session_id=session_id,
            terminal_at=terminal_at,
        )

    except Exception as exc:
        return CloserResult.failed(
            session_id=session_id,
            error=(
                f"Session close failed — session may accept "
                f"further transitions: {exc}"
            ),
        )
