"""
Output Verifier — Tests (OV-01 → OV-10).

6 checks validated across CSV, Excel, and Power BI files.
"""

import csv
import pytest
from pathlib import Path

from app.export.output_verifier import verify_output, VerificationResult
from app.export.csv_generator import generate_csv
from app.export.excel_generator import generate_excel
from app.export.power_bi_generator import generate_power_bi
from app.export.column_order import EXPORT_COLUMN_ORDER


MOCK_ROWS = [
    {
        "region": "us-east-1",
        "gpu_pool_id": "pool-a",
        "date": "2026-01-15",
        "billing_period": "2026-01",
        "allocation_target": "tenant-A",
        "unallocated_type": "",
        "failed_tenant_id": "",
        "gpu_hours": "100.000000",
        "cost_per_gpu_hour": "2.500000",
        "contracted_rate": "4.000000",
        "revenue": "400.00",
        "cogs": "250.00",
        "gross_margin": "150.00",
        "session_id": "test-sess",
        "source_files": '["test.csv"]',
    },
    {
        "region": "us-east-1",
        "gpu_pool_id": "pool-a",
        "date": "2026-01-15",
        "billing_period": "2026-01",
        "allocation_target": "unallocated",
        "unallocated_type": "capacity_idle",
        "failed_tenant_id": "",
        "gpu_hours": "30.000000",
        "cost_per_gpu_hour": "3.000000",
        "contracted_rate": "",
        "revenue": "0.00",
        "cogs": "90.00",
        "gross_margin": "-90.00",
        "session_id": "test-sess",
        "source_files": '["test.csv"]',
    },
]


class TestOutputVerifier:
    """Step 7.9 — Output Verifier (6 checks)."""

    # OV-01: CSV passes all 6 checks
    def test_ov_01_csv_all_pass(self, tmp_path):
        path = generate_csv(MOCK_ROWS, tmp_path, "sess-1")
        result = verify_output(path, expected_row_count=2, file_format="csv")
        assert result.all_passed, f"Errors: {result.errors}"

    # OV-02: Excel passes all 6 checks
    def test_ov_02_excel_all_pass(self, tmp_path):
        path = generate_excel(MOCK_ROWS, tmp_path, "sess-1")
        result = verify_output(path, expected_row_count=2, file_format="excel")
        assert result.all_passed, f"Errors: {result.errors}"

    # OV-03: Power BI passes all 6 checks
    def test_ov_03_power_bi_all_pass(self, tmp_path):
        path = generate_power_bi(MOCK_ROWS, tmp_path, "sess-1")
        result = verify_output(
            path, expected_row_count=2, file_format="power_bi"
        )
        assert result.all_passed, f"Errors: {result.errors}"

    # OV-04: Check 1 — nonexistent file fails
    def test_ov_04_check1_file_not_found(self, tmp_path):
        fake = tmp_path / "nonexistent.csv"
        result = verify_output(fake, expected_row_count=0, file_format="csv")
        assert not result.check_1_file_exists
        assert not result.all_passed

    # OV-05: Check 2 — wrong row count fails
    def test_ov_05_check2_wrong_row_count(self, tmp_path):
        path = generate_csv(MOCK_ROWS, tmp_path, "sess-1")
        result = verify_output(path, expected_row_count=99, file_format="csv")
        assert result.check_1_file_exists
        assert not result.check_2_row_count_match

    # OV-06: Check 3 — missing column fails
    def test_ov_06_check3_missing_column(self, tmp_path):
        # Write a CSV with a missing column
        path = tmp_path / "bad.csv"
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["region", "session_id", "source_files"])
            writer.writerow(["us-east-1", "sess", "[]"])
        result = verify_output(path, expected_row_count=1, file_format="csv")
        assert not result.check_3_columns_present

    # OV-07: Check 4 — invalid subtype fails
    def test_ov_07_check4_invalid_subtype(self, tmp_path):
        bad_rows = [
            {**MOCK_ROWS[0], "unallocated_type": "INVALID_TYPE"},
        ]
        path = generate_csv(bad_rows, tmp_path, "sess-1")
        result = verify_output(path, expected_row_count=1, file_format="csv")
        assert not result.check_4_subtypes_correct

    # OV-08: Check 6 — metadata columns must be last two
    def test_ov_08_check6_metadata_last_two(self, tmp_path):
        path = generate_csv(MOCK_ROWS, tmp_path, "sess-1")
        result = verify_output(path, expected_row_count=2, file_format="csv")
        assert result.check_6_metadata_format

    # OV-09: all_passed property works
    def test_ov_09_all_passed_true(self, tmp_path):
        path = generate_csv(MOCK_ROWS, tmp_path, "sess-1")
        result = verify_output(path, expected_row_count=2, file_format="csv")
        assert result.all_passed is True

    # OV-10: errors list populated on failure
    def test_ov_10_errors_populated(self, tmp_path):
        fake = tmp_path / "nonexistent.csv"
        result = verify_output(fake, expected_row_count=0, file_format="csv")
        assert len(result.errors) > 0
