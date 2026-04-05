"""
Tests for Type A Record Builder — Component 5/10.

TAB-01  Single Type A record → SUCCESS
TAB-02  allocation_target = tenant_id
TAB-03  unallocated_type = None
TAB-04  failed_tenant_id = None
TAB-05  cost_per_gpu_hour from cost rate lookup
TAB-06  contracted_rate passes through from IAM
TAB-07  Missing cost rate → FAIL
"""

from datetime import date
from decimal import Decimal

from app.allocation.iam_resolver import TypeARecord
from app.allocation.cost_rate_reader import CostRateRecord
from app.allocation.type_a_builder import build_type_a_records


def _type_a(tenant="T1", region="us-east", pool="pool-a",
            d=date(2026, 3, 15), bp="2026-03",
            hours=Decimal("10.000000"), rate=Decimal("5.500000")):
    return TypeARecord(
        tenant_id=tenant, region=region, gpu_pool_id=pool,
        date=d, billing_period=bp, gpu_hours=hours,
        contracted_rate=rate,
    )


def _cost(region="us-east", pool="pool-a", d=date(2026, 3, 15),
          reserved=Decimal("100.000000"), cost=Decimal("2.500000")):
    return CostRateRecord(
        region=region, gpu_pool_id=pool, date=d,
        reserved_gpu_hours=reserved, cost_per_gpu_hour=cost,
    )


# ── TAB-01: Single Type A record → SUCCESS ──
def test_single_record_success():
    result = build_type_a_records([_type_a()], [_cost()])
    assert result.result == "SUCCESS"
    assert len(result.records) == 1


# ── TAB-02: allocation_target = tenant_id ──
def test_allocation_target_is_tenant_id():
    result = build_type_a_records([_type_a(tenant="ACME")], [_cost()])
    assert result.records[0].allocation_target == "ACME"


# ── TAB-03: unallocated_type = None ──
def test_unallocated_type_is_none():
    result = build_type_a_records([_type_a()], [_cost()])
    assert result.records[0].unallocated_type is None


# ── TAB-04: failed_tenant_id = None ──
def test_failed_tenant_id_is_none():
    result = build_type_a_records([_type_a()], [_cost()])
    assert result.records[0].failed_tenant_id is None


# ── TAB-05: cost_per_gpu_hour from cost rate lookup ──
def test_cost_per_gpu_hour_from_cost_rate():
    result = build_type_a_records(
        [_type_a()], [_cost(cost=Decimal("7.770000"))]
    )
    assert result.records[0].cost_per_gpu_hour == Decimal("7.770000")


# ── TAB-06: contracted_rate passes through from IAM ──
def test_contracted_rate_passes_through():
    result = build_type_a_records(
        [_type_a(rate=Decimal("12.345678"))], [_cost()]
    )
    assert result.records[0].contracted_rate == Decimal("12.345678")


# ── TAB-07: Missing cost rate → FAIL ──
def test_missing_cost_rate_returns_fail():
    result = build_type_a_records(
        [_type_a(region="ap-south")], [_cost(region="us-east")]
    )
    assert result.result == "FAIL"
    assert "ap-south" in result.error
