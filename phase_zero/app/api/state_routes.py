"""
State API routes — serves application_state to the UI.

GET /api/state
  Returns: {session_id, application_state, analysis_status}
  Used by: Screen Router, View 1/2 Footer Control Managers

The UI reads state on EVERY render (server-state render invariant).
Button states are NEVER derived from local/cached UI state.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Connection, text

from app.api.deps import get_connection, get_engine

router = APIRouter(prefix="/api", tags=["state"])


class StateResponse(BaseModel):
    """Current application state for UI consumption."""

    session_id: UUID | None
    application_state: str | None
    analysis_status: str | None


_LATEST_SESSION_SQL = text("""
    SELECT TOP 1
        ss.session_id,
        ss.application_state,
        ss.analysis_status
    FROM dbo.state_store ss
    WHERE ss.session_status <> 'TERMINAL'
    ORDER BY ss.session_id DESC
""")


@router.get("/state", response_model=StateResponse)
def get_current_state(
    conn: Connection = Depends(get_connection),
) -> StateResponse:
    """
    Return the current application state for the active session.

    If no active session exists, returns null fields — the Screen Router
    treats this as EMPTY state.
    """
    row = conn.execute(_LATEST_SESSION_SQL).fetchone()

    if row is None:
        return StateResponse(
            session_id=None,
            application_state=None,
            analysis_status=None,
        )

    return StateResponse(
        session_id=row.session_id,
        application_state=row.application_state,
        analysis_status=row.analysis_status,
    )


# ── Close Session ────────────────────────────────────────────────────

class CloseSessionRequest(BaseModel):
    session_id: UUID


class CloseSessionResponse(BaseModel):
    result: str
    session_id: UUID | None = None


@router.post("/session/close", response_model=CloseSessionResponse)
def close_session_endpoint(req: CloseSessionRequest):
    """
    Mark an APPROVED session as TERMINAL so the UI returns to VIEW_1.

    Called by the "New Session" button after the user has finished exporting.
    Celery Beat also closes APPROVED sessions automatically as a safety net.
    """
    from app.state_machine.state_store import read_state, StateWriteRequest, write_state

    engine = get_engine()

    with engine.connect() as conn:
        with conn.begin():
            snapshot = read_state(conn, req.session_id)

            if snapshot is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"No session found: {req.session_id}",
                )

            if snapshot.application_state != "APPROVED":
                raise HTTPException(
                    status_code=400,
                    detail=f"Session is {snapshot.application_state}, not APPROVED",
                )

            if snapshot.session_status == "TERMINAL":
                return CloseSessionResponse(
                    result="ALREADY_CLOSED", session_id=req.session_id,
                )

            store_result = write_state(
                conn,
                StateWriteRequest(
                    new_state="APPROVED",
                    trigger="SESSION_CLOSED",
                    session_id=req.session_id,
                    session_status="TERMINAL",
                ),
                from_state="APPROVED",
            )

            if store_result.result != "SUCCESS":
                raise HTTPException(
                    status_code=500,
                    detail=f"Session close failed: {store_result.error}",
                )

    return CloseSessionResponse(result="CLOSED", session_id=req.session_id)
