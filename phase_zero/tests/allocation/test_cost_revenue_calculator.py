"""
Tests for Cost & Revenue Calculator — Component 8/10.

CALC-01  Type A: revenue = gpu_hours × contracted_rate
CALC-02  Type A: cogs = gpu_hours × cost_per_gpu_hour
CALC-03  Type A: gross_margin = revenue − cogs
CALC-04  Type B identity_broken: revenue = 0
CALC-05  Type B identity_broken: cogs = gpu_hours × cost_per_gpu_hour
CALC-06  Type B identity_broken: gross_margin = −cogs (always negative)
CALC-07  Type B capacity_idle: revenue = 0
CALC-08  Type B capacity_idle: cogs = gpu_hours × cost_per_gpu_hour
CALC-09  Type B capacity_idle: gross_margin = −cogs (always negative)
CALC-10  failed_tenant_id pass-through — Type A = None preserved
CALC-11  failed_tenant_id pass-through — identity_broken = tenant_id preserved
CALC-12  failed_tenant_id pass-through — capacity_idle = None preserved
CALC-13  Type A zero gpu_hours → FAIL
CALC-14  Type A zero contracted_rate → FAIL
CALC-15  Type B zero gpu_hours → FAIL
CALC-16  Mixed inputs — all three record types computed in one call
"""

from datetime import date
from decimal import Decimal

from app.allocation.type_a_builder import TypeAGrainRecord
from app.allocation.identity_broken_builder import IdentityBrokenGrainRecord
from app.allocation.closure_rule_enforcer import CapacityIdleRecord
from app.allocation.cost_revenue_calculator import calculate_cost_revenue


def _type_a(hours=Decimal("10.000000"), cph=Decimal("2.000000"),
            rate=Decimal("5.000000"), target="T1"):
    return TypeAGrainRecord(
        region="us-east", gpu_pool_id="pool-a", date=date(2026, 3, 15),
        billing_period="2026-03", allocation_target=target,
        unallocated_type=None, failed_tenant_id=None,
        gpu_hours=hours, cost_per_gpu_hour=cph, contracted_rate=rate,
    )


def _ib(hours=Decimal("10.000000"), cph=Decimal("2.000000"),
        tenant="GHOST"):
    return IdentityBrokenGrainRecord(
        region="us-east", gpu_pool_id="pool-a", date=date(2026, 3, 15),
        billing_period="2026-03", allocation_target="unallocated",
        unallocated_type="identity_broken", failed_tenant_id=tenant,
        gpu_hours=hours, cost_per_gpu_hour=cph,
        contracted_rate=None, revenue=Decimal("0"),
    )


def _idle(hours=Decimal("10.000000"), cph=Decimal("2.000000")):
    return CapacityIdleRecord(
        region="us-east", gpu_pool_id="pool-a", date=date(2026, 3, 15),
        billing_period="2026-03", allocation_target="unallocated",
        unallocated_type="capacity_idle", failed_tenant_id=None,
        gpu_hours=hours, cost_per_gpu_hour=cph,
        contracted_rate=None, revenue=Decimal("0"),
    )


# ── CALC-01: Type A revenue = gpu_hours × contracted_rate ──
def test_type_a_revenue():
    result = calculate_cost_revenue([_type_a()], [], [])
    assert result.records[0].revenue == Decimal("50.000000")


# ── CALC-02: Type A cogs = gpu_hours × cost_per_gpu_hour ──
def test_type_a_cogs():
    result = calculate_cost_revenue([_type_a()], [], [])
    assert result.records[0].cogs == Decimal("20.000000")


# ── CALC-03: Type A gross_margin = revenue − cogs ──
def test_type_a_gross_margin():
    result = calculate_cost_revenue([_type_a()], [], [])
    assert result.records[0].gross_margin == Decimal("30.000000")


# ── CALC-04: Type B identity_broken revenue = 0 ──
def test_identity_broken_revenue():
    result = calculate_cost_revenue([], [_ib()], [])
    assert result.records[0].revenue == Decimal("0")


# ── CALC-05: Type B identity_broken cogs = gpu_hours × cost_per_gpu_hour ──
def test_identity_broken_cogs():
    result = calculate_cost_revenue([], [_ib()], [])
    assert result.records[0].cogs == Decimal("20.000000")


# ── CALC-06: Type B identity_broken gross_margin = −cogs (negative) ──
def test_identity_broken_gross_margin_negative():
    result = calculate_cost_revenue([], [_ib()], [])
    assert result.records[0].gross_margin == Decimal("-20.000000")
    assert result.records[0].gross_margin < 0


# ── CALC-07: Type B capacity_idle revenue = 0 ──
def test_capacity_idle_revenue():
    result = calculate_cost_revenue([], [], [_idle()])
    assert result.records[0].revenue == Decimal("0")


# ── CALC-08: Type B capacity_idle cogs = gpu_hours × cost_per_gpu_hour ──
def test_capacity_idle_cogs():
    result = calculate_cost_revenue([], [], [_idle()])
    assert result.records[0].cogs == Decimal("20.000000")


# ── CALC-09: Type B capacity_idle gross_margin = −cogs (negative) ──
def test_capacity_idle_gross_margin_negative():
    result = calculate_cost_revenue([], [], [_idle()])
    assert result.records[0].gross_margin == Decimal("-20.000000")
    assert result.records[0].gross_margin < 0


# ── CALC-10: failed_tenant_id pass-through — Type A = None ──
def test_type_a_failed_tenant_id_passthrough():
    result = calculate_cost_revenue([_type_a()], [], [])
    assert result.records[0].failed_tenant_id is None


# ── CALC-11: failed_tenant_id pass-through — identity_broken = tenant_id ──
def test_identity_broken_failed_tenant_id_passthrough():
    result = calculate_cost_revenue([], [_ib(tenant="PHANTOM")], [])
    assert result.records[0].failed_tenant_id == "PHANTOM"


# ── CALC-12: failed_tenant_id pass-through — capacity_idle = None ──
def test_capacity_idle_failed_tenant_id_passthrough():
    result = calculate_cost_revenue([], [], [_idle()])
    assert result.records[0].failed_tenant_id is None


# ── CALC-13: Type A zero gpu_hours → FAIL ──
def test_type_a_zero_gpu_hours_fails():
    result = calculate_cost_revenue(
        [_type_a(hours=Decimal("0"))], [], []
    )
    assert result.result == "FAIL"
    assert "gpu_hours" in result.error


# ── CALC-14: Type A zero contracted_rate → FAIL ──
def test_type_a_zero_contracted_rate_fails():
    result = calculate_cost_revenue(
        [_type_a(rate=Decimal("0"))], [], []
    )
    assert result.result == "FAIL"
    assert "contracted_rate" in result.error


# ── CALC-15: Type B zero gpu_hours → FAIL ──
def test_type_b_zero_gpu_hours_fails():
    result = calculate_cost_revenue(
        [], [_ib(hours=Decimal("0"))], []
    )
    assert result.result == "FAIL"
    assert "gpu_hours" in result.error


# ── CALC-16: Mixed inputs — all three types computed ──
def test_mixed_inputs_all_computed():
    result = calculate_cost_revenue(
        [_type_a()], [_ib()], [_idle()]
    )
    assert result.result == "SUCCESS"
    assert len(result.records) == 3
    # Type A: positive margin
    assert result.records[0].gross_margin > 0
    # identity_broken: negative margin
    assert result.records[1].gross_margin < 0
    # capacity_idle: negative margin
    assert result.records[2].gross_margin < 0
