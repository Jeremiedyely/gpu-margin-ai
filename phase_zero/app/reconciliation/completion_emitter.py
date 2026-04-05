"""
Reconciliation Engine Completion Emitter — Component 7/7.

Layer: Reconciliation.

Emits reconciliation_engine_result to Engine Completion Collector (State Machine).

IF write_result = SUCCESS → emit {result=SUCCESS, session_id}
IF write_result = FAIL OR aggregated_results = FATAL
  → emit {result=FAIL, session_id, error}

Pure logic — no database access. Produces the structured signal;
delivery mechanism is wired in the orchestrator.

Spec: reconciliation-engine-design.md — Component 7 — Completion Emitter
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.reconciliation.result_aggregator import AggregatedResults
from app.reconciliation.result_writer import REWriteResult


class ReconciliationEngineResult(BaseModel):
    """Signal emitted on reconciliation engine completion."""

    result: Literal["SUCCESS", "FAIL"]
    session_id: UUID | None = None
    error: str | None = None

    @classmethod
    def success(cls, session_id: UUID) -> ReconciliationEngineResult:
        return cls(result="SUCCESS", session_id=session_id)

    @classmethod
    def failed(
        cls, session_id: UUID | None, error: str
    ) -> ReconciliationEngineResult:
        return cls(result="FAIL", session_id=session_id, error=error)


def emit_re_completion(
    write_result: REWriteResult | None = None,
    aggregated: AggregatedResults | None = None,
    session_id: UUID | None = None,
) -> ReconciliationEngineResult:
    """
    Emit reconciliation engine completion signal.

    Parameters
    ----------
    write_result : REWriteResult | None
        Result from Result Writer (SUCCESS path).
    aggregated : AggregatedResults | None
        Result from Aggregator (FATAL path — skips writer entirely).
    session_id : UUID | None
        Current ingestion session (fallback if not on write_result).

    Returns
    -------
    ReconciliationEngineResult
        SUCCESS or FAIL signal for State Machine Engine Completion Collector.
    """
    # Resolve session_id from available sources
    sid = (
        (write_result.session_id if write_result else None)
        or session_id
    )

    # SUCCESS path: write succeeded
    if write_result and write_result.result == "SUCCESS" and sid is not None:
        return ReconciliationEngineResult.success(session_id=sid)

    # FATAL path: aggregator failed, writer never ran
    if aggregated and aggregated.result == "FATAL":
        return ReconciliationEngineResult.failed(
            session_id=sid,
            error=aggregated.error
            or "Reconciliation engine failed — no error detail provided",
        )

    # FAIL path: writer failed
    if write_result and write_result.result == "FAIL":
        return ReconciliationEngineResult.failed(
            session_id=sid,
            error=write_result.error
            or "Reconciliation engine failed — no error detail provided",
        )

    # Defensive: no valid input provided
    return ReconciliationEngineResult.failed(
        session_id=sid,
        error="Reconciliation engine failed — "
        "no write_result or aggregated_results provided",
    )
