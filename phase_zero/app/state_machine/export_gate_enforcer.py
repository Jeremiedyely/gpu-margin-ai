"""
Export Gate Enforcer — Component 11/12.

Layer: State.

Responds OPEN or BLOCKED to the Export Module APPROVED State Gate.
Reads application_state and write_result from State Store.
Four mutually exclusive evaluation paths (P1 #27 FIX — NULL before ≠ SUCCESS):

1. APPROVED + write_result=SUCCESS     → OPEN
2. state ≠ APPROVED                    → BLOCKED (GATE_BLOCKED_NOT_APPROVED)
3. APPROVED + write_result IS NULL     → BLOCKED (GATE_BLOCKED_WRITE_NULL)
4. APPROVED + write_result ≠ SUCCESS   → BLOCKED (GATE_BLOCKED_WRITE_FAILED)
5. State Store unreadable              → BLOCKED (GATE_BLOCKED_STATE_UNREADABLE)

Spec: state-machine-design.md — Component 11 — Export Gate Enforcer
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Connection

from app.state_machine.state_store import read_state


# ── Models ──────────────────────────────────────────────────────────

GateResult = Literal["OPEN", "BLOCKED"]

GateReasonCode = Literal[
    "GATE_OPEN",
    "GATE_BLOCKED_NOT_APPROVED",
    "GATE_BLOCKED_WRITE_NULL",
    "GATE_BLOCKED_WRITE_FAILED",
    "GATE_BLOCKED_STATE_UNREADABLE",
]


class GateResponse(BaseModel):
    """Output of the Export Gate Enforcer."""

    result: GateResult
    reason_code: GateReasonCode
    reason: str | None = None
    session_id: UUID | None = None

    @classmethod
    def open(cls, session_id: UUID) -> GateResponse:
        return cls(
            result="OPEN",
            reason_code="GATE_OPEN",
            session_id=session_id,
        )

    @classmethod
    def blocked(
        cls,
        reason_code: GateReasonCode,
        reason: str,
        session_id: UUID | None = None,
    ) -> GateResponse:
        return cls(
            result="BLOCKED",
            reason_code=reason_code,
            reason=reason,
            session_id=session_id,
        )


# ── Public API ──────────────────────────────────────────────────────

def check_export_gate(
    conn: Connection,
    session_id: UUID,
) -> GateResponse:
    """
    Evaluate whether the export gate is OPEN or BLOCKED.

    Reads application_state and write_result from State Store for
    the given session_id. Returns a structured GateResponse with
    result, reason_code, and human-readable reason.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection (caller owns outer transaction).
    session_id : UUID
        The session to evaluate.

    Returns
    -------
    GateResponse
        OPEN if state=APPROVED and write_result=SUCCESS,
        BLOCKED with specific reason_code otherwise.
    """
    # ── Read state ──────────────────────────────────────────────────
    try:
        snapshot = read_state(conn, session_id)
    except Exception:
        return GateResponse.blocked(
            reason_code="GATE_BLOCKED_STATE_UNREADABLE",
            reason="State unreadable — export blocked",
            session_id=session_id,
        )

    if snapshot is None:
        return GateResponse.blocked(
            reason_code="GATE_BLOCKED_STATE_UNREADABLE",
            reason="State unreadable — export blocked",
            session_id=session_id,
        )

    # ── Condition 2: state ≠ APPROVED ───────────────────────────────
    if snapshot.application_state != "APPROVED":
        return GateResponse.blocked(
            reason_code="GATE_BLOCKED_NOT_APPROVED",
            reason=(
                f"State is {snapshot.application_state} "
                f"— export requires APPROVED"
            ),
            session_id=session_id,
        )

    # ── Condition 3: APPROVED + write_result IS NULL (P1 #27) ──────
    if snapshot.write_result is None:
        return GateResponse.blocked(
            reason_code="GATE_BLOCKED_WRITE_NULL",
            reason=(
                "Approved result table write not yet confirmed "
                "— export blocked (write_result not yet set)"
            ),
            session_id=session_id,
        )

    # ── Condition 1: APPROVED + write_result = SUCCESS → OPEN ──────
    if snapshot.write_result == "SUCCESS":
        return GateResponse.open(session_id=session_id)

    # ── Condition 4: APPROVED + write_result ≠ SUCCESS (NOT NULL) ──
    return GateResponse.blocked(
        reason_code="GATE_BLOCKED_WRITE_FAILED",
        reason="Approved result table not confirmed — export blocked",
        session_id=session_id,
    )
