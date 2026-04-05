"""
End-to-End Smoke Test — Full Pipeline Proof.

Exercises the entire causal chain in one test:
  Ingest 5 CSVs → Allocation Engine → Reconciliation Engine →
  Write State ANALYZED → UI Aggregators read correct data →
  Transition ANALYZED→APPROVED → Export 3 formats → Verify all outputs.

This is NOT a component test. It proves the *system* works, not just the parts.
All steps run within a single transaction (rolled back after test).

Assertions: E2E-01 through E2E-12
"""

from __future__ import annotations

import json
import tempfile
import uuid
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Connection, text

# ── Ingestion ──────────────────────────────────────────────────────
from app.ingestion.validators.telemetry import validate_telemetry_file
from app.ingestion.validators.cost_management import validate_cost_management_file
from app.ingestion.validators.iam import validate_iam_file
from app.ingestion.validators.billing import validate_billing_file
from app.ingestion.validators.erp import validate_erp_file

from app.ingestion.parsers.telemetry import parse_telemetry_file
from app.ingestion.parsers.cost_management import parse_cost_management_file
from app.ingestion.parsers.iam import parse_iam_file
from app.ingestion.parsers.billing import parse_billing_file
from app.ingestion.parsers.erp import parse_erp_file

from app.ingestion.writers.telemetry import write_telemetry
from app.ingestion.writers.cost_management import write_cost_management
from app.ingestion.writers.iam import write_iam
from app.ingestion.writers.billing import write_billing
from app.ingestion.writers.erp import write_erp

# ── Allocation Engine ──────────────────────────────────────────────
from app.allocation.telemetry_aggregator import aggregate_telemetry
from app.allocation.billing_period_deriver import derive_billing_periods
from app.allocation.cost_rate_reader import read_cost_rates
from app.allocation.iam_resolver import resolve_iam
from app.allocation.type_a_builder import build_type_a_records
from app.allocation.identity_broken_builder import build_identity_broken_records
from app.allocation.closure_rule_enforcer import enforce_closure_rule
from app.allocation.cost_revenue_calculator import calculate_cost_revenue
from app.allocation.grain_writer import write_allocation_grain

# ── Reconciliation Engine ──────────────────────────────────────────
from app.reconciliation.check1_executor import execute_check1
from app.reconciliation.check2_executor import execute_check2
from app.reconciliation.check3_executor import execute_check3
from app.reconciliation.result_aggregator import aggregate_results
from app.reconciliation.result_writer import write_reconciliation_results

# ── State Machine ──────────────────────────────────────────────────
from app.state_machine.state_store import (
    StateWriteRequest,
    write_state,
    read_state,
)

# ── UI Aggregators ─────────────────────────────────────────────────
from app.ui.kpi_data_aggregator import aggregate_kpis, read_kpi_cache
from app.ui.customer_data_aggregator import aggregate_customers
from app.ui.region_data_aggregator import aggregate_regions
from app.ui.reconciliation_result_reader import read_reconciliation_results

# ── Export Module ──────────────────────────────────────────────────
from app.export.export_source_reader import read_export_source
from app.export.session_metadata_appender import append_session_metadata
from app.export.format_router import route_export
from app.export.output_verifier import verify_output
from app.export.file_delivery_handler import deliver_file
from app.state_machine.export_gate_enforcer import check_export_gate


# ═══════════════════════════════════════════════════════════════════
# Test Data — 5 CSV source files
# ═══════════════════════════════════════════════════════════════════

# 3 tenants in us-east-1 / pool-A on 2026-03-15.
# reserved_gpu_hours = 300. tenant-A: 100h, tenant-B: 80h, tenant-BROKEN: 50h.
# Total consumed = 230, idle = 70.

TELEMETRY_CSV = """\
tenant_id,region,gpu_pool_id,date,gpu_hours_consumed
tenant-A,us-east-1,pool-A,2026-03-15,100.00
tenant-B,us-east-1,pool-A,2026-03-15,80.00
tenant-BROKEN,us-east-1,pool-A,2026-03-15,50.00
"""

