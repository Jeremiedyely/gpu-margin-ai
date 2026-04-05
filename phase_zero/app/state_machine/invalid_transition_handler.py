"""
Invalid Transition Rejection Handler — Component 10/12.

Layer: State.

Two input paths:
1. Transition Validator → INVALID result → rejection_type = INVALID_TRANSITION
2. Engine Completion Collector → FAIL result → rejection_type = ENGINE_FAILURE

Pure logic — does NOT modify State Store.
Does NOT advance state. Surfaces rejection message to UI.

Spec: state-machine-design.md — Component 10 — Invalid Transition Rejection Handler
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.state_machine.engine_completion_collector import CollectionResult
from app.state_machine.transition_validator import ValidationResult


# ── Models ──────────────────────────────────────────────────────────

class RejectionResponse(BaseModel):
    """Output of the Invalid Transition Rejection Handler."""

    type: Literal["INVALID_TRANSITION", "ENGINE_FAILURE"]
    message: str
    state: str


# ── Public API ──────────────────────────────────────────────────────

def handle_invalid_transition(
    validation_result: ValidationResult,
) -> RejectionResponse:
    """
    Handle an INVALID validation result from Transition Validator.

    Parameters
    ----------
    validation_result : ValidationResult
        Must have result = INVALID.

    Returns
    -------
    RejectionResponse
        type = INVALID_TRANSITION, message includes reason,
        state = current state (unchanged).
    """
    # ── Guard: result must be INVALID ───────────────────────────────
    if validation_result.result != "INVALID":
        return RejectionResponse(
            type="INVALID_TRANSITION",
            message=(
                "Rejection handler received non-INVALID result: "
                f"{validation_result.result}"
            ),
            state=validation_result.current_state,
        )

    return RejectionResponse(
        type="INVALID_TRANSITION",
        message=f"Transition not permitted: {validation_result.reason}",
        state=validation_result.current_state,
    )


def handle_engine_failure(
    collection_result: CollectionResult,
    current_state: str,
) -> RejectionResponse:
    """
    Handle a FAIL collection result from Engine Completion Collector.

    State remains UPLOADED. [Analyze] returns to ACTIVE.

    Parameters
    ----------
    collection_result : CollectionResult
        Must have result = FAIL.
    current_state : str
        Current application_state (should be UPLOADED).

    Returns
    -------
    RejectionResponse
        type = ENGINE_FAILURE, message includes all named engine errors,
        state = current_state (unchanged — UPLOADED).
    """
    if collection_result.result != "FAIL":
        return RejectionResponse(
            type="ENGINE_FAILURE",
            message=(
                "Rejection handler received non-FAIL collection: "
                f"{collection_result.result}"
            ),
            state=current_state,
        )

    errors = collection_result.errors or []
    if errors:
        error_detail = "; ".join(errors)
        message = f"Engine failure: {error_detail}"
    else:
        message = "Engine failure: no error details provided"

    return RejectionResponse(
        type="ENGINE_FAILURE",
        message=message,
        state=current_state,
    )
