"""
Telemetry File Validator — Component 1 of 19 (Ingestion Module Layer 1)

Input:   Raw CSV string from UI Slot 1 (Telemetry & Metering)
Output:  ValidationResult { verdict: PASS|FAIL, errors: [...] }
Feeds:   Telemetry File Parser (Step 2.2)

Validation chain (fail-fast on structural, collect on row-level):
  1. Valid CSV format
  2. Required columns present
  3. File not empty (zero data rows)
  4. Per-row: null checks -> tenant_id regex (P1 #7) -> date ISO -> gpu_hours decimal+positive

Design note — tenant_id regex (P1 #7):
  A malformed tenant_id that passes non-null will silently fail the IAM
  Resolver LEFT JOIN in the Allocation Engine. The row becomes identity_broken
  when it should be Type A. The CFO receives a false identity failure signal
  with no traceable root cause. Regex rejection at ingestion prevents this.

  The pattern is configurable at deployment time via the tenant_id_pattern
  parameter. Default: alphanumeric + hyphens + underscores + dots,
  starting and ending with alphanumeric, length 1-255.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .base import ValidationError, ValidationResult

# -- Configurable tenant_id pattern -------------------------------------------
# Default: starts with alphanumeric, body allows [a-zA-Z0-9._-], length 1-255
# Override at deployment for org-specific format (UUID v4, etc.)
TENANT_ID_PATTERN = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,253}[a-zA-Z0-9]$|^[a-zA-Z0-9]$"
)

REQUIRED_COLUMNS = frozenset({
    "tenant_id",
    "region",
    "gpu_pool_id",
    "date",
    "gpu_hours_consumed",
})


def validate_telemetry_file(
    content: str,
    *,
    tenant_id_pattern: re.Pattern[str] | None = None,
) -> ValidationResult:
    """Validate a telemetry CSV file.

    Args:
        content: Raw CSV string (header + data rows).
        tenant_id_pattern: Compiled regex for tenant_id format.
                           Defaults to TENANT_ID_PATTERN.

    Returns:
        ValidationResult with PASS or FAIL + named errors.
    """
    pattern = tenant_id_pattern or TENANT_ID_PATTERN
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
    for i, row in enumerate(rows, start=1):
        # Normalize row keys to match REQUIRED_COLUMNS
        row = {k.strip().lower(): v for k, v in row.items()}

        # 4a. Null / empty checks on all required columns
        for col in sorted(REQUIRED_COLUMNS):
            val = row.get(col)
            if val is None or val.strip() == "":
                errors.append(ValidationError(
                    field=col, row=i,
                    message=f"Null value in required field: {col}",
                ))

        # If nulls found in this row, skip further checks for it
        row_has_nulls = any(
            (row.get(c) is None or row.get(c, "").strip() == "")
            for c in REQUIRED_COLUMNS
        )
        if row_has_nulls:
            continue

        # 4b. tenant_id format (P1 #7)
        tid = row["tenant_id"].strip()
        if not pattern.match(tid):
            errors.append(ValidationError(
                field="tenant_id", row=i,
                message=f"tenant_id format invalid — found: {tid}",
            ))

        # 4c. date — ISO format YYYY-MM-DD
        date_val = row["date"].strip()
        try:
            datetime.strptime(date_val, "%Y-%m-%d")
        except ValueError:
            errors.append(ValidationError(
                field="date", row=i,
                message=f"Type error: date — found: {date_val}",
            ))

        # 4d. gpu_hours_consumed — castable to decimal, must be > 0
        gpu_val = row["gpu_hours_consumed"].strip()
        try:
            dec = Decimal(gpu_val)
            if dec <= 0:
                errors.append(ValidationError(
                    field="gpu_hours_consumed", row=i,
                    message=f"gpu_hours_consumed must be > 0 — found: {gpu_val}",
                ))
        except InvalidOperation:
            errors.append(ValidationError(
                field="gpu_hours_consumed", row=i,
                message=f"Type error: gpu_hours_consumed — found: {gpu_val}",
            ))

    if errors:
        return ValidationResult.failed(errors)

    return ValidationResult.passed()
