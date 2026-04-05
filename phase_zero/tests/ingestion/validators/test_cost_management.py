"""
TEST — Cost Management File Validator
19 assertions covering all validation paths from ingestion-module-design.md

Structural checks (fail-fast):
  CM-01  Valid CSV with all fields -> PASS
  CM-02  Not valid CSV -> FAIL
  CM-03  Missing one required column -> FAIL (named field)
  CM-04  Missing multiple required columns -> FAIL (all named)
  CM-05  Empty file (header only, zero data rows) -> FAIL

Row-level checks (collected):
  CM-06  Null value in region -> FAIL (named field + row)
  CM-07  Empty string in gpu_pool_id -> FAIL (named field + row)
  CM-08  date wrong format (DD/MM/YYYY) -> FAIL
  CM-09  date not a date (abc) -> FAIL
  CM-10  reserved_gpu_hours not decimal (abc) -> FAIL
  CM-11  reserved_gpu_hours zero -> FAIL
  CM-12  reserved_gpu_hours negative -> FAIL
  CM-13  cost_per_gpu_hour not decimal (abc) -> FAIL
  CM-14  cost_per_gpu_hour zero -> FAIL
  CM-15  cost_per_gpu_hour negative -> FAIL
  CM-16  Duplicate natural key (region + gpu_pool_id + date) -> FAIL
  CM-17  Same region+pool different date -> PASS (not duplicate)
  CM-18  Multiple rows, error on row 2 only -> row=2 reported
  CM-19  Multiple errors collected across rows -> all reported
"""

import pytest

from app.ingestion.validators.cost_management import validate_cost_management_file


# -- Helpers ------------------------------------------------------------------

def _csv(header: str, *rows: str) -> str:
    """Build CSV string from header + data rows."""
    return "\n".join([header] + list(rows))


HEADER = "region,gpu_pool_id,date,reserved_gpu_hours,cost_per_gpu_hour"
VALID_ROW = "us-east-1,pool-a,2025-03-01,100.000000,2.500000"


# -- Structural Checks -------------------------------------------------------

def test_cm01_valid_csv_passes():
    """CM-01: Valid CSV with all required fields -> PASS"""
    result = validate_cost_management_file(_csv(HEADER, VALID_ROW))
    assert result.verdict == "PASS"
    assert result.errors == []


def test_cm02_not_valid_csv():
    """CM-02: Not valid CSV -> FAIL"""
    result = validate_cost_management_file("")
    assert result.verdict == "FAIL"
    assert any("not valid CSV" in e.message or "no data" in e.message for e in result.errors)


