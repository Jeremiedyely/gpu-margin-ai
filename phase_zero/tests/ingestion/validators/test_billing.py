"""
TEST — Billing File Validator
17 assertions covering all validation paths from ingestion-module-design.md

Structural checks (fail-fast):
  BIL-01  Valid CSV with all fields -> PASS
  BIL-02  Not valid CSV -> FAIL
  BIL-03  Missing one required column -> FAIL (named field)
  BIL-04  Missing multiple required columns -> FAIL (all named)
  BIL-05  Empty file (header only, zero data rows) -> FAIL

Row-level checks (collected):
  BIL-06  Null value in tenant_id -> FAIL (named field + row)
  BIL-07  Empty string in billing_period -> FAIL
  BIL-08  billing_period wrong format (2025/03) -> FAIL
  BIL-09  billing_period invalid month (2025-13) -> FAIL
  BIL-10  billable_amount not decimal (abc) -> FAIL
  BIL-11  billable_amount negative -> PASS (credit memos allowed — R4-W-3)
  BIL-12  billable_amount zero -> PASS
  BIL-13  Duplicate natural key (tenant_id + billing_period) -> FAIL
  BIL-14  Same tenant different period -> PASS (not duplicate)
  BIL-15  Multiple rows, error on row 2 only -> row=2 reported
  BIL-16  Multiple errors collected across rows -> all reported
  BIL-17  Valid edge case: large negative credit memo -> PASS
"""

import pytest

from app.ingestion.validators.billing import validate_billing_file


# -- Helpers ------------------------------------------------------------------

def _csv(header: str, *rows: str) -> str:
    return "\n".join([header] + list(rows))


HEADER = "tenant_id,billing_period,billable_amount"
VALID_ROW = "tenant-01,2025-03,1500.000000"


# -- Structural Checks -------------------------------------------------------

def test_bil01_valid_csv_passes():
    """BIL-01: Valid CSV with all required fields -> PASS"""
    result = validate_billing_file(_csv(HEADER, VALID_ROW))
    assert result.verdict == "PASS"
    assert result.errors == []


def test_bil02_not_valid_csv():
    """BIL-02: Not valid CSV -> FAIL"""
    result = validate_billing_file("")
    assert result.verdict == "FAIL"
    assert any("not valid CSV" in e.message or "no data" in e.message for e in result.errors)


def test_bil03_missing_one_column():
    """BIL-03: Missing one required column -> FAIL with named field"""
    bad_header = "tenant_id,billing_period"
    result = validate_billing_file(_csv(bad_header, "t1,2025-03"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "billable_amount" and "Missing column" in e.message
        for e in result.errors
    )


def test_bil04_missing_multiple_columns():
    """BIL-04: Missing multiple required columns -> all named"""
    bad_header = "tenant_id"
    result = validate_billing_file(_csv(bad_header, "t1"))
    assert result.verdict == "FAIL"
    missing_fields = {e.field for e in result.errors if "Missing column" in e.message}
    assert missing_fields == {"billing_period", "billable_amount"}


def test_bil05_empty_file_no_data_rows():
    """BIL-05: Header only, zero data rows -> FAIL"""
    result = validate_billing_file(HEADER)
    assert result.verdict == "FAIL"
    assert any("no data rows" in e.message for e in result.errors)


# -- Row-Level: Null Checks ---------------------------------------------------

def test_bil06_null_tenant_id():
    """BIL-06: Null tenant_id -> FAIL with named field and row"""
    result = validate_billing_file(_csv(HEADER, ",2025-03,1500"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "tenant_id" and e.row == 1 and "Null" in e.message
        for e in result.errors
    )


def test_bil07_empty_string_billing_period():
    """BIL-07: Empty string in billing_period -> FAIL"""
    result = validate_billing_file(_csv(HEADER, "tenant-01,,1500"))
    assert result.verdict == "FAIL"
    assert any(e.field == "billing_period" and "Null" in e.message for e in result.errors)


# -- Row-Level: billing_period Format -----------------------------------------

def test_bil08_billing_period_wrong_format():
    """BIL-08: billing_period as 2025/03 -> FAIL"""
    result = validate_billing_file(_csv(HEADER, "tenant-01,2025/03,1500"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "billing_period" and "YYYY-MM format" in e.message
        for e in result.errors
    )


def test_bil09_billing_period_invalid_month():
    """BIL-09: billing_period month 13 -> FAIL"""
    result = validate_billing_file(_csv(HEADER, "tenant-01,2025-13,1500"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "billing_period" and "YYYY-MM format" in e.message
        for e in result.errors
    )


# -- Row-Level: billable_amount -----------------------------------------------

def test_bil10_billable_amount_not_decimal():
    """BIL-10: billable_amount = 'abc' -> FAIL"""
    result = validate_billing_file(_csv(HEADER, "tenant-01,2025-03,abc"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "billable_amount" and "Type error" in e.message
        for e in result.errors
    )


def test_bil11_billable_amount_negative_passes():
    """BIL-11: billable_amount = -500 -> PASS (credit memos allowed — R4-W-3)"""
    result = validate_billing_file(_csv(HEADER, "tenant-01,2025-03,-500.00"))
    assert result.verdict == "PASS"


def test_bil12_billable_amount_zero_passes():
    """BIL-12: billable_amount = 0 -> PASS"""
    result = validate_billing_file(_csv(HEADER, "tenant-01,2025-03,0"))
    assert result.verdict == "PASS"


# -- Duplicate Natural Key ---------------------------------------------------

def test_bil13_duplicate_natural_key():
    """BIL-13: Duplicate (tenant_id + billing_period) -> FAIL"""
    csv_content = _csv(
        HEADER,
        "tenant-01,2025-03,1500",
        "tenant-01,2025-03,2000",  # same key
    )
    result = validate_billing_file(csv_content)
    assert result.verdict == "FAIL"
    assert any("Duplicate key" in e.message for e in result.errors)


def test_bil14_same_tenant_different_period_passes():
    """BIL-14: Same tenant, different billing_period -> PASS"""
    csv_content = _csv(
        HEADER,
        "tenant-01,2025-03,1500",
        "tenant-01,2025-04,1500",
    )
    result = validate_billing_file(csv_content)
    assert result.verdict == "PASS"


# -- Multi-Row Error Reporting ------------------------------------------------

def test_bil15_error_on_row_2_only():
    """BIL-15: Row 1 valid, row 2 invalid -> error reports row=2"""
    csv_content = _csv(HEADER, VALID_ROW, "tenant-02,2025/04,1500")
    result = validate_billing_file(csv_content)
    assert result.verdict == "FAIL"
    assert any(e.row == 2 and e.field == "billing_period" for e in result.errors)
    assert not any(e.row == 1 for e in result.errors)


def test_bil16_multiple_errors_collected():
    """BIL-16: Multiple errors across rows -> all reported"""
    csv_content = _csv(
        HEADER,
        "tenant-01,2025-13,1500",      # row 1: bad billing_period
        "tenant-02,2025-03,abc",        # row 2: bad billable_amount
    )
    result = validate_billing_file(csv_content)
    assert result.verdict == "FAIL"
    assert len(result.errors) >= 2
    assert any(e.row == 1 and e.field == "billing_period" for e in result.errors)
    assert any(e.row == 2 and e.field == "billable_amount" for e in result.errors)


# -- Edge Cases ---------------------------------------------------------------

def test_bil17_large_negative_credit_memo_passes():
    """BIL-17: Large negative credit memo (-99999.99) -> PASS"""
    result = validate_billing_file(_csv(HEADER, "tenant-01,2025-03,-99999.990000"))
    assert result.verdict == "PASS"
