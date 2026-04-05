"""
TEST — ERP File Parser — 7 assertions
  ERPP-01  Valid CSV -> PASS with correct record count
  ERPP-02  Record fields have correct types
  ERPP-03  Multiple rows in order
  ERPP-04  Decimal precision preserved
  ERPP-05  Negative amount_posted parses correctly (R4-W-3)
  ERPP-06  Unparseable decimal -> FAIL with row number
  ERPP-07  No records on failure
"""

from decimal import Decimal

import pytest

from app.ingestion.parsers.erp import ERPRecord, parse_erp_file


def _csv(header: str, *rows: str) -> str:
    return "\n".join([header] + list(rows))

HEADER = "tenant_id,billing_period,amount_posted"
VALID_ROW_1 = "tenant-01,2025-03,1500.000000"
VALID_ROW_2 = "tenant-02,2025-04,2500.000000"


def test_erpp01_valid_csv_passes():
    result = parse_erp_file(_csv(HEADER, VALID_ROW_1))
    assert result.result == "PASS"
    assert len(result.records) == 1
    assert result.error is None

def test_erpp02_record_types_correct():
    result = parse_erp_file(_csv(HEADER, VALID_ROW_1))
    rec = result.records[0]
    assert isinstance(rec, ERPRecord)
    assert isinstance(rec.tenant_id, str)
    assert isinstance(rec.billing_period, str)
    assert isinstance(rec.amount_posted, Decimal)

def test_erpp03_multiple_rows_in_order():
    result = parse_erp_file(_csv(HEADER, VALID_ROW_1, VALID_ROW_2))
    assert result.result == "PASS"
    assert len(result.records) == 2
    assert result.records[0].tenant_id == "tenant-01"
    assert result.records[1].tenant_id == "tenant-02"

def test_erpp04_decimal_precision_preserved():
    result = parse_erp_file(_csv(HEADER, VALID_ROW_1))
    assert result.records[0].amount_posted == Decimal("1500.000000")

def test_erpp05_negative_amount_posted_parses():
    """R4-W-3: GL reversals are negative — parser must handle them"""
    result = parse_erp_file(_csv(HEADER, "tenant-01,2025-03,-500.000000"))
    assert result.result == "PASS"
    assert result.records[0].amount_posted == Decimal("-500.000000")

def test_erpp06_unparseable_decimal_fails():
    result = parse_erp_file(_csv(HEADER, "tenant-01,2025-03,not-decimal"))
    assert result.result == "FAIL"
    assert "row 1" in result.error
    assert result.records == []

def test_erpp07_no_records_on_failure():
    result = parse_erp_file(_csv(HEADER, "tenant-01,2025-03,abc"))
    assert result.result == "FAIL"
    assert len(result.records) == 0
