"""
Telemetry File Parser — Component 6 of 19 (Ingestion Module Layer 2)

Input:   telemetry_validation = PASS + raw CSV string
Output:  ParseResult { result: PASS|FAIL, records: [TelemetryRecord, ...], error: str|None }
Feeds:   Telemetry Raw Table Writer (Step 2.3)

Parses each row into a typed Pydantic model:
  tenant_id          : str
  region             : str
  gpu_pool_id        : str
  date               : date (ISO 8601)
  gpu_hours_consumed : Decimal
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

from .base import ParseResult


class TelemetryRecord(BaseModel):
    """Typed record for a single telemetry CSV row."""
    tenant_id: str
    region: str
    gpu_pool_id: str
    date: date
    gpu_hours_consumed: Decimal


def parse_telemetry_file(content: str) -> ParseResult:
    """Parse a validated telemetry CSV file into typed records.

    Args:
        content: Raw CSV string (already validated by Telemetry File Validator).

    Returns:
        ParseResult with PASS + records, or FAIL + error.
    """
    reader = csv.DictReader(io.StringIO(content))
    records: list[TelemetryRecord] = []

    for i, row in enumerate(reader, start=1):
        # Normalize keys (consistent with validator) — safe against None
        row = {
            (k or "").strip().lower(): (v or "").strip()
            for k, v in row.items()
        }

        try:
            record = TelemetryRecord(
                tenant_id=row["tenant_id"],
                region=row["region"],
                gpu_pool_id=row["gpu_pool_id"],
                date=datetime.strptime(row["date"], "%Y-%m-%d").date(),
                gpu_hours_consumed=Decimal(row["gpu_hours_consumed"]),
            )
            records.append(record)
        except (KeyError, ValueError, InvalidOperation) as exc:
            return ParseResult.failed(
                f"Parse error at row {i}: {exc}"
            )

    return ParseResult.passed(records)
