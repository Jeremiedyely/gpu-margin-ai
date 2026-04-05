"""
State Store — Component 1/12.

Layer: State.

Persists application_state, analysis_status, session_status, write_result,
and retry_count to dbo.state_store. Appends every state transition to
dbo.state_history atomically — state persisted + history appended, or neither.

Authorized callers: Transition Executors, Analysis Dispatcher, Approved
Result Writer, APPROVED Session Closer.

Spec: state-machine-design.md — Component 1 — State Store
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Connection, text


# ── Enumerated trigger values (V12 CHK_history_trigger) ─────────────

VALID_TRIGGERS: frozenset[str] = frozenset({
    "INGESTION_COMPLETE",
    "ANALYSIS_DISPATCHED",
    "ENGINES_COMPLETE",
    "CFO_APPROVAL",
    "ANALYSIS_FAILED",
    "SESSION_CLOSED",
    "SYSTEM_RECOVERY",
})


# ── Models ──────────────────────────────────────────────────────────

class StateWriteRequest(BaseModel):
    """Request to write state to the State Store."""

    new_state: Literal["EMPTY", "UPLOADED", "ANALYZED", "APPROVED"]
    analysis_status: Literal["IDLE", "ANALYZING"] | None = None
    trigger: str
    session_id: UUID
    # Optional fields for atomic APPROVED write (P1 #26)
    write_result: Literal["SUCCESS", "FAIL"] | None = None
    session_status: Literal["ACTIVE", "TERMINAL"] | None = None


class StoreWriteResult(BaseModel):
    """Result of a State Store write."""

    result: Literal["SUCCESS", "FAIL"]
    session_id: UUID | None = None
    error: str | None = None

    @classmethod
    def success(cls, session_id: UUID) -> StoreWriteResult:
        return cls(result="SUCCESS", session_id=session_id)

    @classmethod
    def failed(cls, session_id: UUID | None, error: str) -> StoreWriteResult:
        return cls(result="FAIL", session_id=session_id, error=error)


class StateSnapshot(BaseModel):
    """Current state read from the State Store."""

    session_id: UUID
    application_state: str
    session_status: str
    analysis_status: str | None = None
    write_result: str | None = None
    retry_count: int = 0


# ── SQL ─────────────────────────────────────────────────────────────

_READ_STATE_SQL = text("""
    SELECT session_id, application_state, session_status,
           analysis_status, write_result, retry_count
    FROM dbo.state_store
    WHERE session_id = :sid
""")

_UPSERT_STATE_SQL = text("""
    MERGE dbo.state_store AS tgt
    USING (SELECT :sid AS session_id) AS src
    ON tgt.session_id = src.session_id
    WHEN MATCHED THEN UPDATE SET
        application_state = :app_state,
        analysis_status   = COALESCE(:analysis_status, 'IDLE'),
        session_status    = COALESCE(:session_status, tgt.session_status),
        write_result      = COALESCE(:write_result, tgt.write_result),
        retry_count       = COALESCE(:retry_count, tgt.retry_count)
    WHEN NOT MATCHED THEN INSERT
        (session_id, application_state, session_status,
         analysis_status, write_result, retry_count)
    VALUES
        (:sid, :app_state,
         COALESCE(:session_status, 'ACTIVE'),
         COALESCE(:analysis_status, 'IDLE'), :write_result,
         COALESCE(:retry_count, 0));
""")

_INSERT_HISTORY_SQL = text("""
    INSERT INTO dbo.state_history
        (session_id, from_state, to_state, transition_trigger, transitioned_at)
    VALUES
        (:sid, :from_state, :to_state, :trigger, :transitioned_at)
