"""
IAM Resolver — Component 4/10.

Layer: Allocation.

LEFT JOINs enriched telemetry records against raw.iam on
tenant_id + billing_period. Classifies each record:
  - Match found    → TYPE_A (contracted_rate from IAM)
  - No match found → IDENTITY_BROKEN (contracted_rate = None)

billing_period join key is guaranteed YYYY-MM by IAM Validator (S1).
Join is exact — no approximation logic required.

Spec: allocation-engine-design.md — Component 4 — IAM Resolver
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from app.allocation.billing_period_deriver import TelemetryEnrichedRecord


@dataclass(frozen=True)
class TypeARecord:
    """Telemetry record matched to IAM — classified as Type A."""

    tenant_id: str
    region: str
    gpu_pool_id: str
    date: date
    billing_period: str
    gpu_hours: Decimal
    contracted_rate: Decimal


@dataclass(frozen=True)
class IdentityBrokenRecord:
    """Telemetry record with no IAM match — classified as identity_broken."""

    tenant_id: str
    region: str
    gpu_pool_id: str
    date: date
    billing_period: str
    gpu_hours: Decimal


class ResolverResult(BaseModel):
    """Result of the IAM Resolver."""

    result: Literal["SUCCESS", "FAIL"]
    type_a: list[TypeARecord] = Field(default_factory=list)
    identity_broken: list[IdentityBrokenRecord] = Field(default_factory=list)
    error: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def success(
        cls,
        type_a: list[TypeARecord],
        identity_broken: list[IdentityBrokenRecord],
    ) -> ResolverResult:
        return cls(result="SUCCESS", type_a=type_a,
                   identity_broken=identity_broken)

    @classmethod
    def failed(cls, error: str) -> ResolverResult:
        return cls(result="FAIL", error=error)


_IAM_LOOKUP_SQL = text("""
    SELECT contracted_rate
    FROM raw.iam
    WHERE tenant_id = :tenant_id
      AND billing_period = :billing_period
      AND session_id = :sid
""")


def resolve_iam(
    conn: Connection,
    session_id: UUID,
    records: list[TelemetryEnrichedRecord],
) -> ResolverResult:
    """
    Resolve each enriched telemetry record against raw.iam.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection (caller owns transaction boundary).
    session_id : UUID
        Current ingestion session.
    records : list[TelemetryEnrichedRecord]
        Output from the Billing Period Deriver.

    Returns
    -------
    ResolverResult
        SUCCESS with classified type_a and identity_broken lists.
        FAIL if raw.iam is unreadable.
    """
    type_a: list[TypeARecord] = []
    identity_broken: list[IdentityBrokenRecord] = []

    try:
        for rec in records:
            row = conn.execute(
                _IAM_LOOKUP_SQL,
                {
                    "tenant_id": rec.tenant_id,
                    "billing_period": rec.billing_period,
                    "sid": str(session_id),
                },
            ).fetchone()

            if row is not None:
                type_a.append(
                    TypeARecord(
                        tenant_id=rec.tenant_id,
                        region=rec.region,
                        gpu_pool_id=rec.gpu_pool_id,
                        date=rec.date,
                        billing_period=rec.billing_period,
                        gpu_hours=rec.gpu_hours,
                        contracted_rate=row.contracted_rate,
                    )
                )
            else:
                identity_broken.append(
                    IdentityBrokenRecord(
                        tenant_id=rec.tenant_id,
                        region=rec.region,
                        gpu_pool_id=rec.gpu_pool_id,
                        date=rec.date,
                        billing_period=rec.billing_period,
                        gpu_hours=rec.gpu_hours,
                    )
                )

        return ResolverResult.success(type_a=type_a,
                                      identity_broken=identity_broken)

    except Exception as exc:
        return ResolverResult.failed(error=f"raw.iam unavailable: {exc}")
