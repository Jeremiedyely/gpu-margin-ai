"""
File Delivery Handler — Tests (FDH-01 → FDH-05).

Returns computer:// link for generated file.
"""

import pytest
from pathlib import Path

from app.export.file_delivery_handler import deliver_file, DeliveryResult


class TestFileDeliveryHandler:
    """Step 7.10 — File Delivery Handler."""

    # FDH-01: success returns computer:// link
    def test_fdh_01_success_link(self, tmp_path):
        filepath = tmp_path / "export.csv"
        filepath.write_text("header\ndata\n")
        result = deliver_file(filepath)
        assert result.result == "SUCCESS"
        assert result.link.startswith("computer://")
        assert "export.csv" in result.link

    # FDH-02: nonexistent file returns FAIL
    def test_fdh_02_nonexistent_file(self, tmp_path):
        filepath = tmp_path / "missing.csv"
        result = deliver_file(filepath)
        assert result.result == "FAIL"
        assert "not found" in result.error

    # FDH-03: empty file returns FAIL
    def test_fdh_03_empty_file(self, tmp_path):
        filepath = tmp_path / "empty.csv"
        filepath.write_text("")
        result = deliver_file(filepath)
        assert result.result == "FAIL"
        assert "empty" in result.error.lower()

    # FDH-04: filepath field populated on success
    def test_fdh_04_filepath_populated(self, tmp_path):
        filepath = tmp_path / "export.xlsx"
        filepath.write_text("data")
        result = deliver_file(filepath)
        assert result.filepath is not None
        assert "export.xlsx" in result.filepath

    # FDH-05: link resolves to correct path
    def test_fdh_05_link_resolves(self, tmp_path):
        filepath = tmp_path / "test.txt"
        filepath.write_text("pipe|data\n")
        result = deliver_file(filepath)
        # Strip computer:// prefix and verify the path exists
        resolved = result.link.replace("computer://", "")
        assert Path(resolved).exists()
