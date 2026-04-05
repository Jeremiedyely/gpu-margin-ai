"""
Cost Management File Validator — Component 2 of 19 (Ingestion Module Layer 1)

Input:   Raw CSV string from UI Slot 2 (Cost Management / FinOps)
Output:  ValidationResult { verdict: PASS|FAIL, errors: [...] }
Feeds:   Cost Management File Parser (Step 2.2)

Validation chain (fail-fast on structural, collect on row-level):
  1. Valid CSV format
  2. Required columns present
  3. File not empty (zero data rows)
  4. Per-row: null checks -> date ISO -> reserved_gpu_hours decimal+positive
     -> cost_per_gpu_hour decimal+positive
  5. Duplicate natural key check: (region, gpu_pool_id, date)

Design note — no tenant_id in cost management:
  Cost data is per pool, not per tenant. The Allocation Engine joins
  cost data to telemetry at the (region, gpu_pool_id, date) grain.
  Duplicate keys at this grain would double-count capacity — producing
  wrong margin denominators that propagate silently to the CFO.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .base import ValidationError, ValidationResult

REQUIRED_COLUMNS = frozenset({
    "region",
    "gpu_pool_id",
    "date",
    "reserved_gpu_hours",
    "cost_per_gpu_hour",
})


def validate_cost_management_file(content: str) -> ValidationResult:
    """Validate a cost management CSV file.

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
    seen_keys: set[tuple[str, str, str]] = set()

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

        # 4b. date — ISO format YYYY-MM-DD
        date_val = row["date"].strip()
        try:
            datetime.strptime(date_val, "%Y-%m-%d")
        except ValueError:
            errors.append(ValidationError(
                field="date", row=i,
                message=f"Type error: date — found: {date_val}",
            ))

        # 4c. reserved_gpu_hours — castable to decimal, must be > 0
        rgh_val = row["reserved_gpu_hours"].strip()
        try:
            dec = Decimal(rgh_val)
            if dec <= 0:
                errors.append(ValidationError(
                    field="reserved_gpu_hours", row=i,
                    message=f"reserved_gpu_hours must be > 0 — found: {rgh_val}",
                ))
        except InvalidOperation:
            errors.append(ValidationError(
                field="reserved_gpu_hours", row=i,
                message=f"Type error: reserved_gpu_hours — found: {rgh_val}",
            ))

        # 4d. cost_per_gpu_hour — castable to decimal, must be > 0
        cph_val = row["cost_per_gpu_hour"].strip()
        try:
            dec = Decimal(cph_val)
            if dec <= 0:
                errors.append(ValidationError(
                    field="cost_per_gpu_hour", row=i,
                    message=f"cost_per_gpu_hour must be > 0 — found: {cph_val}",
                ))
        except InvalidOperation:
            errors.append(ValidationError(
                field="cost_per_gpu_hour", row=i,
                message=f"Type error: cost_per_gpu_hour — found: {cph_val}",
            ))

        # 4e. Duplicate natural key check (region + gpu_pool_id + date)
        key = (
            row["region"].strip().lower(),
            row["gpu_pool_id"].strip().lower(),
            date_val,
        )
        if key in seen_keys:
            errors.append(ValidationError(
                field="(region, gpu_pool_id, date)", row=i,
                message="Duplicate key: (region, gpu_pool_id, date)",
            ))
        else:
            seen_keys.add(key)

    if errors:
        return ValidationResult.failed(errors)

    return ValidationResult.passed()
