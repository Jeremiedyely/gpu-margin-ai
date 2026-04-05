"""
TEST — IAM File Validator
18 assertions covering all validation paths from ingestion-module-design.md

Structural checks (fail-fast):
  IAM-01  Valid CSV with all fields -> PASS
  IAM-02  Not valid CSV -> FAIL
  IAM-03  Missing one required column -> FAIL (named field)
  IAM-04  Missing multiple required columns -> FAIL (all named)
  IAM-05  Empty file (header only, zero data rows) -> FAIL

Row-level checks (collected):
  IAM-06  Null value in tenant_id -> FAIL (named field + row)
  IAM-07  Empty string in billing_period -> FAIL
  IAM-08  billing_period wrong format (2025/03) -> FAIL
  IAM-09  billing_period invalid month (2025-13) -> FAIL
  IAM-10  billing_period month 00 -> FAIL
  IAM-11  contracted_rate not decimal (abc) -> FAIL
  IAM-12  contracted_rate zero -> FAIL (stricter than DB)
  IAM-13  contracted_rate negative -> FAIL
  IAM-14  Duplicate natural key (tenant_id + billing_period) -> FAIL
  IAM-15  Same tenant different period -> PASS (not duplicate)
  IAM-16  Multiple rows, error on row 2 only -> row=2 reported
  IAM-17  Multiple errors collected across rows -> all reported
  IAM-18  Valid edge case: high contracted_rate -> PASS
"""

import pytest

from app.ingestion.validators.iam import validate_iam_file


# -- Helpers ------------------------------------------------------------------

def _csv(header: str, *rows: str) -> str:
    """Build CSV string from header + data rows."""
    return "\n".join([header] + list(rows))


HEADER = "tenant_id,billing_period,contracted_rate"
VALID_ROW = "tenant-01,2025-03,0.750000"


# -- Structural Checks -------------------------------------------------------

def test_iam01_valid_csv_passes():
    """IAM-01: Valid CSV with all required fields -> PASS"""
    result = validate_iam_file(_csv(HEADER, VALID_ROW))
    assert result.verdict == "PASS"
    assert result.errors == []


def test_iam02_not_valid_csv():
    """IAM-02: Not valid CSV -> FAIL"""
    result = validate_iam_file("")
    assert result.verdict == "FAIL"
    assert any("not valid CSV" in e.message or "no data" in e.message for e in result.errors)


