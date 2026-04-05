"""
Ingestion Orchestrator — Component 16/19.

Generates session_id before any writes begin.
Coordinates validation and parsing for all 5 source files.
Does NOT write to the database — that responsibility belongs
to the Ingestion Commit (Component 17), which owns the transaction.

Spec: ingestion-module-design.md — Layer 4 — Orchestration
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.ingestion.validators.telemetry import validate_telemetry_file
from app.ingestion.validators.cost_management import validate_cost_management_file
from app.ingestion.validators.iam import validate_iam_file
from app.ingestion.validators.billing import validate_billing_file
from app.ingestion.validators.erp import validate_erp_file

from app.ingestion.parsers.telemetry import parse_telemetry_file
from app.ingestion.parsers.cost_management import parse_cost_management_file
from app.ingestion.parsers.iam import parse_iam_file
from app.ingestion.parsers.billing import parse_billing_file
from app.ingestion.parsers.erp import parse_erp_file


class OrchestrationPayload(BaseModel):
    """Result of the ingestion orchestration (validate + parse)."""

    result: Literal["SUCCESS", "FAIL"]
    session_id: UUID
    source_files: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    parsed_records: dict[str, list[Any]] = Field(default_factory=dict)

    @classmethod
    def success(
        cls,
        session_id: UUID,
        source_files: list[str],
        parsed_records: dict[str, list[Any]],
    ) -> OrchestrationPayload:
        return cls(
            result="SUCCESS",
            session_id=session_id,
            source_files=source_files,
            parsed_records=parsed_records,
        )

    @classmethod
    def failed(
        cls, session_id: UUID, errors: list[str]
    ) -> OrchestrationPayload:
        return cls(result="FAIL", session_id=session_id, errors=errors)


@dataclass
class UploadedFile:
    """One uploaded CSV file with its slot name and raw content."""

    slot: str
    filename: str
    content: str


# Pipeline registry: slot → (validator, parser)
_PIPELINES = {
    "telemetry": (validate_telemetry_file, parse_telemetry_file),
    "cost_management": (validate_cost_management_file, parse_cost_management_file),
    "iam": (validate_iam_file, parse_iam_file),
    "billing": (validate_billing_file, parse_billing_file),
    "erp": (validate_erp_file, parse_erp_file),
}

# Deterministic slot order
_SLOT_ORDER = ["telemetry", "cost_management", "iam", "billing", "erp"]


def run_orchestration(
    files: dict[str, UploadedFile],
) -> OrchestrationPayload:
    """
    Validate and parse all 5 source files. No database access.

    Parameters
    ----------
    files : dict[str, UploadedFile]
        Map of slot name → UploadedFile. All 5 slots required.

    Returns
    -------
    OrchestrationPayload
        SUCCESS with session_id, source_files, and parsed_records.
        FAIL with session_id and consolidated error list.
    """
    # ── Generate session_id BEFORE any processing ──
    try:
        session_id = uuid4()
    except Exception as exc:
        return OrchestrationPayload.failed(
            session_id=UUID("00000000-0000-0000-0000-000000000000"),
            errors=[f"Session ID generation failed: {exc}"],
        )

    # ── Validate all 5 slots are present ──
    required_slots = set(_SLOT_ORDER)
    missing = required_slots - set(files.keys())
    if missing:
        return OrchestrationPayload.failed(
            session_id=session_id,
            errors=[f"Missing required file slots: {sorted(missing)}"],
        )

    errors: list[str] = []
    source_files: list[str] = []
    parsed_records: dict[str, list[Any]] = {}

    for slot in _SLOT_ORDER:
        uploaded = files[slot]
        source_files.append(uploaded.filename)
        validator, parser = _PIPELINES[slot]

        # ── Layer 1: Validate ──
        validation = validator(uploaded.content)
        if validation.verdict == "FAIL":
            error_msgs = "; ".join(e.message for e in validation.errors)
            errors.append(f"{slot}: validation failed — {error_msgs}")
            continue

        # ── Layer 2: Parse ──
        parse_result = parser(uploaded.content)
        if parse_result.result == "FAIL":
            errors.append(f"{slot}: parse failed — {parse_result.error}")
            continue

        parsed_records[slot] = parse_result.records

    # ── Collect results ──
    if errors:
        return OrchestrationPayload.failed(
            session_id=session_id, errors=errors
        )

    return OrchestrationPayload.success(
        session_id=session_id,
        source_files=source_files,
        parsed_records=parsed_records,
    )
