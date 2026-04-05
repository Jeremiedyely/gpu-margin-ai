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

from app.api.deps import get_connection

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
