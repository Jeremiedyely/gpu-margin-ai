"""
Customer Data Aggregator Tests — Step 6.5.

Tests: CDA-01 through CDA-14
Assertions: 24

Test data: Same 4-row grain as KDA tests:
  Type A tenant-A:  rev=500, cogs=250 → GM% = 50.00% → green
  Type A tenant-B:  rev=360, cogs=200 → GM% = 44.44% → green
  identity_broken:  tenant-BROKEN (unallocated)
  capacity_idle:    (unallocated)

Phase 6 hard gate: identity_broken tenant → Risk flag fires in Zone 2R.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, text

from app.ui.customer_data_aggregator import (
    aggregate_customers,
    read_identity_broken_set,
    CustomerAggregatorResult,
    CustomerRecord,
    _compute_gm_color,
)


# ── Helper: insert allocation_grain rows ────────────────────────────

_INSERT_GRAIN_SQL = text("""
    INSERT INTO dbo.allocation_grain (
        session_id, region, gpu_pool_id, date, billing_period,
        allocation_target, unallocated_type, failed_tenant_id,
        gpu_hours, cost_per_gpu_hour, contracted_rate,
        revenue, cogs, gross_margin
    ) VALUES (
        :sid, :region, :pool, :date, :bp,
        :target, :utype, :ftid,
        :hours, :cpgh, :rate,
        :rev, :cogs, :gm
    )
""")


def _insert_standard_grain(conn: Connection, sid: UUID) -> None:
    """Insert the standard 4-row test grain for one session."""
    rows = [
        {
            "sid": str(sid), "region": "us-east-1", "pool": "pool-A",
            "date": "2026-03-15", "bp": "2026-03",
            "target": "tenant-A", "utype": None, "ftid": None,
            "hours": Decimal("100.00"), "cpgh": Decimal("2.50"),
            "rate": Decimal("5.00"),
            "rev": Decimal("500.00"), "cogs": Decimal("250.00"),
            "gm": Decimal("250.00"),
        },
        {
            "sid": str(sid), "region": "us-east-1", "pool": "pool-A",
            "date": "2026-03-15", "bp": "2026-03",
            "target": "tenant-B", "utype": None, "ftid": None,
            "hours": Decimal("80.00"), "cpgh": Decimal("2.50"),
            "rate": Decimal("4.50"),
            "rev": Decimal("360.00"), "cogs": Decimal("200.00"),
            "gm": Decimal("160.00"),
        },
        {
            "sid": str(sid), "region": "us-east-1", "pool": "pool-A",
            "date": "2026-03-15", "bp": "2026-03",
            "target": "unallocated", "utype": "identity_broken",
            "ftid": "tenant-BROKEN",
            "hours": Decimal("50.00"), "cpgh": Decimal("2.50"),
            "rate": None,
            "rev": Decimal("0.00"), "cogs": Decimal("125.00"),
            "gm": Decimal("-125.00"),
        },
        {
            "sid": str(sid), "region": "us-east-1", "pool": "pool-A",
            "date": "2026-03-15", "bp": "2026-03",
            "target": "unallocated", "utype": "capacity_idle",
            "ftid": None,
            "hours": Decimal("70.00"), "cpgh": Decimal("2.50"),
            "rate": None,
            "rev": Decimal("0.00"), "cogs": Decimal("175.00"),
            "gm": Decimal("-175.00"),
        },
    ]
    for r in rows:
        conn.execute(_INSERT_GRAIN_SQL, r)


def _insert_negative_margin_tenant(conn: Connection, sid: UUID) -> None:
    """Insert a Type A tenant with negative margin (cogs > revenue)."""
    conn.execute(_INSERT_GRAIN_SQL, {
        "sid": str(sid), "region": "us-east-1", "pool": "pool-A",
        "date": "2026-03-15", "bp": "2026-03",
        "target": "tenant-LOSS", "utype": None, "ftid": None,
        "hours": Decimal("100.00"), "cpgh": Decimal("5.00"),
        "rate": Decimal("3.00"),
        "rev": Decimal("300.00"), "cogs": Decimal("500.00"),
        "gm": Decimal("-200.00"),
    })


# ═══════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════


def test_standard_aggregate(db_connection: Connection, test_session_id: UUID):
    """CDA-01: Standard 4-row grain → 2 customer records, correct GM%."""
    _insert_standard_grain(db_connection, test_session_id)
    result = aggregate_customers(db_connection, test_session_id)

    assert result.result == "SUCCESS"                               # CDA-01a
    assert len(result.payload) == 2                                 # CDA-01b
    # tenant-A: GM% = (500-250)/500 * 100 = 50.00%
    ta = next(r for r in result.payload if r.allocation_target == "tenant-A")
    assert ta.gm_pct == Decimal("50.00")                            # CDA-01c
    # tenant-B: GM% = (360-200)/360 * 100 = 44.44%
    tb = next(r for r in result.payload if r.allocation_target == "tenant-B")
    assert tb.gm_pct == Decimal("44.44")                            # CDA-01d


def test_identity_broken_set_populated(db_connection: Connection, test_session_id: UUID):
    """CDA-02: identity_broken_set contains 'tenant-BROKEN'."""
    _insert_standard_grain(db_connection, test_session_id)
    result = aggregate_customers(db_connection, test_session_id)

    assert result.result == "SUCCESS"
    assert "tenant-BROKEN" in result.identity_broken_set            # CDA-02


def test_identity_broken_cached_in_db(db_connection: Connection, test_session_id: UUID):
    """CDA-03: identity_broken_tenants table has tenant-BROKEN row."""
    _insert_standard_grain(db_connection, test_session_id)
    aggregate_customers(db_connection, test_session_id)

    row = db_connection.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM dbo.identity_broken_tenants
            WHERE session_id = :sid AND failed_tenant_id = 'tenant-BROKEN'
        """),
        {"sid": str(test_session_id)},
    ).fetchone()
    assert row.cnt == 1                                             # CDA-03


