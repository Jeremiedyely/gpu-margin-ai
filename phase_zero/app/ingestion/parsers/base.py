"""
Shared parse result model for all 5 file parsers.
Used by: Telemetry, Cost Management, IAM, Billing, ERP parsers.
Consumed by: Raw Table Writers (Step 2.3) — receive records list.

Design note — fail-fast on parse error:
  The spec defines a single error field (varchar | NULL), not a list.
  If any row fails casting after validation passed, parsing stops
  immediately. A parse failure at this layer means the validator
  missed something — it should be investigated, not collected.

Implementation note — default_factory:
  records uses Field(default_factory=list) instead of [] to avoid
  mutable default issues across instances. This is best practice
  for Pydantic and prevents shared state bugs.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ParseResult(BaseModel):
    """Outcome of a single file parser."""

    # PASS or FAIL result
    result: Literal["PASS", "FAIL"]
    # Parsed records (typed Pydantic models)
    # default_factory avoids mutable default list issues
    records: list[Any] = Field(default_factory=list)
    # Single fail-fast error message
    error: str | None = None

    @classmethod
    def passed(cls, records: list[Any]) -> "ParseResult":
        """Return successful parse result."""
        return cls(
            result="PASS",
            records=records,
            error=None,
        )

    @classmethod
    def failed(cls, error: str) -> "ParseResult":
        """Return failed parse result."""
        return cls(
            result="FAIL",
            records=[],
            error=error,
        )
