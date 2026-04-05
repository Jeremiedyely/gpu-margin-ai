"""
EXPORT_COLUMN_ORDER — Shared Constant Module.

Single source of truth for the column ordering in all export formats
(CSV, Excel, Power BI). Contract 5: all 4 coupled components — CSV
Generator, Excel Generator, Power BI Generator, and Output Verifier —
MUST import from this module. No inline column list in any generator.

Grain columns from final.allocation_result + metadata columns appended
by Session Metadata Appender (session_id, source_files as last two).

Note: session_id is already a grain column. The metadata version is
retained because the spec requires it as one of the "last two columns".
We keep session_id in its grain position AND as a metadata confirmation.
"""

from __future__ import annotations

from typing import Sequence

# ── Grain columns (from final.allocation_result) ──────────────────
GRAIN_COLUMNS: Sequence[str] = (
    "region",
    "gpu_pool_id",
    "date",
    "billing_period",
    "allocation_target",
    "unallocated_type",
    "failed_tenant_id",
    "gpu_hours",
    "cost_per_gpu_hour",
    "contracted_rate",
    "revenue",
    "cogs",
    "gross_margin",
)

# ── Metadata columns (appended by Session Metadata Appender) ──────
METADATA_COLUMNS: Sequence[str] = (
    "session_id",
    "source_files",
)

# ── Full export column order ───────────────────────────────────────
EXPORT_COLUMN_ORDER: Sequence[str] = (*GRAIN_COLUMNS, *METADATA_COLUMNS)
