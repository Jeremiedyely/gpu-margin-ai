"""
TEST — Billing File Parser — 7 assertions
  BILP-01  Valid CSV -> PASS with correct record count
  BILP-02  Record fields have correct types
  BILP-03  Multiple rows in order
  BILP-04  Decimal precision preserved
  BILP-05  Negative billable_amount parses correctly (R4-W-3)
  BILP-06  Unparseable decimal -> FAIL with row number
  BILP-07  No records on failure
"""

from decimal import Decimal

import pytest

from app.ingestion.parsers.billing import BillingRecord, parse_billing_file


def _csv(header: str, *rows: str) -> str:
    return "\n".join([header] + list(rows))

HEADER = "tenant_id,billing_period,billable_amount"
VALID_ROW_1 = "tenant-01,2025-03,1500.000000"
VALID_ROW_2 = "tenant-02,2025-04,2500.000000"


def test_bilp01_valid_csv_passes():
    result = parse_billing_file(_csv(HEADER, VALID_ROW_1))
    assert result.result == "PASS"
    assert len(result.records) == 1
    assert result.error is None

def test_bilp02_record_types_correct():
    result = parse_billing_file(_csv(HEADER, VALID_ROW_1))
    rec = result.records[0]
    assert isinstance(rec, BillingRecord)
    assert isinstance(rec.tenant_id, str)
    assert isinstance(rec.billing_period, str)
    assert isinstance(rec.billable_amount, Decimal)

def test_bilp03_multiple_rows_in_order():
    result = parse_billing_file(_csv(HEADER, VALID_ROW_1, VALID_ROW_2))
    assert result.result == "PASS"
    assert len(result.records) == 2
    assert result.records[0].tenant_id == "tenant-01"
    assert result.records[1].tenant_id == "tenant-02"

def test_bilp04_decimal_precision_preserved():
    result = parse_billing_file(_csv(HEADER, VALID_ROW_1))
    assert result.records[0].billable_amount == Decimal("1500.000000")

def test_bilp05_negative_billable_amount_parses():
    """R4-W-3: credit memos are negative — parser must handle them"""
    result = parse_billing_file(_csv(HEADER, "tenant-01,2025-03,-500.000000"))
    assert result.result == "PASS"
    assert result.records[0].billable_amount == Decimal("-500.000000")

def test_bilp06_unparseable_decimal_fails():
    result = parse_billing_file(_csv(HEADER, "tenant-01,2025-03,not-decimal"))
    assert result.result == "FAIL"
    assert "row 1" in result.error
    assert result.records == []

def test_bilp07_no_records_on_failure():
    result = parse_billing_file(_csv(HEADER, "tenant-01,2025-03,abc"))
    assert result.result == "FAIL"
    assert len(result.records) == 0
