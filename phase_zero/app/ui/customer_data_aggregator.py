"""
Customer Data Aggregator — Component 8/14 (spec) · Step 6.5 (build).

Layer: UI (backend aggregator).
Grain: allocation_target — Type A records only
       (WHERE allocation_target ≠ 'unallocated').

Two responsibilities:
  1. Build identity_broken_tenants SET and cache to dbo.identity_broken_tenants
  2. Compute per-customer GM%, gm_color (4-tier), revenue, risk_flag

GM color tiers (L2 P2 #36):
  red    IF GM% < 0%   (negative margin)
  orange IF GM% 0–29%
  yellow IF GM% 30–37%
  green  IF GM% ≥ 38%

Risk flag logic:
  FLAG  IF (GM% IS NOT NULL AND GM% < 0)
           OR (allocation_target ∈ identity_broken_tenants)
  CLEAR otherwise

SET artifact requirement (L2 P2 #31):
  identity_broken_tenants SET is pre-built at analysis completion time
  and stored in dbo.identity_broken_tenants. Customer Zone renders read
  from the artifact — not by re-scanning allocation_grain on every render.

Spec: ui-screen-design.md — Component 8 — Customer Data Aggregator
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import Connection, text


# ── GM% color tiers ─────────────────────────────────────────────────

GmColor = Literal["red", "orange", "yellow", "green"]
RiskFlag = Literal["FLAG", "CLEAR"]


def _compute_gm_color(gm_pct: Decimal) -> GmColor:
    """Assign 4-tier GM% color per L2 P2 #36."""
    if gm_pct < Decimal("0"):
        return "red"
    if gm_pct < Decimal("30"):
        return "orange"
    if gm_pct < Decimal("38"):
        return "yellow"
    return "green"


# ── Models ───────────────────────────────────────────────────────────

class CustomerRecord(BaseModel):
    """One row in the customer payload — Zone 2R input."""

    allocation_target: str
    gm_pct: Decimal | None
    gm_color: GmColor | None
    revenue: Decimal
    risk_flag: RiskFlag


class CustomerAggregatorResult(BaseModel):
    """Result of the Customer Data Aggregator."""

    result: Literal["SUCCESS", "FAIL"]
    payload: list[CustomerRecord] = Field(default_factory=list)
    identity_broken_set: set[str] = Field(default_factory=set)
    error: str | None = None

    @classmethod
    def success(
        cls,
        payload: list[CustomerRecord],
        identity_broken_set: set[str],
    ) -> CustomerAggregatorResult:
        return cls(
            result="SUCCESS",
            payload=payload,
            identity_broken_set=identity_broken_set,
        )

    @classmethod
    def failed(cls, error: str) -> CustomerAggregatorResult:
        return cls(result="FAIL", error=error)


# ── SQL ──────────────────────────────────────────────────────────────

_IDENTITY_BROKEN_SET_SQL = text("""
    SELECT DISTINCT failed_tenant_id
    FROM dbo.allocation_grain
    WHERE session_id = :sid
      AND unallocated_type = 'identity_broken'
      AND failed_tenant_id IS NOT NULL
""")

_WRITE_IB_TENANT_SQL = text("""
    INSERT INTO dbo.identity_broken_tenants (session_id, failed_tenant_id)
    VALUES (:sid, :ftid)
""")

_CUSTOMER_AGGREGATE_SQL = text("""
    SELECT
        allocation_target,
        SUM(gpu_hours * contracted_rate) AS revenue,
        SUM(gpu_hours * cost_per_gpu_hour) AS cogs
    FROM dbo.allocation_grain
    WHERE session_id = :sid
      AND allocation_target <> 'unallocated'
    GROUP BY allocation_target
""")

_READ_IB_SET_SQL = text("""
    SELECT failed_tenant_id
    FROM dbo.identity_broken_tenants
    WHERE session_id = :sid
""")


# ── Public API ───────────────────────────────────────────────────────

