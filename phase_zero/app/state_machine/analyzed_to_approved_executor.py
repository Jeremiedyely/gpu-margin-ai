"""
ANALYZED → APPROVED Executor — Component 8/12.

Layer: State.

Receives a VALID validation result for ANALYZED→APPROVED from the
Approve Confirmation Dialog. Does NOT write APPROVED to State Store
directly (C-3 FIX). Validates the transition and passes to the
Approved Result Writer (Component 9), which performs the single
atomic write of application_state=APPROVED + write_result (P1 #26).

Spec: state-machine-design.md — Component 8 — ANALYZED → APPROVED Executor
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.state_machine.transition_validator import ValidationResult


# ── Models ──────────────────────────────────────────────────────────

class ApprovalTransitionResult(BaseModel):
    """
    Output of the ANALYZED → APPROVED Executor.

    On SUCCESS, carries trigger + session_id to the Approved Result
    Writer. This component does NOT write APPROVED — Component 9 does.
    """

    result: Literal["SUCCESS", "FAIL"]
    new_state: str = "APPROVED"
    session_id: UUID | None = None
    trigger: str | None = None
    error: str | None = None

    @classmethod
    def success(cls, session_id: UUID) -> ApprovalTransitionResult:
        return cls(
            result="SUCCESS",
            new_state="APPROVED",
            session_id=session_id,
            trigger="CFO_APPROVAL",
        )

    @classmethod
    def failed(
        cls, session_id: UUID | None, error: str,
    ) -> ApprovalTransitionResult:
        return cls(
            result="FAIL",
            new_state="APPROVED",
            session_id=session_id,
            error=error,
        )


# ── Public API ──────────────────────────────────────────────────────

def execute_analyzed_to_approved(
    validation: ValidationResult,
) -> ApprovalTransitionResult:
    """
    Validate the ANALYZED → APPROVED transition.

    Does NOT write to State Store. Returns SUCCESS with trigger and
    session_id for the Approved Result Writer (Component 9) to
    perform the atomic write.

    Parameters
    ----------
    validation : ValidationResult
        Must be VALID with requested_transition = "ANALYZED→APPROVED".

    Returns
    -------
    ApprovalTransitionResult
        SUCCESS (pass to Component 9) or FAIL (do not trigger writer).
    """
    # Guard: only execute on VALID result for this transition
    if validation.result != "VALID":
        return ApprovalTransitionResult.failed(
            session_id=validation.session_id,
            error=(
                "ANALYZED→APPROVED executor received non-VALID validation: "
                f"{validation.result}"
            ),
        )

    if validation.requested_transition != "ANALYZED→APPROVED":
        return ApprovalTransitionResult.failed(
            session_id=validation.session_id,
            error=(
                "ANALYZED→APPROVED executor received wrong transition: "
                f"{validation.requested_transition!r}"
            ),
        )

    if validation.session_id is None:
        return ApprovalTransitionResult.failed(
            session_id=None,
            error="ANALYZED→APPROVED transition requires session_id",
        )

    # Validation passed — pass to Approved Result Writer (Component 9)
    # This component does NOT write APPROVED to State Store (C-3 FIX)
    return ApprovalTransitionResult.success(session_id=validation.session_id)
