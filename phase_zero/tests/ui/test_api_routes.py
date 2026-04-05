"""
API Route Tests — FastAPI endpoints for UI data.

Tests: API-01 through API-10
Assertions: 16

Tests use FastAPI TestClient with dependency override to inject
the same transaction-rollback db_connection from conftest.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.main import app
from app.api.deps import get_connection


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture()
def client(db_connection: Connection):
    """
    FastAPI TestClient with db_connection dependency override.

    All requests in a test share the same connection + transaction,
    which is rolled back after the test.
    """
    def _override():
        yield db_connection

    app.dependency_overrides[get_connection] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Helpers ─────────────────────────────────────────────────────────

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

_INSERT_RECON_SQL = text("""
    INSERT INTO dbo.reconciliation_results (
        session_id, check_name, check_order, verdict,
        fail_subtype, failing_count, detail
    ) VALUES (
        :sid, :cn, :co, :v, :fs, :fc, :d
    )
""")

_INSERT_STATE_SQL = text("""
    INSERT INTO dbo.state_store (
        session_id, application_state, session_status, analysis_status
    ) VALUES (
        :sid, :state, :status, :astatus
    )
""")


def _insert_standard_grain(conn: Connection, sid: UUID) -> None:
    """Insert 4-row test grain."""
    rows = [
        {"sid": str(sid), "region": "us-east-1", "pool": "pool-A",
         "date": "2026-03-15", "bp": "2026-03",
         "target": "tenant-A", "utype": None, "ftid": None,
         "hours": Decimal("100.00"), "cpgh": Decimal("2.50"),
         "rate": Decimal("5.00"),
         "rev": Decimal("500.00"), "cogs": Decimal("250.00"), "gm": Decimal("250.00")},
        {"sid": str(sid), "region": "us-east-1", "pool": "pool-A",
         "date": "2026-03-15", "bp": "2026-03",
         "target": "tenant-B", "utype": None, "ftid": None,
         "hours": Decimal("80.00"), "cpgh": Decimal("2.50"),
         "rate": Decimal("4.50"),
         "rev": Decimal("360.00"), "cogs": Decimal("200.00"), "gm": Decimal("160.00")},
        {"sid": str(sid), "region": "us-east-1", "pool": "pool-A",
         "date": "2026-03-15", "bp": "2026-03",
         "target": "unallocated", "utype": "identity_broken", "ftid": "tenant-BROKEN",
         "hours": Decimal("50.00"), "cpgh": Decimal("2.50"), "rate": None,
         "rev": Decimal("0.00"), "cogs": Decimal("125.00"), "gm": Decimal("-125.00")},
        {"sid": str(sid), "region": "us-east-1", "pool": "pool-A",
         "date": "2026-03-15", "bp": "2026-03",
         "target": "unallocated", "utype": "capacity_idle", "ftid": None,
         "hours": Decimal("70.00"), "cpgh": Decimal("2.50"), "rate": None,
         "rev": Decimal("0.00"), "cogs": Decimal("175.00"), "gm": Decimal("-175.00")},
    ]
    for r in rows:
        conn.execute(_INSERT_GRAIN_SQL, r)


def _insert_all_pass_recon(conn: Connection, sid: UUID) -> None:
    """Insert 3 PASS reconciliation verdicts."""
    checks = [
        ("Capacity vs Usage", 1),
        ("Usage vs Tenant Mapping", 2),
        ("Computed vs Billed vs Posted", 3),
    ]
    for name, order in checks:
        conn.execute(_INSERT_RECON_SQL, {
            "sid": str(sid), "cn": name, "co": order,
            "v": "PASS", "fs": None, "fc": None, "d": None,
        })


def _insert_kpi_cache(conn: Connection, sid: UUID) -> None:
    """Insert KPI cache row via aggregate_kpis."""
    from app.ui.kpi_data_aggregator import aggregate_kpis
    result = aggregate_kpis(conn, sid)
    assert result.result == "SUCCESS"


# ═══════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════


def test_health(client: TestClient):
    """API-01: Health check returns 200."""
    resp = client.get("/health")
    assert resp.status_code == 200                                  # API-01


def test_state_no_session(client: TestClient):
    """API-02: No active session → null state fields."""
    resp = client.get("/api/state")
    assert resp.status_code == 200                                  # API-02a
    data = resp.json()
    assert data["application_state"] is None                        # API-02b


def test_state_with_session(client: TestClient, db_connection: Connection, test_session_id: UUID):
    """API-03: Active session → correct state returned."""
    db_connection.execute(_INSERT_STATE_SQL, {
        "sid": str(test_session_id), "state": "ANALYZED",
        "status": "ACTIVE", "astatus": "IDLE",
    })
    resp = client.get("/api/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["application_state"] == "ANALYZED"                  # API-03


def test_kpi_endpoint(client: TestClient, db_connection: Connection, test_session_id: UUID):
    """API-04: KPI endpoint returns cached values."""
    _insert_standard_grain(db_connection, test_session_id)
    _insert_kpi_cache(db_connection, test_session_id)

    resp = client.get(f"/api/kpi/{test_session_id}")
    assert resp.status_code == 200                                  # API-04a
    data = resp.json()
    assert data["gpu_revenue"] == "860.00"                          # API-04b


def test_kpi_404(client: TestClient, test_session_id: UUID):
    """API-05: KPI with no cache → 404."""
    resp = client.get(f"/api/kpi/{test_session_id}")
    assert resp.status_code == 404                                  # API-05


def test_customers_endpoint(client: TestClient, db_connection: Connection, test_session_id: UUID):
    """API-06: Customers endpoint returns payload + identity_broken list."""
    _insert_standard_grain(db_connection, test_session_id)

    resp = client.get(f"/api/customers/{test_session_id}")
    assert resp.status_code == 200                                  # API-06a
    data = resp.json()
    assert len(data["payload"]) == 2                                # API-06b
    assert "tenant-BROKEN" in data["identity_broken_tenants"]       # API-06c


def test_regions_endpoint(client: TestClient, db_connection: Connection, test_session_id: UUID):
    """API-07: Regions endpoint returns region payload."""
    _insert_standard_grain(db_connection, test_session_id)

    resp = client.get(f"/api/regions/{test_session_id}")
    assert resp.status_code == 200                                  # API-07a
    data = resp.json()
    assert len(data["payload"]) == 1                                # API-07b
    assert data["payload"][0]["region"] == "us-east-1"              # API-07c


def test_reconciliation_endpoint(client: TestClient, db_connection: Connection, test_session_id: UUID):
    """API-08: Reconciliation endpoint returns 3 verdicts."""
    _insert_all_pass_recon(db_connection, test_session_id)

    resp = client.get(f"/api/reconciliation/{test_session_id}")
    assert resp.status_code == 200                                  # API-08a
    data = resp.json()
    assert len(data["payload"]) == 3                                # API-08b


def test_reconciliation_404(client: TestClient, test_session_id: UUID):
    """API-09: Reconciliation with no results → 404."""
    resp = client.get(f"/api/reconciliation/{test_session_id}")
    assert resp.status_code == 404                                  # API-09


def test_regions_empty(client: TestClient, test_session_id: UUID):
    """API-10: Regions with no grain → 200 with empty payload."""
    resp = client.get(f"/api/regions/{test_session_id}")
    assert resp.status_code == 200                                  # API-10a
    data = resp.json()
    assert len(data["payload"]) == 0                                # API-10b
