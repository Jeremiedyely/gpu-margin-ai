"""
Shared fixtures for Export Module tests.

Export tests need:
- ingestion_log row (FK parent)
- state_store row (APPROVED + write_result=SUCCESS)
- final.allocation_result rows (export source)
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine, Connection


SOURCE_FILES_FIXTURE = [
    "telemetry_metering.csv",
    "cost_management.csv",
    "iam_tenant.csv",
    "billing_system.csv",
    "erp_general_ledger.csv",
]


@pytest.fixture()
def db_connection(engine: Engine):
    """
    Yield a connection wrapped in a transaction.

    After the test, the transaction is rolled back so the database
    stays clean between tests.
    """
    conn = engine.connect()
    txn = conn.begin()
    try:
        yield conn
    finally:
        txn.rollback()
        conn.close()


@pytest.fixture()
def test_session_id(db_connection: Connection) -> uuid.UUID:
    """
    Insert ingestion_log + state_store (APPROVED/SUCCESS)
    + 3 final.allocation_result rows.

    Returns the session_id for export tests.
    """
    sid = uuid.uuid4()
    source_files_json = json.dumps(SOURCE_FILES_FIXTURE)

    # 1. Ingestion log (FK parent)
    db_connection.execute(
        text("""
            INSERT INTO raw.ingestion_log (session_id, source_files, status)
            VALUES (:sid, :sf, 'COMMITTED')
        """),
        {"sid": str(sid), "sf": source_files_json},
    )

    # 2. State store — APPROVED + write_result = SUCCESS
    db_connection.execute(
        text("""
            INSERT INTO dbo.state_store
                (session_id, application_state, session_status,
                 analysis_status, write_result)
            VALUES (:sid, 'APPROVED', 'ACTIVE', 'IDLE', 'SUCCESS')
        """),
        {"sid": str(sid)},
    )

    # 3. Three allocation_result rows (Type A + identity_broken + capacity_idle)
    rows = [
        {
            "sid": str(sid),
            "region": "us-east-1",
            "gpu_pool_id": "pool-a",
            "date": "2026-01-15",
            "billing_period": "2026-01",
            "allocation_target": "tenant-A",
            "unallocated_type": None,
            "failed_tenant_id": None,
            "gpu_hours": "100.000000",
            "cost_per_gpu_hour": "2.500000",
            "contracted_rate": "4.000000",
            "revenue": "400.00",
            "cogs": "250.00",
            "gross_margin": "150.00",
        },
        {
            "sid": str(sid),
            "region": "us-east-1",
            "gpu_pool_id": "pool-a",
            "date": "2026-01-15",
            "billing_period": "2026-01",
            "allocation_target": "unallocated",
            "unallocated_type": "identity_broken",
            "failed_tenant_id": "tenant-BROKEN",
            "gpu_hours": "50.000000",
            "cost_per_gpu_hour": "2.500000",
            "contracted_rate": None,
            "revenue": "0.00",
            "cogs": "125.00",
            "gross_margin": "-125.00",
        },
        {
            "sid": str(sid),
            "region": "eu-west-1",
            "gpu_pool_id": "pool-b",
            "date": "2026-01-15",
            "billing_period": "2026-01",
            "allocation_target": "unallocated",
            "unallocated_type": "capacity_idle",
            "failed_tenant_id": None,
            "gpu_hours": "30.000000",
            "cost_per_gpu_hour": "3.000000",
            "contracted_rate": None,
            "revenue": "0.00",
            "cogs": "90.00",
            "gross_margin": "-90.00",
        },
    ]

    for r in rows:
        db_connection.execute(
            text("""
                INSERT INTO final.allocation_result
                    (session_id, region, gpu_pool_id, date, billing_period,
                     allocation_target, unallocated_type, failed_tenant_id,
                     gpu_hours, cost_per_gpu_hour, contracted_rate,
                     revenue, cogs, gross_margin)
                VALUES
                    (:sid, :region, :gpu_pool_id, :date, :billing_period,
                     :allocation_target, :unallocated_type, :failed_tenant_id,
                     :gpu_hours, :cost_per_gpu_hour, :contracted_rate,
                     :revenue, :cogs, :gross_margin)
            """),
            r,
        )

    return sid
