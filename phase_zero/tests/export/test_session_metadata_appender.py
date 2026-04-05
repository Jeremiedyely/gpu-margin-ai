"""
Session Metadata Appender — Tests (SMA-01 → SMA-06).

Appends session_id and source_files as last two columns.
"""

import json
import uuid
import pytest
from sqlalchemy import text

from app.export.session_metadata_appender import append_session_metadata
from app.export.column_order import METADATA_COLUMNS
from tests.export.conftest import SOURCE_FILES_FIXTURE


class TestSessionMetadataAppender:
    """Step 7.3 — Session Metadata Appender."""

    # SMA-01: appends session_id to each row
    def test_sma_01_appends_session_id(self, db_connection, test_session_id):
        rows = [{"region": "us-east-1"}]
        enriched = append_session_metadata(
            db_connection, test_session_id, rows
        )
        assert enriched[0]["session_id"] == str(test_session_id)

    # SMA-02: appends source_files as JSON string
    def test_sma_02_appends_source_files(self, db_connection, test_session_id):
        rows = [{"region": "us-east-1"}]
        enriched = append_session_metadata(
            db_connection, test_session_id, rows
        )
        sf = json.loads(enriched[0]["source_files"])
        assert sf == SOURCE_FILES_FIXTURE

    # SMA-03: metadata keys are last two in dict
    def test_sma_03_metadata_keys_last(self, db_connection, test_session_id):
        rows = [{"region": "us-east-1", "gpu_pool_id": "pool-a"}]
        enriched = append_session_metadata(
            db_connection, test_session_id, rows
        )
        keys = list(enriched[0].keys())
        assert keys[-2] == "session_id"
        assert keys[-1] == "source_files"

    # SMA-04: preserves original grain columns
    def test_sma_04_preserves_grain(self, db_connection, test_session_id):
        rows = [{"region": "us-east-1", "revenue": "400.00"}]
        enriched = append_session_metadata(
            db_connection, test_session_id, rows
        )
        assert enriched[0]["region"] == "us-east-1"
        assert enriched[0]["revenue"] == "400.00"

    # SMA-05: multiple rows all get metadata
    def test_sma_05_multiple_rows(self, db_connection, test_session_id):
        rows = [{"region": "us-east-1"}, {"region": "eu-west-1"}]
        enriched = append_session_metadata(
            db_connection, test_session_id, rows
        )
        assert len(enriched) == 2
        for r in enriched:
            assert "session_id" in r
            assert "source_files" in r

    # SMA-06: missing ingestion_log returns empty source_files
    def test_sma_06_missing_ingestion_log(self, db_connection):
        unknown_sid = uuid.uuid4()
        rows = [{"region": "us-east-1"}]
        enriched = append_session_metadata(
            db_connection, unknown_sid, rows
        )
        assert enriched[0]["source_files"] == "[]"
