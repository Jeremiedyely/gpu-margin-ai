"""
EXPORT_COLUMN_ORDER — Tests (COL-01 → COL-07).

Verifies the shared constant module structure.
"""

import pytest

from app.export.column_order import (
    EXPORT_COLUMN_ORDER,
    GRAIN_COLUMNS,
    METADATA_COLUMNS,
)


class TestColumnOrder:
    """Step 7.5 — EXPORT_COLUMN_ORDER constant module."""

    # COL-01: full order is grain + metadata
    def test_col_01_full_order_is_grain_plus_metadata(self):
        assert list(EXPORT_COLUMN_ORDER) == list(GRAIN_COLUMNS) + list(
            METADATA_COLUMNS
        )

    # COL-02: metadata columns are last two
    def test_col_02_metadata_columns_are_last_two(self):
        assert EXPORT_COLUMN_ORDER[-2] == "session_id"
        assert EXPORT_COLUMN_ORDER[-1] == "source_files"

    # COL-03: grain columns count = 13
    def test_col_03_grain_column_count(self):
        assert len(GRAIN_COLUMNS) == 13

    # COL-04: metadata columns count = 2
    def test_col_04_metadata_column_count(self):
        assert len(METADATA_COLUMNS) == 2

    # COL-05: full order count = 15
    def test_col_05_full_order_count(self):
        assert len(EXPORT_COLUMN_ORDER) == 15

    # COL-06: no duplicate column names in full order
    def test_col_06_no_duplicates(self):
        assert len(set(EXPORT_COLUMN_ORDER)) == len(EXPORT_COLUMN_ORDER)

    # COL-07: grain columns match final.allocation_result schema
    def test_col_07_grain_matches_schema(self):
        expected_grain = {
            "region", "gpu_pool_id", "date", "billing_period",
            "allocation_target", "unallocated_type", "failed_tenant_id",
            "gpu_hours", "cost_per_gpu_hour", "contracted_rate",
            "revenue", "cogs", "gross_margin",
        }
        assert set(GRAIN_COLUMNS) == expected_grain
