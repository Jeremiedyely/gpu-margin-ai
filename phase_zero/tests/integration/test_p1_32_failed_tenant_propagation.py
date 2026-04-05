"""
P1 #32 — Failed Tenant Propagation Integration Test.

Pre-Phase 6 gate.  Validates the full pipeline:
  Ingestion → Allocation Engine → Reconciliation Engine

Scenario:
  3 tenants in telemetry.  2 have IAM records, 1 does not (tenant-BROKEN).
  The broken tenant must propagate through the entire pipeline as an
  identity_broken record, land in allocation_grain with
  failed_tenant_id = 'tenant-BROKEN', survive the Cost & Revenue
  Calculator unchanged, and cause Check 2 to FAIL with the correct
  unresolved (tenant_id, billing_period) pair.

Grain: Region × GPU Pool × Day × Allocation Target
DB: 7-step sequential pipeline — single long test function.

Assertions: P132-01 through P132-07
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Connection, text

# ── Ingestion: validators ───────────────────────────────────────────
from app.ingestion.validators.telemetry import validate_telemetry_file
from app.ingestion.validators.cost_management import validate_cost_management_file
from app.ingestion.validators.iam import validate_iam_file
from app.ingestion.validators.billing import validate_billing_file
from app.ingestion.validators.erp import validate_erp_file

# ── Ingestion: parsers ──────────────────────────────────────────────
from app.ingestion.parsers.telemetry import parse_telemetry_file
from app.ingestion.parsers.cost_management import parse_cost_management_file
from app.ingestion.parsers.iam import parse_iam_file
from app.ingestion.parsers.billing import parse_billing_file
from app.ingestion.parsers.erp import parse_erp_file

# ── Ingestion: writers ──────────────────────────────────────────────
from app.ingestion.writers.telemetry import write_telemetry
from app.ingestion.writers.cost_management import write_cost_management
from app.ingestion.writers.iam import write_iam
from app.ingestion.writers.billing import write_billing
from app.ingestion.writers.erp import write_erp

# ── Allocation Engine ───────────────────────────────────────────────
from app.allocation.telemetry_aggregator import aggregate_telemetry
from app.allocation.billing_period_deriver import derive_billing_periods
from app.allocation.cost_rate_reader import read_cost_rates
from app.allocation.iam_resolver import resolve_iam
from app.allocation.type_a_builder import build_type_a_records
from app.allocation.identity_broken_builder import build_identity_broken_records
from app.allocation.closure_rule_enforcer import enforce_closure_rule
from app.allocation.cost_revenue_calculator import calculate_cost_revenue
from app.allocation.grain_writer import write_allocation_grain

# ── Reconciliation Engine ───────────────────────────────────────────
from app.reconciliation.check2_executor import execute_check2


# ═══════════════════════════════════════════════════════════════════
# Test Data — 5 CSV source files
# ═══════════════════════════════════════════════════════════════════

# 3 tenants in us-east-1 / pool-A on 2026-03-15.
# reserved_gpu_hours = 300 to ensure closure rule has idle capacity.
# tenant-A: 100 hours, tenant-B: 80 hours, tenant-BROKEN: 50 hours
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

# IAM: deliberately NO row for tenant-BROKEN + 2026-03.
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


# ═══════════════════════════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════════════════════════

def _ingest_file(validator, parser, writer, csv_content, conn, sid):
    """Validate → Parse → Write a single CSV file. Returns WriteResult."""
    v = validator(csv_content)
    assert v.verdict == "PASS", f"Validation failed: {v.errors}"
    p = parser(csv_content)
    assert p.result == "PASS", f"Parse failed: {p.error}"
    w = writer(conn, sid, p.records)
    assert w.result == "SUCCESS", f"Write failed: {w.error}"
    return w


# ═══════════════════════════════════════════════════════════════════
# P1 #32 — 7-Step Integration Test
# ═══════════════════════════════════════════════════════════════════

def test_failed_tenant_propagation(db_connection: Connection, test_session_id: UUID):
    """
    End-to-end: tenant-BROKEN has telemetry but no IAM record.
    It must propagate through the full pipeline as identity_broken
    and cause Check 2 to FAIL.
    """
    conn = db_connection
    sid = test_session_id

    # ── STEP 1: Ingest all 5 source files ───────────────────────  P132-01
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
    # If we reach here, all 5 ingestions succeeded.                  P132-01 ✓

    # ── STEP 2: Run Allocation Engine pipeline ──────────────────  P132-02
    # 2a. Aggregate telemetry
    agg = aggregate_telemetry(conn, sid)
    assert agg.result == "SUCCESS", f"Aggregator failed: {agg.error}"
    assert len(agg.records) == 3  # tenant-A, tenant-B, tenant-BROKEN

    # 2b. Derive billing periods
    der = derive_billing_periods(agg.records)
    assert der.result == "SUCCESS", f"Deriver failed: {der.error}"
    assert len(der.records) == 3

    # 2c. Read cost rates
    cr = read_cost_rates(conn, sid)
    assert cr.result == "SUCCESS", f"Cost Rate Reader failed: {cr.error}"

    # 2d. Resolve IAM — THIS IS THE KEY STEP
    res = resolve_iam(conn, sid, der.records)
    assert res.result == "SUCCESS", f"IAM Resolver failed: {res.error}"
    assert len(res.type_a) == 2, (
        f"Expected 2 Type A records, got {len(res.type_a)}"
    )
    assert len(res.identity_broken) == 1, (
        f"Expected 1 identity_broken record, got {len(res.identity_broken)}"
    )
    ib_rec = res.identity_broken[0]
    assert ib_rec.tenant_id == "tenant-BROKEN"                      # P132-02a
    assert ib_rec.billing_period == "2026-03"                       # P132-02b

    # 2e. Build Type A records
    ta_build = build_type_a_records(res.type_a, cr.records)
    assert ta_build.result == "SUCCESS", f"Type A Builder failed: {ta_build.error}"

    # 2f. Build identity_broken records
    ib_build = build_identity_broken_records(res.identity_broken, cr.records)
    assert ib_build.result == "SUCCESS", f"IB Builder failed: {ib_build.error}"
    assert len(ib_build.records) == 1
    ib_grain = ib_build.records[0]
    assert ib_grain.failed_tenant_id == "tenant-BROKEN"             # P132-02c
    assert ib_grain.unallocated_type == "identity_broken"           # P132-02d
    assert ib_grain.allocation_target == "unallocated"              # P132-02e

    # 2g. Enforce closure rule
    closure = enforce_closure_rule(ta_build.records, ib_build.records, cr.records)
    assert closure.result == "SUCCESS", f"Closure Rule failed: {closure.error}"
    # idle = 300 - (100 + 80 + 50) = 70
    assert len(closure.capacity_idle) == 1
    assert closure.capacity_idle[0].gpu_hours == Decimal("70")      # P132-02f

    # 2h. Calculate cost & revenue
    calc = calculate_cost_revenue(
        ta_build.records, ib_build.records, closure.capacity_idle,
    )
    assert calc.result == "SUCCESS", f"Calculator failed: {calc.error}"
    # 2 Type A + 1 identity_broken + 1 capacity_idle = 4 records
    assert len(calc.records) == 4                                   # P132-02g

    # 2i. Write to allocation_grain
    gw = write_allocation_grain(conn, sid, calc.records)
    assert gw.result == "SUCCESS", f"Grain Writer failed: {gw.error}"
    assert gw.row_count == 4                                        # P132-02h

    # ── STEP 3: Verify allocation_grain has identity_broken row ─  P132-03
    ib_rows = conn.execute(
        text("""
            SELECT failed_tenant_id, unallocated_type, allocation_target,
                   gpu_hours, cost_per_gpu_hour, billing_period
            FROM dbo.allocation_grain
            WHERE session_id = :sid
              AND unallocated_type = 'identity_broken'
        """),
        {"sid": str(sid)},
    ).fetchall()
    assert len(ib_rows) == 1                                        # P132-03a
    assert ib_rows[0].failed_tenant_id == "tenant-BROKEN"           # P132-03b
    assert ib_rows[0].unallocated_type == "identity_broken"         # P132-03c
    assert ib_rows[0].allocation_target == "unallocated"            # P132-03d
    assert ib_rows[0].gpu_hours == Decimal("50.00")                 # P132-03e
    assert ib_rows[0].billing_period == "2026-03"                   # P132-03f

    # ── STEP 4: Calculator pass-through ─────────────────────────  P132-04
    # Verify the ComputedRecord for identity_broken has unchanged failed_tenant_id.
    ib_computed = [r for r in calc.records if r.failed_tenant_id == "tenant-BROKEN"]
    assert len(ib_computed) == 1                                    # P132-04a
    assert ib_computed[0].unallocated_type == "identity_broken"     # P132-04b
    assert ib_computed[0].revenue == Decimal("0")                   # P132-04c
    assert ib_computed[0].cogs == Decimal("50.00") * Decimal("2.50")  # P132-04d
    assert ib_computed[0].gross_margin == -ib_computed[0].cogs      # P132-04e

    # ── STEP 5: Check 2 — tenant-BROKEN unresolved ─────────────  P132-05
    c2 = execute_check2(conn, sid)
    assert c2.verdict == "FAIL"                                     # P132-05a
    assert c2.failing_count >= 1                                    # P132-05b
    unresolved_tenants = {p.tenant_id for p in c2.unresolved_pairs}
    assert "tenant-BROKEN" in unresolved_tenants                    # P132-05c
    # Verify the billing_period in the unresolved pair
    broken_pairs = [
        p for p in c2.unresolved_pairs if p.tenant_id == "tenant-BROKEN"
    ]
    assert broken_pairs[0].billing_period == "2026-03"              # P132-05d

    # ── STEP 6: Identity broken SET query ───────────────────────  P132-06
    ib_set = conn.execute(
        text("""
            SELECT DISTINCT failed_tenant_id
            FROM dbo.allocation_grain
            WHERE session_id = :sid
              AND unallocated_type = 'identity_broken'
              AND failed_tenant_id IS NOT NULL
        """),
        {"sid": str(sid)},
    ).fetchall()
    ib_set_ids = {row.failed_tenant_id for row in ib_set}
    assert "tenant-BROKEN" in ib_set_ids                            # P132-06a
    # Only tenant-BROKEN should be in the set — tenant-A and tenant-B resolved
    assert "tenant-A" not in ib_set_ids                             # P132-06b
    assert "tenant-B" not in ib_set_ids                             # P132-06c

    # ── STEP 7: Risk flag data ──────────────────────────────────  P132-07
    # For tenant-BROKEN, the SET membership (Step 6) is the data that
    # drives risk_flag = FLAG.  Confirm the identity_broken record
    # carries the negative margin (cost with zero revenue) that
    # constitutes the risk signal.
    risk_row = conn.execute(
        text("""
            SELECT revenue, cogs, gross_margin
            FROM dbo.allocation_grain
            WHERE session_id = :sid
              AND failed_tenant_id = 'tenant-BROKEN'
        """),
        {"sid": str(sid)},
    ).fetchone()
    assert risk_row is not None                                     # P132-07a
    assert risk_row.revenue == Decimal("0")                         # P132-07b
    assert risk_row.cogs > Decimal("0")                             # P132-07c
    assert risk_row.gross_margin < Decimal("0")                     # P132-07d
