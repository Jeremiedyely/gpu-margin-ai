"""
Cost & Revenue Calculator — Component 8/10.

Layer: Allocation.
Grain: All grain records (Type A + identity_broken + capacity_idle).

For each Type A record:
  revenue      = gpu_hours × contracted_rate
  cogs         = gpu_hours × cost_per_gpu_hour
  gross_margin = revenue − cogs

For each Type B record (identity_broken or capacity_idle):
  revenue      = 0   (set by record builders — carried through)
  cogs         = gpu_hours × cost_per_gpu_hour
  gross_margin = −cogs
  (gross_margin is never 0 — always negative — always a cost)

Pass-through invariant (L2 P2 #14):
  failed_tenant_id is a PASS-THROUGH field in this component.
  It must NOT be evaluated, modified, nullified, or conditionally assigned.
  It is set once — by Identity Broken Record Builder (= tenant_id)
  or as NULL by Type A Record Builder and Closure Rule Enforcer —
  and must arrive at the Allocation Grain Writer unchanged.

Spec: allocation-engine-design.md — Component 8 — Cost & Revenue Calculator
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.allocation.type_a_builder import TypeAGrainRecord
from app.allocation.identity_broken_builder import IdentityBrokenGrainRecord
from app.allocation.closure_rule_enforcer import CapacityIdleRecord


@dataclass(frozen=True)
class ComputedRecord:
    """Fully computed grain record — ready for Grain Writer."""

    region: str
    gpu_pool_id: str
    date: date
    billing_period: str
    allocation_target: str
    unallocated_type: str | None
    failed_tenant_id: str | None     # pass-through — L2 P2 #14
    gpu_hours: Decimal
    cost_per_gpu_hour: Decimal
    contracted_rate: Decimal | None
    revenue: Decimal
    cogs: Decimal
    gross_margin: Decimal


class CalculatorResult(BaseModel):
    """Result of the Cost & Revenue Calculator."""

    result: Literal["SUCCESS", "FAIL"]
    records: list[ComputedRecord] = Field(default_factory=list)
    error: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def success(cls, records: list[ComputedRecord]) -> CalculatorResult:
        return cls(result="SUCCESS", records=records)

    @classmethod
    def failed(cls, error: str) -> CalculatorResult:
        return cls(result="FAIL", error=error)


def _validate_type_a(rec: TypeAGrainRecord) -> str | None:
    """Return error string if a required Type A field is null or zero."""
    if not rec.gpu_hours or rec.gpu_hours == Decimal("0"):
        return f"Null or zero in required field: gpu_hours · {rec}"
    if not rec.cost_per_gpu_hour or rec.cost_per_gpu_hour == Decimal("0"):
        return f"Null or zero in required field: cost_per_gpu_hour · {rec}"
    if not rec.contracted_rate or rec.contracted_rate == Decimal("0"):
        return f"Null or zero in required field: contracted_rate · {rec}"
    return None


def _validate_type_b(rec: IdentityBrokenGrainRecord | CapacityIdleRecord,
                     label: str) -> str | None:
    """Return error string if a required Type B field is null or zero."""
    if not rec.gpu_hours or rec.gpu_hours == Decimal("0"):
        return f"Null or zero in required field: gpu_hours · {label} · {rec}"
    if not rec.cost_per_gpu_hour or rec.cost_per_gpu_hour == Decimal("0"):
        return f"Null or zero in required field: cost_per_gpu_hour · {label} · {rec}"
    return None


def calculate_cost_revenue(
    type_a: list[TypeAGrainRecord],
    identity_broken: list[IdentityBrokenGrainRecord],
    capacity_idle: list[CapacityIdleRecord],
) -> CalculatorResult:
    """
    Compute revenue, cogs, and gross_margin for all grain records.

    Parameters
    ----------
    type_a : list[TypeAGrainRecord]
        Type A grain records from Type A Builder.
    identity_broken : list[IdentityBrokenGrainRecord]
        Identity broken grain records from Identity Broken Builder.
    capacity_idle : list[CapacityIdleRecord]
        Capacity idle records from Closure Rule Enforcer.

    Returns
    -------
    CalculatorResult
        SUCCESS with computed records, or FAIL if validation fails.
    """
    computed: list[ComputedRecord] = []

    # ── Type A: revenue = gpu_hours × contracted_rate ──
    for rec in type_a:
        err = _validate_type_a(rec)
        if err:
            return CalculatorResult.failed(error=err)

        revenue = rec.gpu_hours * rec.contracted_rate
        cogs = rec.gpu_hours * rec.cost_per_gpu_hour
        gross_margin = revenue - cogs

        computed.append(
            ComputedRecord(
                region=rec.region,
                gpu_pool_id=rec.gpu_pool_id,
                date=rec.date,
                billing_period=rec.billing_period,
                allocation_target=rec.allocation_target,
                unallocated_type=rec.unallocated_type,
                failed_tenant_id=rec.failed_tenant_id,   # pass-through
                gpu_hours=rec.gpu_hours,
                cost_per_gpu_hour=rec.cost_per_gpu_hour,
                contracted_rate=rec.contracted_rate,
                revenue=revenue,
                cogs=cogs,
                gross_margin=gross_margin,
            )
        )

    # ── Type B / identity_broken: revenue = 0, gross_margin = −cogs ──
    for rec in identity_broken:
        err = _validate_type_b(rec, "identity_broken")
        if err:
            return CalculatorResult.failed(error=err)

        cogs = rec.gpu_hours * rec.cost_per_gpu_hour
        gross_margin = -cogs

        computed.append(
            ComputedRecord(
                region=rec.region,
                gpu_pool_id=rec.gpu_pool_id,
                date=rec.date,
                billing_period=rec.billing_period,
                allocation_target=rec.allocation_target,
                unallocated_type=rec.unallocated_type,
                failed_tenant_id=rec.failed_tenant_id,   # pass-through
                gpu_hours=rec.gpu_hours,
                cost_per_gpu_hour=rec.cost_per_gpu_hour,
                contracted_rate=rec.contracted_rate,
                revenue=rec.revenue,
                cogs=cogs,
                gross_margin=gross_margin,
            )
        )

    # ── Type B / capacity_idle: revenue = 0, gross_margin = −cogs ──
    for rec in capacity_idle:
        err = _validate_type_b(rec, "capacity_idle")
        if err:
            return CalculatorResult.failed(error=err)

        cogs = rec.gpu_hours * rec.cost_per_gpu_hour
        gross_margin = -cogs

        computed.append(
            ComputedRecord(
                region=rec.region,
                gpu_pool_id=rec.gpu_pool_id,
                date=rec.date,
                billing_period=rec.billing_period,
                allocation_target=rec.allocation_target,
                unallocated_type=rec.unallocated_type,
                failed_tenant_id=rec.failed_tenant_id,   # pass-through
                gpu_hours=rec.gpu_hours,
                cost_per_gpu_hour=rec.cost_per_gpu_hour,
                contracted_rate=rec.contracted_rate,
                revenue=rec.revenue,
                cogs=cogs,
                gross_margin=gross_margin,
            )
        )

    return CalculatorResult.success(records=computed)
