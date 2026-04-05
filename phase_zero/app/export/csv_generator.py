"""
CSV Generator — Component 5/9.

Layer: Export.

Writes CSV using EXPORT_COLUMN_ORDER imported constant.
Uses Python csv stdlib. Column order matches constant — never inline.

Spec: build-checklist.md — Step 7.6
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from app.export.column_order import EXPORT_COLUMN_ORDER


def generate_csv(
    rows: list[dict[str, Any]],
    output_dir: Path,
    session_id_str: str,
) -> Path:
    """
    Generate a CSV export file.

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
        Absolute path to the generated CSV file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / f"gpu_margin_export_{session_id_str}.csv"

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(EXPORT_COLUMN_ORDER),
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows:
            # Coerce all values to strings for CSV, None → empty
            out_row = {
                col: ("" if row.get(col) is None else str(row[col]))
                for col in EXPORT_COLUMN_ORDER
            }
            writer.writerow(out_row)

    return filepath.resolve()