COST_MANAGEMENT_CSV = """\
region,gpu_pool_id,date,reserved_gpu_hours,cost_per_gpu_hour
us-east-1,pool-A,2026-03-15,300.00,2.50
"""

IAM_CSV = """\
tenant_id,billing_period,contracted_rate
tenant-A,2026-03,5.00
tenant-B,2026-03,4.50
"""

BILLING_CSV = """\
tenant_id,billing_period,billable_amount
tenant-A,2026-03,500.00
tenant-B,2026-03,360.00
"""

ERP_CSV = """\
tenant_id,billing_period,amount_posted
tenant-A,2026-03,500.00
tenant-B,2026-03,360.00
"""

SOURCE_FILES = [
    "telemetry_metering.csv",
    "cost_management.csv",
    "iam_tenant.csv",
    "billing_system.csv",
    "erp_general_ledger.csv",
]


# ═══════════════════════════════════════════════════════════════════
# Fixture Override — E2E needs 5 source files + EMPTY state
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture()
def test_session_id(db_connection: Connection) -> uuid.UUID:
    """
    Override integration conftest fixture.
    Insert ingestion_log with 5 source files + state_store at EMPTY.
    """
    sid = uuid.uuid4()
    source_files_json = json.dumps(SOURCE_FILES)

    # ingestion_log (FK parent for all raw/dbo tables)
    db_connection.execute(
        text("""
            INSERT INTO raw.ingestion_log (session_id, source_files, status)
            VALUES (:sid, :sf, 'COMMITTED')
        """),
        {"sid": str(sid), "sf": source_files_json},
    )

    # state_store — start at EMPTY
    db_connection.execute(
        text("""
            INSERT INTO dbo.state_store
                (session_id, application_state, session_status,
                 analysis_status, write_result)
            VALUES (:sid, 'EMPTY', 'ACTIVE', 'IDLE', NULL)
        """),
        {"sid": str(sid)},
    )

    return sid


# ═══════════════════════════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════════════════════════

def _ingest_file(validator, parser, writer, csv_content, conn, sid):
    """Validate → Parse → Write a single CSV file."""
    v = validator(csv_content)
    assert v.verdict == "PASS", f"Validation failed: {v.errors}"
    p = parser(csv_content)
    assert p.result == "PASS", f"Parse failed: {p.error}"
    w = writer(conn, sid, p.records)
    assert w.result == "SUCCESS", f"Write failed: {w.error}"
    return w


# ═══════════════════════════════════════════════════════════════════
# E2E Smoke Test — 12 Steps
# ═══════════════════════════════════════════════════════════════════

