"""
Closure Rule Enforcer — Component 7/10.

Layer: Allocation.
Grain: Region × GPU Pool × Day (evaluated per pool per day).

For each Region × GPU Pool × Day in cost_rates:
  consumed = SUM(gpu_hours) across type_a + identity_broken WHERE key matches
  reserved = cost_rates.reserved_gpu_hours
  idle     = reserved − consumed

  idle > 0 → force one capacity_idle record (Type B)
  idle = 0 → no capacity_idle row — pool fully consumed
  idle < 0 → FAIL with source-labeled error (L2 P2 #13)

Closure guarantee after this component:
  SUM(all gpu_hours per pool per day) = reserved_gpu_hours
  No cost is hidden. No idle is a remainder.

Record Builder Required Field Checklist (L2 P1 #11) — capacity_idle:
  1. failed_tenant_id  = None
  2. unallocated_type  = 'capacity_idle'
  3. allocation_target = 'unallocated'

Spec: allocation-engine-design.md — Component 7 — Closure Rule Enforcer
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.allocation.type_a_builder import TypeAGrainRecord
from app.allocation.identity_broken_builder import IdentityBrokenGrainRecord
from app.allocation.cost_rate_reader import CostRateRecord
from app.shared.billing_period import derive_billing_period


@dataclass(frozen=True)
class CapacityIdleRecord:
    """Type B / capacity_idle grain record."""

    region: str
    gpu_pool_id: str
    date: date
    billing_period: str
    allocation_target: str          # always 'unallocated'
    unallocated_type: str           # always 'capacity_idle'
    failed_tenant_id: str | None    # always None
    gpu_hours: Decimal
    cost_per_gpu_hour: Decimal
    contracted_rate: Decimal | None  # always None
    revenue: Decimal                 # always 0


class ClosureResult(BaseModel):
    """Result of the Closure Rule Enforcer."""

    result: Literal["SUCCESS", "FAIL"]
    capacity_idle: list[CapacityIdleRecord] = Field(default_factory=list)
    error: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def success(cls, records: list[CapacityIdleRecord]) -> ClosureResult:
        return cls(result="SUCCESS", capacity_idle=records)

    @classmethod
    def failed(cls, error: str) -> ClosureResult:
        return cls(result="FAIL", error=error)


def enforce_closure_rule(
    type_a: list[TypeAGrainRecord],
    identity_broken: list[IdentityBrokenGrainRecord],
    cost_rates: list[CostRateRecord],
) -> ClosureResult:
    """
    Enforce the closure rule: SUM(gpu_hours) per pool per day = reserved.

    Parameters
    ----------
    type_a : list[TypeAGrainRecord]
        Type A grain records from Type A Builder.
    identity_broken : list[IdentityBrokenGrainRecord]
        Identity broken grain records from Identity Broken Builder.
    cost_rates : list[CostRateRecord]
        Cost rates from Cost Rate Reader.

    Returns
    -------
    ClosureResult
        SUCCESS with capacity_idle records, or FAIL if consumed > reserved.
    """
    # ── Build consumed index: (region, gpu_pool_id, date) → total gpu_hours ──
    consumed: dict[tuple[str, str, date], Decimal] = {}

    for rec in type_a:
        key = (rec.region, rec.gpu_pool_id, rec.date)
        consumed[key] = consumed.get(key, Decimal("0")) + rec.gpu_hours

    for rec in identity_broken:
        key = (rec.region, rec.gpu_pool_id, rec.date)
        consumed[key] = consumed.get(key, Decimal("0")) + rec.gpu_hours

    # ── Evaluate each pool-day from cost_rates ──
    idle_records: list[CapacityIdleRecord] = []

    for cr in cost_rates:
        key = (cr.region, cr.gpu_pool_id, cr.date)
        total_consumed = consumed.get(key, Decimal("0"))
        idle = cr.reserved_gpu_hours - total_consumed

        if idle < 0:
            return ClosureResult.failed(
                error=(
                    "[Allocation Engine — Closure Rule Enforcer] "
                    f"Consumed exceeds reserved: "
                    f"region={cr.region} · pool={cr.gpu_pool_id} · "
                    f"date={cr.date} · "
                    f"consumed={total_consumed} · reserved={cr.reserved_gpu_hours}"
                )
            )

        if idle > 0:
            idle_records.append(
                CapacityIdleRecord(
                    region=cr.region,
                    gpu_pool_id=cr.gpu_pool_id,
                    date=cr.date,
                    billing_period=derive_billing_period(cr.date),
                    allocation_target="unallocated",
                    unallocated_type="capacity_idle",
                    failed_tenant_id=None,
                    gpu_hours=idle,
                    cost_per_gpu_hour=cr.cost_per_gpu_hour,
                    contracted_rate=None,
                    revenue=Decimal("0"),
                )
            )
        # idle == 0 → no record — pool fully consumed

    return ClosureResult.success(records=idle_records)
