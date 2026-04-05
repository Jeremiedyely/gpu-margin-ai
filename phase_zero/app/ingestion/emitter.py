"""
State Transition Emitter (EMPTY → UPLOADED) — Component 19/19.

Layer 6 — State Transition.

Emits a state_transition_signal ONLY when log_write.result = SUCCESS.
On FAIL, no signal is emitted and the State Machine is not contacted.
The failure is surfaced directly to the UI.

Pure logic — no database access. Receives LogWriteResult, produces
a StateTransitionSignal or None.

Spec: ingestion-module-design.md — Layer 6 — State Transition Emitter
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.ingestion.log_writer import LogWriteResult


class StateTransitionSignal(BaseModel):
    """Signal emitted to the State Machine on successful ingestion."""

    signal: Literal["FIRE"]
    requested_transition: str
    source: str
    session_id: UUID


def emit_state_transition(log_write: LogWriteResult) -> StateTransitionSignal | None:
    """
    Emit a state transition signal if log write succeeded.

    Parameters
    ----------
    log_write : LogWriteResult
        Result from run_log_writer().

    Returns
    -------
    StateTransitionSignal | None
        Signal with FIRE + EMPTY→UPLOADED if log write succeeded.
        None if log write failed — State Machine is not contacted.
    """
    if log_write.result != "SUCCESS" or log_write.session_id is None:
        return None

    return StateTransitionSignal(
        signal="FIRE",
        requested_transition="EMPTY→UPLOADED",
        source="INGESTION",
        session_id=log_write.session_id,
    )
