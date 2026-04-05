"""
Allocation Engine Completion Listener — Component 3/7.

Layer: Reconciliation.

Receives allocation_engine_result from AE Completion Emitter.
  SUCCESS → READY — allocation_grain available for Check 3.
  FAIL    → BLOCKED — Check 3 cannot execute.

Output feeds two consumers (fan-out wired in orchestrator):
  1. Check 3 Executor (if READY)
  2. Reconciliation Result Aggregator (BOTH paths)
     READY   → t_ae_complete timing signal for dynamic deadline
     BLOCKED → forced FAIL signal with error detail

ACK contract (L2 P1 #15):
  Must ACK within ACK_TIMEOUT. Idempotent on same session_id.
  Re-emission from Emitter targets this Listener only.

Spec: reconciliation-engine-design.md — Component 3 — AE Completion Listener
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.allocation.completion_emitter import AllocationEngineResult


class ListenerResult(BaseModel):
    """Result of AE Completion Listener — consumed by Check 3 and Aggregator."""

    result: Literal["READY", "BLOCKED"]
    session_id: UUID
    t_ae_complete: datetime
    error: str | None = None

    @classmethod
    def ready(cls, session_id: UUID, t_ae_complete: datetime) -> ListenerResult:
        return cls(result="READY", session_id=session_id, t_ae_complete=t_ae_complete)

    @classmethod
    def blocked(
        cls, session_id: UUID, t_ae_complete: datetime, error: str
    ) -> ListenerResult:
        return cls(
            result="BLOCKED",
            session_id=session_id,
            t_ae_complete=t_ae_complete,
            error=error,
        )


def listen_for_ae_completion(
    ae_result: AllocationEngineResult,
) -> ListenerResult:
    """
    Process the Allocation Engine completion signal.

    Parameters
    ----------
    ae_result : AllocationEngineResult
        Signal from AE Completion Emitter — SUCCESS or FAIL.

    Returns
    -------
    ListenerResult
        READY if AE succeeded (Check 3 can proceed).
        BLOCKED if AE failed (Check 3 forced to FAIL).
    """
    now = datetime.now(timezone.utc)

    if ae_result.result == "SUCCESS" and ae_result.session_id is not None:
        return ListenerResult.ready(
            session_id=ae_result.session_id,
            t_ae_complete=now,
        )

    # FAIL path — or SUCCESS with missing session_id (defensive)
    error = ae_result.error or "Allocation Engine failed — Check 3 cannot execute"

    if ae_result.session_id is None:
        # Defensive: should not happen with valid AE emitter, but surface it
        return ListenerResult.blocked(
            session_id=UUID("00000000-0000-0000-0000-000000000000"),
            t_ae_complete=now,
            error=f"[Reconciliation Engine — AE Completion Listener] "
            f"session_id missing in AE signal: {error}",
        )

    return ListenerResult.blocked(
        session_id=ae_result.session_id,
        t_ae_complete=now,
        error=error,
    )
