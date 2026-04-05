"""
Transition Validator — Component 3/12.

Layer: State.

Applies the three-rule valid transition table to incoming
TransitionRequests from the Transition Request Receiver.

Valid transition table:
  EMPTY    + "EMPTY→UPLOADED"    + source=INGESTION       → VALID
  UPLOADED + "UPLOADED→ANALYZED"  + source=UI_ANALYZE      → VALID
  ANALYZED + "ANALYZED→APPROVED"  + source=APPROVAL_DIALOG → VALID

All other combinations → INVALID with named reason.
APPROVED + any → INVALID (terminal state).

Spec: state-machine-design.md — Component 3 — Transition Validator
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.state_machine.transition_request_receiver import TransitionRequest


# ── Valid transition table ──────────────────────────────────────────

# Each entry: (current_state, requested_transition, source) → VALID
_VALID_TRANSITIONS: frozenset[tuple[str, str, str]] = frozenset({
    ("EMPTY", "EMPTY→UPLOADED", "INGESTION"),
    ("UPLOADED", "UPLOADED→ANALYZED", "UI_ANALYZE"),
    ("ANALYZED", "ANALYZED→APPROVED", "APPROVAL_DIALOG"),
})


# ── Models ──────────────────────────────────────────────────────────

class ValidationResult(BaseModel):
    """Output of the Transition Validator."""

    result: Literal["VALID", "INVALID"]
    requested_transition: str
    current_state: str
    session_id: UUID | None = None
    reason: str | None = None

    @classmethod
    def valid(
        cls,
        request: TransitionRequest,
    ) -> ValidationResult:
        return cls(
            result="VALID",
            requested_transition=request.requested_transition,
            current_state=request.current_state,
            session_id=request.session_id,
        )

    @classmethod
    def invalid(
        cls,
        request: TransitionRequest,
        reason: str,
    ) -> ValidationResult:
        return cls(
            result="INVALID",
            requested_transition=request.requested_transition,
            current_state=request.current_state,
            session_id=request.session_id,
            reason=reason,
        )


# ── Public API ──────────────────────────────────────────────────────

def validate_transition(request: TransitionRequest) -> ValidationResult:
    """
    Validate a transition request against the three-rule table.

    Parameters
    ----------
    request : TransitionRequest
        The validated request from the Transition Request Receiver.

    Returns
    -------
    ValidationResult
        VALID if the transition is permitted, INVALID with reason
        if not.
    """
    # Terminal state — no transitions permitted
    if request.current_state == "APPROVED":
        return ValidationResult.invalid(
            request,
            reason="Session is terminal — no further transitions",
        )

    # Check against the three-rule table
    key = (request.current_state, request.requested_transition, request.source)
    if key in _VALID_TRANSITIONS:
        return ValidationResult.valid(request)

    # All other combinations are invalid
    return ValidationResult.invalid(
        request,
        reason=(
            f"Transition {request.requested_transition!r} not valid "
            f"from state {request.current_state!r}"
        ),
    )