def test_read_identity_broken_set(db_connection: Connection, test_session_id: UUID):
    """CDA-04: read_identity_broken_set returns cached SET."""
    _insert_standard_grain(db_connection, test_session_id)
    aggregate_customers(db_connection, test_session_id)

    ib_set = read_identity_broken_set(db_connection, test_session_id)
    assert "tenant-BROKEN" in ib_set                                # CDA-04


def test_gm_color_green(db_connection: Connection, test_session_id: UUID):
    """CDA-05: GM% ≥ 38% → green."""
    _insert_standard_grain(db_connection, test_session_id)
    result = aggregate_customers(db_connection, test_session_id)

    ta = next(r for r in result.payload if r.allocation_target == "tenant-A")
    assert ta.gm_color == "green"                                   # CDA-05


def test_gm_color_tiers():
    """CDA-06: All 4 color tiers return correct values (unit test)."""
    assert _compute_gm_color(Decimal("-5.00")) == "red"             # CDA-06a
    assert _compute_gm_color(Decimal("15.00")) == "orange"          # CDA-06b
    assert _compute_gm_color(Decimal("35.00")) == "yellow"          # CDA-06c
    assert _compute_gm_color(Decimal("50.00")) == "green"           # CDA-06d


def test_gm_color_boundaries():
    """CDA-07: Boundary values at tier edges."""
    assert _compute_gm_color(Decimal("0.00")) == "orange"           # CDA-07a (0 is not negative)
    assert _compute_gm_color(Decimal("29.99")) == "orange"          # CDA-07b
    assert _compute_gm_color(Decimal("30.00")) == "yellow"          # CDA-07c
    assert _compute_gm_color(Decimal("37.99")) == "yellow"          # CDA-07d
    assert _compute_gm_color(Decimal("38.00")) == "green"           # CDA-07e


def test_negative_margin_risk_flag(db_connection: Connection, test_session_id: UUID):
    """CDA-08: Negative margin tenant → risk_flag = FLAG + gm_color = red."""
    _insert_standard_grain(db_connection, test_session_id)
    _insert_negative_margin_tenant(db_connection, test_session_id)
    result = aggregate_customers(db_connection, test_session_id)

    loss = next(r for r in result.payload if r.allocation_target == "tenant-LOSS")
    assert loss.risk_flag == "FLAG"                                 # CDA-08a
    assert loss.gm_color == "red"                                   # CDA-08b
    # GM% = (300-500)/300 * 100 = -66.67%
    assert loss.gm_pct < Decimal("0")                               # CDA-08c


def test_clear_tenant_risk_flag(db_connection: Connection, test_session_id: UUID):
    """CDA-09: Healthy tenant not in identity_broken SET → CLEAR."""
    _insert_standard_grain(db_connection, test_session_id)
    result = aggregate_customers(db_connection, test_session_id)

    ta = next(r for r in result.payload if r.allocation_target == "tenant-A")
    assert ta.risk_flag == "CLEAR"                                  # CDA-09


def test_no_type_a_records(db_connection: Connection, test_session_id: UUID):
    """CDA-10: Only unallocated rows → empty payload (not failure)."""
    conn = db_connection
    sid = test_session_id
    conn.execute(_INSERT_GRAIN_SQL, {
        "sid": str(sid), "region": "us-east-1", "pool": "pool-A",
        "date": "2026-03-15", "bp": "2026-03",
        "target": "unallocated", "utype": "capacity_idle", "ftid": None,
        "hours": Decimal("70.00"), "cpgh": Decimal("2.50"),
        "rate": None,
        "rev": Decimal("0.00"), "cogs": Decimal("175.00"),
        "gm": Decimal("-175.00"),
    })
    result = aggregate_customers(conn, sid)
    assert result.result == "SUCCESS"                               # CDA-10a
    assert len(result.payload) == 0                                 # CDA-10b


def test_sort_order_gm_descending(db_connection: Connection, test_session_id: UUID):
    """CDA-11: Payload sorted by GM% descending."""
    _insert_standard_grain(db_connection, test_session_id)
    result = aggregate_customers(db_connection, test_session_id)

    gm_values = [r.gm_pct for r in result.payload]
    assert gm_values == sorted(gm_values, reverse=True)            # CDA-11


def test_empty_grain(db_connection: Connection, test_session_id: UUID):
    """CDA-12: No allocation_grain rows → SUCCESS with empty payload + empty SET."""
    result = aggregate_customers(db_connection, test_session_id)
    assert result.result == "SUCCESS"                               # CDA-12a
    assert len(result.payload) == 0                                 # CDA-12b
    assert len(result.identity_broken_set) == 0                     # CDA-12c


def test_duplicate_cache_write_fails(db_connection: Connection, test_session_id: UUID):
    """CDA-13: Second aggregate_customers with identity_broken → FAIL (PK)."""
    _insert_standard_grain(db_connection, test_session_id)
    first = aggregate_customers(db_connection, test_session_id)
    assert first.result == "SUCCESS"

    second = aggregate_customers(db_connection, test_session_id)
    assert second.result == "FAIL"                                  # CDA-13


def test_read_empty_set(db_connection: Connection, test_session_id: UUID):
    """CDA-14: read_identity_broken_set with no cache → empty set."""
    ib_set = read_identity_broken_set(db_connection, test_session_id)
    assert len(ib_set) == 0                                         # CDA-14
