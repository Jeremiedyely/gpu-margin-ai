"""
Reconciliation Result Aggregator — Component 5/7.

Layer: Reconciliation.

Collects all three check results and assembles a three-row result set
for the Reconciliation Result Writer.

Row 1: check_name = 'Capacity vs Usage'        (Check 1)
Row 2: check_name = 'Usage vs Tenant Mapping'   (Check 2)
Row 3: check_name = 'Computed vs Billed vs Posted' (Check 3)

IF all three results received → aggregation_result = SUCCESS → rows emitted
IF any check result has a fatal detail (non-verdict error) → FATAL

Timeout tracking (t_dispatch, t_ae_complete, dynamic deadline) is an
orchestrator concern. This component receives assembled results only.

Spec: reconciliation-engine-design.md — Component 5 — Result Aggregator
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.reconciliation.check1_executor import Check1Result
from app.reconciliation.check2_executor import Check2Result
from app.reconciliation.check3_executor import Check3Result


class AggregatedRow(BaseModel):
    """One row in the aggregated result set — maps to one reconciliation_results row."""

    check_name: str
    verdict: Literal["PASS", "FAIL"]
    session_id: UUID
    failing_count: int | None = None
    fail_subtype: str | None = None  # 'FAIL-1' | 'FAIL-2' — Check 3 only
    detail: str | None = None


class AggregatedResults(BaseModel):
    """Output of the Reconciliation Result Aggregator."""

    result: Literal["SUCCESS", "FATAL"]
    rows: list[AggregatedRow] = Field(default_factory=list)
    error: str | None = None

    @classmethod
    def success(cls, rows: list[AggregatedRow]) -> AggregatedResults:
        return cls(result="SUCCESS", rows=rows)

    @classmethod
    def fatal(cls, error: str) -> AggregatedResults:
        return cls(result="FATAL", error=error)


def _serialize_detail(records: list, field_name: str) -> str | None:
    """Serialize failing records/pairs to JSON string for detail column."""
    if not records:
        return None
    return json.dumps([asdict(r) for r in records], default=str)


def aggregate_results(
    check1: Check1Result,
    check2: Check2Result,
    check3: Check3Result,
    session_id: UUID,
) -> AggregatedResults:
    """
    Aggregate three check results into a three-row result set.

    Parameters
    ----------
    check1 : Check1Result
        Result from Check 1 Executor (Capacity vs Usage).
    check2 : Check2Result
        Result from Check 2 Executor (Usage vs Tenant Mapping).
    check3 : Check3Result
        Result from Check 3 Executor (Computed vs Billed vs Posted).
    session_id : UUID
        Current ingestion session.

    Returns
    -------
    AggregatedResults
        SUCCESS with 3 rows, or FATAL with error detail.
    """
    # Fatal error check — any check that couldn't execute surfaces a detail
    # but has no failing_records (detail describes the structural failure)
    fatal_errors: list[str] = []

    if check1.detail and not check1.failing_records:
        fatal_errors.append(f"Check 1: {check1.detail}")
    if check2.detail and not check2.unresolved_pairs:
        fatal_errors.append(f"Check 2: {check2.detail}")
    if check3.detail and not check3.failing_records:
        fatal_errors.append(f"Check 3: {check3.detail}")

    if fatal_errors:
        return AggregatedResults.fatal(
            error="Reconciliation engine fatal — "
            + "; ".join(fatal_errors)
        )

    # Assemble three-row result set
    row1 = AggregatedRow(
        check_name="Capacity vs Usage",
        verdict=check1.verdict,
        session_id=session_id,
        failing_count=check1.failing_count,
        detail=_serialize_detail(check1.failing_records, "failing_records"),
    )

    row2 = AggregatedRow(
        check_name="Usage vs Tenant Mapping",
        verdict=check2.verdict,
        session_id=session_id,
        failing_count=check2.failing_count,
        detail=_serialize_detail(check2.unresolved_pairs, "unresolved_pairs"),
    )

    # Derive fail_subtype for Check 3: FAIL-1 takes precedence over FAIL-2
    fail_subtype: str | None = None
    if check3.verdict == "FAIL" and check3.failing_records:
        if any(r.fail_type == "FAIL-1" for r in check3.failing_records):
            fail_subtype = "FAIL-1"
        else:
            fail_subtype = "FAIL-2"

    row3 = AggregatedRow(
        check_name="Computed vs Billed vs Posted",
        verdict=check3.verdict,
        session_id=session_id,
        failing_count=check3.failing_count,
        fail_subtype=fail_subtype,
        detail=_serialize_detail(check3.failing_records, "failing_records"),
    )

    return AggregatedResults.success(rows=[row1, row2, row3])
