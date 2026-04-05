"""
TEST — Cost Management File Parser — 7 assertions
  CMP-01  Valid CSV -> PASS with correct record count
  CMP-02  Record fields have correct types
  CMP-03  Multiple rows in order
  CMP-04  Decimal precision preserved
  CMP-05  Date parsed to date object
  CMP-06  Unparseable decimal -> FAIL with row number
  CMP-07  No records on failure
"""

from datetime import date
from decimal import Decimal

import pytest

from app.ingestion.parsers.cost_management import CostManagementRecord, parse_cost_management_file


def _csv(header: str, *rows: str) -> str:
    return "\n".join([header] + list(rows))

HEADER = "region,gpu_pool_id,date,reserved_gpu_hours,cost_per_gpu_hour"
VALID_ROW_1 = "us-east-1,pool-a,2025-03-01,100.000000,2.500000"
VALID_ROW_2 = "eu-west-1,pool-b,2025-03-02,200.000000,3.250000"


def test_cmp01_valid_csv_passes():
    result = parse_cost_management_file(_csv(HEADER, VALID_ROW_1))
    assert result.result == "PASS"
    assert len(result.records) == 1
    assert result.error is None

def test_cmp02_record_types_correct():
    result = parse_cost_management_file(_csv(HEADER, VALID_ROW_1))
    rec = result.records[0]
    assert isinstance(rec, CostManagementRecord)
    assert isinstance(rec.date, date)
    assert isinstance(rec.reserved_gpu_hours, Decimal)
    assert isinstance(rec.cost_per_gpu_hour, Decimal)

def test_cmp03_multiple_rows_in_order():
    result = parse_cost_management_file(_csv(HEADER, VALID_ROW_1, VALID_ROW_2))
    assert result.result == "PASS"
    assert len(result.records) == 2
    assert result.records[0].region == "us-east-1"
    assert result.records[1].region == "eu-west-1"

def test_cmp04_decimal_precision_preserved():
    result = parse_cost_management_file(_csv(HEADER, VALID_ROW_1))
    assert result.records[0].reserved_gpu_hours == Decimal("100.000000")
    assert result.records[0].cost_per_gpu_hour == Decimal("2.500000")

def test_cmp05_date_parsed_to_date_object():
    result = parse_cost_management_file(_csv(HEADER, VALID_ROW_1))
    assert result.records[0].date == date(2025, 3, 1)

def test_cmp06_unparseable_decimal_fails():
    result = parse_cost_management_file(_csv(HEADER, "us-east-1,pool-a,2025-03-01,not-num,2.5"))
    assert result.result == "FAIL"
    assert "row 1" in result.error
    assert result.records == []

def test_cmp07_no_records_on_failure():
    result = parse_cost_management_file(_csv(HEADER, "us-east-1,pool-a,bad-date,100,2.5"))
    assert result.result == "FAIL"
    assert len(result.records) == 0
