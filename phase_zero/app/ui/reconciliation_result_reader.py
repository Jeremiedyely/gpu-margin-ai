"""
Reconciliation Result Reader — Component 10/14.

Layer: UI (backend aggregator).

Reads reconciliation_results for the active session.
Returns exactly three rows in fixed order:
  Row 1: Capacity vs Usage            → PASS | FAIL
  Row 2: Usage vs Tenant Mapping      → PASS | FAIL
  Row 3: Computed vs Billed vs Posted → PASS | FAIL

If result set has < 3 rows or is null → result_payload = NULL.
Do not render PASS for rows with missing data.

Spec: ui-screen-design.md — Component 10 — Reconciliation Result Reader
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import Connection, text


class ReconciliationRecord(BaseModel):
    """One reconciliation check verdict."""

    check: str
    verdict: Literal["PASS", "FAIL"]


class ReconciliationReaderResult(BaseModel):
    """Result of the Reconciliation Result Reader."""

    result: Literal["SUCCESS", "FAIL"]
    payload: list[ReconciliationRecord] | None = None
    error: str | None = None

    @classmethod
    def success(
        cls, payload: list[ReconciliationRecord],
    ) -> ReconciliationReaderResult:
        return cls(result="SUCCESS", payload=payload)

    @classmethod
    def failed(cls, error: str) -> ReconciliationReaderResult:
        return cls(result="FAIL", error=error)


_EXPECTED_CHECKS = [
    "Capacity vs Usage",
    "Usage vs Tenant Mapping",
    "Computed vs Billed vs Posted",
]

_READ_SQL = text("""
    SELECT check_name, verdict
    FROM dbo.reconciliation_results
    WHERE session_id = :sid
    ORDER BY check_order ASC
""")


def read_reconciliation_results(
    conn: Connection,
    session_id: UUID,
) -> ReconciliationReaderResult:
    """
    Read reconciliation verdicts for the given session.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection (caller owns transaction boundary).
    session_id : UUID
        Current session.

    Returns
    -------
    ReconciliationReaderResult
        SUCCESS with exactly 3 ReconciliationRecord rows, or FAIL.
    """
    try:
        rows = conn.execute(_READ_SQL, {"sid": str(session_id)}).fetchall()
    except Exception as exc:
        return ReconciliationReaderResult.failed(
            error=(
                f"Reconciliation results read failed "
                f"for session {session_id}: {exc}"
            )
        )

    if len(rows) != 3:
        return ReconciliationReaderResult.failed(
            error=(
                f"Expected 3 reconciliation rows for session {session_id}, "
                f"got {len(rows)}"
            )
        )

    # Validate check names match expected set in correct order
    for i, row in enumerate(rows):
        if row.check_name != _EXPECTED_CHECKS[i]:
            return ReconciliationReaderResult.failed(
                error=(
                    f"Unexpected check at position {i + 1}: "
                    f"'{row.check_name}' — expected '{_EXPECTED_CHECKS[i]}'"
                )
            )

    payload = [
        ReconciliationRecord(check=row.check_name, verdict=row.verdict)
        for row in rows
    ]

    return ReconciliationReaderResult.success(payload=payload)
