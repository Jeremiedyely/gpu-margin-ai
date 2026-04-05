"""
TEST — ERP File Validator
17 assertions covering all validation paths from ingestion-module-design.md

Structural checks (fail-fast):
  ERP-01  Valid CSV with all fields -> PASS
  ERP-02  Not valid CSV -> FAIL
  ERP-03  Missing one required column -> FAIL (named field)
  ERP-04  Missing multiple required columns -> FAIL (all named)
  ERP-05  Empty file (header only, zero data rows) -> FAIL

Row-level checks (collected):
  ERP-06  Null value in tenant_id -> FAIL (named field + row)
  ERP-07  Empty string in billing_period -> FAIL
  ERP-08  billing_period wrong format (2025/03) -> FAIL
  ERP-09  billing_period invalid month (2025-13) -> FAIL
  ERP-10  amount_posted not decimal (abc) -> FAIL
  ERP-11  amount_posted negative -> PASS (GL reversals allowed — R4-W-3)
  ERP-12  amount_posted zero -> PASS
  ERP-13  Duplicate natural key (tenant_id + billing_period) -> FAIL
  ERP-14  Same tenant different period -> PASS (not duplicate)
  ERP-15  Multiple rows, error on row 2 only -> row=2 reported
  ERP-16  Multiple errors collected across rows -> all reported
  ERP-17  Valid edge case: large negative GL reversal -> PASS
"""

import pytest

from app.ingestion.validators.erp import validate_erp_file


# -- Helpers ------------------------------------------------------------------

def _csv(header: str, *rows: str) -> str:
    return "\n".join([header] + list(rows))


HEADER = "tenant_id,billing_period,amount_posted"
VALID_ROW = "tenant-01,2025-03,1500.000000"


# -- Structural Checks -------------------------------------------------------

def test_erp01_valid_csv_passes():
    """ERP-01: Valid CSV with all required fields -> PASS"""
    result = validate_erp_file(_csv(HEADER, VALID_ROW))
    assert result.verdict == "PASS"
    assert result.errors == []


def test_erp02_not_valid_csv():
    """ERP-02: Not valid CSV -> FAIL"""
    result = validate_erp_file("")
    assert result.verdict == "FAIL"
    assert any("not valid CSV" in e.message or "no data" in e.message for e in result.errors)


def test_erp03_missing_one_column():
    """ERP-03: Missing one required column -> FAIL with named field"""
    bad_header = "tenant_id,billing_period"
    result = validate_erp_file(_csv(bad_header, "t1,2025-03"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "amount_posted" and "Missing column" in e.message
        for e in result.errors
    )


def test_erp04_missing_multiple_columns():
    """ERP-04: Missing multiple required columns -> all named"""
    bad_header = "tenant_id"
    result = validate_erp_file(_csv(bad_header, "t1"))
    assert result.verdict == "FAIL"
    missing_fields = {e.field for e in result.errors if "Missing column" in e.message}
    assert missing_fields == {"billing_period", "amount_posted"}


def test_erp05_empty_file_no_data_rows():
    """ERP-05: Header only, zero data rows -> FAIL"""
    result = validate_erp_file(HEADER)
    assert result.verdict == "FAIL"
    assert any("no data rows" in e.message for e in result.errors)


# -- Row-Level: Null Checks ---------------------------------------------------

def test_erp06_null_tenant_id():
    """ERP-06: Null tenant_id -> FAIL with named field and row"""
    result = validate_erp_file(_csv(HEADER, ",2025-03,1500"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "tenant_id" and e.row == 1 and "Null" in e.message
        for e in result.errors
    )


def test_erp07_empty_string_billing_period():
    """ERP-07: Empty string in billing_period -> FAIL"""
    result = validate_erp_file(_csv(HEADER, "tenant-01,,1500"))
    assert result.verdict == "FAIL"
    assert any(e.field == "billing_period" and "Null" in e.message for e in result.errors)


# -- Row-Level: billing_period Format -----------------------------------------

def test_erp08_billing_period_wrong_format():
    """ERP-08: billing_period as 2025/03 -> FAIL"""
    result = validate_erp_file(_csv(HEADER, "tenant-01,2025/03,1500"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "billing_period" and "YYYY-MM format" in e.message
        for e in result.errors
    )


def test_erp09_billing_period_invalid_month():
    """ERP-09: billing_period month 13 -> FAIL"""
    result = validate_erp_file(_csv(HEADER, "tenant-01,2025-13,1500"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "billing_period" and "YYYY-MM format" in e.message
        for e in result.errors
    )


# -- Row-Level: amount_posted -------------------------------------------------

def test_erp10_amount_posted_not_decimal():
    """ERP-10: amount_posted = 'abc' -> FAIL"""
    result = validate_erp_file(_csv(HEADER, "tenant-01,2025-03,abc"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "amount_posted" and "Type error" in e.message
        for e in result.errors
    )


def test_erp11_amount_posted_negative_passes():
    """ERP-11: amount_posted = -500 -> PASS (GL reversals allowed — R4-W-3)"""
    result = validate_erp_file(_csv(HEADER, "tenant-01,2025-03,-500.00"))
    assert result.verdict == "PASS"


def test_erp12_amount_posted_zero_passes():
    """ERP-12: amount_posted = 0 -> PASS"""
    result = validate_erp_file(_csv(HEADER, "tenant-01,2025-03,0"))
    assert result.verdict == "PASS"


# -- Duplicate Natural Key ---------------------------------------------------

def test_erp13_duplicate_natural_key():
    """ERP-13: Duplicate (tenant_id + billing_period) -> FAIL"""
    csv_content = _csv(
        HEADER,
        "tenant-01,2025-03,1500",
        "tenant-01,2025-03,2000",
    )
    result = validate_erp_file(csv_content)
    assert result.verdict == "FAIL"
    assert any("Duplicate key" in e.message for e in result.errors)


def test_erp14_same_tenant_different_period_passes():
    """ERP-14: Same tenant, different billing_period -> PASS"""
    csv_content = _csv(
        HEADER,
        "tenant-01,2025-03,1500",
        "tenant-01,2025-04,1500",
    )
    result = validate_erp_file(csv_content)
    assert result.verdict == "PASS"


# -- Multi-Row Error Reporting ------------------------------------------------

def test_erp15_error_on_row_2_only():
    """ERP-15: Row 1 valid, row 2 invalid -> error reports row=2"""
    csv_content = _csv(HEADER, VALID_ROW, "tenant-02,2025/04,1500")
    result = validate_erp_file(csv_content)
    assert result.verdict == "FAIL"
    assert any(e.row == 2 and e.field == "billing_period" for e in result.errors)
    assert not any(e.row == 1 for e in result.errors)


def test_erp16_multiple_errors_collected():
    """ERP-16: Multiple errors across rows -> all reported"""
    csv_content = _csv(
        HEADER,
        "tenant-01,2025-13,1500",
        "tenant-02,2025-03,abc",
    )
    result = validate_erp_file(csv_content)
    assert result.verdict == "FAIL"
    assert len(result.errors) >= 2
    assert any(e.row == 1 and e.field == "billing_period" for e in result.errors)
    assert any(e.row == 2 and e.field == "amount_posted" for e in result.errors)


# -- Edge Cases ---------------------------------------------------------------

def test_erp17_large_negative_gl_reversal_passes():
    """ERP-17: Large negative GL reversal (-99999.99) -> PASS"""
    result = validate_erp_file(_csv(HEADER, "tenant-01,2025-03,-99999.990000"))
    assert result.verdict == "PASS"