def test_e2e_full_pipeline(db_connection: Connection, test_session_id: UUID):
    """
    Full pipeline proof: CSV → Allocation → Reconciliation → State →
    UI Aggregators → Approve → Export → Verify.
    """
    conn = db_connection
    sid = test_session_id

    # ── STEP 1: Ingest all 5 source files ───────────────────────  E2E-01
    _ingest_file(validate_telemetry_file, parse_telemetry_file,
                 write_telemetry, TELEMETRY_CSV, conn, sid)
    _ingest_file(validate_cost_management_file, parse_cost_management_file,
                 write_cost_management, COST_MANAGEMENT_CSV, conn, sid)
    _ingest_file(validate_iam_file, parse_iam_file,
                 write_iam, IAM_CSV, conn, sid)
    _ingest_file(validate_billing_file, parse_billing_file,
                 write_billing, BILLING_CSV, conn, sid)
    _ingest_file(validate_erp_file, parse_erp_file,
                 write_erp, ERP_CSV, conn, sid)
    # All 5 ingestions succeeded                                      E2E-01 ✓

    # ── STEP 2: Write UPLOADED state ────────────────────────────  E2E-02
    ws_uploaded = write_state(
        conn,
        StateWriteRequest(
            new_state="UPLOADED",
            trigger="INGESTION_COMPLETE",
            session_id=sid,
            analysis_status="IDLE",
        ),
        from_state="EMPTY",
    )
    assert ws_uploaded.result == "SUCCESS"                             # E2E-02 ✓

    # ── STEP 3: Run Allocation Engine ───────────────────────────  E2E-03
    agg = aggregate_telemetry(conn, sid)
    assert agg.result == "SUCCESS"
    assert len(agg.records) == 3

    der = derive_billing_periods(agg.records)
    assert der.result == "SUCCESS"

    cr = read_cost_rates(conn, sid)
    assert cr.result == "SUCCESS"

    res = resolve_iam(conn, sid, der.records)
    assert res.result == "SUCCESS"
    assert len(res.type_a) == 2
    assert len(res.identity_broken) == 1

    ta_build = build_type_a_records(res.type_a, cr.records)
    assert ta_build.result == "SUCCESS"

    ib_build = build_identity_broken_records(res.identity_broken, cr.records)
    assert ib_build.result == "SUCCESS"

    closure = enforce_closure_rule(ta_build.records, ib_build.records, cr.records)
    assert closure.result == "SUCCESS"
    assert len(closure.capacity_idle) == 1

    calc = calculate_cost_revenue(
        ta_build.records, ib_build.records, closure.capacity_idle,
    )
    assert calc.result == "SUCCESS"
    assert len(calc.records) == 4  # 2 Type A + 1 IB + 1 Idle

    gw = write_allocation_grain(conn, sid, calc.records)
    assert gw.result == "SUCCESS"
    assert gw.row_count == 4                                          # E2E-03 ✓

    # ── STEP 4: Run Reconciliation Engine ───────────────────────  E2E-04
    c1 = execute_check1(conn, sid)
    c2 = execute_check2(conn, sid)
    c3 = execute_check3(conn, sid)

    # Check 2 must FAIL (tenant-BROKEN has no IAM mapping)
    assert c2.verdict == "FAIL"                                        # E2E-04a

    agg_results = aggregate_results(c1, c2, c3, sid)
    assert agg_results.result == "SUCCESS"

    rw = write_reconciliation_results(conn, agg_results, sid)
    assert rw.result == "SUCCESS"                                      # E2E-04b ✓

    # ── STEP 5: Transition to ANALYZED ──────────────────────────  E2E-05
    ws_analyzed = write_state(
        conn,
        StateWriteRequest(
            new_state="ANALYZED",
            trigger="ENGINES_COMPLETE",
            session_id=sid,
        ),
        from_state="UPLOADED",
    )
    assert ws_analyzed.result == "SUCCESS"
    snapshot = read_state(conn, sid)
    assert snapshot.application_state == "ANALYZED"                     # E2E-05 ✓

    # ── STEP 6: UI Aggregators produce correct data ─────────────  E2E-06
    # 6a. KPI aggregator
    kpi_result = aggregate_kpis(conn, sid)
    assert kpi_result.result == "SUCCESS"
    kpi = read_kpi_cache(conn, sid)
    assert kpi is not None
    assert kpi.payload is not None
    assert kpi.payload.gpu_revenue > Decimal("0")                      # E2E-06a

    # 6b. Customer aggregator
    cust_result = aggregate_customers(conn, sid)
    assert cust_result.result == "SUCCESS"
    # Should have customers with GM% colors and at least one FLAG
    assert len(cust_result.payload) >= 1                               # E2E-06b

    # 6c. Region aggregator
    region_result = aggregate_regions(conn, sid)
    assert region_result.result == "SUCCESS"
    assert len(region_result.payload) >= 1                             # E2E-06c

    # 6d. Reconciliation results reader
    recon = read_reconciliation_results(conn, sid)
    assert len(recon.payload) == 3  # 3 checks in order               # E2E-06d ✓

    # ── STEP 7: Export gate BLOCKED before APPROVED ─────────────  E2E-07
    gate_before = check_export_gate(conn, sid)
    assert gate_before.result == "BLOCKED"
    assert gate_before.reason_code == "GATE_BLOCKED_NOT_APPROVED"      # E2E-07 ✓

    # ── STEP 8: Copy grain to final.allocation_result ───────────  E2E-08
    conn.execute(
        text("""
            INSERT INTO final.allocation_result
                (session_id, region, gpu_pool_id, date, billing_period,
                 allocation_target, unallocated_type, failed_tenant_id,
                 gpu_hours, cost_per_gpu_hour, contracted_rate,
                 revenue, cogs, gross_margin)
            SELECT
                session_id, region, gpu_pool_id, date, billing_period,
                allocation_target, unallocated_type, failed_tenant_id,
                gpu_hours, cost_per_gpu_hour, contracted_rate,
                revenue, cogs, gross_margin
            FROM dbo.allocation_grain
            WHERE session_id = :sid
        """),
        {"sid": str(sid)},
    )

    # Transition to APPROVED with write_result=SUCCESS
    ws_approved = write_state(
        conn,
        StateWriteRequest(
            new_state="APPROVED",
            trigger="CFO_APPROVAL",
            session_id=sid,
            write_result="SUCCESS",
        ),
        from_state="ANALYZED",
    )
    assert ws_approved.result == "SUCCESS"
    snapshot = read_state(conn, sid)
    assert snapshot.application_state == "APPROVED"
    assert snapshot.write_result == "SUCCESS"                           # E2E-08 ✓

    # ── STEP 9: Export gate NOW OPEN ────────────────────────────  E2E-09
    gate_after = check_export_gate(conn, sid)
    assert gate_after.result == "OPEN"                                 # E2E-09 ✓

    # ── STEP 10: Read export source ─────────────────────────────  E2E-10
    export_rows = read_export_source(conn, sid)
    assert len(export_rows) == 4  # Same 4 rows as allocation_grain

    enriched = append_session_metadata(conn, sid, export_rows)
    assert len(enriched) == 4
    assert enriched[0]["session_id"] == str(sid)
    sf = json.loads(enriched[0]["source_files"])
    assert len(sf) == 5  # 5 source files                             # E2E-10 ✓

    # ── STEP 11: Generate all 3 export formats ──────────────────  E2E-11
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        sid_str = str(sid)

        csv_path = route_export("csv", enriched, out_dir / "csv", sid_str)
        xlsx_path = route_export("excel", enriched, out_dir / "xlsx", sid_str)
        pbi_path = route_export("power_bi", enriched, out_dir / "pbi", sid_str)

        assert csv_path.exists()
        assert xlsx_path.exists()
        assert pbi_path.exists()                                       # E2E-11 ✓

        # ── STEP 12: Verify all 3 outputs ──────────────────────  E2E-12
        csv_v = verify_output(csv_path, expected_row_count=4, file_format="csv")
        assert csv_v.all_passed, f"CSV verify failed: {csv_v.errors}"

        xlsx_v = verify_output(xlsx_path, expected_row_count=4, file_format="excel")
        assert xlsx_v.all_passed, f"Excel verify failed: {xlsx_v.errors}"

        pbi_v = verify_output(pbi_path, expected_row_count=4, file_format="power_bi")
        assert pbi_v.all_passed, f"Power BI verify failed: {pbi_v.errors}"

        # Delivery handler returns valid links
        csv_d = deliver_file(csv_path)
        assert csv_d.result == "SUCCESS"
        assert csv_d.link.startswith("computer://")

        xlsx_d = deliver_file(xlsx_path)
        assert xlsx_d.result == "SUCCESS"

        pbi_d = deliver_file(pbi_path)
        assert pbi_d.result == "SUCCESS"                               # E2E-12 ✓
