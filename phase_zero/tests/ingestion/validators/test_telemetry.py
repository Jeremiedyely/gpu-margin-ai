"""
TEST — Telemetry File Validator
18 assertions covering all validation paths from ingestion-module-design.md

Structural checks (fail-fast):
  T-01  Valid CSV with all fields -> PASS
  T-02  Not valid CSV -> FAIL
  T-03  Missing one required column -> FAIL (named field)
  T-04  Missing multiple required columns -> FAIL (all named)
  T-05  Empty file (header only, zero data rows) -> FAIL

Row-level checks (collected):
  T-06  Null value in tenant_id -> FAIL (named field + row)
  T-07  Empty string in region -> FAIL (named field + row)
  T-08  tenant_id format invalid — spaces -> FAIL
  T-09  tenant_id format invalid — special chars -> FAIL
  T-10  tenant_id single char valid -> PASS
  T-11  date wrong format (DD/MM/YYYY) -> FAIL
  T-12  date not a date (abc) -> FAIL
  T-13  gpu_hours_consumed not decimal (abc) -> FAIL
  T-14  gpu_hours_consumed zero -> FAIL
  T-15  gpu_hours_consumed negative -> FAIL
  T-16  Multiple rows, error on row 2 only -> row=2 reported
  T-17  Multiple errors collected across rows -> all reported
  T-18  Custom tenant_id_pattern override -> FAIL on non-UUID
"""

import re

import pytest

from app.ingestion.validators.telemetry import validate_telemetry_file


# -- Helpers ------------------------------------------------------------------

def _csv(header: str, *rows: str) -> str:
    """Build CSV string from header + data rows."""
    return "\n".join([header] + list(rows))


HEADER = "tenant_id,region,gpu_pool_id,date,gpu_hours_consumed"
VALID_ROW = "tenant-01,us-east-1,pool-a,2025-03-01,10.500000"


# -- Structural Checks -------------------------------------------------------

def test_t01_valid_csv_passes():
    """T-01: Valid CSV with all required fields -> PASS"""
    result = validate_telemetry_file(_csv(HEADER, VALID_ROW))
    assert result.verdict == "PASS"
    assert result.errors == []


def test_t02_not_valid_csv():
    """T-02: Not valid CSV -> FAIL"""
    result = validate_telemetry_file("")
    assert result.verdict == "FAIL"
    assert any("not valid CSV" in e.message or "no data" in e.message for e in result.errors)


