"""
Cost Management File Parser — Component 7 of 19 (Ingestion Module Layer 2)

Input:   cost_mgmt_validation = PASS + raw CSV string
Output:  ParseResult { result: PASS|FAIL, records: [CostManagementRecord, ...], error: str|None }
Feeds:   Cost Management Raw Table Writer (Step 2.3)
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

from .base import ParseResult


class CostManagementRecord(BaseModel):
    """Typed record for a single cost management CSV row."""
    region: str
    gpu_pool_id: str
    date: date
    reserved_gpu_hours: Decimal
    cost_per_gpu_hour: Decimal


def parse_cost_management_file(content: str) -> ParseResult:
    """Parse a validated cost management CSV file into typed records."""
    reader = csv.DictReader(io.StringIO(content))
    records: list[CostManagementRecord] = []

    for i, row in enumerate(reader, start=1):
        row = {
            (k or "").strip().lower(): (v or "").strip()
            for k, v in row.items()
        }

        try:
            record = CostManagementRecord(
                region=row["region"],
                gpu_pool_id=row["gpu_pool_id"],
                date=datetime.strptime(row["date"], "%Y-%m-%d").date(),
                reserved_gpu_hours=Decimal(row["reserved_gpu_hours"]),
                cost_per_gpu_hour=Decimal(row["cost_per_gpu_hour"]),
            )
            records.append(record)
        except (KeyError, ValueError, InvalidOperation) as exc:
            return ParseResult.failed(f"Parse error at row {i}: {exc}")

    return ParseResult.passed(records)
