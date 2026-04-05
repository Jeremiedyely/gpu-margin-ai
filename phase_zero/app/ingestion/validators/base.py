"""
Shared validation result models for all 5 file validators.
Used by: Telemetry, Cost Management, IAM, Billing, ERP validators.
Consumed by: Ingestion Orchestrator (Step 2.4) — routes PASS/FAIL.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ValidationError(BaseModel):
    """One named error identifying the field and row."""
    field: str | None = None
    row: int | None = None        # 1-based data row (excludes header)
    message: str


class ValidationResult(BaseModel):
    """Outcome of a single file validator."""
    verdict: Literal["PASS", "FAIL"]
    errors: list[ValidationError] = []

    @classmethod
    def passed(cls) -> ValidationResult:
        return cls(verdict="PASS")

    @classmethod
    def failed(cls, errors: list[ValidationError]) -> ValidationResult:
        return cls(verdict="FAIL", errors=errors)
