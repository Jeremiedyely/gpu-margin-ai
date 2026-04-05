"""
Tests for IAM Resolver — Component 4/10.

IAM-R-01  Matched tenant → Type A record
IAM-R-02  Type A has contracted_rate from IAM
IAM-R-03  Unmatched tenant → identity_broken record
IAM-R-04  identity_broken preserves tenant_id (failed_tenant_id source)
IAM-R-05  Mixed tenants → correct classification split
IAM-R-06  All fields pass through on Type A
IAM-R-07  All fields pass through on identity_broken
IAM-R-08  Empty input → SUCCESS with empty lists
IAM-R-09  Decimal precision preserved on contracted_rate
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import text

from app.allocation.billing_period_deriver import TelemetryEnrichedRecord
from app.allocation.iam_resolver import resolve_iam


def _enriched(tenant="T1", region="us-east", pool="pool-a",
              d=date(2026, 3, 15), bp="2026-03",
              hours=Decimal("10.000000")):
    return TelemetryEnrichedRecord(
        tenant_id=tenant, region=region, gpu_pool_id=pool,
        date=d, billing_period=bp, gpu_hours=hours,
    )


def _insert_iam(conn, sid, tenant, rate, billing_period="2026-03"):
    conn.execute(
        text("""
            INSERT INTO raw.iam
                (session_id, tenant_id, contracted_rate, billing_period)
            VALUES (:sid, :tenant, :rate, :bp)
        """),
        {"sid": str(sid), "tenant": tenant, "rate": rate, "bp": billing_period},
    )


# ── IAM-R-01: Matched tenant → Type A ──
def test_matched_tenant_is_type_a(db_connection, test_session_id):
    _insert_iam(db_connection, test_session_id, "T1", "5.500000")
    result = resolve_iam(db_connection, test_session_id, [_enriched(tenant="T1")])
    assert len(result.type_a) == 1
    assert len(result.identity_broken) == 0


# ── IAM-R-02: Type A has contracted_rate from IAM ──
def test_type_a_has_contracted_rate(db_connection, test_session_id):
    _insert_iam(db_connection, test_session_id, "T1", "5.500000")
    result = resolve_iam(db_connection, test_session_id, [_enriched(tenant="T1")])
    assert result.type_a[0].contracted_rate == Decimal("5.500000")


# ── IAM-R-03: Unmatched tenant → identity_broken ──
def test_unmatched_tenant_is_identity_broken(db_connection, test_session_id):
    result = resolve_iam(db_connection, test_session_id,
                         [_enriched(tenant="UNKNOWN")])
    assert len(result.identity_broken) == 1
    assert len(result.type_a) == 0


# ── IAM-R-04: identity_broken preserves tenant_id ──
def test_identity_broken_preserves_tenant_id(db_connection, test_session_id):
    result = resolve_iam(db_connection, test_session_id,
                         [_enriched(tenant="GHOST")])
    assert result.identity_broken[0].tenant_id == "GHOST"


# ── IAM-R-05: Mixed tenants → correct split ──
def test_mixed_classification(db_connection, test_session_id):
    _insert_iam(db_connection, test_session_id, "T1", "5.000000")
    recs = [_enriched(tenant="T1"), _enriched(tenant="T2")]
    result = resolve_iam(db_connection, test_session_id, recs)
    assert len(result.type_a) == 1
    assert len(result.identity_broken) == 1


# ── IAM-R-06: All fields pass through on Type A ──
def test_type_a_fields_pass_through(db_connection, test_session_id):
    _insert_iam(db_connection, test_session_id, "T1", "5.000000",
                billing_period="2026-01")
    rec = _enriched(tenant="T1", region="eu-west", pool="pool-b",
                    d=date(2026, 1, 10), bp="2026-01",
                    hours=Decimal("7.250000"))
    result = resolve_iam(db_connection, test_session_id, [rec])
    a = result.type_a[0]
    assert a.region == "eu-west"
    assert a.gpu_pool_id == "pool-b"
    assert a.date == date(2026, 1, 10)
    assert a.billing_period == "2026-01"
    assert a.gpu_hours == Decimal("7.250000")


# ── IAM-R-07: All fields pass through on identity_broken ──
def test_identity_broken_fields_pass_through(db_connection, test_session_id):
    rec = _enriched(tenant="GHOST", region="ap-south", pool="pool-c",
                    d=date(2026, 2, 20), bp="2026-02",
                    hours=Decimal("3.333333"))
    result = resolve_iam(db_connection, test_session_id, [rec])
    ib = result.identity_broken[0]
    assert ib.region == "ap-south"
    assert ib.gpu_pool_id == "pool-c"
    assert ib.date == date(2026, 2, 20)
    assert ib.billing_period == "2026-02"
    assert ib.gpu_hours == Decimal("3.333333")


# ── IAM-R-08: Empty input → SUCCESS with empty lists ──
def test_empty_input_returns_success(db_connection, test_session_id):
    result = resolve_iam(db_connection, test_session_id, [])
    assert result.result == "SUCCESS"
    assert result.type_a == []
    assert result.identity_broken == []


# ── IAM-R-09: Decimal precision preserved on contracted_rate ──
def test_contracted_rate_decimal_precision(db_connection, test_session_id):
    _insert_iam(db_connection, test_session_id, "T1", "12.345678")
    result = resolve_iam(db_connection, test_session_id, [_enriched(tenant="T1")])
    assert result.type_a[0].contracted_rate == Decimal("12.345678")
