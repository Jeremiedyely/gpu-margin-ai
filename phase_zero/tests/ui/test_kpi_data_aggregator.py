"""
KPI Data Aggregator Tests — Step 6.4.

Tests: KDA-01 through KDA-12
Assertions: 18

Test data setup:
  2 Type A rows (tenant-A, tenant-B) + 1 identity_broken + 1 capacity_idle
  Same grain as P1 #32: us-east-1 / pool-A / 2026-03-15

  Type A tenant-A:  gpu_hours=100, cost=2.50, rate=5.00
    → revenue=500, cogs=250
  Type A tenant-B:  gpu_hours=80, cost=2.50, rate=4.50
    → revenue=360, cogs=200
  identity_broken:  gpu_hours=50, cost=2.50
    → cogs=125, revenue=0
  capacity_idle:    gpu_hours=70, cost=2.50
    → cogs=175, revenue=0

Expected KPIs:
  GPU Revenue        = 500 + 360 = 860.00
  GPU COGS           = 250 + 200 = 450.00
  Idle GPU Cost      = 125 + 175 = 300.00
  Total Cost Base    = 450 + 300 = 750.00
  Idle GPU Cost %    = 300 / 750 × 100 = 40.00
  Cost Allocation    = 450 / 750 × 100 = 60.00
  Complement check:  40.00 + 60.00 = 100.00 ✓
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, text

from app.ui.kpi_data_aggregator import (
    aggregate_kpis,
    read_kpi_cache,
    KPIAggregatorResult,
    KPIPayload,
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
        # Type A — tenant-A
        {
            "sid": str(sid), "region": "us-east-1", "pool": "pool-A",
            "date": "2026-03-15", "bp": "2026-03",
            "target": "tenant-A", "utype": None, "ftid": None,
            "hours": Decimal("100.00"), "cpgh": Decimal("2.50"),
            "rate": Decimal("5.00"),
            "rev": Decimal("500.00"), "cogs": Decimal("250.00"),
            "gm": Decimal("250.00"),
        },
        # Type A — tenant-B
        {
            "sid": str(sid), "region": "us-east-1", "pool": "pool-A",
            "date": "2026-03-15", "bp": "2026-03",
            "target": "tenant-B", "utype": None, "ftid": None,
            "hours": Decimal("80.00"), "cpgh": Decimal("2.50"),
            "rate": Decimal("4.50"),
            "rev": Decimal("360.00"), "cogs": Decimal("200.00"),
            "gm": Decimal("160.00"),
        },
        # identity_broken — tenant-BROKEN
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
        # capacity_idle
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


# ═══════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════


def test_aggregate_kpis_success(db_connection: Connection, test_session_id: UUID):
    """KDA-01: Standard 4-row grain → correct KPI values."""
    _insert_standard_grain(db_connection, test_session_id)
    result = aggregate_kpis(db_connection, test_session_id)

    assert result.result == "SUCCESS"                               # KDA-01a
    assert result.payload is not None                               # KDA-01b
    p = result.payload
    assert p.gpu_revenue == Decimal("860.00")                       # KDA-01c
    assert p.gpu_cogs == Decimal("450.00")                          # KDA-01d
    assert p.idle_gpu_cost == Decimal("300.00")                     # KDA-01e
    assert p.idle_gpu_cost_pct == Decimal("40.00")                  # KDA-01f
    assert p.cost_allocation_rate == Decimal("60.00")               # KDA-01g


def test_complement_integrity(db_connection: Connection, test_session_id: UUID):
    """KDA-02: Idle GPU Cost % + Cost Allocation Rate = 100.00."""
    _insert_standard_grain(db_connection, test_session_id)
    result = aggregate_kpis(db_connection, test_session_id)

    assert result.result == "SUCCESS"
    p = result.payload
    assert p.idle_gpu_cost_pct + p.cost_allocation_rate == Decimal("100.00")  # KDA-02


def test_cache_written(db_connection: Connection, test_session_id: UUID):
    """KDA-03: After aggregate_kpis, dbo.kpi_cache has a row."""
    _insert_standard_grain(db_connection, test_session_id)
    aggregate_kpis(db_connection, test_session_id)

    row = db_connection.execute(
        text("SELECT COUNT(*) AS cnt FROM dbo.kpi_cache WHERE session_id = :sid"),
        {"sid": str(test_session_id)},
    ).fetchone()
    assert row.cnt == 1                                             # KDA-03


def test_read_kpi_cache_after_aggregate(db_connection: Connection, test_session_id: UUID):
    """KDA-04: read_kpi_cache returns the same values aggregate_kpis wrote."""
    _insert_standard_grain(db_connection, test_session_id)
    agg = aggregate_kpis(db_connection, test_session_id)
    read = read_kpi_cache(db_connection, test_session_id)

    assert read.result == "SUCCESS"                                 # KDA-04a
    assert read.payload == agg.payload                              # KDA-04b


def test_read_kpi_cache_miss(db_connection: Connection, test_session_id: UUID):
    """KDA-05: read_kpi_cache with no cache entry → FAIL."""
    result = read_kpi_cache(db_connection, test_session_id)
    assert result.result == "FAIL"                                  # KDA-05


def test_empty_grain_zero_cost_base(db_connection: Connection, test_session_id: UUID):
    """KDA-06: No allocation_grain rows → FAIL (zero cost base)."""
    # No grain rows inserted — COALESCE returns 0 for all, total_cost = 0
    result = aggregate_kpis(db_connection, test_session_id)
    assert result.result == "FAIL"                                  # KDA-06


def test_type_a_only_no_idle(db_connection: Connection, test_session_id: UUID):
    """KDA-07: Only Type A rows → idle_gpu_cost = 0, cost_allocation_rate = 100."""
    conn = db_connection
    sid = test_session_id
    # Insert single Type A row
    conn.execute(_INSERT_GRAIN_SQL, {
        "sid": str(sid), "region": "us-east-1", "pool": "pool-A",
        "date": "2026-03-15", "bp": "2026-03",
        "target": "tenant-A", "utype": None, "ftid": None,
        "hours": Decimal("100.00"), "cpgh": Decimal("2.50"),
        "rate": Decimal("5.00"),
        "rev": Decimal("500.00"), "cogs": Decimal("250.00"),
        "gm": Decimal("250.00"),
    })
    result = aggregate_kpis(conn, sid)
    assert result.result == "SUCCESS"
    assert result.payload.idle_gpu_cost == Decimal("0")             # KDA-07a
    assert result.payload.cost_allocation_rate == Decimal("100.00") # KDA-07b
    assert result.payload.idle_gpu_cost_pct == Decimal("0.00")      # KDA-07c


def test_idle_only_no_type_a(db_connection: Connection, test_session_id: UUID):
    """KDA-08: Only unallocated rows → gpu_revenue = 0, gpu_cogs = 0."""
    conn = db_connection
    sid = test_session_id
    # Insert single capacity_idle row
    conn.execute(_INSERT_GRAIN_SQL, {
        "sid": str(sid), "region": "us-east-1", "pool": "pool-A",
        "date": "2026-03-15", "bp": "2026-03",
        "target": "unallocated", "utype": "capacity_idle", "ftid": None,
        "hours": Decimal("70.00"), "cpgh": Decimal("2.50"),
        "rate": None,
        "rev": Decimal("0.00"), "cogs": Decimal("175.00"),
        "gm": Decimal("-175.00"),
    })
    result = aggregate_kpis(conn, sid)
    assert result.result == "SUCCESS"
    assert result.payload.gpu_revenue == Decimal("0")               # KDA-08a
    assert result.payload.gpu_cogs == Decimal("0")                  # KDA-08b
    assert result.payload.idle_gpu_cost_pct == Decimal("100.00")    # KDA-08c


def test_duplicate_cache_write_fails(db_connection: Connection, test_session_id: UUID):
    """KDA-09: Second aggregate_kpis for same session → FAIL (PK violation)."""
    _insert_standard_grain(db_connection, test_session_id)
    first = aggregate_kpis(db_connection, test_session_id)
    assert first.result == "SUCCESS"

    second = aggregate_kpis(db_connection, test_session_id)
    assert second.result == "FAIL"                                  # KDA-09


def test_session_id_guard(db_connection: Connection, test_session_id: UUID):
    """KDA-10: aggregate_kpis with wrong session_id → FAIL (no data)."""
    _insert_standard_grain(db_connection, test_session_id)
    wrong_sid = uuid4()
    # Insert ingestion_log for wrong_sid so FK doesn't block
    db_connection.execute(
        text("""
            INSERT INTO raw.ingestion_log (session_id, source_files, status)
            VALUES (:sid, :sf, 'COMMITTED')
        """),
        {"sid": str(wrong_sid), "sf": '["test.csv"]'},
    )
    result = aggregate_kpis(db_connection, wrong_sid)
    assert result.result == "FAIL"                                  # KDA-10


def test_payload_model_fields(db_connection: Connection, test_session_id: UUID):
    """KDA-11: KPIPayload has exactly 5 fields."""
    _insert_standard_grain(db_connection, test_session_id)
    result = aggregate_kpis(db_connection, test_session_id)
    assert result.result == "SUCCESS"
    fields = set(KPIPayload.model_fields.keys())
    expected = {
        "gpu_revenue", "gpu_cogs", "idle_gpu_cost",
        "idle_gpu_cost_pct", "cost_allocation_rate",
    }
    assert fields == expected                                       # KDA-11


def test_cache_values_match_db(db_connection: Connection, test_session_id: UUID):
    """KDA-12: Cache row in DB matches payload values exactly."""
    _insert_standard_grain(db_connection, test_session_id)
    result = aggregate_kpis(db_connection, test_session_id)
    assert result.result == "SUCCESS"

    row = db_connection.execute(
        text("""
            SELECT gpu_revenue, gpu_cogs, idle_gpu_cost,
                   idle_gpu_cost_pct, cost_allocation_rate
            FROM dbo.kpi_cache
            WHERE session_id = :sid
        """),
        {"sid": str(test_session_id)},
    ).fetchone()
    assert row.gpu_revenue == result.payload.gpu_revenue            # KDA-12a
    assert row.gpu_cogs == result.payload.gpu_cogs                  # KDA-12b
    assert row.idle_gpu_cost == result.payload.idle_gpu_cost        # KDA-12c
