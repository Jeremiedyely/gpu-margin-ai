"""
Allocation Engine Run Receiver — Component 0/10.

Entry point for the Allocation Engine. Receives a run_signal from the
State Machine Analysis Dispatcher when UPLOADED → ANALYZED transition
is requested. Validates the signal and extracts session_id for all
downstream components.

Pydantic enforces Literal["ANALYZE"] on trigger — invalid triggers are
rejected at construction time. Invalid session_id (non-UUID) is also
rejected by Pydantic. The function itself is a clean pass-through.

Spec: allocation-engine-design.md — Component 0 — Run Receiver
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class RunSignal(BaseModel):
    """Signal received from the State Machine Analysis Dispatcher."""

    trigger: Literal["ANALYZE"]
    session_id: UUID


class ReceiverResult(BaseModel):
    """Result of the Run Receiver validation."""

    result: Literal["READY", "FAIL"]
    session_id: UUID | None = None
    error: str | None = None

    @classmethod
    def ready(cls, session_id: UUID) -> ReceiverResult:
        return cls(result="READY", session_id=session_id)

    @classmethod
    def failed(cls, error: str) -> ReceiverResult:
        return cls(result="FAIL", error=error)


def receive_run_signal(signal: RunSignal) -> ReceiverResult:
    """
    Validate the run signal and extract session_id.

    With Literal["ANALYZE"] on RunSignal, Pydantic rejects invalid
    triggers at construction time. This function confirms READY
    and passes session_id downstream.

    Parameters
    ----------
    signal : RunSignal
        Signal from the State Machine Analysis Dispatcher.

    Returns
    -------
    ReceiverResult
        READY with session_id — signal already validated by Pydantic.
    """
    return ReceiverResult.ready(session_id=signal.session_id)
