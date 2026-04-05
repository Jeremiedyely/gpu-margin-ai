"""
TEST — Telemetry File Parser
8 assertions covering all parsing paths from ingestion-module-design.md

  TP-01  Valid CSV -> PASS with correct record count
  TP-02  Record fields have correct types (str, date, Decimal)
  TP-03  Multiple rows -> all records returned in order
  TP-04  Decimal precision preserved (10.500000)
  TP-05  Date parsed to date object (not string)
  TP-06  Unparseable date (post-validation edge case) -> FAIL with row number
  TP-07  Unparseable decimal (post-validation edge case) -> FAIL with row number
  TP-08  Empty records list not returned on failure
"""

from datetime import date
from decimal import Decimal

import pytest

from app.ingestion.parsers.telemetry import TelemetryRecord, parse_telemetry_file


# -- Helpers ------------------------------------------------------------------

def _csv(header: str, *rows: str) -> str:
    return "\n".join([header] + list(rows))


HEADER = "tenant_id,region,gpu_pool_id,date,gpu_hours_consumed"
VALID_ROW_1 = "tenant-01,us-east-1,pool-a,2025-03-01,10.500000"
VALID_ROW_2 = "tenant-02,eu-west-1,pool-b,2025-03-02,25.750000"


# -- Success Path -------------------------------------------------------------

def test_tp01_valid_csv_passes():
    """TP-01: Valid CSV -> PASS with correct record count"""
    result = parse_telemetry_file(_csv(HEADER, VALID_ROW_1))
    assert result.result == "PASS"
    assert len(result.records) == 1
    assert result.error is None


def test_tp02_record_types_correct():
    """TP-02: Record fields have correct types"""
    result = parse_telemetry_file(_csv(HEADER, VALID_ROW_1))
    rec = result.records[0]
    assert isinstance(rec, TelemetryRecord)
    assert isinstance(rec.tenant_id, str)
    assert isinstance(rec.date, date)
    assert isinstance(rec.gpu_hours_consumed, Decimal)


def test_tp03_multiple_rows_in_order():
    """TP-03: Multiple rows -> all records returned in order"""
    result = parse_telemetry_file(_csv(HEADER, VALID_ROW_1, VALID_ROW_2))
    assert result.result == "PASS"
    assert len(result.records) == 2
    assert result.records[0].tenant_id == "tenant-01"
    assert result.records[1].tenant_id == "tenant-02"


def test_tp04_decimal_precision_preserved():
    """TP-04: Decimal precision preserved"""
    result = parse_telemetry_file(_csv(HEADER, VALID_ROW_1))
    assert result.records[0].gpu_hours_consumed == Decimal("10.500000")


def test_tp05_date_parsed_to_date_object():
    """TP-05: Date parsed to date object, not string"""
    result = parse_telemetry_file(_csv(HEADER, VALID_ROW_1))
    assert result.records[0].date == date(2025, 3, 1)


# -- Failure Path (post-validation edge cases) --------------------------------

def test_tp06_unparseable_date_fails():
    """TP-06: Unparseable date -> FAIL with row number"""
    result = parse_telemetry_file(_csv(HEADER, "tenant-01,us-east-1,pool-a,not-a-date,10.5"))
    assert result.result == "FAIL"
    assert "row 1" in result.error
    assert result.records == []


def test_tp07_unparseable_decimal_fails():
    """TP-07: Unparseable decimal -> FAIL with row number"""
    result = parse_telemetry_file(_csv(HEADER, "tenant-01,us-east-1,pool-a,2025-03-01,not-decimal"))
    assert result.result == "FAIL"
    assert "row 1" in result.error
    assert result.records == []


def test_tp08_no_records_on_failure():
    """TP-08: Failed parse returns empty records list"""
    result = parse_telemetry_file(_csv(HEADER, "tenant-01,us-east-1,pool-a,bad,10.5"))
    assert result.result == "FAIL"
    assert len(result.records) == 0
