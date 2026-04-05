"""
ERP File Parser — Component 10 of 19 (Ingestion Module Layer 2)

Input:   erp_validation = PASS + raw CSV string
Output:  ParseResult { result: PASS|FAIL, records: [ERPRecord, ...], error: str|None }
Feeds:   ERP Raw Table Writer (Step 2.3)
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

from .base import ParseResult


class ERPRecord(BaseModel):
    """Typed record for a single ERP CSV row."""
    tenant_id: str
    billing_period: str
    amount_posted: Decimal


def parse_erp_file(content: str) -> ParseResult:
    """Parse a validated ERP CSV file into typed records."""
    reader = csv.DictReader(io.StringIO(content))
    records: list[ERPRecord] = []

    for i, row in enumerate(reader, start=1):
        row = {
            (k or "").strip().lower(): (v or "").strip()
            for k, v in row.items()
        }

        try:
            record = ERPRecord(
                tenant_id=row["tenant_id"],
                billing_period=row["billing_period"],
                amount_posted=Decimal(row["amount_posted"]),
            )
            records.append(record)
        except (KeyError, ValueError, InvalidOperation) as exc:
            return ParseResult.failed(f"Parse error at row {i}: {exc}")

    return ParseResult.passed(records)
