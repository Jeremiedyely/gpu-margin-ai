"""
Tests for Reconciliation Result Writer — Component 6/7.

DB integration tests. Validates atomic 3-row write, fail_subtype population,
FATAL rejection, savepoint rollback, and session_id isolation.

Assertions: RW-01 through RW-09
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Connection, text

from app.reconciliation.result_aggregator import AggregatedResults, AggregatedRow
from app.reconciliation.result_writer import write_reconciliation_results


# ── Helpers ──────────────────────────────────────────────────────────

def _success_aggregated(sid):
    """Build a valid SUCCESS aggregated result with all PASS verdicts."""
    return AggregatedResults.success(rows=[
        AggregatedRow(
            check_name="Capacity vs Usage", verdict="PASS",
            session_id=sid, failing_count=None, detail=None,
        ),
        AggregatedRow(
            check_name="Usage vs Tenant Mapping", verdict="PASS",
            session_id=sid, failing_count=None, detail=None,
        ),
        AggregatedRow(
            check_name="Computed vs Billed vs Posted", verdict="PASS",
            session_id=sid, failing_count=None, detail=None,
        ),
    ])


def _mixed_aggregated(sid):
    """Build a SUCCESS aggregated result with mixed verdicts including fail_subtype."""
    return AggregatedResults.success(rows=[
        AggregatedRow(
            check_name="Capacity vs Usage", verdict="FAIL",
            session_id=sid, failing_count=1,
            detail='[{"region":"us-east-1"}]',
        ),
        AggregatedRow(
            check_name="Usage vs Tenant Mapping", verdict="PASS",
            session_id=sid, failing_count=None, detail=None,
        ),
        AggregatedRow(
            check_name="Computed vs Billed vs Posted", verdict="FAIL",
            session_id=sid, failing_count=2, fail_subtype="FAIL-1",
            detail='[{"fail_type":"FAIL-1"}]',
        ),
    ])


def _read_results(conn: Connection, sid):
    """Read reconciliation_results rows for a session, ordered by check_name."""
    return conn.execute(
        text("""
            SELECT check_name, verdict, fail_subtype, failing_count, detail
            FROM dbo.reconciliation_results
            WHERE session_id = :sid
            ORDER BY check_name
        """),
        {"sid": str(sid)},
    ).fetchall()


# ── RW-01: All PASS → 3 rows written ────────────────────────────────

def test_all_pass_writes_three_rows(db_connection, test_session_id):
    sid = test_session_id
    agg = _success_aggregated(sid)
    result = write_reconciliation_results(db_connection, agg, sid)
    assert result.result == "SUCCESS"                        # RW-01a
    rows = _read_results(db_connection, sid)
    assert len(rows) == 3                                    # RW-01b


# ── RW-02: check_name values in DB match spec ───────────────────────

def test_check_names_in_db(db_connection, test_session_id):
    sid = test_session_id
    agg = _success_aggregated(sid)
    write_reconciliation_results(db_connection, agg, sid)
    rows = _read_results(db_connection, sid)
    names = {r.check_name for r in rows}
    assert names == {
        "Capacity vs Usage",
        "Usage vs Tenant Mapping",
        "Computed vs Billed vs Posted",
    }                                                        # RW-02


# ── RW-03: Mixed verdicts written correctly ──────────────────────────

def test_mixed_verdicts(db_connection, test_session_id):
    sid = test_session_id
    agg = _mixed_aggregated(sid)
    write_reconciliation_results(db_connection, agg, sid)
    rows = _read_results(db_connection, sid)
    by_name = {r.check_name: r for r in rows}
    assert by_name["Capacity vs Usage"].verdict == "FAIL"                    # RW-03a
    assert by_name["Usage vs Tenant Mapping"].verdict == "PASS"              # RW-03b
    assert by_name["Computed vs Billed vs Posted"].verdict == "FAIL"         # RW-03c


# ── RW-04: fail_subtype written for Check 3 FAIL ────────────────────

def test_fail_subtype_written(db_connection, test_session_id):
    sid = test_session_id
    agg = _mixed_aggregated(sid)
    write_reconciliation_results(db_connection, agg, sid)
    rows = _read_results(db_connection, sid)
    by_name = {r.check_name: r for r in rows}
    assert by_name["Computed vs Billed vs Posted"].fail_subtype == "FAIL-1"  # RW-04a
    assert by_name["Capacity vs Usage"].fail_subtype is None                 # RW-04b
    assert by_name["Usage vs Tenant Mapping"].fail_subtype is None           # RW-04c


# ── RW-05: failing_count written correctly ───────────────────────────

def test_failing_count_written(db_connection, test_session_id):
    sid = test_session_id
    agg = _mixed_aggregated(sid)
    write_reconciliation_results(db_connection, agg, sid)
    rows = _read_results(db_connection, sid)
    by_name = {r.check_name: r for r in rows}
    assert by_name["Capacity vs Usage"].failing_count == 1                   # RW-05a
    assert by_name["Usage vs Tenant Mapping"].failing_count is None          # RW-05b
    assert by_name["Computed vs Billed vs Posted"].failing_count == 2        # RW-05c


# ── RW-06: FATAL aggregation → write skipped ────────────────────────

def test_fatal_aggregation_skipped(db_connection, test_session_id):
    sid = test_session_id
    agg = AggregatedResults.fatal(error="Check 1 source unreadable")
    result = write_reconciliation_results(db_connection, agg, sid)
    assert result.result == "FAIL"                           # RW-06a
    assert "aggregation result" in result.error              # RW-06b
    rows = _read_results(db_connection, sid)
    assert len(rows) == 0                                    # RW-06c


# ── RW-07: Empty rows → FAIL ────────────────────────────────────────

def test_empty_rows_fail(db_connection, test_session_id):
    sid = test_session_id
    agg = AggregatedResults(result="SUCCESS", rows=[])
    result = write_reconciliation_results(db_connection, agg, sid)
    assert result.result == "FAIL"                           # RW-07a
    assert "no rows to write" in result.error                # RW-07b


# ── RW-08: Savepoint rollback on constraint violation ────────────────

def test_savepoint_rollback(db_connection, test_session_id):
    sid = test_session_id
    # Build aggregated with an invalid check_name to trigger DB constraint
    bad_agg = AggregatedResults.success(rows=[
        AggregatedRow(
            check_name="Capacity vs Usage", verdict="PASS",
            session_id=sid,
        ),
        AggregatedRow(
            check_name="INVALID_CHECK", verdict="PASS",
            session_id=sid,
        ),
        AggregatedRow(
            check_name="Computed vs Billed vs Posted", verdict="PASS",
            session_id=sid,
        ),
    ])
    result = write_reconciliation_results(db_connection, bad_agg, sid)
    assert result.result == "FAIL"                           # RW-08a
    assert "rolled back" in result.error                     # RW-08b
    # Confirm no partial write — first valid row also rolled back
    rows = _read_results(db_connection, sid)
    assert len(rows) == 0                                    # RW-08c


# ── RW-09: session_id appended to every row ──────────────────────────

def test_session_id_appended(db_connection, test_session_id):
    sid = test_session_id
    agg = _success_aggregated(sid)
    write_reconciliation_results(db_connection, agg, sid)
    rows = db_connection.execute(
        text("""
            SELECT session_id FROM dbo.reconciliation_results
            WHERE session_id = :sid
        """),
        {"sid": str(sid)},
    ).fetchall()
    assert len(rows) == 3                                    # RW-09a
    assert all(
        str(r.session_id).lower() == str(sid).lower() for r in rows
    )                                                        # RW-09b
