"""
Shared result model for all raw-table writers.

Every writer returns a WriteResult indicating success/failure,
the session_id that was tagged, and how many rows were inserted.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class WriteResult(BaseModel):
    """Outcome of a single raw-table write operation."""

    result: Literal["SUCCESS", "FAIL"]
    session_id: UUID
    row_count: int = Field(default=0)
    error: str | None = None

    @classmethod
    def success(cls, session_id: UUID, row_count: int) -> WriteResult:
        return cls(result="SUCCESS", session_id=session_id, row_count=row_count)

    @classmethod
    def failed(cls, session_id: UUID, error: str) -> WriteResult:
        return cls(result="FAIL", session_id=session_id, row_count=0, error=error)
