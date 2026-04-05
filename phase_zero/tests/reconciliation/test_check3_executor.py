"""
Tests for Check 3 Executor — Computed vs Billed vs Posted — Component 4/7.

DB integration tests. Validates FAIL-1, FAIL-2, precedence, contract boundary
(L2 P1 #18), missing billing/ERP rows, and session_id isolation.

Assertions: C3-01 through C3-12
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Connection, text

from app.reconciliation.check3_executor import execute_check3


# ── Helpers ──────────────────────────────────────────────────────────

def _insert_grain(conn: Connection, sid, allocation_target: str,
                  billing_period: str, revenue: Decimal,
                  region: str = "us-east-1", gpu_pool_id: str = "pool-A"):
    """Insert an allocation_grain row (Type A only — allocation_target = tenant_id).

    Derives contracted_rate from revenue so CHK_grain_revenue_math passes:
      gpu_hours=100, cost_per_gpu_hour=0.50, contracted_rate=revenue/100
      revenue = gpu_hours * contracted_rate, cogs = gpu_hours * cost_per_gpu_hour = 50
      gross_margin = revenue - cogs
    Derives date from billing_period (YYYY-MM → YYYY-MM-15) so unique index
    UQ_grain_type_a_natural_key is not violated across different periods.
    """
    gpu_hours = Decimal("100")
    cost_per_gpu_hour = Decimal("0.50")
    contracted_rate = revenue / gpu_hours
    cogs = gpu_hours * cost_per_gpu_hour
    gross_margin = revenue - cogs
    grain_date = f"{billing_period}-15"
    conn.execute(
        text("""
            INSERT INTO dbo.allocation_grain
                (session_id, region, gpu_pool_id, date, billing_period,
                 allocation_target, unallocated_type, failed_tenant_id,
                 gpu_hours, cost_per_gpu_hour, contracted_rate,
                 revenue, cogs, gross_margin)
            VALUES
                (:sid, :region, :pool, :dt, :bp,
                 :target, NULL, NULL,
                 :gpu_hours, :cpgh, :cr,
                 :revenue, :cogs, :gm)
        """),
        {"sid": str(sid), "region": region, "pool": gpu_pool_id,
         "dt": grain_date, "bp": billing_period, "target": allocation_target,
         "gpu_hours": gpu_hours, "cpgh": cost_per_gpu_hour, "cr": contracted_rate,
         "revenue": revenue, "cogs": cogs, "gm": gross_margin},
    )


def _insert_unallocated_grain(conn: Connection, sid,
                               unallocated_type: str = "capacity_idle",
                               billing_period: str = "2026-03"):
    """Insert an unallocated allocation_grain row (Type B)."""
    conn.execute(
        text("""
            INSERT INTO dbo.allocation_grain
                (session_id, region, gpu_pool_id, date, billing_period,
                 allocation_target, unallocated_type, failed_tenant_id,
                 gpu_hours, cost_per_gpu_hour, contracted_rate,
                 revenue, cogs, gross_margin)
            VALUES
                (:sid, 'us-east-1', 'pool-A', '2026-03-15', :bp,
                 'unallocated', :utype, :ftid,
                 50, 0.50, NULL,
                 0, 25.00, -25.00)
        """),
        {"sid": str(sid), "bp": billing_period, "utype": unallocated_type,
         "ftid": "tenant-X" if unallocated_type == "identity_broken" else None},
    )


def _insert_billing(conn: Connection, sid, tenant_id: str,
                    billing_period: str, billable_amount: Decimal):
    conn.execute(
        text("""
            INSERT INTO raw.billing (session_id, tenant_id, billing_period, billable_amount)
            VALUES (:sid, :tid, :bp, :amt)
        """),
        {"sid": str(sid), "tid": tenant_id, "bp": billing_period,
         "amt": billable_amount},
    )


def _insert_erp(conn: Connection, sid, tenant_id: str,
                billing_period: str, amount_posted: Decimal):
    conn.execute(
        text("""
            INSERT INTO raw.erp (session_id, tenant_id, billing_period, amount_posted)
            VALUES (:sid, :tid, :bp, :amt)
        """),
        {"sid": str(sid), "tid": tenant_id, "bp": billing_period,
         "amt": amount_posted},
    )


# ── C3-01: All match → PASS ─────────────────────────────────────────

def test_all_match_passes(db_connection, test_session_id):
    sid = test_session_id
    _insert_grain(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))
    _insert_billing(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))
    _insert_erp(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))

    result = execute_check3(db_connection, sid)
    assert result.verdict == "PASS"                          # C3-01


# ── C3-02: computed ≠ billed → FAIL-1 ───────────────────────────────

def test_computed_ne_billed_fail1(db_connection, test_session_id):
    sid = test_session_id
    _insert_grain(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))
    _insert_billing(db_connection, sid, "tenant-1", "2026-03", Decimal("90.00"))
    _insert_erp(db_connection, sid, "tenant-1", "2026-03", Decimal("90.00"))

    result = execute_check3(db_connection, sid)
    assert result.verdict == "FAIL"                          # C3-02a
    assert result.failing_records[0].fail_type == "FAIL-1"   # C3-02b


# ── C3-03: billed ≠ posted → FAIL-2 ─────────────────────────────────

def test_billed_ne_posted_fail2(db_connection, test_session_id):
    sid = test_session_id
    _insert_grain(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))
    _insert_billing(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))
    _insert_erp(db_connection, sid, "tenant-1", "2026-03", Decimal("80.00"))

    result = execute_check3(db_connection, sid)
    assert result.verdict == "FAIL"                          # C3-03a
    assert result.failing_records[0].fail_type == "FAIL-2"   # C3-03b


# ── C3-04: FAIL-1 + FAIL-2 same pair → precedence: FAIL-1 only ──────

def test_fail1_precedence_over_fail2(db_connection, test_session_id):
    sid = test_session_id
    # computed=100, billed=90, posted=80 → both FAIL-1 and FAIL-2 present
    # Precedence rule: record FAIL-1 only
    _insert_grain(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))
    _insert_billing(db_connection, sid, "tenant-1", "2026-03", Decimal("90.00"))
    _insert_erp(db_connection, sid, "tenant-1", "2026-03", Decimal("80.00"))

    result = execute_check3(db_connection, sid)
    assert result.failing_count == 1                         # C3-04a
    assert result.failing_records[0].fail_type == "FAIL-1"   # C3-04b


# ── C3-05: Missing billing row → FAIL-1 ─────────────────────────────

def test_missing_billing_row_fail1(db_connection, test_session_id):
    sid = test_session_id
    _insert_grain(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))
    # No billing row inserted
    _insert_erp(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))

    result = execute_check3(db_connection, sid)
    assert result.verdict == "FAIL"                          # C3-05a
    assert result.failing_records[0].fail_type == "FAIL-1"   # C3-05b
    assert result.failing_records[0].billed is None          # C3-05c


# ── C3-06: Missing ERP row → FAIL-2 ─────────────────────────────────

def test_missing_erp_row_fail2(db_connection, test_session_id):
    sid = test_session_id
    _insert_grain(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))
    _insert_billing(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))
    # No ERP row inserted

    result = execute_check3(db_connection, sid)
    assert result.verdict == "FAIL"                          # C3-06a
    assert result.failing_records[0].fail_type == "FAIL-2"   # C3-06b
    assert result.failing_records[0].posted is None          # C3-06c


# ── C3-07: CONTRACT BOUNDARY — unallocated rows excluded (L2 P1 #18) ─

def test_unallocated_rows_excluded(db_connection, test_session_id):
    """
    Critical contract boundary test.
    Unallocated rows (capacity_idle, identity_broken) MUST NOT be checked
    against billing/ERP. Without the WHERE filter, these produce spurious
    FAIL-1 verdicts because no billing row exists for 'unallocated'.
    """
    sid = test_session_id
    # Insert one valid Type A pair that fully matches
    _insert_grain(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))
    _insert_billing(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))
    _insert_erp(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))

    # Insert unallocated rows — no billing/ERP rows for 'unallocated'
    _insert_unallocated_grain(db_connection, sid, "capacity_idle")

    result = execute_check3(db_connection, sid)
    assert result.verdict == "PASS"                          # C3-07


# ── C3-08: Multiple tenants — mixed results ──────────────────────────

def test_multiple_tenants_mixed(db_connection, test_session_id):
    sid = test_session_id
    # tenant-1: all match → PASS
    _insert_grain(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))
    _insert_billing(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))
    _insert_erp(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))
    # tenant-2: computed ≠ billed → FAIL-1
    _insert_grain(db_connection, sid, "tenant-2", "2026-03", Decimal("200.00"))
    _insert_billing(db_connection, sid, "tenant-2", "2026-03", Decimal("150.00"))
    _insert_erp(db_connection, sid, "tenant-2", "2026-03", Decimal("150.00"))

    result = execute_check3(db_connection, sid)
    assert result.verdict == "FAIL"                          # C3-08a
    assert result.failing_count == 1                         # C3-08b
    assert result.failing_records[0].allocation_target == "tenant-2"  # C3-08c


# ── C3-09: Same tenant, different billing_periods ────────────────────

def test_same_tenant_different_periods(db_connection, test_session_id):
    sid = test_session_id
    # 2026-03: match
    _insert_grain(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))
    _insert_billing(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))
    _insert_erp(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))
    # 2026-04: mismatch
    _insert_grain(db_connection, sid, "tenant-1", "2026-04", Decimal("200.00"))
    _insert_billing(db_connection, sid, "tenant-1", "2026-04", Decimal("180.00"))
    _insert_erp(db_connection, sid, "tenant-1", "2026-04", Decimal("180.00"))

    result = execute_check3(db_connection, sid)
    assert result.verdict == "FAIL"                          # C3-09a
    assert result.failing_records[0].billing_period == "2026-04"  # C3-09b


# ── C3-10: Empty allocation_grain → FAIL with detail ────────────────

def test_empty_grain_fails(db_connection, test_session_id):
    sid = test_session_id
    # No grain rows — or only unallocated rows (same effect after filter)
    result = execute_check3(db_connection, sid)
    assert result.verdict == "FAIL"                          # C3-10a
    assert "allocation_grain" in result.detail               # C3-10b


# ── C3-11: Failing record fields populated correctly ─────────────────

def test_failing_record_fields(db_connection, test_session_id):
    sid = test_session_id
    _insert_grain(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))
    _insert_billing(db_connection, sid, "tenant-1", "2026-03", Decimal("80.00"))
    _insert_erp(db_connection, sid, "tenant-1", "2026-03", Decimal("80.00"))

    result = execute_check3(db_connection, sid)
    rec = result.failing_records[0]
    assert rec.allocation_target == "tenant-1"               # C3-11a
    assert rec.billing_period == "2026-03"                   # C3-11b
    assert rec.computed == Decimal("100.00")                 # C3-11c
    assert rec.billed == Decimal("80.00")                    # C3-11d


# ── C3-12: session_id filter — cross-session isolation ───────────────

def test_session_id_filter(db_connection, test_session_id):
    sid = test_session_id
    other_sid = uuid4()
    # Register other session
    db_connection.execute(
        text("""
            INSERT INTO raw.ingestion_log (session_id, source_files, status)
            VALUES (:sid, '["other.csv"]', 'COMMITTED')
        """),
        {"sid": str(other_sid)},
    )
    # Current session: all match
    _insert_grain(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))
    _insert_billing(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))
    _insert_erp(db_connection, sid, "tenant-1", "2026-03", Decimal("100.00"))

    # Other session: mismatch — must NOT contaminate current session
    _insert_grain(db_connection, other_sid, "tenant-1", "2026-03", Decimal("999.00"))
    _insert_billing(db_connection, other_sid, "tenant-1", "2026-03", Decimal("1.00"))
    _insert_erp(db_connection, other_sid, "tenant-1", "2026-03", Decimal("1.00"))

    result = execute_check3(db_connection, sid)
    assert result.verdict == "PASS"                          # C3-12
