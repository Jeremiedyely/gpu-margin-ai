"""
Check 2 Executor — Usage vs Tenant Mapping — Component 2/7.

Layer: Reconciliation.
Grain: Every distinct tenant_id + billing_period in raw.telemetry.

For every DISTINCT tenant_id + billing_period in raw.telemetry
WHERE session_id = current session:
  LEFT JOIN to raw.iam ON tenant_id + billing_period + session_id
  IF no iam row found → unresolved pair

IF ANY unresolved pair → verdict = FAIL
IF ALL pairs resolve  → verdict = PASS

Coupling contract (L2 P2 #22):
  billing_period derived using derive_billing_period from
  app/shared/billing_period.py — Contract 1.
  Same derivation as IAM Resolver (AE Component 4).
  A change to either is a mandatory simultaneous change to the other.

Both source tables filtered by session_id (defense in depth).

Spec: reconciliation-engine-design.md — Component 2 — Check 2 Executor
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from app.shared.billing_period import derive_billing_period


@dataclass(frozen=True)
class UnresolvedPair:
    """One tenant_id + billing_period with no IAM match."""

    tenant_id: str
    billing_period: str


class Check2Result(BaseModel):
    """Result of the Check 2 Executor."""

    verdict: Literal["PASS", "FAIL"]
    session_id: UUID | None = None
    failing_count: int | None = None
    unresolved_pairs: list[UnresolvedPair] = Field(default_factory=list)
    detail: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def passed(cls, session_id: UUID) -> Check2Result:
        return cls(verdict="PASS", session_id=session_id)

    @classmethod
    def failed(cls, session_id: UUID, pairs: list[UnresolvedPair]) -> Check2Result:
        return cls(
            verdict="FAIL", session_id=session_id,
            failing_count=len(pairs), unresolved_pairs=pairs,
        )

    @classmethod
    def error(cls, session_id: UUID, detail: str) -> Check2Result:
        return cls(verdict="FAIL", session_id=session_id, detail=detail)


_TELEMETRY_PAIRS_SQL = text("""
    SELECT DISTINCT
        tenant_id,
        date
    FROM raw.telemetry
    WHERE session_id = :sid
""")

_IAM_CHECK_SQL = text("""
    SELECT 1
    FROM raw.iam
    WHERE session_id = :sid
      AND tenant_id = :tid
      AND billing_period = :bp
""")


def execute_check2(
    conn: Connection,
    session_id: UUID,
) -> Check2Result:
    """
    Execute Check 2: Usage vs Tenant Mapping.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection (caller owns transaction boundary).
    session_id : UUID
        Current ingestion session.

    Returns
    -------
    Check2Result
        PASS if all tenant+billing_period pairs resolve, FAIL otherwise.
    """
    try:
        telemetry_rows = conn.execute(
            _TELEMETRY_PAIRS_SQL, {"sid": str(session_id)}
        ).fetchall()
    except Exception as exc:
        return Check2Result.error(
            session_id=session_id,
            detail=f"Check 2 could not execute — source unreadable: raw.telemetry: {exc}",
        )

    if not telemetry_rows:
        return Check2Result.error(
            session_id=session_id,
            detail="Check 2 could not execute — raw.telemetry empty for session",
        )

    # Derive distinct tenant_id + billing_period pairs using shared module
    seen: set[tuple[str, str]] = set()
    for row in telemetry_rows:
        bp = derive_billing_period(row.date)
        seen.add((row.tenant_id, bp))

    unresolved: list[UnresolvedPair] = []

    for tenant_id, billing_period in sorted(seen):
        try:
            match = conn.execute(
                _IAM_CHECK_SQL,
                {"sid": str(session_id), "tid": tenant_id, "bp": billing_period},
            ).fetchone()
        except Exception as exc:
            return Check2Result.error(
                session_id=session_id,
                detail=f"Check 2 could not execute — source unreadable: raw.iam: {exc}",
            )

        if match is None:
            unresolved.append(
                UnresolvedPair(tenant_id=tenant_id, billing_period=billing_period)
            )

    if unresolved:
        return Check2Result.failed(session_id=session_id, pairs=unresolved)

    return Check2Result.passed(session_id=session_id)
