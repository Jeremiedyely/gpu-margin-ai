"""
KPI Data Aggregator — Component 4/14.

Layer: UI (backend aggregator).
Grain: All Region × GPU Pool × Day × Allocation Target (full table).

Pre-computes five Zone 1 KPI values at ANALYZED time and caches them
in dbo.kpi_cache.  UI renders read from the cache — not from
allocation_grain directly (L2 P2 #30).

KPI definitions:
  GPU Revenue         = SUM(gpu_hours × contracted_rate)
                        WHERE allocation_target ≠ 'unallocated'
  GPU COGS            = SUM(gpu_hours × cost_per_gpu_hour)
                        WHERE allocation_target ≠ 'unallocated'
  Idle GPU Cost       = SUM(gpu_hours × cost_per_gpu_hour)
                        WHERE allocation_target = 'unallocated'
  Idle GPU Cost %     = Idle GPU Cost / (GPU COGS + Idle GPU Cost) × 100
  Cost Allocation Rate = GPU COGS / (GPU COGS + Idle GPU Cost) × 100

Complement integrity: Idle GPU Cost % + Cost Allocation Rate = 100.00
(enforced by CHK_kpi_complement in V14).

Cache key: session_id.  Immutable once written (TR_kpi_cache_prevent_mutation).

Spec: ui-screen-design.md — Component 4 — KPI Data Aggregator
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Connection, text


class KPIPayload(BaseModel):
    """Pre-computed Zone 1 KPI values for one session."""

    gpu_revenue: Decimal
    gpu_cogs: Decimal
    idle_gpu_cost: Decimal
    idle_gpu_cost_pct: Decimal
    cost_allocation_rate: Decimal


class KPIAggregatorResult(BaseModel):
    """Result of the KPI Data Aggregator."""

    result: Literal["SUCCESS", "FAIL"]
    payload: KPIPayload | None = None
    error: str | None = None

    @classmethod
    def success(cls, payload: KPIPayload) -> KPIAggregatorResult:
        return cls(result="SUCCESS", payload=payload)

    @classmethod
    def failed(cls, error: str) -> KPIAggregatorResult:
        return cls(result="FAIL", error=error)


_AGGREGATE_SQL = text("""
    SELECT
        COALESCE(SUM(
            CASE WHEN allocation_target <> 'unallocated'
                 THEN gpu_hours * contracted_rate
                 ELSE 0 END
        ), 0) AS gpu_revenue,
        COALESCE(SUM(
            CASE WHEN allocation_target <> 'unallocated'
                 THEN gpu_hours * cost_per_gpu_hour
                 ELSE 0 END
        ), 0) AS gpu_cogs,
        COALESCE(SUM(
            CASE WHEN allocation_target = 'unallocated'
                 THEN gpu_hours * cost_per_gpu_hour
                 ELSE 0 END
        ), 0) AS idle_gpu_cost
    FROM dbo.allocation_grain
    WHERE session_id = :sid
""")


_WRITE_CACHE_SQL = text("""
    INSERT INTO dbo.kpi_cache (
        session_id, gpu_revenue, gpu_cogs, idle_gpu_cost,
        idle_gpu_cost_pct, cost_allocation_rate
    ) VALUES (
        :sid, :gpu_revenue, :gpu_cogs, :idle_gpu_cost,
        :idle_gpu_cost_pct, :cost_allocation_rate
    )
""")


_READ_CACHE_SQL = text("""
    SELECT gpu_revenue, gpu_cogs, idle_gpu_cost,
           idle_gpu_cost_pct, cost_allocation_rate
    FROM dbo.kpi_cache
    WHERE session_id = :sid
