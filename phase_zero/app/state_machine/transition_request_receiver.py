"""
Transition Request Receiver — Component 2/12.

Layer: State.

Single entry point for all transition signals. Validates the signal
source, reads current state from the State Store, checks the
idempotency contract (P3 #28), and forwards to the Transition Validator.

Recognized sources:
  INGESTION       — Ingestion State Transition Emitter (EMPTY → UPLOADED)
  UI_ANALYZE      — UI [Analyze] button click          (UPLOADED → ANALYZED)
  APPROVAL_DIALOG — Approve Confirmation Dialog FIRE   (ANALYZED → APPROVED)

Spec: state-machine-design.md — Component 2 — Transition Request Receiver
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Connection

from app.state_machine.state_store import read_state


# ── Constants ───────────────────────────────────────────────────────

RECOGNIZED_SOURCES: frozenset[str] = frozenset({
    "INGESTION",
    "UI_ANALYZE",
    "APPROVAL_DIALOG",
})

# Maps requested_transition → the target state that signals completion
_TRANSITION_TARGET: dict[str, str] = {
    "EMPTY→UPLOADED": "UPLOADED",
    "UPLOADED→ANALYZED": "ANALYZED",
    "ANALYZED→APPROVED": "APPROVED",
}


# ── Models ──────────────────────────────────────────────────────────

class TransitionSignal(BaseModel):
    """Incoming signal from an external source."""

    requested_transition: str
    source: str
    session_id: UUID | None = None


class TransitionRequest(BaseModel):
    """Validated request forwarded to Transition Validator."""

    current_state: str
    requested_transition: str
    source: str
    session_id: UUID | None = None


class IdempotentResponse(BaseModel):
    """Returned when the requested transition is already complete."""

    result: Literal["ALREADY_COMPLETE"] = "ALREADY_COMPLETE"
    current_state: str
    message: str


class ReceiverResult(BaseModel):
    """
    Output of the Transition Request Receiver.

    Exactly one of transition_request, idempotent_response, or error
    is populated.
    """

    result: Literal["FORWARD", "ALREADY_COMPLETE", "REJECTED"]
    transition_request: TransitionRequest | None = None
    idempotent_response: IdempotentResponse | None = None
    error: str | None = None

    @classmethod
    def forward(cls, request: TransitionRequest) -> ReceiverResult:
        return cls(result="FORWARD", transition_request=request)

    @classmethod
    def already_complete(cls, response: IdempotentResponse) -> ReceiverResult:
        return cls(result="ALREADY_COMPLETE", idempotent_response=response)

    @classmethod
    def rejected(cls, error: str) -> ReceiverResult:
        return cls(result="REJECTED", error=error)


# ── Public API ──────────────────────────────────────────────────────

def receive_transition_signal(
    conn: Connection,
    signal: TransitionSignal,
) -> ReceiverResult:
    """
    Process an incoming transition signal.

    1. Validate source is recognized.
    2. Read current_state from State Store.
    3. Check idempotency: if current_state already equals the target
       state of the requested transition → ALREADY_COMPLETE (P3 #28).
    4. Forward to Transition Validator as TransitionRequest.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection for State Store read.
    signal : TransitionSignal
        The incoming transition signal.

    Returns
    -------
    ReceiverResult
        FORWARD (new transition), ALREADY_COMPLETE (idempotent no-op),
        or REJECTED (bad source / unreadable state).
    """
    # ── 1. Source validation ────────────────────────────────────────
    if signal.source not in RECOGNIZED_SOURCES:
        return ReceiverResult.rejected(
            error=f"Unrecognized transition source: {signal.source!r}",
        )

    # ── 2. Read current state ───────────────────────────────────────
    #   For INGESTION source, session_id is required to read state.
    #   For UI_ANALYZE, session_id may be None — the Analysis Dispatcher
    #   resolves it later. But we still need to read state, so we need
    #   at least one active session. For now, if session_id is None,
    #   we cannot read state — reject.
    if signal.session_id is None:
        return ReceiverResult.rejected(
            error="Cannot process transition — session_id is required",
        )

    snapshot = read_state(conn, signal.session_id)
    if snapshot is None:
        return ReceiverResult.rejected(
            error=(
                "Cannot process transition — state unreadable: "
                f"no state_store row for session_id {signal.session_id}"
            ),
        )

    current_state = snapshot.application_state

    # ── 3. Idempotency check (P3 #28) ──────────────────────────────
    target = _TRANSITION_TARGET.get(signal.requested_transition)
    if target is not None and current_state == target:
        return ReceiverResult.already_complete(
            IdempotentResponse(
                current_state=current_state,
                message=(
                    f"Transition {signal.requested_transition} already "
                    f"completed for session {signal.session_id}. "
                    f"No action taken."
                ),
            ),
        )

    # ── 4. Forward to Transition Validator ──────────────────────────
    return ReceiverResult.forward(
        TransitionRequest(
            current_state=current_state,
            requested_transition=signal.requested_transition,
            source=signal.source,
            session_id=signal.session_id,
        ),
    )
