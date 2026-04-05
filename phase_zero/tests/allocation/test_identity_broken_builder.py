"""
Tests for Identity Broken Record Builder — Component 6/10.

IBB-01  Single identity_broken record → SUCCESS
IBB-02  allocation_target = 'unallocated'
IBB-03  unallocated_type = 'identity_broken'
IBB-04  failed_tenant_id = tenant_id from IAM Resolver
IBB-05  contracted_rate = None
IBB-06  revenue = 0
IBB-07  cost_per_gpu_hour from cost rate lookup
IBB-08  Missing cost rate → FAIL
IBB-09  Empty input → SUCCESS with empty list
"""

from datetime import date
from decimal import Decimal

from app.allocation.iam_resolver import IdentityBrokenRecord
from app.allocation.cost_rate_reader import CostRateRecord
from app.allocation.identity_broken_builder import build_identity_broken_records


def _ib(tenant="GHOST", region="us-east", pool="pool-a",
        d=date(2026, 3, 15), bp="2026-03",
        hours=Decimal("10.000000")):
    return IdentityBrokenRecord(
        tenant_id=tenant, region=region, gpu_pool_id=pool,
        date=d, billing_period=bp, gpu_hours=hours,
    )


def _cost(region="us-east", pool="pool-a", d=date(2026, 3, 15),
          reserved=Decimal("100.000000"), cost=Decimal("2.500000")):
    return CostRateRecord(
        region=region, gpu_pool_id=pool, date=d,
        reserved_gpu_hours=reserved, cost_per_gpu_hour=cost,
    )


# ── IBB-01: Single identity_broken record → SUCCESS ──
def test_single_record_success():
    result = build_identity_broken_records([_ib()], [_cost()])
    assert result.result == "SUCCESS"
    assert len(result.records) == 1


# ── IBB-02: allocation_target = 'unallocated' ──
def test_allocation_target_is_unallocated():
    result = build_identity_broken_records([_ib()], [_cost()])
    assert result.records[0].allocation_target == "unallocated"


# ── IBB-03: unallocated_type = 'identity_broken' ──
def test_unallocated_type_is_identity_broken():
    result = build_identity_broken_records([_ib()], [_cost()])
    assert result.records[0].unallocated_type == "identity_broken"


# ── IBB-04: failed_tenant_id = tenant_id from IAM Resolver ──
def test_failed_tenant_id_is_tenant_id():
    result = build_identity_broken_records([_ib(tenant="PHANTOM")], [_cost()])
    assert result.records[0].failed_tenant_id == "PHANTOM"


# ── IBB-05: contracted_rate = None ──
def test_contracted_rate_is_none():
    result = build_identity_broken_records([_ib()], [_cost()])
    assert result.records[0].contracted_rate is None


# ── IBB-06: revenue = 0 ──
def test_revenue_is_zero():
    result = build_identity_broken_records([_ib()], [_cost()])
    assert result.records[0].revenue == Decimal("0")


# ── IBB-07: cost_per_gpu_hour from cost rate lookup ──
def test_cost_per_gpu_hour_from_cost_rate():
    result = build_identity_broken_records(
        [_ib()], [_cost(cost=Decimal("9.990000"))]
    )
    assert result.records[0].cost_per_gpu_hour == Decimal("9.990000")


# ── IBB-08: Missing cost rate → FAIL ──
def test_missing_cost_rate_returns_fail():
    result = build_identity_broken_records(
        [_ib(region="ap-south")], [_cost(region="us-east")]
    )
    assert result.result == "FAIL"
    assert "ap-south" in result.error


# ── IBB-09: Empty input → SUCCESS with empty list ──
def test_empty_input_returns_success():
    result = build_identity_broken_records([], [_cost()])
    assert result.result == "SUCCESS"
    assert result.records == []
