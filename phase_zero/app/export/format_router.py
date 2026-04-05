"""
Format Router — Component 4/9.

Layer: Export.

Dispatches to exactly one generator per request.
Supported formats: csv, excel, power_bi.

Spec: build-checklist.md — Step 7.4
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from app.export.csv_generator import generate_csv
from app.export.excel_generator import generate_excel
from app.export.power_bi_generator import generate_power_bi


ExportFormat = Literal["csv", "excel", "power_bi"]


def route_export(
    fmt: ExportFormat,
    rows: list[dict[str, Any]],
    output_dir: Path,
    session_id_str: str,
) -> Path:
    """
    Dispatch to exactly one generator and return the output file path.

    Parameters
    ----------
    fmt : ExportFormat
        One of "csv", "excel", "power_bi".
    rows : list[dict]
        Fully enriched rows (grain + metadata).
    output_dir : Path
        Directory to write the generated file into.
    session_id_str : str
        Used in the output filename.

    Returns
    -------
    Path
        Absolute path to the generated file.

    Raises
    ------
    ValueError
        If fmt is not a recognized format.
    """
    if fmt == "csv":
        return generate_csv(rows, output_dir, session_id_str)
    elif fmt == "excel":
        return generate_excel(rows, output_dir, session_id_str)
    elif fmt == "power_bi":
        return generate_power_bi(rows, output_dir, session_id_str)
    else:
        raise ValueError(f"Unsupported export format: {fmt}")
