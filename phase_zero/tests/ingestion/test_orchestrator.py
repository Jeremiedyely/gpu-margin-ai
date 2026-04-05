"""
Unit tests for the Ingestion Orchestrator.
8 assertions: ORCH-01 through ORCH-08.
No database required — orchestrator does validate + parse only.
"""

from __future__ import annotations

import textwrap

from app.ingestion.orchestrator import UploadedFile, run_orchestration


def _make_files(
    telemetry=None, cost_management=None, iam=None, billing=None, erp=None
) -> dict[str, UploadedFile]:
    """Helper to build a full set of 5 UploadedFile objects."""
    defaults = {
        "telemetry": textwrap.dedent("""\
            tenant_id,region,gpu_pool_id,date,gpu_hours_consumed
            tenant-a,us-east-1,pool-1,2025-01-15,10.5
        """),
        "cost_management": textwrap.dedent("""\
            region,gpu_pool_id,date,reserved_gpu_hours,cost_per_gpu_hour
            us-east-1,pool-1,2025-01-15,100.0,2.50
        """),
        "iam": textwrap.dedent("""\
            tenant_id,billing_period,contracted_rate
            tenant-a,2025-01,3.50
        """),
        "billing": textwrap.dedent("""\
            tenant_id,billing_period,billable_amount
            tenant-a,2025-01,1500.00
        """),
        "erp": textwrap.dedent("""\
            tenant_id,billing_period,amount_posted
            tenant-a,2025-01,1500.00
        """),
    }

    overrides = {
        "telemetry": telemetry,
        "cost_management": cost_management,
        "iam": iam,
        "billing": billing,
        "erp": erp,
    }

    result = {}
    for slot, default_content in defaults.items():
        content = overrides[slot] if overrides[slot] is not None else default_content
        result[slot] = UploadedFile(
            slot=slot, filename=f"{slot}.csv", content=content
        )
    return result


# ---------------------------------------------------------------------------
# ORCH-01  Full success — all 5 files valid and parsed
# ---------------------------------------------------------------------------
def test_full_success():
    files = _make_files()
    payload = run_orchestration(files)

    assert payload.result == "SUCCESS"                          # ORCH-01


# ---------------------------------------------------------------------------
# ORCH-02  session_id is generated
# ---------------------------------------------------------------------------
def test_session_id_generated():
    files = _make_files()
    payload = run_orchestration(files)

    assert payload.session_id is not None                       # ORCH-02


# ---------------------------------------------------------------------------
# ORCH-03  source_files collected on success
# ---------------------------------------------------------------------------
def test_source_files_collected():
    files = _make_files()
    payload = run_orchestration(files)

    assert len(payload.source_files) == 5                       # ORCH-03


# ---------------------------------------------------------------------------
# ORCH-04  parsed_records contains all 5 slots on success
# ---------------------------------------------------------------------------
def test_parsed_records_all_slots():
    files = _make_files()
    payload = run_orchestration(files)

    assert set(payload.parsed_records.keys()) == {
        "telemetry", "cost_management", "iam", "billing", "erp"
    }                                                           # ORCH-04


# ---------------------------------------------------------------------------
# ORCH-05  Single file validation failure → FAIL
# ---------------------------------------------------------------------------
def test_single_validation_failure():
    bad_telemetry = "wrong_col_a,wrong_col_b\n1,2\n"
    files = _make_files(telemetry=bad_telemetry)
    payload = run_orchestration(files)

    assert payload.result == "FAIL"                             # ORCH-05


# ---------------------------------------------------------------------------
# ORCH-06  Errors list populated on failure
# ---------------------------------------------------------------------------
def test_errors_populated_on_failure():
    bad_telemetry = "wrong_col_a,wrong_col_b\n1,2\n"
    files = _make_files(telemetry=bad_telemetry)
    payload = run_orchestration(files)

    assert len(payload.errors) > 0                              # ORCH-06a
    assert "telemetry" in payload.errors[0].lower()             # ORCH-06b


# ---------------------------------------------------------------------------
# ORCH-07  Missing file slot → FAIL
# ---------------------------------------------------------------------------
def test_missing_slot_fails():
    files = _make_files()
    del files["erp"]
    payload = run_orchestration(files)

    assert payload.result == "FAIL"                             # ORCH-07a
    assert "erp" in payload.errors[0].lower()                   # ORCH-07b


# ---------------------------------------------------------------------------
# ORCH-08  Parse failure mid-pipeline → FAIL
# ---------------------------------------------------------------------------
def test_parse_failure():
    bad_iam = textwrap.dedent("""\
        tenant_id,billing_period,contracted_rate
        tenant-a,2025-01,not_a_number
    """)
    files = _make_files(iam=bad_iam)
    payload = run_orchestration(files)

    assert payload.result == "FAIL"                             # ORCH-08a
    assert "iam" in payload.errors[0].lower()                   # ORCH-08b
