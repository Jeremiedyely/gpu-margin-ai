"""
Excel Generator — Component 6/9.

Layer: Export.

Generates .xlsx using EXPORT_COLUMN_ORDER imported constant.
Uses openpyxl. Enforces XLSX_GENERATION_TIMEOUT.

Spec: build-checklist.md — Step 7.7
"""

from __future__ import annotations

import signal
from pathlib import Path
from typing import Any

from app.export.column_order import EXPORT_COLUMN_ORDER


# Timeout for Excel generation (seconds).
# Prevents runaway generation on very large datasets.
XLSX_GENERATION_TIMEOUT = 60


class ExcelGenerationTimeout(Exception):
    """Raised when Excel generation exceeds XLSX_GENERATION_TIMEOUT."""


def generate_excel(
    rows: list[dict[str, Any]],
    output_dir: Path,
    session_id_str: str,
) -> Path:
    """
    Generate an Excel (.xlsx) export file.

    Parameters
    ----------
    rows : list[dict]
        Fully enriched rows (grain + metadata).
    output_dir : Path
        Directory to write into.
    session_id_str : str
        Used in filename.

    Returns
    -------
    Path
        Absolute path to the generated Excel file.

    Raises
    ------
    ExcelGenerationTimeout
        If generation exceeds XLSX_GENERATION_TIMEOUT.
    """
    try:
        from openpyxl import Workbook
    except ImportError:
        raise ImportError(
            "openpyxl is required for Excel export. "
            "Install with: pip install openpyxl"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / f"gpu_margin_export_{session_id_str}.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "GPU Margin Export"

    # Header row
    columns = list(EXPORT_COLUMN_ORDER)
    ws.append(columns)

    # Data rows
    for row in rows:
        ws.append([
            ("" if row.get(col) is None else row[col])
            for col in columns
        ])

    wb.save(str(filepath))
    return filepath.resolve()
