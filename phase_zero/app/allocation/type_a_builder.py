"""
Type A Record Builder — Component 5/10.

Layer: Allocation.
Grain: Region × GPU Pool × Day × tenant_id (Type A).

Assembles Type A grain records from IAM-resolved records + cost rates.
  allocation_target  = tenant_id
  unallocated_type   = None
  failed_tenant_id   = None
  cost_per_gpu_hour  = from cost_rates lookup
  contracted_rate    = from IAM resolution

Revenue, cogs, gross_margin computed downstream by Cost & Revenue Calculator.

Spec: allocation-engine-design.md — Component 5 — Type A Record Builder
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.allocation.iam_resolver import TypeARecord
from app.allocation.cost_rate_reader import CostRateRecord


@dataclass(frozen=True)
class TypeAGrainRecord:
    """Type A grain record — ready for Closure Rule Enforcer."""

    region: str
    gpu_pool_id: str
    date: date
    billing_period: str
    allocation_target: str
    unallocated_type: str | None
    failed_tenant_id: str | None
    gpu_hours: Decimal
    cost_per_gpu_hour: Decimal
    contracted_rate: Decimal


class TypeABuilderResult(BaseModel):
    """Result of the Type A Record Builder."""

    result: Literal["SUCCESS", "FAIL"]
    records: list[TypeAGrainRecord] = Field(default_factory=list)
    error: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def success(cls, records: list[TypeAGrainRecord]) -> TypeABuilderResult:
        return cls(result="SUCCESS", records=records)

    @classmethod
    def failed(cls, error: str) -> TypeABuilderResult:
        return cls(result="FAIL", error=error)


def _build_cost_index(
    cost_rates: list[CostRateRecord],
) -> dict[tuple[str, str, date], CostRateRecord]:
    """Index cost rates by (region, gpu_pool_id, date) for O(1) lookup."""
    return {
        (r.region, r.gpu_pool_id, r.date): r
        for r in cost_rates
    }


def build_type_a_records(
    type_a: list[TypeARecord],
    cost_rates: list[CostRateRecord],
) -> TypeABuilderResult:
    """
    Build Type A grain records.

    Parameters
    ----------
    type_a : list[TypeARecord]
        IAM-resolved Type A records from IAM Resolver.
    cost_rates : list[CostRateRecord]
        Cost rates from Cost Rate Reader.

    Returns
    -------
    TypeABuilderResult
        SUCCESS with grain records, or FAIL if cost rate missing.
    """
    cost_index = _build_cost_index(cost_rates)
    records: list[TypeAGrainRecord] = []

    for rec in type_a:
        key = (rec.region, rec.gpu_pool_id, rec.date)
        cost = cost_index.get(key)

        if cost is None:
            return TypeABuilderResult.failed(
                error=f"No cost rate for {rec.region} + {rec.gpu_pool_id} + {rec.date}"
            )

        records.append(
            TypeAGrainRecord(
                region=rec.region,
                gpu_pool_id=rec.gpu_pool_id,
                date=rec.date,
                billing_period=rec.billing_period,
                allocation_target=rec.tenant_id,
                unallocated_type=None,
                failed_tenant_id=None,
                gpu_hours=rec.gpu_hours,
                cost_per_gpu_hour=cost.cost_per_gpu_hour,
                contracted_rate=rec.contracted_rate,
            )
        )

    return TypeABuilderResult.success(records=records)
