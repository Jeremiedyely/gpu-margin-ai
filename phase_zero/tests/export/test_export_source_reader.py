"""
Export Source Reader — Tests (ESR-01 → ESR-06).

Reads from final.allocation_result for the approved session.
"""

import uuid
import pytest
from sqlalchemy import text

from app.export.export_source_reader import read_export_source
from app.export.column_order import GRAIN_COLUMNS


class TestExportSourceReader:
    """Step 7.2 — Export Source Reader."""

    # ESR-01: reads 3 fixture rows for the test session
    def test_esr_01_reads_fixture_rows(self, db_connection, test_session_id):
        rows = read_export_source(db_connection, test_session_id)
        assert len(rows) == 3

    # ESR-02: each row has all grain columns
    def test_esr_02_grain_columns_present(self, db_connection, test_session_id):
        rows = read_export_source(db_connection, test_session_id)
        for row in rows:
            for col in GRAIN_COLUMNS:
                assert col in row, f"Missing column: {col}"

    # ESR-03: no rows from other sessions
    def test_esr_03_no_cross_session_rows(self, db_connection, test_session_id):
        other_sid = uuid.uuid4()
        rows = read_export_source(db_connection, other_sid)
        assert len(rows) == 0

    # ESR-04: rows contain correct allocation_target values
    def test_esr_04_allocation_targets(self, db_connection, test_session_id):
        rows = read_export_source(db_connection, test_session_id)
        targets = {r["allocation_target"] for r in rows}
        assert "tenant-A" in targets
        assert "unallocated" in targets

    # ESR-05: unallocated_type values are correct
    def test_esr_05_unallocated_types(self, db_connection, test_session_id):
        rows = read_export_source(db_connection, test_session_id)
        types = {r["unallocated_type"] for r in rows}
        assert "identity_broken" in types
        assert "capacity_idle" in types

    # ESR-06: empty session returns empty list
    def test_esr_06_empty_session(self, db_connection):
        # Create a session with no allocation_result rows
        sid = uuid.uuid4()
        db_connection.execute(
            text("""
                INSERT INTO raw.ingestion_log (session_id, source_files, status)
                VALUES (:sid, '["empty.csv"]', 'COMMITTED')
            """),
            {"sid": str(sid)},
        )
        rows = read_export_source(db_connection, sid)
        assert rows == []
