"""
Allocation Engine Completion Emitter — Component 10/10.

Layer: Allocation.

Emits allocation_engine_result to two downstream consumers:
  1. Engine Completion Collector (State Machine) — UPLOADED → ANALYZED transition
  2. Allocation Engine Completion Listener (Reconciliation Engine) — gates Check 3

IF write_result = SUCCESS → emit {result=SUCCESS, session_id}
IF write_result = FAIL    → emit {result=FAIL, session_id, error}

Pure logic — no database access. Produces the structured signal;
delivery mechanism is wired in the orchestrator.

Delivery contract (L2 P1 #15):
  Each consumer must ACK within ACK_TIMEOUT.
  Re-emission targets non-acknowledging consumer only.
  Consumers must be idempotent on same session_id.

Spec: allocation-engine-design.md — Component 10 — Completion Emitter
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.allocation.grain_writer import GrainWriteResult


class AllocationEngineResult(BaseModel):
    """Signal emitted on allocation engine completion."""

    result: Literal["SUCCESS", "FAIL"]
    session_id: UUID | None = None
    error: str | None = None

    @classmethod
    def success(cls, session_id: UUID) -> AllocationEngineResult:
        return cls(result="SUCCESS", session_id=session_id)

    @classmethod
    def failed(cls, session_id: UUID | None, error: str) -> AllocationEngineResult:
        return cls(result="FAIL", session_id=session_id, error=error)


def emit_completion(write_result: GrainWriteResult) -> AllocationEngineResult:
    """
    Emit allocation engine completion signal.

    Parameters
    ----------
    write_result : GrainWriteResult
        Result from Allocation Grain Writer.

    Returns
    -------
    AllocationEngineResult
        SUCCESS or FAIL signal for both downstream consumers.
    """
    if write_result.result == "SUCCESS" and write_result.session_id is not None:
        return AllocationEngineResult.success(session_id=write_result.session_id)

    return AllocationEngineResult.failed(
        session_id=write_result.session_id,
        error=write_result.error or "Allocation engine failed — no error detail provided",
    )
