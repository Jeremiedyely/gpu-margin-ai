"""
ERP File Validator — Component 5 of 19 (Ingestion Module Layer 1)

Input:   Raw CSV string from UI Slot 5 (ERP / General Ledger)
Output:  ValidationResult { verdict: PASS|FAIL, errors: [...] }
Feeds:   ERP File Parser (Step 2.2)

Validation chain (fail-fast on structural, collect on row-level):
  1. Valid CSV format
  2. Required columns present
  3. File not empty (zero data rows)
  4. Per-row: null checks -> billing_period YYYY-MM -> amount_posted decimal
  5. Duplicate natural key check: (tenant_id, billing_period)

Design note — amount_posted sign NOT constrained (R4-W-3):
  Negative values represent GL credit entries / reversals.
  Joint scope decision with raw.billing.billable_amount.
  May produce false FAIL-2 verdicts in RE Check 3 — accepted risk.
"""

from __future__ import annotations

import csv
import io
import re
from decimal import Decimal, InvalidOperation

from .base import ValidationError, ValidationResult

REQUIRED_COLUMNS = frozenset({
    "tenant_id",
    "billing_period",
    "amount_posted",
})

BILLING_PERIOD_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def validate_erp_file(content: str) -> ValidationResult:
    """Validate an ERP CSV file."""
    errors: list[ValidationError] = []

    # -- CHECK 1: Valid CSV ---------------------------------------------------
    try:
        reader = csv.DictReader(io.StringIO(content))
        headers = reader.fieldnames
        if headers is None:
            return ValidationResult.failed([
                ValidationError(message="File is not valid CSV")
            ])
    except csv.Error:
        return ValidationResult.failed([
            ValidationError(message="File is not valid CSV")
        ])

    # -- CHECK 2: Required columns --------------------------------------------
    actual = {h.strip().lower() for h in headers} if headers else set()
    missing = REQUIRED_COLUMNS - actual
    if missing:
        return ValidationResult.failed([
            ValidationError(field=col, message=f"Missing column: {col}")
            for col in sorted(missing)
        ])

    # -- CHECK 3: Non-empty file ----------------------------------------------
    rows = list(reader)
    if len(rows) == 0:
        return ValidationResult.failed([
            ValidationError(message="File contains no data rows")
        ])

    # -- CHECK 4: Row-level validation ----------------------------------------
    seen_keys: set[tuple[str, str]] = set()

    for i, row in enumerate(rows, start=1):
        row = {k.strip().lower(): v for k, v in row.items()}

        # 4a. Null / empty checks
        for col in sorted(REQUIRED_COLUMNS):
            val = row.get(col)
            if val is None or val.strip() == "":
                errors.append(ValidationError(
                    field=col, row=i,
                    message=f"Null value in required field: {col}",
                ))

        row_has_nulls = any(
            (row.get(c) is None or row.get(c, "").strip() == "")
            for c in REQUIRED_COLUMNS
        )
        if row_has_nulls:
            continue

        # 4b. billing_period — YYYY-MM format, month 01-12
        bp_val = row["billing_period"].strip()
        if not BILLING_PERIOD_PATTERN.match(bp_val):
            errors.append(ValidationError(
                field="billing_period", row=i,
                message=f"billing_period must be YYYY-MM format — found: {bp_val}",
            ))

        # 4c. amount_posted — castable to decimal (NO sign constraint — R4-W-3)
        ap_val = row["amount_posted"].strip()
        try:
            Decimal(ap_val)
        except InvalidOperation:
            errors.append(ValidationError(
                field="amount_posted", row=i,
                message=f"Type error: amount_posted — found: {ap_val}",
            ))

        # 4d. Duplicate natural key check (tenant_id + billing_period)
        key = (
            row["tenant_id"].strip().lower(),
            bp_val,
        )
        if key in seen_keys:
            errors.append(ValidationError(
                field="(tenant_id, billing_period)", row=i,
                message="Duplicate key: (tenant_id, billing_period)",
            ))
        else:
            seen_keys.add(key)

    if errors:
        return ValidationResult.failed(errors)

    return ValidationResult.passed()
