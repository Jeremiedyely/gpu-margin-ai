"""
Power BI Generator — Component 7/9.

Layer: Export.

Writes pipe-delimited file using EXPORT_COLUMN_ORDER imported constant.
source_files is pipe-delimited within the field (already JSON array).

Spec: build-checklist.md — Step 7.8
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from app.export.column_order import EXPORT_COLUMN_ORDER


def generate_power_bi(
    rows: list[dict[str, Any]],
    output_dir: Path,
    session_id_str: str,
) -> Path:
    """
    Generate a pipe-delimited export file for Power BI.

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
        Absolute path to the generated pipe-delimited file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / f"gpu_margin_export_{session_id_str}.txt"

    columns = list(EXPORT_COLUMN_ORDER)

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=columns,
            delimiter="|",
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows:
            out_row = {
                col: ("" if row.get(col) is None else str(row[col]))
                for col in columns
            }
            writer.writerow(out_row)

    return filepath.resolve()
