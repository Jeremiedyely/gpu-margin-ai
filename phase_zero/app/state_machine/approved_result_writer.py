"""
Approved Result Writer — Component 9/12.

Layer: State.

Writes final.allocation_result as an immutable grain copy from
dbo.allocation_grain for the current session. Then persists
application_state=APPROVED + write_result in ONE atomic State Store
transaction (P1 #26). No crash window between the two writes.

Spec: state-machine-design.md — Component 9 — Approved Result Writer
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Connection, text

from app.state_machine.analyzed_to_approved_executor import (
    ApprovalTransitionResult,
)
from app.state_machine.state_store import StateWriteRequest, write_state


# ── SQL ─────────────────────────────────────────────────────────────

_COPY_GRAIN_SQL = text("""
    INSERT INTO final.allocation_result
        (session_id, region, gpu_pool_id, date, billing_period,
         allocation_target, unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate,
         revenue, cogs, gross_margin)
    SELECT
        session_id, region, gpu_pool_id, date, billing_period,
        allocation_target, unallocated_type, failed_tenant_id,
        gpu_hours, cost_per_gpu_hour, contracted_rate,
        revenue, cogs, gross_margin
    FROM dbo.allocation_grain
    WHERE session_id = :sid
""")

_COUNT_RESULT_SQL = text("""
    SELECT COUNT(*) AS cnt
    FROM final.allocation_result
    WHERE session_id = :sid
""")


# ── Models ──────────────────────────────────────────────────────────

class ApprovedWriteResult(BaseModel):
    """Output of the Approved Result Writer."""

    result: Literal["SUCCESS", "FAIL"]
    session_id: UUID | None = None
    approved_at: datetime | None = None
    row_count: int = 0
    error: str | None = None

    @classmethod
    def success(
        cls, session_id: UUID, approved_at: datetime, row_count: int,
    ) -> ApprovedWriteResult:
        return cls(
            result="SUCCESS",
            session_id=session_id,
            approved_at=approved_at,
            row_count=row_count,
        )

    @classmethod
    def failed(
        cls, session_id: UUID | None, error: str,
    ) -> ApprovedWriteResult:
        return cls(result="FAIL", session_id=session_id, error=error)


# ── Public API ──────────────────────────────────────────────────────

def write_approved_result(
    conn: Connection,
    transition: ApprovalTransitionResult,
) -> ApprovedWriteResult:
    """
    Write the approved result and persist APPROVED state atomically.

    Steps (all within ONE savepoint):
    1. Guard: transition must be SUCCESS with session_id.
    2. Copy allocation_grain → final.allocation_result.
    3. Verify row_count > 0 (non-empty grain).
    4. Write application_state=APPROVED + write_result=SUCCESS
       to State Store (P1 #26 atomic).
    5. Commit savepoint — both writes land or neither does.

    On failure at any step:
    - Savepoint is rolled back (no partial writes).
    - write_result=FAIL is persisted to State Store outside the
      savepoint (state stays ANALYZED, write_result records failure).

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection (caller owns outer transaction).
    transition : ApprovalTransitionResult
        Must be SUCCESS from Component 8.

    Returns
    -------
    ApprovedWriteResult
        SUCCESS with row_count and approved_at, or FAIL with error.
    """
    # ── 1. Guard ────────────────────────────────────────────────────
    if transition.result != "SUCCESS":
        return ApprovedWriteResult.failed(
            session_id=transition.session_id,
            error=(
                "Approved Result Writer received non-SUCCESS transition: "
                f"{transition.result}"
            ),
        )

    if transition.session_id is None:
        return ApprovedWriteResult.failed(
            session_id=None,
            error="Approved Result Writer requires session_id",
        )

    session_id = transition.session_id
    approved_at = datetime.now(timezone.utc)

    # ── 2–5. Atomic write: grain copy + APPROVED state ──────────────
    try:
        savepoint = conn.begin_nested()
        try:
            # 2. Copy grain → final.allocation_result
            conn.execute(_COPY_GRAIN_SQL, {"sid": str(session_id)})

            # 3. Verify row_count > 0
            row = conn.execute(
                _COUNT_RESULT_SQL, {"sid": str(session_id)},
            ).fetchone()
            row_count = row.cnt if row else 0

            if row_count == 0:
                savepoint.rollback()
                # Persist write_result=FAIL to State Store
                write_state(
                    conn,
                    StateWriteRequest(
                        new_state="APPROVED",
                        trigger="CFO_APPROVAL",
                        session_id=session_id,
                        write_result="FAIL",
                    ),
                    from_state="ANALYZED",
                )
                return ApprovedWriteResult.failed(
                    session_id=session_id,
                    error=(
                        "Approved result table write failed — "
                        "no allocation_grain rows for session"
                    ),
                )

            # 4. Write APPROVED + write_result=SUCCESS to State Store
            #    This MUST be inside the same savepoint (P1 #26)
            store_result = write_state(
                conn,
                StateWriteRequest(
                    new_state="APPROVED",
                    trigger="CFO_APPROVAL",
                    session_id=session_id,
                    write_result="SUCCESS",
                ),
                from_state="ANALYZED",
            )

            if store_result.result != "SUCCESS":
                savepoint.rollback()
                return ApprovedWriteResult.failed(
                    session_id=session_id,
                    error=(
                        "Approved result table written but state persist "
                        f"failed: {store_result.error}"
                    ),
                )

            # 5. Commit — both writes land
            savepoint.commit()

        except Exception as exc:
            savepoint.rollback()
            # Persist write_result=FAIL to State Store
            try:
                write_state(
                    conn,
                    StateWriteRequest(
                        new_state="APPROVED",
                        trigger="CFO_APPROVAL",
                        session_id=session_id,
                        write_result="FAIL",
                    ),
                    from_state="ANALYZED",
                )
            except Exception:
                pass  # Best-effort FAIL recording
            return ApprovedWriteResult.failed(
                session_id=session_id,
                error=(
                    f"Approved result table write failed: {exc}"
                ),
            )

        return ApprovedWriteResult.success(
            session_id=session_id,
            approved_at=approved_at,
            row_count=row_count,
        )

    except Exception as exc:
        return ApprovedWriteResult.failed(
            session_id=session_id,
            error=(
                f"CRITICAL: approved result writer failed — "
                f"data integrity at risk: {exc}"
            ),
        )
