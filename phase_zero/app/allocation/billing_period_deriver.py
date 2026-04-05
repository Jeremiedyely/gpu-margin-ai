"""
Billing Period Deriver — Component 2/10.

Layer: Allocation.

Enriches each aggregated telemetry record with billing_period = YYYY-MM,
derived from the record's date field. Imports the derivation from the
shared constant module (Contract 1 — no inline derivation).

Spec: allocation-engine-design.md — Component 2 — Billing Period Deriver
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.shared.billing_period import derive_billing_period
from app.allocation.telemetry_aggregator import TelemetryAggregatedRecord


@dataclass(frozen=True)
class TelemetryEnrichedRecord:
    """Telemetry record enriched with billing_period."""

    tenant_id: str
    region: str
    gpu_pool_id: str
    date: date
    billing_period: str
    gpu_hours: Decimal


class DeriverResult(BaseModel):
    """Result of the Billing Period Deriver."""

    result: Literal["SUCCESS", "FAIL"]
    records: list[TelemetryEnrichedRecord] = Field(default_factory=list)
    error: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def success(cls, records: list[TelemetryEnrichedRecord]) -> DeriverResult:
        return cls(result="SUCCESS", records=records)

    @classmethod
    def failed(cls, error: str) -> DeriverResult:
        return cls(result="FAIL", error=error)


def derive_billing_periods(
    records: list[TelemetryAggregatedRecord],
) -> DeriverResult:
    """
    Enrich aggregated telemetry records with billing_period.

    Parameters
    ----------
    records : list[TelemetryAggregatedRecord]
        Output from the Telemetry Aggregator.

    Returns
    -------
    DeriverResult
        SUCCESS with enriched records, or FAIL if any date is invalid.
    """
    enriched: list[TelemetryEnrichedRecord] = []

    for rec in records:
        try:
            bp = derive_billing_period(rec.date)
        except Exception as exc:
            return DeriverResult.failed(
                error=f"Cannot derive billing_period — invalid date: {rec.date} ({exc})"
            )

        enriched.append(
            TelemetryEnrichedRecord(
                tenant_id=rec.tenant_id,
                region=rec.region,
                gpu_pool_id=rec.gpu_pool_id,
                date=rec.date,
                billing_period=bp,
                gpu_hours=rec.gpu_hours,
            )
        )

    return DeriverResult.success(records=enriched)
