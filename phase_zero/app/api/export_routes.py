"""
Export API routes — serves file downloads for approved sessions.

GET /api/export/{session_id}/{format}
  format: csv | excel | power_bi
  Returns: StreamingResponse with the generated file.

Pipeline: Export Gate Enforcer → Export Source Reader →
          Session Metadata Appender → Format Router →
          Output Verifier → File Delivery (StreamingResponse).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import Connection

from app.api.deps import get_connection
from app.state_machine.export_gate_enforcer import check_export_gate
from app.export.export_source_reader import read_export_source
from app.export.session_metadata_appender import append_session_metadata
from app.export.format_router import route_export
from app.export.output_verifier import verify_output

router = APIRouter(prefix="/api", tags=["export"])

# Temp directory for generated files
EXPORT_DIR = Path("/tmp/gpu_margin_exports")

CONTENT_TYPES = {
    "csv": "text/csv",
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "power_bi": "text/plain",
}

EXTENSIONS = {
    "csv": ".csv",
    "excel": ".xlsx",
    "power_bi": ".txt",
}


@router.get("/export/{session_id}/{fmt}")
def export_file(
    session_id: UUID,
    fmt: Literal["csv", "excel", "power_bi"],
    conn: Connection = Depends(get_connection),
):
    """
    Generate and return an export file for an approved session.

    Enforces the export gate, reads from final.allocation_result,
    appends metadata, generates the file, verifies it, and streams
    it back as a download.
    """
    # Step 1: Export Gate — only APPROVED + write_result=SUCCESS
    gate = check_export_gate(conn, session_id)
    if gate.result != "OPEN":
        raise HTTPException(
            status_code=403,
            detail=f"Export blocked: {gate.reason}",
        )

    # Step 2: Read source rows from final.allocation_result
    rows = read_export_source(conn, session_id)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No approved rows for session {session_id}",
        )

    # Step 3: Append session metadata
    enriched = append_session_metadata(conn, session_id, rows)

    # Step 4: Generate file via Format Router
    session_id_str = str(session_id)
    try:
        filepath = route_export(fmt, enriched, EXPORT_DIR, session_id_str)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"File generation failed: {exc}",
        )

    # Step 5: Verify output
    verification = verify_output(filepath, len(rows), fmt)
    if not verification.all_passed:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Export verification failed",
                "failures": verification.errors,
            },
        )

    # Step 6: Stream file as download
    content_type = CONTENT_TYPES[fmt]
    extension = EXTENSIONS[fmt]
    filename = f"gpu_margin_export_{session_id_str}{extension}"

    def iterfile():
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                yield chunk

    return StreamingResponse(
        iterfile(),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
