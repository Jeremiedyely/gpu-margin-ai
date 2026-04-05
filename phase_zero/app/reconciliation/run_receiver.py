"""
Reconciliation Engine Run Receiver — Component 0/7.

Layer: Reconciliation.

Entry point — receives run_signal from State Machine Analysis Dispatcher.
Validates trigger and session_id, extracts session_id for downstream components.

Pydantic Literal["ANALYZE"] enforces boundary validation at construction —
invalid triggers never reach the function body.

Spec: reconciliation-engine-design.md — Component 0 — Run Receiver
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class RERunSignal(BaseModel):
    """Run signal for the Reconciliation Engine."""

    trigger: Literal["ANALYZE"]
    session_id: UUID


class REReceiverResult(BaseModel):
    """Result of the Reconciliation Engine Run Receiver."""

    result: Literal["READY", "FAIL"]
    session_id: UUID | None = None
    error: str | None = None

    @classmethod
    def ready(cls, session_id: UUID) -> REReceiverResult:
        return cls(result="READY", session_id=session_id)

    @classmethod
    def failed(cls, error: str) -> REReceiverResult:
        return cls(result="FAIL", error=error)


def receive_re_run_signal(signal: RERunSignal) -> REReceiverResult:
    """
    Receive and validate the Reconciliation Engine run signal.

    Parameters
    ----------
    signal : RERunSignal
        Run signal from Analysis Dispatcher (Pydantic-validated at construction).

    Returns
    -------
    REReceiverResult
        READY with session_id for valid signals.
        Invalid inputs are rejected at model construction by Pydantic.
    """
    return REReceiverResult.ready(session_id=signal.session_id)