""")


# ── Public API ──────────────────────────────────────────────────────

def read_state(conn: Connection, session_id: UUID) -> StateSnapshot | None:
    """
    Read the current state for a session.

    Returns None if no state_store row exists for the session.
    """
    row = conn.execute(_READ_STATE_SQL, {"sid": str(session_id)}).fetchone()
    if row is None:
        return None
    return StateSnapshot(
        session_id=row.session_id if isinstance(row.session_id, UUID)
        else UUID(str(row.session_id)),
        application_state=row.application_state,
        session_status=row.session_status,
        analysis_status=row.analysis_status,
        write_result=row.write_result,
        retry_count=row.retry_count,
    )


def write_state(
    conn: Connection,
    request: StateWriteRequest,
    from_state: str | None = None,
) -> StoreWriteResult:
    """
    Persist state and append to state_history atomically.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection (caller owns outer transaction).
    request : StateWriteRequest
        The state write payload.
    from_state : str | None
        Previous application_state for state_history. If None,
        reads current state from store (or defaults to 'EMPTY'
        on first write).

    Returns
    -------
    StoreWriteResult
        SUCCESS if atomic write completes, FAIL on error.
    """
    # Validate trigger against enumerated set
    if request.trigger not in VALID_TRIGGERS:
        return StoreWriteResult.failed(
            session_id=request.session_id,
            error=(
                "state_history write rejected — trigger not in "
                f"enumerated set: {request.trigger!r}"
            ),
        )

    # Resolve from_state if not provided
    if from_state is None:
        current = read_state(conn, request.session_id)
        from_state = current.application_state if current else "EMPTY"

    now = datetime.now(timezone.utc)

    # Determine whether this is a state transition or a metadata-only update.
    # CHK_history_no_self_transition blocks from_state == to_state unless
    # trigger = SYSTEM_RECOVERY. Metadata-only updates (e.g. session_status
    # → TERMINAL on an already-APPROVED session) skip the history append.
    is_state_transition = (
        from_state != request.new_state
        or request.trigger in ("SYSTEM_RECOVERY", "SESSION_CLOSED")
    )

    try:
        savepoint = conn.begin_nested()
        try:
            # Persist state
            conn.execute(
                _UPSERT_STATE_SQL,
                {
                    "sid": str(request.session_id),
                    "app_state": request.new_state,
                    "analysis_status": request.analysis_status,
                    "session_status": request.session_status,
                    "write_result": request.write_result,
                    "retry_count": None,  # preserve existing unless explicitly set
                },
            )

            # Append to state_history — only on actual state transitions.
            if is_state_transition:
                conn.execute(
                    _INSERT_HISTORY_SQL,
                    {
                        "sid": str(request.session_id),
                        "from_state": from_state,
                        "to_state": request.new_state,
                        "trigger": request.trigger,
                        "transitioned_at": now,
                    },
                )

            savepoint.commit()
        except Exception as exc:
            savepoint.rollback()
            return StoreWriteResult.failed(
                session_id=request.session_id,
                error=(
                    f"State persist failed — state may be inconsistent: "
                    f"{exc} · session_id: {request.session_id}"
                ),
            )

        return StoreWriteResult.success(session_id=request.session_id)

    except Exception as exc:
        return StoreWriteResult.failed(
            session_id=request.session_id,
            error=(
                f"CRITICAL: state_store rollback failed — "
                f"data integrity at risk: {exc} · session_id: {request.session_id}"
            ),
        )


def increment_retry_count(conn: Connection, session_id: UUID) -> StoreWriteResult:
    """
    Increment retry_count for a session.

    Used by Engine Completion Collector on FAIL.
    """
    try:
        conn.execute(
            text("""
                UPDATE dbo.state_store
                SET retry_count = retry_count + 1
                WHERE session_id = :sid
            """),
            {"sid": str(session_id)},
        )
        return StoreWriteResult.success(session_id=session_id)
    except Exception as exc:
        return StoreWriteResult.failed(
            session_id=session_id,
            error=f"retry_count increment failed: {exc}",
        )


def reset_retry_count(conn: Connection, session_id: UUID) -> StoreWriteResult:
    """
    Reset retry_count to 0 for a session.

    Used on successful UPLOADED → ANALYZED transition.
    """
    try:
        conn.execute(
            text("""
                UPDATE dbo.state_store
                SET retry_count = 0
                WHERE session_id = :sid
            """),
            {"sid": str(session_id)},
        )
        return StoreWriteResult.success(session_id=session_id)
    except Exception as exc:
        return StoreWriteResult.failed(
            session_id=session_id,
            error=f"retry_count reset failed: {exc}",
        )