def test_t03_missing_one_column():
    """T-03: Missing one required column -> FAIL with named field"""
    bad_header = "tenant_id,region,gpu_pool_id,date"  # missing gpu_hours_consumed
    result = validate_telemetry_file(_csv(bad_header, "t1,us-east-1,pool-a,2025-03-01"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "gpu_hours_consumed" and "Missing column" in e.message
        for e in result.errors
    )


def test_t04_missing_multiple_columns():
    """T-04: Missing multiple required columns -> all named"""
    bad_header = "tenant_id,date"
    result = validate_telemetry_file(_csv(bad_header, "t1,2025-03-01"))
    assert result.verdict == "FAIL"
    missing_fields = {e.field for e in result.errors if "Missing column" in e.message}
    assert missing_fields == {"region", "gpu_pool_id", "gpu_hours_consumed"}


def test_t05_empty_file_no_data_rows():
    """T-05: Header only, zero data rows -> FAIL"""
    result = validate_telemetry_file(HEADER)
    assert result.verdict == "FAIL"
    assert any("no data rows" in e.message for e in result.errors)


# -- Row-Level: Null Checks ---------------------------------------------------

def test_t06_null_tenant_id():
    """T-06: Null tenant_id -> FAIL with named field and row"""
    result = validate_telemetry_file(_csv(HEADER, ",us-east-1,pool-a,2025-03-01,10.5"))
    assert result.verdict == "FAIL"
    assert any(
        e.field == "tenant_id" and e.row == 1 and "Null" in e.message
        for e in result.errors
    )


def test_t07_empty_string_region():
    """T-07: Empty string in region -> FAIL with named field"""
    result = validate_telemetry_file(_csv(HEADER, "tenant-01,,pool-a,2025-03-01,10.5"))
    assert result.verdict == "FAIL"
    assert any(e.field == "region" and "Null" in e.message for e in result.errors)


# -- Row-Level: tenant_id Format (P1 #7) -------------------------------------

def test_t08_tenant_id_spaces():
    """T-08: tenant_id with spaces -> FAIL (P1 #7)"""
    result = validate_telemetry_file(
        _csv(HEADER, "tenant 01,us-east-1,pool-a,2025-03-01,10.5")
    )
    assert result.verdict == "FAIL"
    assert any(
        e.field == "tenant_id" and "format invalid" in e.message
        for e in result.errors
    )


def test_t09_tenant_id_special_chars():
    """T-09: tenant_id with special chars -> FAIL (P1 #7)"""
    result = validate_telemetry_file(
        _csv(HEADER, "tenant@01!,us-east-1,pool-a,2025-03-01,10.5")
    )
    assert result.verdict == "FAIL"
    assert any(
        e.field == "tenant_id" and "format invalid" in e.message
        for e in result.errors
    )


def test_t10_tenant_id_single_char():
    """T-10: Single alphanumeric tenant_id -> PASS"""
    result = validate_telemetry_file(
        _csv(HEADER, "A,us-east-1,pool-a,2025-03-01,10.5")
    )
    assert result.verdict == "PASS"


# -- Row-Level: Date Format ---------------------------------------------------

def test_t11_date_wrong_format():
    """T-11: Date in DD/MM/YYYY -> FAIL"""
    result = validate_telemetry_file(
        _csv(HEADER, "tenant-01,us-east-1,pool-a,01/03/2025,10.5")
    )
    assert result.verdict == "FAIL"
    assert any(
        e.field == "date" and "Type error: date" in e.message
        for e in result.errors
    )


def test_t12_date_not_a_date():
    """T-12: Date as 'abc' -> FAIL"""
    result = validate_telemetry_file(
        _csv(HEADER, "tenant-01,us-east-1,pool-a,abc,10.5")
    )
    assert result.verdict == "FAIL"
    assert any(
        e.field == "date" and "Type error: date" in e.message
        for e in result.errors
    )


# -- Row-Level: gpu_hours_consumed --------------------------------------------

def test_t13_gpu_hours_not_decimal():
    """T-13: gpu_hours_consumed = 'abc' -> FAIL"""
    result = validate_telemetry_file(
        _csv(HEADER, "tenant-01,us-east-1,pool-a,2025-03-01,abc")
    )
    assert result.verdict == "FAIL"
    assert any(
        e.field == "gpu_hours_consumed" and "Type error" in e.message
        for e in result.errors
    )


def test_t14_gpu_hours_zero():
    """T-14: gpu_hours_consumed = 0 -> FAIL (must be > 0)"""
    result = validate_telemetry_file(
        _csv(HEADER, "tenant-01,us-east-1,pool-a,2025-03-01,0")
    )
    assert result.verdict == "FAIL"
    assert any(
        e.field == "gpu_hours_consumed" and "must be > 0" in e.message
        for e in result.errors
    )


def test_t15_gpu_hours_negative():
    """T-15: gpu_hours_consumed = -5.0 -> FAIL"""
    result = validate_telemetry_file(
        _csv(HEADER, "tenant-01,us-east-1,pool-a,2025-03-01,-5.0")
    )
    assert result.verdict == "FAIL"
    assert any(
        e.field == "gpu_hours_consumed" and "must be > 0" in e.message
        for e in result.errors
    )


# -- Row-Level: Multi-Row Error Reporting -------------------------------------

def test_t16_error_on_row_2_only():
    """T-16: Row 1 valid, row 2 invalid -> error reports row=2"""
    csv_content = _csv(HEADER, VALID_ROW, "tenant-02,us-east-1,pool-a,bad-date,10.5")
    result = validate_telemetry_file(csv_content)
    assert result.verdict == "FAIL"
    assert any(e.row == 2 and e.field == "date" for e in result.errors)
    assert not any(e.row == 1 for e in result.errors)


def test_t17_multiple_errors_collected():
    """T-17: Multiple errors across rows — all reported"""
    csv_content = _csv(
        HEADER,
        "tenant 01,us-east-1,pool-a,2025-03-01,10.5",   # row 1: bad tenant_id
        "tenant-02,us-east-1,pool-a,2025-03-01,-1.0",    # row 2: negative gpu_hours
    )
    result = validate_telemetry_file(csv_content)
    assert result.verdict == "FAIL"
    assert len(result.errors) >= 2
    assert any(e.row == 1 and e.field == "tenant_id" for e in result.errors)
    assert any(e.row == 2 and e.field == "gpu_hours_consumed" for e in result.errors)


# -- Configurable Pattern Override --------------------------------------------

def test_t18_custom_tenant_id_pattern():
    """T-18: Custom regex (UUID only) rejects non-UUID tenant_id"""
    uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )
    # "tenant-01" is valid under default pattern but NOT a UUID
    result = validate_telemetry_file(
        _csv(HEADER, VALID_ROW),
        tenant_id_pattern=uuid_pattern,
    )
    assert result.verdict == "FAIL"
    assert any(
        e.field == "tenant_id" and "format invalid" in e.message
        for e in result.errors
    )
