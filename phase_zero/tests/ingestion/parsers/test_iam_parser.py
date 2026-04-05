"""
TEST — IAM File Parser — 6 assertions
  IAMP-01  Valid CSV -> PASS with correct record count
  IAMP-02  Record fields have correct types
  IAMP-03  Multiple rows in order
  IAMP-04  Decimal precision preserved
  IAMP-05  Unparseable decimal -> FAIL with row number
  IAMP-06  No records on failure
"""

from decimal import Decimal

import pytest

from app.ingestion.parsers.iam import IAMRecord, parse_iam_file


def _csv(header: str, *rows: str) -> str:
    return "\n".join([header] + list(rows))

HEADER = "tenant_id,billing_period,contracted_rate"
VALID_ROW_1 = "tenant-01,2025-03,0.750000"
VALID_ROW_2 = "tenant-02,2025-04,1.200000"


def test_iamp01_valid_csv_passes():
    result = parse_iam_file(_csv(HEADER, VALID_ROW_1))
    assert result.result == "PASS"
    assert len(result.records) == 1
    assert result.error is None

def test_iamp02_record_types_correct():
    result = parse_iam_file(_csv(HEADER, VALID_ROW_1))
    rec = result.records[0]
    assert isinstance(rec, IAMRecord)
    assert isinstance(rec.tenant_id, str)
    assert isinstance(rec.billing_period, str)
    assert isinstance(rec.contracted_rate, Decimal)

def test_iamp03_multiple_rows_in_order():
    result = parse_iam_file(_csv(HEADER, VALID_ROW_1, VALID_ROW_2))
    assert result.result == "PASS"
    assert len(result.records) == 2
    assert result.records[0].tenant_id == "tenant-01"
    assert result.records[1].tenant_id == "tenant-02"

def test_iamp04_decimal_precision_preserved():
    result = parse_iam_file(_csv(HEADER, VALID_ROW_1))
    assert result.records[0].contracted_rate == Decimal("0.750000")

def test_iamp05_unparseable_decimal_fails():
    result = parse_iam_file(_csv(HEADER, "tenant-01,2025-03,not-decimal"))
    assert result.result == "FAIL"
    assert "row 1" in result.error
    assert result.records == []

def test_iamp06_no_records_on_failure():
    result = parse_iam_file(_csv(HEADER, "tenant-01,2025-03,abc"))
    assert result.result == "FAIL"
    assert len(result.records) == 0
