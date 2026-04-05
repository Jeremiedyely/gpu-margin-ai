"""
UPLOADED → ANALYZED Executor — Component 7/12.

Layer: State.

Receives collection_result = SUCCESS from Engine Completion Collector
and writes new_state = ANALYZED to State Store. Resets retry_count
to 0 on successful transition. Sets trigger = ENGINES_COMPLETE.

Spec: state-machine-design.md — Component 7 — UPLOADED → ANALYZED Executor
"""

from __future__ import annotations

from sqlalchemy import Connection

from app.state_machine.empty_to_uploaded_executor import TransitionResult
from app.state_machine.engine_completion_collector import CollectionResult
from app.state_machine.state_store import (
    StateWriteRequest,
    reset_retry_count,
    write_state,
)


# ── Public API ──────────────────────────────────────────────────────

def execute_uploaded_to_analyzed(
    conn: Connection,
    collection: CollectionResult,
) -> TransitionResult:
    """
    Execute the UPLOADED → ANALYZED transition.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection (caller owns outer transaction).
    collection : CollectionResult
        Must be SUCCESS from Engine Completion Collector.

    Returns
    -------
    TransitionResult
        SUCCESS if State Store write completes, FAIL on error.
    """
    # Guard: only execute on SUCCESS collection
    if collection.result != "SUCCESS":
        return TransitionResult.failed(
            new_state="ANALYZED",
            session_id=collection.session_id,
            error=(
                "UPLOADED→ANALYZED executor received non-SUCCESS collection: "
                f"{collection.result}"
            ),
        )

    # Write to State Store
    store_result = write_state(
        conn,
        StateWriteRequest(
            new_state="ANALYZED",
            analysis_status=None,  # COALESCE → IDLE in MERGE
            trigger="ENGINES_COMPLETE",
            session_id=collection.session_id,
        ),
        from_state="UPLOADED",
    )

    if store_result.result != "SUCCESS":
        return TransitionResult.failed(
            new_state="ANALYZED",
            session_id=collection.session_id,
            error=(
                "UPLOADED→ANALYZED transition failed — state not persisted: "
                f"{store_result.error}"
            ),
        )

    # Reset retry_count on successful transition
    reset_retry_count(conn, collection.session_id)

    return TransitionResult.success(
        new_state="ANALYZED",
        session_id=collection.session_id,
    )