""")


def aggregate_kpis(
    conn: Connection,
    session_id: UUID,
) -> KPIAggregatorResult:
    """
    Pre-compute Zone 1 KPI values and write to dbo.kpi_cache.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection (caller owns transaction boundary).
    session_id : UUID
        Current session — must have allocation_grain rows.

    Returns
    -------
    KPIAggregatorResult
        SUCCESS with KPIPayload, or FAIL with error.
    """
    # ── Guard: check allocation_grain has rows for this session ──
    try:
        row = conn.execute(_AGGREGATE_SQL, {"sid": str(session_id)}).fetchone()
    except Exception as exc:
        return KPIAggregatorResult.failed(
            error=f"KPI aggregation query failed for session {session_id}: {exc}"
        )

    if row is None:
        return KPIAggregatorResult.failed(
            error=f"allocation_grain returned no aggregate row for session {session_id}"
        )

    gpu_revenue: Decimal = row.gpu_revenue
    gpu_cogs: Decimal = row.gpu_cogs
    idle_gpu_cost: Decimal = row.idle_gpu_cost

    # ── Guard: total cost base must be positive for percentage calculation ──
    total_cost = gpu_cogs + idle_gpu_cost
    if total_cost == Decimal("0"):
        return KPIAggregatorResult.failed(
            error=(
                f"Total cost base is zero for session {session_id} — "
                f"cannot compute Idle GPU Cost % or Cost Allocation Rate"
            )
        )

    # ── Compute percentages ──
    idle_gpu_cost_pct = (idle_gpu_cost / total_cost * Decimal("100")).quantize(
        Decimal("0.01")
    )
    cost_allocation_rate = (gpu_cogs / total_cost * Decimal("100")).quantize(
        Decimal("0.01")
    )

    payload = KPIPayload(
        gpu_revenue=gpu_revenue,
        gpu_cogs=gpu_cogs,
        idle_gpu_cost=idle_gpu_cost,
        idle_gpu_cost_pct=idle_gpu_cost_pct,
        cost_allocation_rate=cost_allocation_rate,
    )

    # ── Write to cache ──
    try:
        savepoint = conn.begin_nested()
        try:
            conn.execute(
                _WRITE_CACHE_SQL,
                {
                    "sid": str(session_id),
                    "gpu_revenue": payload.gpu_revenue,
                    "gpu_cogs": payload.gpu_cogs,
                    "idle_gpu_cost": payload.idle_gpu_cost,
                    "idle_gpu_cost_pct": payload.idle_gpu_cost_pct,
                    "cost_allocation_rate": payload.cost_allocation_rate,
                },
            )
            savepoint.commit()
        except Exception as exc:
            savepoint.rollback()
            return KPIAggregatorResult.failed(
                error=(
                    f"KPI cache write failed for session {session_id}: {exc}"
                )
            )
    except Exception as exc:
        return KPIAggregatorResult.failed(
            error=(
                f"KPI cache savepoint failed for session {session_id}: {exc}"
            )
        )

    return KPIAggregatorResult.success(payload=payload)


def read_kpi_cache(
    conn: Connection,
    session_id: UUID,
) -> KPIAggregatorResult:
    """
    Read pre-computed KPI values from dbo.kpi_cache.

    Used by the UI render path — reads from cache, never re-aggregates.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection.
    session_id : UUID
        Session to look up.

    Returns
    -------
    KPIAggregatorResult
        SUCCESS with KPIPayload, or FAIL if cache miss.
    """
    try:
        row = conn.execute(_READ_CACHE_SQL, {"sid": str(session_id)}).fetchone()
    except Exception as exc:
        return KPIAggregatorResult.failed(
            error=f"KPI cache read failed for session {session_id}: {exc}"
        )

    if row is None:
        return KPIAggregatorResult.failed(
            error=f"No KPI cache entry for session {session_id}"
        )

    return KPIAggregatorResult.success(
        payload=KPIPayload(
            gpu_revenue=row.gpu_revenue,
            gpu_cogs=row.gpu_cogs,
            idle_gpu_cost=row.idle_gpu_cost,
            idle_gpu_cost_pct=row.idle_gpu_cost_pct,
            cost_allocation_rate=row.cost_allocation_rate,
        )
    )
