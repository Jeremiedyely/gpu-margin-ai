"""
Region Data Aggregator Tests — Step 6.6.

Tests: RDA-01 through RDA-12
Assertions: 20

Test data: Standard 4-row grain in us-east-1:
  Type A tenant-A:  rev=500, cogs=250
  Type A tenant-B:  rev=360, cogs=200
  identity_broken:  cogs=125
  capacity_idle:    cogs=175

Per-region expected:
  Revenue = 860, COGS_A = 450, COGS_B = 300
  GM% = (860 - 450) / 860 × 100 = 47.67%
  Idle% = 300 / (450 + 300) × 100 = 40.00%
  Status = AT RISK (40% > 30%)
  identity_broken_count = 1, capacity_idle_count = 1
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, text

from app.ui.region_data_aggregator import (
    aggregate_regions,
    RegionAggregatorResult,
    RegionRecord,
)


# ── Helper ──────────────────────────────────────────────────────────

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
    """Insert the standard 4-row test grain (us-east-1)."""
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


def _insert_second_region(conn: Connection, sid: UUID) -> None:
    """Insert a second region (eu-west-1) with only Type A (no idle)."""
    conn.execute(_INSERT_GRAIN_SQL, {
        "sid": str(sid), "region": "eu-west-1", "pool": "pool-B",
        "date": "2026-03-15", "bp": "2026-03",
        "target": "tenant-C", "utype": None, "ftid": None,
        "hours": Decimal("200.00"), "cpgh": Decimal("3.00"),
        "rate": Decimal("6.00"),
        "rev": Decimal("1200.00"), "cogs": Decimal("600.00"),
        "gm": Decimal("600.00"),
    })


# ═══════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════


def test_standard_region_aggregate(db_connection: Connection, test_session_id: UUID):
    """RDA-01: Standard grain → correct region metrics."""
    _insert_standard_grain(db_connection, test_session_id)
    result = aggregate_regions(db_connection, test_session_id)

    assert result.result == "SUCCESS"                               # RDA-01a
    assert len(result.payload) == 1                                 # RDA-01b
    r = result.payload[0]
    assert r.region == "us-east-1"                                  # RDA-01c
    assert r.revenue == Decimal("860.00")                           # RDA-01d
    # GM% = (860 - 450) / 860 × 100 = 47.67%
    assert r.gm_pct == Decimal("47.67")                             # RDA-01e


def test_idle_pct(db_connection: Connection, test_session_id: UUID):
    """RDA-02: Idle% = COGS_B / (COGS_A + COGS_B) × 100 = 40.00%."""
    _insert_standard_grain(db_connection, test_session_id)
    result = aggregate_regions(db_connection, test_session_id)

    r = result.payload[0]
    assert r.idle_pct == Decimal("40.00")                           # RDA-02


def test_status_at_risk(db_connection: Connection, test_session_id: UUID):
    """RDA-03: Idle% > 30% → AT RISK."""
    _insert_standard_grain(db_connection, test_session_id)
    result = aggregate_regions(db_connection, test_session_id)

    assert result.payload[0].status == "AT RISK"                    # RDA-03


def test_status_holding(db_connection: Connection, test_session_id: UUID):
    """RDA-04: Region with no idle → Idle% = 0 → HOLDING."""
    _insert_second_region(db_connection, test_session_id)
    result = aggregate_regions(db_connection, test_session_id)

    r = result.payload[0]
    assert r.idle_pct == Decimal("0.00")                            # RDA-04a
    assert r.status == "HOLDING"                                    # RDA-04b


def test_subtype_pill_counts(db_connection: Connection, test_session_id: UUID):
    """RDA-05: Subtype pill counts correct."""
    _insert_standard_grain(db_connection, test_session_id)
    result = aggregate_regions(db_connection, test_session_id)

    r = result.payload[0]
    assert r.identity_broken_count == 1                             # RDA-05a
    assert r.capacity_idle_count == 1                               # RDA-05b


def test_multi_region(db_connection: Connection, test_session_id: UUID):
    """RDA-06: Two regions → two rows, sorted by GM% descending."""
    _insert_standard_grain(db_connection, test_session_id)
    _insert_second_region(db_connection, test_session_id)
    result = aggregate_regions(db_connection, test_session_id)

    assert len(result.payload) == 2                                 # RDA-06a
    # eu-west-1 GM% = (1200-600)/1200 = 50% > us-east-1 47.67%
    assert result.payload[0].region == "eu-west-1"                  # RDA-06b
    assert result.payload[1].region == "us-east-1"                  # RDA-06c


def test_empty_grain(db_connection: Connection, test_session_id: UUID):
    """RDA-07: No allocation_grain rows → SUCCESS with empty payload."""
    result = aggregate_regions(db_connection, test_session_id)
    assert result.result == "SUCCESS"                               # RDA-07a
    assert len(result.payload) == 0                                 # RDA-07b


def test_zero_revenue_gm_null(db_connection: Connection, test_session_id: UUID):
    """RDA-08: Region with zero revenue → GM% = NULL."""
    conn = db_connection
    sid = test_session_id
    # Insert only unallocated rows for a region
    conn.execute(_INSERT_GRAIN_SQL, {
        "sid": str(sid), "region": "ap-south-1", "pool": "pool-C",
        "date": "2026-03-15", "bp": "2026-03",
        "target": "unallocated", "utype": "capacity_idle", "ftid": None,
        "hours": Decimal("50.00"), "cpgh": Decimal("2.00"),
        "rate": None,
        "rev": Decimal("0.00"), "cogs": Decimal("100.00"),
        "gm": Decimal("-100.00"),
    })
    result = aggregate_regions(conn, sid)
    assert result.payload[0].gm_pct is None                         # RDA-08


def test_no_idle_pills_zero(db_connection: Connection, test_session_id: UUID):
    """RDA-09: Region with only Type A → both pill counts = 0."""
    _insert_second_region(db_connection, test_session_id)
    result = aggregate_regions(db_connection, test_session_id)

    r = result.payload[0]
    assert r.identity_broken_count == 0                             # RDA-09a
    assert r.capacity_idle_count == 0                               # RDA-09b


def test_holding_boundary(db_connection: Connection, test_session_id: UUID):
    """RDA-10: Idle% = exactly 30% → HOLDING (≤ 30%)."""
    conn = db_connection
    sid = test_session_id
    # Construct: COGS_A = 70, COGS_B = 30 → Idle% = 30%
    conn.execute(_INSERT_GRAIN_SQL, {
        "sid": str(sid), "region": "us-west-2", "pool": "pool-D",
        "date": "2026-03-15", "bp": "2026-03",
        "target": "tenant-X", "utype": None, "ftid": None,
        "hours": Decimal("70.00"), "cpgh": Decimal("1.00"),
        "rate": Decimal("2.00"),
        "rev": Decimal("140.00"), "cogs": Decimal("70.00"),
        "gm": Decimal("70.00"),
    })
    conn.execute(_INSERT_GRAIN_SQL, {
        "sid": str(sid), "region": "us-west-2", "pool": "pool-D",
        "date": "2026-03-15", "bp": "2026-03",
        "target": "unallocated", "utype": "capacity_idle", "ftid": None,
        "hours": Decimal("30.00"), "cpgh": Decimal("1.00"),
        "rate": None,
        "rev": Decimal("0.00"), "cogs": Decimal("30.00"),
        "gm": Decimal("-30.00"),
    })
    result = aggregate_regions(conn, sid)
    r = result.payload[0]
    assert r.idle_pct == Decimal("30.00")                           # RDA-10a
    assert r.status == "HOLDING"                                    # RDA-10b


def test_session_isolation(db_connection: Connection, test_session_id: UUID):
    """RDA-11: Data from another session not included."""
    _insert_standard_grain(db_connection, test_session_id)
    # Create second session
    other_sid = uuid4()
    db_connection.execute(
        text("""
            INSERT INTO raw.ingestion_log (session_id, source_files, status)
            VALUES (:sid, :sf, 'COMMITTED')
        """),
        {"sid": str(other_sid), "sf": '["test.csv"]'},
    )
    db_connection.execute(_INSERT_GRAIN_SQL, {
        "sid": str(other_sid), "region": "eu-central-1", "pool": "pool-Z",
        "date": "2026-03-15", "bp": "2026-03",
        "target": "tenant-Z", "utype": None, "ftid": None,
        "hours": Decimal("999.00"), "cpgh": Decimal("9.00"),
        "rate": Decimal("9.00"),
        "rev": Decimal("8991.00"), "cogs": Decimal("8991.00"),
        "gm": Decimal("0.00"),
    })
    result = aggregate_regions(db_connection, test_session_id)
    regions = {r.region for r in result.payload}
    assert "eu-central-1" not in regions                            # RDA-11


def test_sort_null_gm_last(db_connection: Connection, test_session_id: UUID):
    """RDA-12: NULL GM% sorted last."""
    conn = db_connection
    sid = test_session_id
    _insert_standard_grain(conn, sid)
    # Add region with zero revenue (NULL GM%)
    conn.execute(_INSERT_GRAIN_SQL, {
        "sid": str(sid), "region": "ap-south-1", "pool": "pool-C",
        "date": "2026-03-15", "bp": "2026-03",
        "target": "unallocated", "utype": "capacity_idle", "ftid": None,
        "hours": Decimal("50.00"), "cpgh": Decimal("2.00"),
        "rate": None,
        "rev": Decimal("0.00"), "cogs": Decimal("100.00"),
        "gm": Decimal("-100.00"),
    })
    result = aggregate_regions(conn, sid)
    assert len(result.payload) == 2
    assert result.payload[-1].gm_pct is None                        # RDA-12
