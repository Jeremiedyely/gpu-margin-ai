"""
Reconciliation Result Reader Tests — Step 6.7.

Tests: RRR-01 through RRR-10
Assertions: 14
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, text

from app.ui.reconciliation_result_reader import (
    read_reconciliation_results,
    ReconciliationReaderResult,
    ReconciliationRecord,
)


# ── Helper: insert reconciliation_results rows ──────────────────────

_INSERT_RECON_SQL = text("""
    INSERT INTO dbo.reconciliation_results (
        session_id, check_name, check_order, verdict,
        fail_subtype, failing_count, detail
    ) VALUES (
        :sid, :cn, :co, :v, :fs, :fc, :d
    )
""")


def _insert_all_pass(conn: Connection, sid: UUID) -> None:
    """Insert 3 PASS verdicts."""
    rows = [
        {"sid": str(sid), "cn": "Capacity vs Usage", "co": 1,
         "v": "PASS", "fs": None, "fc": None, "d": None},
        {"sid": str(sid), "cn": "Usage vs Tenant Mapping", "co": 2,
         "v": "PASS", "fs": None, "fc": None, "d": None},
        {"sid": str(sid), "cn": "Computed vs Billed vs Posted", "co": 3,
         "v": "PASS", "fs": None, "fc": None, "d": None},
    ]
    for r in rows:
        conn.execute(_INSERT_RECON_SQL, r)


def _insert_mixed_verdicts(conn: Connection, sid: UUID) -> None:
    """Insert Check 1 PASS, Check 2 FAIL, Check 3 PASS."""
    rows = [
        {"sid": str(sid), "cn": "Capacity vs Usage", "co": 1,
         "v": "PASS", "fs": None, "fc": None, "d": None},
        {"sid": str(sid), "cn": "Usage vs Tenant Mapping", "co": 2,
         "v": "FAIL", "fs": None, "fc": 1,
         "d": "tenant-BROKEN unresolved for 2026-03"},
        {"sid": str(sid), "cn": "Computed vs Billed vs Posted", "co": 3,
         "v": "PASS", "fs": None, "fc": None, "d": None},
    ]
    for r in rows:
        conn.execute(_INSERT_RECON_SQL, r)


def _insert_all_fail(conn: Connection, sid: UUID) -> None:
    """Insert 3 FAIL verdicts."""
    rows = [
        {"sid": str(sid), "cn": "Capacity vs Usage", "co": 1,
         "v": "FAIL", "fs": None, "fc": 2,
         "d": "2 pools over-consumed"},
        {"sid": str(sid), "cn": "Usage vs Tenant Mapping", "co": 2,
         "v": "FAIL", "fs": None, "fc": 1,
         "d": "1 unresolved pair"},
        {"sid": str(sid), "cn": "Computed vs Billed vs Posted", "co": 3,
         "v": "FAIL", "fs": "FAIL-1", "fc": 3,
         "d": "3 billing mismatches"},
    ]
    for r in rows:
        conn.execute(_INSERT_RECON_SQL, r)


# ═══════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════


def test_all_pass(db_connection: Connection, test_session_id: UUID):
    """RRR-01: 3 PASS verdicts → SUCCESS with 3 records."""
    _insert_all_pass(db_connection, test_session_id)
    result = read_reconciliation_results(db_connection, test_session_id)

    assert result.result == "SUCCESS"                               # RRR-01a
    assert result.payload is not None                               # RRR-01b
    assert len(result.payload) == 3                                 # RRR-01c
    assert all(r.verdict == "PASS" for r in result.payload)         # RRR-01d


def test_fixed_order(db_connection: Connection, test_session_id: UUID):
    """RRR-02: Results returned in check_order 1, 2, 3."""
    _insert_all_pass(db_connection, test_session_id)
    result = read_reconciliation_results(db_connection, test_session_id)

    assert result.payload[0].check == "Capacity vs Usage"           # RRR-02a
    assert result.payload[1].check == "Usage vs Tenant Mapping"     # RRR-02b
    assert result.payload[2].check == "Computed vs Billed vs Posted"  # RRR-02c


def test_mixed_verdicts(db_connection: Connection, test_session_id: UUID):
    """RRR-03: Mixed PASS/FAIL → correct verdicts preserved."""
    _insert_mixed_verdicts(db_connection, test_session_id)
    result = read_reconciliation_results(db_connection, test_session_id)

    assert result.result == "SUCCESS"
    assert result.payload[0].verdict == "PASS"                      # RRR-03a
    assert result.payload[1].verdict == "FAIL"                      # RRR-03b
    assert result.payload[2].verdict == "PASS"                      # RRR-03c


def test_all_fail(db_connection: Connection, test_session_id: UUID):
    """RRR-04: 3 FAIL verdicts → SUCCESS with 3 FAIL records."""
    _insert_all_fail(db_connection, test_session_id)
    result = read_reconciliation_results(db_connection, test_session_id)

    assert result.result == "SUCCESS"
    assert all(r.verdict == "FAIL" for r in result.payload)         # RRR-04


def test_no_rows_fail(db_connection: Connection, test_session_id: UUID):
    """RRR-05: No reconciliation rows → FAIL."""
    result = read_reconciliation_results(db_connection, test_session_id)
    assert result.result == "FAIL"                                  # RRR-05


def test_partial_rows_fail(db_connection: Connection, test_session_id: UUID):
    """RRR-06: Only 1 of 3 rows → FAIL (< 3 rows)."""
    db_connection.execute(_INSERT_RECON_SQL, {
        "sid": str(test_session_id), "cn": "Capacity vs Usage", "co": 1,
        "v": "PASS", "fs": None, "fc": None, "d": None,
    })
    result = read_reconciliation_results(db_connection, test_session_id)
    assert result.result == "FAIL"                                  # RRR-06


def test_session_isolation(db_connection: Connection, test_session_id: UUID):
    """RRR-07: Data from another session not included."""
    _insert_all_pass(db_connection, test_session_id)
    # Create second session with all FAIL
    other_sid = uuid4()
    db_connection.execute(
        text("""
            INSERT INTO raw.ingestion_log (session_id, source_files, status)
            VALUES (:sid, :sf, 'COMMITTED')
        """),
        {"sid": str(other_sid), "sf": '["test.csv"]'},
    )
    _insert_all_fail(db_connection, other_sid)

    # Our session should still show all PASS
    result = read_reconciliation_results(db_connection, test_session_id)
    assert result.result == "SUCCESS"
    assert all(r.verdict == "PASS" for r in result.payload)         # RRR-07


def test_wrong_session_no_data(db_connection: Connection, test_session_id: UUID):
    """RRR-08: Query with wrong session_id → FAIL."""
    _insert_all_pass(db_connection, test_session_id)
    wrong_sid = uuid4()
    db_connection.execute(
        text("""
            INSERT INTO raw.ingestion_log (session_id, source_files, status)
            VALUES (:sid, :sf, 'COMMITTED')
        """),
        {"sid": str(wrong_sid), "sf": '["test.csv"]'},
    )
    result = read_reconciliation_results(db_connection, wrong_sid)
    assert result.result == "FAIL"                                  # RRR-08


def test_payload_none_on_fail(db_connection: Connection, test_session_id: UUID):
    """RRR-09: FAIL result → payload is None."""
    result = read_reconciliation_results(db_connection, test_session_id)
    assert result.result == "FAIL"
    assert result.payload is None                                   # RRR-09


def test_record_model_fields(db_connection: Connection, test_session_id: UUID):
    """RRR-10: ReconciliationRecord has exactly 2 fields: check, verdict."""
    fields = set(ReconciliationRecord.model_fields.keys())
    assert fields == {"check", "verdict"}                           # RRR-10