def aggregate_customers(
    conn: Connection,
    session_id: UUID,
) -> CustomerAggregatorResult:
    """
    Build identity_broken SET, cache it, and compute per-customer payload.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection (caller owns transaction boundary).
    session_id : UUID
        Current session — must have allocation_grain rows.

    Returns
    -------
    CustomerAggregatorResult
        SUCCESS with customer payload + identity_broken set, or FAIL.
    """
    # ── Step 1: Build identity_broken_tenants SET ────────────────
    try:
        ib_rows = conn.execute(
            _IDENTITY_BROKEN_SET_SQL, {"sid": str(session_id)}
        ).fetchall()
    except Exception as exc:
        return CustomerAggregatorResult.failed(
            error=f"identity_broken SET query failed for session {session_id}: {exc}"
        )

    ib_set: set[str] = {row.failed_tenant_id for row in ib_rows}

    # ── Step 2: Write SET to dbo.identity_broken_tenants ─────────
    if ib_set:
        try:
            savepoint = conn.begin_nested()
            try:
                for tenant_id in sorted(ib_set):
                    conn.execute(
                        _WRITE_IB_TENANT_SQL,
                        {"sid": str(session_id), "ftid": tenant_id},
                    )
                savepoint.commit()
            except Exception as exc:
                savepoint.rollback()
                return CustomerAggregatorResult.failed(
                    error=(
                        f"identity_broken_tenants cache write failed "
                        f"for session {session_id}: {exc}"
                    )
                )
        except Exception as exc:
            return CustomerAggregatorResult.failed(
                error=(
                    f"identity_broken_tenants savepoint failed "
                    f"for session {session_id}: {exc}"
                )
            )

    # ── Step 3: Aggregate per-customer metrics ───────────────────
    try:
        cust_rows = conn.execute(
            _CUSTOMER_AGGREGATE_SQL, {"sid": str(session_id)}
        ).fetchall()
    except Exception as exc:
        return CustomerAggregatorResult.failed(
            error=f"Customer aggregation query failed for session {session_id}: {exc}"
        )

    if not cust_rows:
        # No Type A records — empty payload is valid (not a failure)
        return CustomerAggregatorResult.success(
            payload=[], identity_broken_set=ib_set,
        )

    # ── Step 4: Compute GM%, gm_color, risk_flag per customer ────
    payload: list[CustomerRecord] = []

    for row in cust_rows:
        revenue: Decimal = row.revenue
        cogs: Decimal = row.cogs
        target: str = row.allocation_target

        if revenue == Decimal("0"):
            gm_pct = None
            gm_color = None
        else:
            gm_pct = ((revenue - cogs) / revenue * Decimal("100")).quantize(
                Decimal("0.01")
            )
            gm_color = _compute_gm_color(gm_pct)

        # Risk flag logic
        risk_flag: RiskFlag
        if (gm_pct is not None and gm_pct < Decimal("0")) or (
            target in ib_set
        ):
            risk_flag = "FLAG"
        else:
            risk_flag = "CLEAR"

        payload.append(
            CustomerRecord(
                allocation_target=target,
                gm_pct=gm_pct,
                gm_color=gm_color,
                revenue=revenue,
                risk_flag=risk_flag,
            )
        )

    # Sort by GM% descending, NULL last
    payload.sort(
        key=lambda r: (r.gm_pct is None, -(r.gm_pct or Decimal("0"))),
    )

    return CustomerAggregatorResult.success(
        payload=payload, identity_broken_set=ib_set,
    )


def read_identity_broken_set(
    conn: Connection,
    session_id: UUID,
) -> set[str]:
    """
    Read pre-built identity_broken SET from dbo.identity_broken_tenants.

    Used by the UI render path — reads from cache, never re-scans grain.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection.
    session_id : UUID
        Session to look up.

    Returns
    -------
    set[str]
        Set of failed_tenant_id values. Empty set if no cache entry.
    """
    try:
        rows = conn.execute(
            _READ_IB_SET_SQL, {"sid": str(session_id)}
        ).fetchall()
        return {row.failed_tenant_id for row in rows}
    except Exception:
        return set()
