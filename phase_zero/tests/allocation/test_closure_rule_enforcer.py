"""
Tests for Closure Rule Enforcer — Component 7/10.

CRE-01  Pool partially consumed → capacity_idle with idle = reserved − consumed
CRE-02  allocation_target = 'unallocated'
CRE-03  unallocated_type = 'capacity_idle'
CRE-04  failed_tenant_id = None
CRE-05  contracted_rate = None
CRE-06  revenue = 0
CRE-07  billing_period derived from date via shared module
CRE-08  Pool fully consumed (idle = 0) → no capacity_idle record
CRE-09  Consumed exceeds reserved (idle < 0) → FAIL with source label
CRE-10  FAIL error contains region, pool, date, consumed, reserved
CRE-11  Multiple pools → one idle record per pool with idle > 0
CRE-12  Empty type_a and identity_broken → all reserved becomes idle
CRE-13  Mixed type_a + identity_broken consumed against same pool
"""

from datetime import date
from decimal import Decimal

from app.allocation.type_a_builder import TypeAGrainRecord
from app.allocation.identity_broken_builder import IdentityBrokenGrainRecord
from app.allocation.cost_rate_reader import CostRateRecord
from app.allocation.closure_rule_enforcer import enforce_closure_rule


def _type_a(region="us-east", pool="pool-a", d=date(2026, 3, 15),
            bp="2026-03", target="T1", hours=Decimal("40.000000"),
            cph=Decimal("2.500000"), rate=Decimal("5.000000")):
    return TypeAGrainRecord(
        region=region, gpu_pool_id=pool, date=d,
        billing_period=bp, allocation_target=target,
        unallocated_type=None, failed_tenant_id=None,
        gpu_hours=hours, cost_per_gpu_hour=cph,
        contracted_rate=rate,
    )


def _ib(region="us-east", pool="pool-a", d=date(2026, 3, 15),
        bp="2026-03", hours=Decimal("10.000000"),
        cph=Decimal("2.500000")):
    return IdentityBrokenGrainRecord(
        region=region, gpu_pool_id=pool, date=d,
        billing_period=bp, allocation_target="unallocated",
        unallocated_type="identity_broken", failed_tenant_id="GHOST",
        gpu_hours=hours, cost_per_gpu_hour=cph,
        contracted_rate=None, revenue=Decimal("0"),
    )


def _cost(region="us-east", pool="pool-a", d=date(2026, 3, 15),
          reserved=Decimal("100.000000"), cph=Decimal("2.500000")):
    return CostRateRecord(
        region=region, gpu_pool_id=pool, date=d,
        reserved_gpu_hours=reserved, cost_per_gpu_hour=cph,
    )


# ── CRE-01: Pool partially consumed → idle = reserved − consumed ──
def test_partial_consumption_creates_idle():
    result = enforce_closure_rule(
        [_type_a(hours=Decimal("60.000000"))], [], [_cost()]
    )
    assert result.result == "SUCCESS"
    assert len(result.capacity_idle) == 1
    assert result.capacity_idle[0].gpu_hours == Decimal("40.000000")


# ── CRE-02: allocation_target = 'unallocated' ──
def test_allocation_target_is_unallocated():
    result = enforce_closure_rule([_type_a()], [], [_cost()])
    assert result.capacity_idle[0].allocation_target == "unallocated"


# ── CRE-03: unallocated_type = 'capacity_idle' ──
def test_unallocated_type_is_capacity_idle():
    result = enforce_closure_rule([_type_a()], [], [_cost()])
    assert result.capacity_idle[0].unallocated_type == "capacity_idle"


# ── CRE-04: failed_tenant_id = None ──
def test_failed_tenant_id_is_none():
    result = enforce_closure_rule([_type_a()], [], [_cost()])
    assert result.capacity_idle[0].failed_tenant_id is None


# ── CRE-05: contracted_rate = None ──
def test_contracted_rate_is_none():
    result = enforce_closure_rule([_type_a()], [], [_cost()])
    assert result.capacity_idle[0].contracted_rate is None


# ── CRE-06: revenue = 0 ──
def test_revenue_is_zero():
    result = enforce_closure_rule([_type_a()], [], [_cost()])
    assert result.capacity_idle[0].revenue == Decimal("0")


# ── CRE-07: billing_period derived from date ──
def test_billing_period_derived_from_date():
    result = enforce_closure_rule(
        [_type_a(d=date(2026, 11, 5), bp="2026-11")],
        [],
        [_cost(d=date(2026, 11, 5))],
    )
    assert result.capacity_idle[0].billing_period == "2026-11"


# ── CRE-08: Pool fully consumed → no capacity_idle ──
def test_fully_consumed_no_idle():
    result = enforce_closure_rule(
        [_type_a(hours=Decimal("100.000000"))], [], [_cost()]
    )
    assert result.result == "SUCCESS"
    assert len(result.capacity_idle) == 0


# ── CRE-09: Consumed exceeds reserved → FAIL ──
def test_consumed_exceeds_reserved_fails():
    result = enforce_closure_rule(
        [_type_a(hours=Decimal("110.000000"))], [], [_cost()]
    )
    assert result.result == "FAIL"


# ── CRE-10: FAIL error contains source label + details ──
def test_fail_error_contains_details():
    result = enforce_closure_rule(
        [_type_a(hours=Decimal("110.000000"))], [], [_cost()]
    )
    assert "Closure Rule Enforcer" in result.error
    assert "us-east" in result.error
    assert "pool-a" in result.error
    assert "110" in result.error
    assert "100" in result.error


# ── CRE-11: Multiple pools → one idle record per pool with idle > 0 ──
def test_multiple_pools_each_get_idle():
    costs = [
        _cost(pool="pool-a", reserved=Decimal("100.000000")),
        _cost(pool="pool-b", reserved=Decimal("50.000000")),
    ]
    type_a = [
        _type_a(pool="pool-a", hours=Decimal("80.000000")),
        _type_a(pool="pool-b", hours=Decimal("50.000000")),
    ]
    result = enforce_closure_rule(type_a, [], costs)
    assert result.result == "SUCCESS"
    # pool-a has 20 idle, pool-b fully consumed
    assert len(result.capacity_idle) == 1
    assert result.capacity_idle[0].gpu_pool_id == "pool-a"
    assert result.capacity_idle[0].gpu_hours == Decimal("20.000000")


# ── CRE-12: Empty type_a and identity_broken → all reserved becomes idle ──
def test_empty_inputs_all_reserved_becomes_idle():
    result = enforce_closure_rule([], [], [_cost(reserved=Decimal("75.000000"))])
    assert result.result == "SUCCESS"
    assert len(result.capacity_idle) == 1
    assert result.capacity_idle[0].gpu_hours == Decimal("75.000000")


# ── CRE-13: Mixed type_a + identity_broken consumed against same pool ──
def test_mixed_type_a_and_identity_broken():
    result = enforce_closure_rule(
        [_type_a(hours=Decimal("60.000000"))],
        [_ib(hours=Decimal("25.000000"))],
        [_cost(reserved=Decimal("100.000000"))],
    )
    assert result.result == "SUCCESS"
    assert len(result.capacity_idle) == 1
    assert result.capacity_idle[0].gpu_hours == Decimal("15.000000")
