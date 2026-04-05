"""
Billing File Parser — Component 9 of 19 (Ingestion Module Layer 2)

Input:   billing_validation = PASS + raw CSV string
Output:  ParseResult { result: PASS|FAIL, records: [BillingRecord, ...], error: str|None }
Feeds:   Billing Raw Table Writer (Step 2.3)
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

from .base import ParseResult


class BillingRecord(BaseModel):
    """Typed record for a single billing CSV row."""
    tenant_id: str
    billing_period: str
    billable_amount: Decimal


def parse_billing_file(content: str) -> ParseResult:
    """Parse a validated billing CSV file into typed records."""
    reader = csv.DictReader(io.StringIO(content))
    records: list[BillingRecord] = []

    for i, row in enumerate(reader, start=1):
        row = {
            (k or "").strip().lower(): (v or "").strip()
            for k, v in row.items()
        }

        try:
            record = BillingRecord(
                tenant_id=row["tenant_id"],
                billing_period=row["billing_period"],
                billable_amount=Decimal(row["billable_amount"]),
            )
            records.append(record)
        except (KeyError, ValueError, InvalidOperation) as exc:
            return ParseResult.failed(f"Parse error at row {i}: {exc}")

    return ParseResult.passed(records)
