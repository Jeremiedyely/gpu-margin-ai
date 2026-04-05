"""
Region Data Aggregator — Component 6/14.

Layer: UI (backend aggregator).
Grain: Region — preserving Type A / Type B separation within each region.

Per region:
  Revenue  = SUM(gpu_hours × contracted_rate)
             WHERE allocation_target ≠ 'unallocated'
  COGS_A   = SUM(gpu_hours × cost_per_gpu_hour)
             WHERE allocation_target ≠ 'unallocated'
  COGS_B   = SUM(gpu_hours × cost_per_gpu_hour)
             WHERE allocation_target = 'unallocated'
  GM%      = IF Revenue = 0 → NULL
             ELSE (Revenue − COGS_A) / Revenue × 100
  Idle%    = COGS_B / (COGS_A + COGS_B) × 100
  Status:  IF Idle% ≤ 30% → HOLDING
           IF Idle% > 30% → AT RISK
  Subtype pill counts:
    identity_broken_count = COUNT rows WHERE unallocated_type = 'identity_broken'
    capacity_idle_count   = COUNT rows WHERE unallocated_type = 'capacity_idle'

If no data for a region → row omitted (not zero-filled).

Spec: ui-screen-design.md — Component 6 — Region Data Aggregator
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import Connection, text


RegionStatus = Literal["HOLDING", "AT RISK"]


class RegionRecord(BaseModel):
    """One row in the region payload — Zone 2L input."""

    region: str
    gm_pct: Decimal | None
    idle_pct: Decimal
    revenue: Decimal
    status: RegionStatus
    identity_broken_count: int
    capacity_idle_count: int


class RegionAggregatorResult(BaseModel):
    """Result of the Region Data Aggregator."""

    result: Literal["SUCCESS", "FAIL"]
    payload: list[RegionRecord] = Field(default_factory=list)
    error: str | None = None

    @classmethod
    def success(cls, payload: list[RegionRecord]) -> RegionAggregatorResult:
        return cls(result="SUCCESS", payload=payload)

    @classmethod
    def failed(cls, error: str) -> RegionAggregatorResult:
        return cls(result="FAIL", error=error)


_REGION_AGGREGATE_SQL = text("""
    SELECT
        region,
        COALESCE(SUM(
            CASE WHEN allocation_target <> 'unallocated'
                 THEN gpu_hours * contracted_rate ELSE 0 END
        ), 0) AS revenue,
        COALESCE(SUM(
            CASE WHEN allocation_target <> 'unallocated'
                 THEN gpu_hours * cost_per_gpu_hour ELSE 0 END
        ), 0) AS cogs_a,
        COALESCE(SUM(
            CASE WHEN allocation_target = 'unallocated'
                 THEN gpu_hours * cost_per_gpu_hour ELSE 0 END
        ), 0) AS cogs_b,
        COUNT(CASE WHEN unallocated_type = 'identity_broken' THEN 1 END)
            AS identity_broken_count,
        COUNT(CASE WHEN unallocated_type = 'capacity_idle' THEN 1 END)
            AS capacity_idle_count
    FROM dbo.allocation_grain
    WHERE session_id = :sid
    GROUP BY region
""")


def aggregate_regions(
    conn: Connection,
    session_id: UUID,
) -> RegionAggregatorResult:
    """
    Aggregate per-region metrics from allocation_grain.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection (caller owns transaction boundary).
    session_id : UUID
        Current session — must have allocation_grain rows.

    Returns
    -------
    RegionAggregatorResult
        SUCCESS with region payload, or FAIL on query error.
    """
    try:
        rows = conn.execute(
            _REGION_AGGREGATE_SQL, {"sid": str(session_id)}
        ).fetchall()
    except Exception as exc:
        return RegionAggregatorResult.failed(
            error=f"Region aggregation query failed for session {session_id}: {exc}"
        )

    if not rows:
        # No data — empty payload is valid (not a failure)
        return RegionAggregatorResult.success(payload=[])

    payload: list[RegionRecord] = []

    for row in rows:
        revenue: Decimal = row.revenue
        cogs_a: Decimal = row.cogs_a
        cogs_b: Decimal = row.cogs_b

        # GM%
        if revenue == Decimal("0"):
            gm_pct = None
        else:
            gm_pct = ((revenue - cogs_a) / revenue * Decimal("100")).quantize(
                Decimal("0.01")
            )

        # Idle%
        total_cost = cogs_a + cogs_b
        if total_cost == Decimal("0"):
            idle_pct = Decimal("0.00")
        else:
            idle_pct = (cogs_b / total_cost * Decimal("100")).quantize(
                Decimal("0.01")
            )

        # Status
        status: RegionStatus = "AT RISK" if idle_pct > Decimal("30") else "HOLDING"

        payload.append(
            RegionRecord(
                region=row.region,
                gm_pct=gm_pct,
                idle_pct=idle_pct,
                revenue=revenue,
                status=status,
                identity_broken_count=row.identity_broken_count,
                capacity_idle_count=row.capacity_idle_count,
            )
        )

    # Sort by GM% descending, NULL last
    payload.sort(
        key=lambda r: (r.gm_pct is None, -(r.gm_pct or Decimal("0"))),
    )

    return RegionAggregatorResult.success(payload=payload)
