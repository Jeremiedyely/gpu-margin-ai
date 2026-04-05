"""
Format Router — Tests (FMR-01 → FMR-05).

Dispatches to exactly one generator per request.
"""

import pytest
from pathlib import Path

from app.export.format_router import route_export


# Minimal row fixture (matches EXPORT_COLUMN_ORDER)
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
        "session_id": "test-sess-id",
        "source_files": '["test.csv"]',
    },
]


class TestFormatRouter:
    """Step 7.4 — Format Router."""

    # FMR-01: routes to CSV
    def test_fmr_01_routes_csv(self, tmp_path):
        path = route_export("csv", MOCK_ROWS, tmp_path, "test-sess")
        assert path.suffix == ".csv"
        assert path.exists()

    # FMR-02: routes to Excel
    def test_fmr_02_routes_excel(self, tmp_path):
        path = route_export("excel", MOCK_ROWS, tmp_path, "test-sess")
        assert path.suffix == ".xlsx"
        assert path.exists()

    # FMR-03: routes to Power BI
    def test_fmr_03_routes_power_bi(self, tmp_path):
        path = route_export("power_bi", MOCK_ROWS, tmp_path, "test-sess")
        assert path.suffix == ".txt"
        assert path.exists()

    # FMR-04: invalid format raises ValueError
    def test_fmr_04_invalid_format_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Unsupported export format"):
            route_export("xml", MOCK_ROWS, tmp_path, "test-sess")

    # FMR-05: each format produces exactly one file
    def test_fmr_05_one_file_per_format(self, tmp_path):
        route_export("csv", MOCK_ROWS, tmp_path / "a", "test-sess")
        route_export("excel", MOCK_ROWS, tmp_path / "b", "test-sess")
        route_export("power_bi", MOCK_ROWS, tmp_path / "c", "test-sess")
        assert len(list((tmp_path / "a").iterdir())) == 1
        assert len(list((tmp_path / "b").iterdir())) == 1
        assert len(list((tmp_path / "c").iterdir())) == 1
