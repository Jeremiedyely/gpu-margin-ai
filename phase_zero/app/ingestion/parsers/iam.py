"""
IAM File Parser — Component 8 of 19 (Ingestion Module Layer 2)

Input:   iam_validation = PASS + raw CSV string
Output:  ParseResult { result: PASS|FAIL, records: [IAMRecord, ...], error: str|None }
Feeds:   IAM Raw Table Writer (Step 2.3)
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

from .base import ParseResult


class IAMRecord(BaseModel):
    """Typed record for a single IAM CSV row."""
    tenant_id: str
    billing_period: str
    contracted_rate: Decimal


def parse_iam_file(content: str) -> ParseResult:
    """Parse a validated IAM CSV file into typed records."""
    reader = csv.DictReader(io.StringIO(content))
    records: list[IAMRecord] = []

    for i, row in enumerate(reader, start=1):
        row = {
            (k or "").strip().lower(): (v or "").strip()
            for k, v in row.items()
        }

        try:
            record = IAMRecord(
                tenant_id=row["tenant_id"],
                billing_period=row["billing_period"],
                contracted_rate=Decimal(row["contracted_rate"]),
            )
            records.append(record)
        except (KeyError, ValueError, InvalidOperation) as exc:
            return ParseResult.failed(f"Parse error at row {i}: {exc}")

    return ParseResult.passed(records)
