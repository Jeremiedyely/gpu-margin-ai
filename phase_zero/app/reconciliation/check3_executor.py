"""
Check 3 Executor — Computed vs Billed vs Posted — Component 4/7.

Layer: Reconciliation.
Grain: allocation_target × billing_period WHERE allocation_target ≠ 'unallocated'.

CONTRACT BOUNDARY (L2 P1 #18):
  The filter WHERE allocation_target ≠ 'unallocated' is mandatory.
  Removing it causes 'unallocated' rows (capacity_idle and identity_broken)
  to attempt billing joins — no billing row exists for 'unallocated' —
  generating spurious FAIL-1 verdicts with no system error.

Per allocation_target × billing_period (WHERE allocation_target ≠ 'unallocated'):
  computed = SUM(allocation_grain.revenue)
  billed   = raw.billing.billable_amount  (join: allocation_target = tenant_id)
  posted   = raw.erp.amount_posted        (join: allocation_target = tenant_id)

  FAIL-1: computed ≠ billed
  FAIL-2: billed ≠ posted
  Precedence: FAIL-1 wins over FAIL-2 for same pair.

Gated on AE Completion Listener READY — caller ensures listener_result = READY
before invoking this component.

All source tables filtered by session_id (defense in depth).

Cross-module coupling (L2 P2 #19):
  billing_period in allocation_grain is written by AE Billing Period Deriver
  using LEFT(date, 7). Check 3 joins on this explicit field.
  A change to the AE derivation requires simultaneous update here.

Spec: reconciliation-engine-design.md — Component 4 — Check 3 Executor
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import Connection, text


@dataclass(frozen=True)
class Check3FailingRecord:
    """One allocation_target × billing_period with a FAIL-1 or FAIL-2."""

    allocation_target: str
    billing_period: str
    fail_type: str  # "FAIL-1" or "FAIL-2"
    computed: Decimal
    billed: Decimal | None
    posted: Decimal | None


class Check3Result(BaseModel):
    """Result of the Check 3 Executor."""

    verdict: Literal["PASS", "FAIL"]
    session_id: UUID | None = None
    failing_count: int | None = None
    failing_records: list[Check3FailingRecord] = Field(default_factory=list)
    detail: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def passed(cls, session_id: UUID) -> Check3Result:
        return cls(verdict="PASS", session_id=session_id)

    @classmethod
    def failed(cls, session_id: UUID, records: list[Check3FailingRecord]) -> Check3Result:
        return cls(
            verdict="FAIL", session_id=session_id,
            failing_count=len(records), failing_records=records,
        )

    @classmethod
    def error(cls, session_id: UUID, detail: str) -> Check3Result:
        return cls(verdict="FAIL", session_id=session_id, detail=detail)


# ── SQL ──────────────────────────────────────────────────────────────

# CONTRACT BOUNDARY: WHERE allocation_target <> 'unallocated' is MANDATORY (L2 P1 #18)
_COMPUTED_SQL = text("""
    SELECT
        allocation_target,
        billing_period,
        SUM(revenue) AS computed
    FROM dbo.allocation_grain
    WHERE session_id = :sid
      AND allocation_target <> 'unallocated'
    GROUP BY allocation_target, billing_period
""")

_BILLING_SQL = text("""
    SELECT
        tenant_id,
        billing_period,
        billable_amount
    FROM raw.billing
    WHERE session_id = :sid
""")

_ERP_SQL = text("""
    SELECT
        tenant_id,
        billing_period,
        amount_posted
    FROM raw.erp
    WHERE session_id = :sid
""")


def execute_check3(
    conn: Connection,
    session_id: UUID,
) -> Check3Result:
    """
    Execute Check 3: Computed vs Billed vs Posted.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection (caller owns transaction boundary).
    session_id : UUID
        Current ingestion session.

    Returns
    -------
    Check3Result
        PASS if computed = billed and billed = posted for all pairs, FAIL otherwise.
    """
    try:
        computed_rows = conn.execute(_COMPUTED_SQL, {"sid": str(session_id)}).fetchall()
        billing_rows = conn.execute(_BILLING_SQL, {"sid": str(session_id)}).fetchall()
        erp_rows = conn.execute(_ERP_SQL, {"sid": str(session_id)}).fetchall()
    except Exception as exc:
        return Check3Result.error(
            session_id=session_id,
            detail=f"Check 3 could not execute — source unreadable: {exc}",
        )

    if not computed_rows:
        return Check3Result.error(
            session_id=session_id,
            detail="Check 3 could not execute — allocation_grain empty or no "
            "allocated records for session",
        )

    # Build billing index: (tenant_id, billing_period) → billable_amount
    billing_index: dict[tuple[str, str], Decimal] = {
        (r.tenant_id, r.billing_period): r.billable_amount
        for r in billing_rows
    }

    # Build ERP index: (tenant_id, billing_period) → amount_posted
    erp_index: dict[tuple[str, str], Decimal] = {
        (r.tenant_id, r.billing_period): r.amount_posted
        for r in erp_rows
    }

    failing: list[Check3FailingRecord] = []

    for row in sorted(computed_rows, key=lambda r: (r.allocation_target, r.billing_period)):
        key = (row.allocation_target, row.billing_period)
        billed = billing_index.get(key)
        posted = erp_index.get(key)

        # Missing billing row → FAIL
        if billed is None:
            failing.append(
                Check3FailingRecord(
                    allocation_target=row.allocation_target,
                    billing_period=row.billing_period,
                    fail_type="FAIL-1",
                    computed=row.computed,
                    billed=None,
                    posted=posted,
                )
            )
            continue

        # FAIL-1 check: computed ≠ billed (precedence — wins over FAIL-2)
        if row.computed != billed:
            failing.append(
                Check3FailingRecord(
                    allocation_target=row.allocation_target,
                    billing_period=row.billing_period,
                    fail_type="FAIL-1",
                    computed=row.computed,
                    billed=billed,
                    posted=posted,
                )
            )
            continue

        # Missing ERP row → FAIL
        if posted is None:
            failing.append(
                Check3FailingRecord(
                    allocation_target=row.allocation_target,
                    billing_period=row.billing_period,
                    fail_type="FAIL-2",
                    computed=row.computed,
                    billed=billed,
                    posted=None,
                )
            )
            continue

        # FAIL-2 check: billed ≠ posted
        if billed != posted:
            failing.append(
                Check3FailingRecord(
                    allocation_target=row.allocation_target,
                    billing_period=row.billing_period,
                    fail_type="FAIL-2",
                    computed=row.computed,
                    billed=billed,
                    posted=posted,
                )
            )

    if failing:
        return Check3Result.failed(session_id=session_id, records=failing)

    return Check3Result.passed(session_id=session_id)