def test_iam03_missing_one_column():
    """IAM-03: Missing one required column -> FAIL with named field"""
    bad_header = "tenant_id,billing_period"
    result = validate_iam_file(_csv(bad_header, "t1,2025-03"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "contracted_rate" and "Missing column" in e.message
        for e in result.errors
    )


def test_iam04_missing_multiple_columns():
    """IAM-04: Missing multiple required columns -> all named"""
    bad_header = "tenant_id"
    result = validate_iam_file(_csv(bad_header, "t1"))
    assert result.verdict == "FAIL"
    missing_fields = {e.field for e in result.errors if "Missing column" in e.message}
    assert missing_fields == {"billing_period", "contracted_rate"}


def test_iam05_empty_file_no_data_rows():
    """IAM-05: Header only, zero data rows -> FAIL"""
    result = validate_iam_file(HEADER)
    assert result.verdict == "FAIL"
    assert any("no data rows" in e.message for e in result.errors)


# -- Row-Level: Null Checks ---------------------------------------------------

def test_iam06_null_tenant_id():
    """IAM-06: Null tenant_id -> FAIL with named field and row"""
    result = validate_iam_file(_csv(HEADER, ",2025-03,0.75"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "tenant_id" and e.row == 1 and "Null" in e.message
        for e in result.errors
    )


def test_iam07_empty_string_billing_period():
    """IAM-07: Empty string in billing_period -> FAIL"""
    result = validate_iam_file(_csv(HEADER, "tenant-01,,0.75"))
    assert result.verdict == "FAIL"
    assert any(e.field == "billing_period" and "Null" in e.message for e in result.errors)


# -- Row-Level: billing_period Format -----------------------------------------

def test_iam08_billing_period_wrong_format():
    """IAM-08: billing_period as 2025/03 -> FAIL"""
    result = validate_iam_file(_csv(HEADER, "tenant-01,2025/03,0.75"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "billing_period" and "YYYY-MM format" in e.message
        for e in result.errors
    )


def test_iam09_billing_period_invalid_month():
    """IAM-09: billing_period month 13 -> FAIL"""
    result = validate_iam_file(_csv(HEADER, "tenant-01,2025-13,0.75"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "billing_period" and "YYYY-MM format" in e.message
        for e in result.errors
    )


def test_iam10_billing_period_month_zero():
    """IAM-10: billing_period month 00 -> FAIL"""
    result = validate_iam_file(_csv(HEADER, "tenant-01,2025-00,0.75"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "billing_period" and "YYYY-MM format" in e.message
        for e in result.errors
    )


# -- Row-Level: contracted_rate -----------------------------------------------

def test_iam11_contracted_rate_not_decimal():
    """IAM-11: contracted_rate = 'abc' -> FAIL"""
    result = validate_iam_file(_csv(HEADER, "tenant-01,2025-03,abc"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "contracted_rate" and "Type error" in e.message
        for e in result.errors
    )


def test_iam12_contracted_rate_zero():
    """IAM-12: contracted_rate = 0 -> FAIL (validator stricter than DB)"""
    result = validate_iam_file(_csv(HEADER, "tenant-01,2025-03,0"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "contracted_rate" and "must be > 0" in e.message
        for e in result.errors
    )


def test_iam13_contracted_rate_negative():
    """IAM-13: contracted_rate = -0.5 -> FAIL"""
    result = validate_iam_file(_csv(HEADER, "tenant-01,2025-03,-0.5"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "contracted_rate" and "must be > 0" in e.message
        for e in result.errors
    )


# -- Duplicate Natural Key ---------------------------------------------------

def test_iam14_duplicate_natural_key():
    """IAM-14: Duplicate (tenant_id + billing_period) -> FAIL"""
    csv_content = _csv(
        HEADER,
        "tenant-01,2025-03,0.75",
        "tenant-01,2025-03,0.80",  # same key, different rate
    )
    result = validate_iam_file(csv_content)
    assert result.verdict == "FAIL"
    assert any("Duplicate key" in e.message for e in result.errors)


def test_iam15_same_tenant_different_period_passes():
    """IAM-15: Same tenant, different billing_period -> PASS"""
    csv_content = _csv(
        HEADER,
        "tenant-01,2025-03,0.75",
        "tenant-01,2025-04,0.80",  # different period
    )
    result = validate_iam_file(csv_content)
    assert result.verdict == "PASS"


# -- Multi-Row Error Reporting ------------------------------------------------

def test_iam16_error_on_row_2_only():
    """IAM-16: Row 1 valid, row 2 invalid -> error reports row=2"""
    csv_content = _csv(HEADER, VALID_ROW, "tenant-02,2025/04,0.50")
    result = validate_iam_file(csv_content)
    assert result.verdict == "FAIL"
    assert any(e.row == 2 and e.field == "billing_period" for e in result.errors)
    assert not any(e.row == 1 for e in result.errors)


def test_iam17_multiple_errors_collected():
    """IAM-17: Multiple errors across rows -> all reported"""
    csv_content = _csv(
        HEADER,
        "tenant-01,2025-13,0.75",    # row 1: bad billing_period
        "tenant-02,2025-03,-0.50",    # row 2: negative contracted_rate
    )
    result = validate_iam_file(csv_content)
    assert result.verdict == "FAIL"
    assert len(result.errors) >= 2
    assert any(e.row == 1 and e.field == "billing_period" for e in result.errors)
    assert any(e.row == 2 and e.field == "contracted_rate" for e in result.errors)


# -- Edge Cases ---------------------------------------------------------------

def test_iam18_high_contracted_rate_passes():
    """IAM-18: Very high contracted_rate (99999.99) -> PASS"""
    result = validate_iam_file(_csv(HEADER, "tenant-01,2025-03,99999.990000"))
    assert result.verdict == "PASS"
