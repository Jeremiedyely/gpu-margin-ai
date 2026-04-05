"""
Integration tests for the Ingestion Commit.
10 assertions: COMMIT-01 through COMMIT-10.
Requires a running SQL Server with gpu_margin database and migrations applied.
"""

from __future__ import annotations

import os
import textwrap
from uuid import UUID

import pytest
from sqlalchemy import create_engine, text

from app.ingestion.orchestrator import UploadedFile, run_orchestration
from app.ingestion.commit import run_ingestion_commit


DEFAULT_URL = (
    "mssql+pyodbc://sa:1Liquidagents99!@localhost:1433"
    "/gpu_margin?driver=ODBC+Driver+17+for+SQL+Server&encrypt=no"
)


@pytest.fixture(scope="module")
def engine():
    url = os.environ.get("TEST_DATABASE_URL", DEFAULT_URL)
    return create_engine(url, future=True)


def _cleanup(engine, session_id: UUID):
    """Remove all data for a given session_id across all tables."""
    with engine.begin() as conn:
        for table in [
            "raw.telemetry", "raw.cost_management",
            "raw.iam", "raw.billing", "raw.erp",
        ]:
            conn.execute(
                text(f"DELETE FROM {table} WHERE session_id = :sid"),
                {"sid": str(session_id)},
            )
        conn.execute(
            text("DELETE FROM raw.ingestion_log WHERE session_id = :sid"),
            {"sid": str(session_id)},
        )


def _make_valid_payload():
    """Run orchestration with valid files and return SUCCESS payload."""
    files = {
        "telemetry": UploadedFile(
            slot="telemetry", filename="telemetry.csv",
            content=textwrap.dedent("""\
                tenant_id,region,gpu_pool_id,date,gpu_hours_consumed
                tenant-a,us-east-1,pool-1,2025-01-15,10.5
            """),
        ),
        "cost_management": UploadedFile(
            slot="cost_management", filename="cost_management.csv",
            content=textwrap.dedent("""\
                region,gpu_pool_id,date,reserved_gpu_hours,cost_per_gpu_hour
                us-east-1,pool-1,2025-01-15,100.0,2.50
            """),
        ),
        "iam": UploadedFile(
            slot="iam", filename="iam.csv",
            content=textwrap.dedent("""\
                tenant_id,billing_period,contracted_rate
                tenant-a,2025-01,3.50
            """),
        ),
        "billing": UploadedFile(
            slot="billing", filename="billing.csv",
            content=textwrap.dedent("""\
                tenant_id,billing_period,billable_amount
                tenant-a,2025-01,1500.00
            """),
        ),
        "erp": UploadedFile(
            slot="erp", filename="erp.csv",
            content=textwrap.dedent("""\
                tenant_id,billing_period,amount_posted
                tenant-a,2025-01,1500.00
            """),
        ),
    }
    return run_orchestration(files)


# ---------------------------------------------------------------------------
# COMMIT-01  Full success — all 5 tables + log written
# ---------------------------------------------------------------------------
def test_full_commit_success(engine):
    payload = _make_valid_payload()
    result = run_ingestion_commit(engine, payload)

    assert result.result == "SUCCESS", f"Commit failed: {result.reason}"  # COMMIT-01

    _cleanup(engine, payload.session_id)


# ---------------------------------------------------------------------------
# COMMIT-02  session_id returned on success
# ---------------------------------------------------------------------------
def test_session_id_returned(engine):
    payload = _make_valid_payload()
    result = run_ingestion_commit(engine, payload)

    assert result.session_id == payload.session_id              # COMMIT-02

    _cleanup(engine, payload.session_id)


# ---------------------------------------------------------------------------
# COMMIT-03  ingestion_log row written with COMMITTED status
# ---------------------------------------------------------------------------
def test_ingestion_log_written(engine):
    payload = _make_valid_payload()
    run_ingestion_commit(engine, payload)

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT status FROM raw.ingestion_log WHERE session_id = :sid"),
            {"sid": str(payload.session_id)},
        ).fetchone()

    assert row is not None                                      # COMMIT-03a
    assert row[0] == "COMMITTED"                                # COMMIT-03b

    _cleanup(engine, payload.session_id)


# ---------------------------------------------------------------------------
# COMMIT-04  All 5 raw tables have rows for session_id
# ---------------------------------------------------------------------------
def test_all_raw_tables_populated(engine):
    payload = _make_valid_payload()
    run_ingestion_commit(engine, payload)

    with engine.connect() as conn:
        for table in [
            "raw.telemetry", "raw.cost_management",
            "raw.iam", "raw.billing", "raw.erp",
        ]:
            row = conn.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE session_id = :sid"),
                {"sid": str(payload.session_id)},
            ).fetchone()
            assert row[0] >= 1, f"No rows in {table}"          # COMMIT-04

    _cleanup(engine, payload.session_id)


