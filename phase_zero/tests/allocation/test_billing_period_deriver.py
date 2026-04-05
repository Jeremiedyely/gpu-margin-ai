"""
Tests for Billing Period Deriver — Component 2/10.

BPD-01  Valid records → SUCCESS
BPD-02  billing_period = YYYY-MM from date
BPD-03  All fields pass through unchanged
BPD-04  Multiple records enriched in order
BPD-05  Empty list → SUCCESS with empty records
BPD-06  Imports derive_billing_period from shared module (Contract 1)
BPD-07  Decimal precision preserved through enrichment
"""

from datetime import date
from decimal import Decimal

from app.allocation.telemetry_aggregator import TelemetryAggregatedRecord
from app.allocation.billing_period_deriver import derive_billing_periods
from app.shared.billing_period import derive_billing_period


def _record(tenant="T1", region="us-east", pool="pool-a",
            d=date(2026, 3, 15), hours=Decimal("10.500000")):
    return TelemetryAggregatedRecord(
        tenant_id=tenant, region=region, gpu_pool_id=pool,
        date=d, gpu_hours=hours,
    )


# ── BPD-01: Valid records → SUCCESS ──
def test_valid_records_return_success():
    result = derive_billing_periods([_record()])
    assert result.result == "SUCCESS"


# ── BPD-02: billing_period = YYYY-MM from date ──
def test_billing_period_derived_correctly():
    result = derive_billing_periods([_record(d=date(2026, 3, 15))])
    assert result.records[0].billing_period == "2026-03"


# ── BPD-03: All fields pass through unchanged ──
def test_fields_pass_through():
    rec = _record(tenant="T1", region="eu-west", pool="pool-b",
                  d=date(2026, 1, 5), hours=Decimal("7.250000"))
    result = derive_billing_periods([rec])
    enriched = result.records[0]
    assert enriched.tenant_id == "T1"
    assert enriched.region == "eu-west"
    assert enriched.gpu_pool_id == "pool-b"
    assert enriched.date == date(2026, 1, 5)
    assert enriched.gpu_hours == Decimal("7.250000")


# ── BPD-04: Multiple records enriched in order ──
def test_multiple_records_in_order():
    recs = [
        _record(tenant="T1", d=date(2026, 3, 15)),
        _record(tenant="T2", d=date(2026, 4, 1)),
    ]
    result = derive_billing_periods(recs)
    assert len(result.records) == 2
    assert result.records[0].billing_period == "2026-03"
    assert result.records[1].billing_period == "2026-04"


# ── BPD-05: Empty list → SUCCESS with empty records ──
def test_empty_list_returns_success():
    result = derive_billing_periods([])
    assert result.result == "SUCCESS"
    assert result.records == []


# ── BPD-06: Shared module import (Contract 1) ──
def test_shared_module_derivation_matches():
    d = date(2026, 12, 25)
    assert derive_billing_period(d) == "2026-12"


# ── BPD-07: Decimal precision preserved ──
def test_decimal_precision_preserved():
    rec = _record(hours=Decimal("1.123456"))
    result = derive_billing_periods([rec])
    assert result.records[0].gpu_hours == Decimal("1.123456")
