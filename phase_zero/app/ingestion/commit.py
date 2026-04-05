"""
Ingestion Commit — Component 17/19.

Atomic gate for the ingestion pipeline.
Receives the OrchestrationPayload and either:
  - Writes all 5 raw tables + ingestion_log in a single transaction (SUCCESS)
  - Returns FAIL with no DB writes (orchestration failed)

If any write fails mid-transaction → ROLLBACK. No partial data survives.
Uses engine.begin() context manager for automatic commit/rollback/close.

Spec: ingestion-module-design.md — Layer 4b — Ingestion Commit
"""

from __future__ import annotations

import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import Engine, text

from app.ingestion.orchestrator import OrchestrationPayload
from app.ingestion.writers.telemetry import write_telemetry
from app.ingestion.writers.cost_management import write_cost_management
from app.ingestion.writers.iam import write_iam
from app.ingestion.writers.billing import write_billing
from app.ingestion.writers.erp import write_erp


class CommitResult(BaseModel):
    """Result of the atomic ingestion commit."""

    result: Literal["SUCCESS", "FAIL"]
    session_id: UUID
    reason: str | None = None

    @classmethod
    def success(cls, session_id: UUID) -> CommitResult:
        return cls(result="SUCCESS", session_id=session_id)

    @classmethod
    def failed(cls, session_id: UUID, reason: str) -> CommitResult:
        return cls(result="FAIL", session_id=session_id, reason=reason)


# Tables to clean during prior session cleanup (deterministic order)
_RAW_TABLES = [
    "raw.telemetry",
    "raw.cost_management",
    "raw.iam",
    "raw.billing",
    "raw.erp",
]

# Writer registry: slot → writer function
_WRITERS = {
    "telemetry": write_telemetry,
    "cost_management": write_cost_management,
    "iam": write_iam,
    "billing": write_billing,
    "erp": write_erp,
}


def run_ingestion_commit(
    engine: Engine,
    payload: OrchestrationPayload,
) -> CommitResult:
    """
    Execute the atomic ingestion commit.

    Parameters
    ----------
    engine : Engine
        SQLAlchemy engine for database access.
    payload : OrchestrationPayload
        Result from the Ingestion Orchestrator.

    Returns
    -------
    CommitResult
        SUCCESS if all writes committed atomically.
        FAIL if orchestration failed or any write/commit failed.
    """
    session_id = payload.session_id

    # ── If orchestration failed, no DB writes ──
    if payload.result == "FAIL":
        return CommitResult.failed(
            session_id=session_id,
            reason=f"Orchestration failed: {'; '.join(payload.errors)}",
        )

    # ── Single connection, single transaction ──
    # engine.begin() auto-commits on clean exit, auto-rollbacks on exception
    try:
        with engine.begin() as conn:
            # ── STEP 1: Drop prior active rows from 5 raw tables ──
            # ingestion_log rows are NOT deleted — they are harmless metadata
            # and downstream FK (FK_grain_session) prevents their removal
            for table in _RAW_TABLES:
                conn.execute(
                    text(f"DELETE FROM {table} WHERE session_id != :sid"),
                    {"sid": str(session_id)},
                )

            # ── STEP 2: Write ingestion_log entry (parent row) ──
            # Must exist BEFORE raw table writes — FK constraint:
            # raw.telemetry.session_id → raw.ingestion_log.session_id
            source_files_json = json.dumps(payload.source_files)
            conn.execute(
                text("""
                    INSERT INTO raw.ingestion_log (session_id, source_files, status)
                    VALUES (:sid, :source_files, 'COMMITTED')
                """),
                {"sid": str(session_id), "source_files": source_files_json},
            )

            # ── STEP 3: Write all 5 raw tables (child rows) ──
            for slot in ["telemetry", "cost_management", "iam", "billing", "erp"]:
                records = payload.parsed_records.get(slot, [])
                writer = _WRITERS[slot]
                write_result = writer(conn, session_id, records)

                if write_result.result == "FAIL":
                    raise RuntimeError(
                        f"Write failed: {slot} — {write_result.error}"
                    )

        # ── If we reach here, engine.begin() committed successfully ──
        return CommitResult.success(session_id=session_id)

    except Exception as exc:
        # ── engine.begin() already rolled back on exception ──
        return CommitResult.failed(
            session_id=session_id,
            reason=f"Commit failed for session {session_id}: {exc}",
        )