# ---------------------------------------------------------------------------
# COMMIT-05  Orchestration FAIL → no DB writes
# ---------------------------------------------------------------------------
def test_orchestration_fail_no_writes(engine):
    payload = _make_valid_payload()
    # Manually override to FAIL
    fail_payload = payload.model_copy(
        update={"result": "FAIL", "errors": ["forced failure"]}
    )
    result = run_ingestion_commit(engine, fail_payload)

    assert result.result == "FAIL"                              # COMMIT-05a

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) FROM raw.ingestion_log WHERE session_id = :sid"),
            {"sid": str(fail_payload.session_id)},
        ).fetchone()
        assert row[0] == 0                                      # COMMIT-05b


# ---------------------------------------------------------------------------
# COMMIT-06  source_files stored as JSON in ingestion_log
# ---------------------------------------------------------------------------
def test_source_files_json(engine):
    payload = _make_valid_payload()
    run_ingestion_commit(engine, payload)

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT source_files FROM raw.ingestion_log WHERE session_id = :sid"),
            {"sid": str(payload.session_id)},
        ).fetchone()

    import json
    source_files = json.loads(row[0])
    assert len(source_files) == 5                               # COMMIT-06a
    assert "telemetry.csv" in source_files                      # COMMIT-06b

    _cleanup(engine, payload.session_id)


# ---------------------------------------------------------------------------
# COMMIT-07  Prior session cleanup — old rows removed
# ---------------------------------------------------------------------------
def test_prior_session_cleanup(engine):
    # Insert session 1
    payload1 = _make_valid_payload()
    run_ingestion_commit(engine, payload1)

    # Insert session 2 — should clean up session 1's raw rows
    payload2 = _make_valid_payload()
    run_ingestion_commit(engine, payload2)

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) FROM raw.telemetry WHERE session_id = :sid"),
            {"sid": str(payload1.session_id)},
        ).fetchone()
        assert row[0] == 0                                      # COMMIT-07

    _cleanup(engine, payload1.session_id)
    _cleanup(engine, payload2.session_id)


# ---------------------------------------------------------------------------
# COMMIT-08  reason populated on FAIL
# ---------------------------------------------------------------------------
def test_reason_on_fail(engine):
    payload = _make_valid_payload()
    fail_payload = payload.model_copy(
        update={"result": "FAIL", "errors": ["test error reason"]}
    )
    result = run_ingestion_commit(engine, fail_payload)

    assert result.reason is not None                            # COMMIT-08a
    assert "test error reason" in result.reason                 # COMMIT-08b


# ---------------------------------------------------------------------------
# COMMIT-09  Atomicity — writer failure mid-transaction rolls back everything
# ---------------------------------------------------------------------------
def test_atomic_rollback_on_writer_failure(engine, monkeypatch):
    from app.ingestion import commit as commit_module
    from app.ingestion.writers.base import WriteResult

    # Telemetry writes first (succeeds), then mock ERP to fail.
    # If atomicity holds: telemetry rows are also rolled back.
    def fake_write_erp(conn, session_id, records):
        return WriteResult.failed(session_id=session_id, error="Simulated ERP failure")

    monkeypatch.setitem(commit_module._WRITERS, "erp", fake_write_erp)

    payload = _make_valid_payload()
    result = run_ingestion_commit(engine, payload)

    assert result.result == "FAIL"                              # COMMIT-09a

    # Verify NO rows in any table — atomic rollback
    with engine.connect() as conn:
        for table in [
            "raw.telemetry", "raw.cost_management",
            "raw.iam", "raw.billing", "raw.erp",
        ]:
            row = conn.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE session_id = :sid"),
                {"sid": str(payload.session_id)},
            ).fetchone()
            assert row[0] == 0, f"Orphaned rows in {table}"    # COMMIT-09b

        # Verify no ingestion_log entry
        row = conn.execute(
            text("SELECT COUNT(*) FROM raw.ingestion_log WHERE session_id = :sid"),
            {"sid": str(payload.session_id)},
        ).fetchone()
        assert row[0] == 0                                      # COMMIT-09c


# ---------------------------------------------------------------------------
# COMMIT-10  Second commit with same session_id fails (PK violation)
# ---------------------------------------------------------------------------
def test_duplicate_session_id_fails(engine):
    payload = _make_valid_payload()
    result1 = run_ingestion_commit(engine, payload)
    assert result1.result == "SUCCESS"

    # Attempt same session_id again — ingestion_log PK violation
    result2 = run_ingestion_commit(engine, payload)
    assert result2.result == "FAIL"                             # COMMIT-10

    _cleanup(engine, payload.session_id)
