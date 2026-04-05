"""
Identity Broken Record Builder — Component 6/10.

Layer: Allocation.
Grain: Region × GPU Pool × Day × 'unallocated' / identity_broken.

Assembles Type B / identity_broken grain records from unresolved
telemetry records + cost rates.
  allocation_target  = 'unallocated'
  unallocated_type   = 'identity_broken'
  failed_tenant_id   = tenant_id (carried from IAM Resolver output)
  contracted_rate    = None
  revenue            = 0

Record Builder Required Field Checklist (L2 P1 #11):
  1. failed_tenant_id  = tenant_id (from IAM Resolver)
  2. unallocated_type  = 'identity_broken'
  3. allocation_target = 'unallocated'

Spec: allocation-engine-design.md — Component 6 — Identity Broken Record Builder
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.allocation.iam_resolver import IdentityBrokenRecord
from app.allocation.cost_rate_reader import CostRateRecord


@dataclass(frozen=True)
class IdentityBrokenGrainRecord:
    """Type B / identity_broken grain record — ready for Closure Rule Enforcer."""

    region: str
    gpu_pool_id: str
    date: date
    billing_period: str
    allocation_target: str
    unallocated_type: str
    failed_tenant_id: str
    gpu_hours: Decimal
    cost_per_gpu_hour: Decimal
    contracted_rate: Decimal | None
    revenue: Decimal


class IdentityBrokenBuilderResult(BaseModel):
    """Result of the Identity Broken Record Builder."""

    result: Literal["SUCCESS", "FAIL"]
    records: list[IdentityBrokenGrainRecord] = Field(default_factory=list)
    error: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def success(cls, records: list[IdentityBrokenGrainRecord]) -> IdentityBrokenBuilderResult:
        return cls(result="SUCCESS", records=records)

    @classmethod
    def failed(cls, error: str) -> IdentityBrokenBuilderResult:
        return cls(result="FAIL", error=error)


def _build_cost_index(
    cost_rates: list[CostRateRecord],
) -> dict[tuple[str, str, date], CostRateRecord]:
    """Index cost rates by (region, gpu_pool_id, date) for O(1) lookup."""
    return {
        (r.region, r.gpu_pool_id, r.date): r
        for r in cost_rates
    }


def build_identity_broken_records(
    identity_broken: list[IdentityBrokenRecord],
    cost_rates: list[CostRateRecord],
) -> IdentityBrokenBuilderResult:
    """
    Build identity_broken grain records.

    Parameters
    ----------
    identity_broken : list[IdentityBrokenRecord]
        Unresolved records from IAM Resolver.
    cost_rates : list[CostRateRecord]
        Cost rates from Cost Rate Reader.

    Returns
    -------
    IdentityBrokenBuilderResult
        SUCCESS with grain records, or FAIL if cost rate missing.
    """
    cost_index = _build_cost_index(cost_rates)
    records: list[IdentityBrokenGrainRecord] = []

    for rec in identity_broken:
        key = (rec.region, rec.gpu_pool_id, rec.date)
        cost = cost_index.get(key)

        if cost is None:
            return IdentityBrokenBuilderResult.failed(
                error=f"No cost rate for {rec.region} + {rec.gpu_pool_id} + {rec.date}"
            )

        records.append(
            IdentityBrokenGrainRecord(
                region=rec.region,
                gpu_pool_id=rec.gpu_pool_id,
                date=rec.date,
                billing_period=rec.billing_period,
                allocation_target="unallocated",
                unallocated_type="identity_broken",
                failed_tenant_id=rec.tenant_id,
                gpu_hours=rec.gpu_hours,
                cost_per_gpu_hour=cost.cost_per_gpu_hour,
                contracted_rate=None,
                revenue=Decimal("0"),
            )
        )

    return IdentityBrokenBuilderResult.success(records=records)