def test_cm03_missing_one_column():
    """CM-03: Missing one required column -> FAIL with named field"""
    bad_header = "region,gpu_pool_id,date,reserved_gpu_hours"
    result = validate_cost_management_file(_csv(bad_header, "us-east-1,pool-a,2025-03-01,100"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "cost_per_gpu_hour" and "Missing column" in e.message
        for e in result.errors
    )


def test_cm04_missing_multiple_columns():
    """CM-04: Missing multiple required columns -> all named"""
    bad_header = "region,date"
    result = validate_cost_management_file(_csv(bad_header, "us-east-1,2025-03-01"))
    assert result.verdict == "FAIL"
    missing_fields = {e.field for e in result.errors if "Missing column" in e.message}
    assert missing_fields == {"gpu_pool_id", "reserved_gpu_hours", "cost_per_gpu_hour"}


def test_cm05_empty_file_no_data_rows():
    """CM-05: Header only, zero data rows -> FAIL"""
    result = validate_cost_management_file(HEADER)
    assert result.verdict == "FAIL"
    assert any("no data rows" in e.message for e in result.errors)


# -- Row-Level: Null Checks ---------------------------------------------------

def test_cm06_null_region():
    """CM-06: Null region -> FAIL with named field and row"""
    result = validate_cost_management_file(_csv(HEADER, ",pool-a,2025-03-01,100,2.5"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "region" and e.row == 1 and "Null" in e.message
        for e in result.errors
    )


def test_cm07_empty_string_gpu_pool_id():
    """CM-07: Empty string in gpu_pool_id -> FAIL"""
    result = validate_cost_management_file(_csv(HEADER, "us-east-1,,2025-03-01,100,2.5"))
    assert result.verdict == "FAIL"
    assert any(e.field == "gpu_pool_id" and "Null" in e.message for e in result.errors)


# -- Row-Level: Date Format ---------------------------------------------------

def test_cm08_date_wrong_format():
    """CM-08: Date in DD/MM/YYYY -> FAIL"""
    result = validate_cost_management_file(
        _csv(HEADER, "us-east-1,pool-a,01/03/2025,100,2.5")
    )
    assert result.verdict == "FAIL"
    assert any(e.field == "date" and "Type error: date" in e.message for e in result.errors)


def test_cm09_date_not_a_date():
    """CM-09: Date as 'abc' -> FAIL"""
    result = validate_cost_management_file(
        _csv(HEADER, "us-east-1,pool-a,abc,100,2.5")
    )
    assert result.verdict == "FAIL"
    assert any(e.field == "date" and "Type error: date" in e.message for e in result.errors)


# -- Row-Level: reserved_gpu_hours --------------------------------------------

def test_cm10_reserved_gpu_hours_not_decimal():
    """CM-10: reserved_gpu_hours = 'abc' -> FAIL"""
    result = validate_cost_management_file(
        _csv(HEADER, "us-east-1,pool-a,2025-03-01,abc,2.5")
    )
    assert result.verdict == "FAIL"
    assert any(
        e.field == "reserved_gpu_hours" and "Type error" in e.message
        for e in result.errors
    )


def test_cm11_reserved_gpu_hours_zero():
    """CM-11: reserved_gpu_hours = 0 -> FAIL (must be > 0)"""
    result = validate_cost_management_file(
        _csv(HEADER, "us-east-1,pool-a,2025-03-01,0,2.5")
    )
    assert result.verdict == "FAIL"
    assert any(
        e.field == "reserved_gpu_hours" and "must be > 0" in e.message
        for e in result.errors
    )


def test_cm12_reserved_gpu_hours_negative():
    """CM-12: reserved_gpu_hours = -50 -> FAIL"""
    result = validate_cost_management_file(
        _csv(HEADER, "us-east-1,pool-a,2025-03-01,-50,2.5")
    )
    assert result.verdict == "FAIL"
    assert any(
        e.field == "reserved_gpu_hours" and "must be > 0" in e.message
        for e in result.errors
    )


# -- Row-Level: cost_per_gpu_hour ---------------------------------------------

def test_cm13_cost_per_gpu_hour_not_decimal():
    """CM-13: cost_per_gpu_hour = 'abc' -> FAIL"""
    result = validate_cost_management_file(
        _csv(HEADER, "us-east-1,pool-a,2025-03-01,100,abc")
    )
    assert result.verdict == "FAIL"
    assert any(
        e.field == "cost_per_gpu_hour" and "Type error" in e.message
        for e in result.errors
    )


def test_cm14_cost_per_gpu_hour_zero():
    """CM-14: cost_per_gpu_hour = 0 -> FAIL (must be > 0)"""
    result = validate_cost_management_file(
        _csv(HEADER, "us-east-1,pool-a,2025-03-01,100,0")
    )
    assert result.verdict == "FAIL"
    assert any(
        e.field == "cost_per_gpu_hour" and "must be > 0" in e.message
        for e in result.errors
    )


def test_cm15_cost_per_gpu_hour_negative():
    """CM-15: cost_per_gpu_hour = -1.5 -> FAIL"""
    result = validate_cost_management_file(
        _csv(HEADER, "us-east-1,pool-a,2025-03-01,100,-1.5")
    )
    assert result.verdict == "FAIL"
    assert any(
        e.field == "cost_per_gpu_hour" and "must be > 0" in e.message
        for e in result.errors
    )


# -- Duplicate Natural Key ---------------------------------------------------

def test_cm16_duplicate_natural_key():
    """CM-16: Duplicate (region + gpu_pool_id + date) -> FAIL"""
    csv_content = _csv(
        HEADER,
        "us-east-1,pool-a,2025-03-01,100,2.5",
        "us-east-1,pool-a,2025-03-01,200,3.0",  # same key
    )
    result = validate_cost_management_file(csv_content)
    assert result.verdict == "FAIL"
    assert any("Duplicate key" in e.message for e in result.errors)


def test_cm17_same_region_pool_different_date_passes():
    """CM-17: Same region+pool, different date -> PASS (not duplicate)"""
    csv_content = _csv(
        HEADER,
        "us-east-1,pool-a,2025-03-01,100,2.5",
        "us-east-1,pool-a,2025-03-02,100,2.5",  # different date
    )
    result = validate_cost_management_file(csv_content)
    assert result.verdict == "PASS"


# -- Multi-Row Error Reporting ------------------------------------------------

def test_cm18_error_on_row_2_only():
    """CM-18: Row 1 valid, row 2 invalid -> error reports row=2"""
    csv_content = _csv(HEADER, VALID_ROW, "us-east-1,pool-b,bad-date,100,2.5")
    result = validate_cost_management_file(csv_content)
    assert result.verdict == "FAIL"
    assert any(e.row == 2 and e.field == "date" for e in result.errors)
    assert not any(e.row == 1 for e in result.errors)


def test_cm19_multiple_errors_collected():
    """CM-19: Multiple errors across rows -> all reported"""
    csv_content = _csv(
        HEADER,
        "us-east-1,pool-a,2025-03-01,abc,2.5",     # row 1: bad reserved_gpu_hours
        "us-east-1,pool-b,2025-03-01,100,-1.0",     # row 2: negative cost_per_gpu_hour
    )
    result = validate_cost_management_file(csv_content)
    assert result.verdict == "FAIL"
    assert len(result.errors) >= 2
    assert any(e.row == 1 and e.field == "reserved_gpu_hours" for e in result.errors)
    assert any(e.row == 2 and e.field == "cost_per_gpu_hour" for e in result.errors)
