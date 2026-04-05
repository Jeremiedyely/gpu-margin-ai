"""
Upload + Action API routes — ingestion, analysis trigger, and approval.

POST /api/upload              → Ingest 5 CSV files, fire EMPTY→UPLOADED
POST /api/analyze             → Dispatch analysis (UPLOADED→ANALYZED)
POST /api/approve             → Approve results (ANALYZED→APPROVED)

Upload accepts multipart/form-data with 5 file fields:
  telemetry, cost_management, iam, billing, erp
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.deps import get_engine
from app.ingestion.orchestrator import UploadedFile, run_orchestration
from app.ingestion.commit import run_ingestion_commit
from app.state_machine.transition_request_receiver import (
    TransitionSignal,
    receive_transition_signal,
)
from app.state_machine.transition_validator import validate_transition
from app.state_machine.empty_to_uploaded_executor import execute_empty_to_uploaded
from app.state_machine.analysis_dispatcher import dispatch_analysis


router = APIRouter(prefix="/api", tags=["actions"])


# ── Upload ─────────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    result: str
    session_id: UUID | None = None
    errors: list[str] | None = None


@router.post("/upload", response_model=UploadResponse)
async def upload_files(
    telemetry: UploadFile = File(...),
    cost_management: UploadFile = File(...),
    iam: UploadFile = File(...),
    billing: UploadFile = File(...),
    erp: UploadFile = File(...),
):
    """
    Ingest 5 CSV files → orchestrate → commit → EMPTY→UPLOADED.

    This is the entry point for the entire pipeline. Returns session_id
    on success; the UI polls /api/state to see the new state.
    """
    # Read file contents
    files = {}
    for slot, upload in [
        ("telemetry", telemetry),
        ("cost_management", cost_management),
        ("iam", iam),
        ("billing", billing),
        ("erp", erp),
    ]:
        raw = await upload.read()
        files[slot] = UploadedFile(
            slot=slot,
            filename=upload.filename or f"{slot}.csv",
            content=raw.decode("utf-8"),
        )

    # Orchestrate (validate + parse — no DB)
    payload = run_orchestration(files)

    if payload.result == "FAIL":
        raise HTTPException(
            status_code=422,
            detail={"result": "FAIL", "errors": payload.errors},
        )

    # Commit (atomic DB write)
    engine = get_engine()
    commit = run_ingestion_commit(engine, payload)

    if commit.result == "FAIL":
        raise HTTPException(
            status_code=500,
            detail={"result": "FAIL", "errors": [commit.reason]},
        )

    session_id = commit.session_id

    # State transition: EMPTY → UPLOADED
    with engine.connect() as state_conn:
        with state_conn.begin():
            signal = TransitionSignal(
                requested_transition="EMPTY→UPLOADED",
                source="INGESTION",
                session_id=session_id,
            )
            receiver = receive_transition_signal(state_conn, signal)

            if receiver.result == "ALREADY_COMPLETE":
                return UploadResponse(result="SUCCESS", session_id=session_id)

            if receiver.result != "FORWARD":
                raise HTTPException(
                    status_code=500,
                    detail={
                        "result": "FAIL",
                        "errors": [
                            f"State transition rejected: {receiver.error}"
                        ],
                    },
                )

            validation = validate_transition(receiver.transition_request)
            if validation.result != "VALID":
                raise HTTPException(
                    status_code=500,
                    detail={
                        "result": "FAIL",
                        "errors": [
                            f"State transition invalid: {validation.error}"
                        ],
                    },
                )

            exec_result = execute_empty_to_uploaded(state_conn, validation)
            if exec_result.result != "SUCCESS":
                raise HTTPException(
                    status_code=500,
                    detail={
                        "result": "FAIL",
                        "errors": [
                            f"State transition failed: {exec_result.error}"
                        ],
                    },
                )

    return UploadResponse(result="SUCCESS", session_id=session_id)


# ── Analyze ────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    session_id: UUID


class AnalyzeResponse(BaseModel):
    result: str
    session_id: UUID | None = None
    error: str | None = None


@router.post("/analyze", response_model=AnalyzeResponse)
def trigger_analysis(req: AnalyzeRequest):
    """
    Dispatch analysis engines for the given session.

    Sets analysis_status = ANALYZING, then fires the Celery task
    that runs both engines + state transition + UI cache.

    Uses explicit engine transaction — the dependency-injected connection
    has no auto-commit, so dispatch_analysis writes would be rolled back
    on connection close. Same pattern as the upload endpoint.
    """
    session_id = req.session_id
    engine = get_engine()

    with engine.connect() as conn:
        with conn.begin():
            # Validate transition
            signal = TransitionSignal(
                requested_transition="UPLOADED→ANALYZED",
                source="UI_ANALYZE",
                session_id=session_id,
            )
            receiver = receive_transition_signal(conn, signal)

            if receiver.result == "ALREADY_COMPLETE":
                return AnalyzeResponse(
                    result="ALREADY_COMPLETE", session_id=session_id,
                )

            if receiver.result != "FORWARD":
                raise HTTPException(
                    status_code=400,
                    detail=receiver.error or "Transition rejected",
                )

            validation = validate_transition(receiver.transition_request)

            if validation.result != "VALID":
                raise HTTPException(
                    status_code=400,
                    detail=validation.error or "Invalid transition",
                )

            # Dispatch — sets analysis_status = ANALYZING
            dispatch = dispatch_analysis(conn, validation)

            if dispatch.result != "DISPATCHED":
                raise HTTPException(
                    status_code=400,
                    detail=dispatch.error or "Dispatch failed",
                )

    # Fire Celery task AFTER commit — ensures ANALYZING state is visible
    from app.tasks import run_analysis_pipeline
    run_analysis_pipeline.delay(str(session_id))

    return AnalyzeResponse(result="DISPATCHED", session_id=session_id)


# ── Approve ────────────────────────────────────────────────────────────

class ApproveRequest(BaseModel):
    session_id: UUID


class ApproveResponse(BaseModel):
    result: str
    session_id: UUID | None = None
    error: str | None = None


@router.post("/approve", response_model=ApproveResponse)
def trigger_approval(req: ApproveRequest):
    """
    Trigger the approval pipeline for the given session.

    Fires a Celery task that runs the full ANALYZED→APPROVED→TERMINAL chain.
    """
    session_id = req.session_id

    # Fire Celery task (async — runs in worker)
    from app.tasks import run_approval_pipeline
    run_approval_pipeline.delay(str(session_id))

    return ApproveResponse(result="SUBMITTED", session_id=session_id)
