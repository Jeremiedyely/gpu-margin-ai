"""
IAM File Validator — Component 3 of 19 (Ingestion Module Layer 1)

Input:   Raw CSV string from UI Slot 3 (IAM / Tenant Management)
Output:  ValidationResult { verdict: PASS|FAIL, errors: [...] }
Feeds:   IAM File Parser (Step 2.2)

Validation chain (fail-fast on structural, collect on row-level):
  1. Valid CSV format
  2. Required columns present
  3. File not empty (zero data rows)
  4. Per-row: null checks -> billing_period YYYY-MM -> contracted_rate decimal+positive
  5. Duplicate natural key check: (tenant_id, billing_period)

Design note — contracted_rate > 0 (not >= 0):
  The DB constraint CHK_iam_rate allows >= 0 (zero rate structurally valid).
  The validator rejects zero at ingestion — defense in depth. A $0 contracted
  rate produces $0 revenue in the grain, which makes gross margin = -cost.
  If intentional (free tier), it should be an explicit business decision,
  not a silent data entry that propagates to the CFO margin report.

Design note — no tenant_id regex here:
  tenant_id format is enforced at the telemetry boundary (P1 #7) because
  that is where malformed IDs cause silent identity_broken misclassification.
  IAM is the lookup table — the Allocation Engine joins ON tenant_id +
  billing_period. A tenant_id present in IAM but absent from telemetry
  simply has no usage rows and never appears in the grain.
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
    "contracted_rate",
})

# YYYY-MM format: 4-digit year, dash, month 01-12
BILLING_PERIOD_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def validate_iam_file(content: str) -> ValidationResult:
    """Validate an IAM CSV file.

    Args:
        content: Raw CSV string (header + data rows).

    Returns:
        ValidationResult with PASS or FAIL + named errors.
    """
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
        # Normalize row keys
        row = {k.strip().lower(): v for k, v in row.items()}

        # 4a. Null / empty checks on all required columns
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

        # 4c. contracted_rate — castable to decimal, must be > 0
        cr_val = row["contracted_rate"].strip()
        try:
            dec = Decimal(cr_val)
            if dec <= 0:
                errors.append(ValidationError(
                    field="contracted_rate", row=i,
                    message=f"contracted_rate must be > 0 — found: {cr_val}",
                ))
        except InvalidOperation:
            errors.append(ValidationError(
                field="contracted_rate", row=i,
                message=f"Type error: contracted_rate — found: {cr_val}",
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
