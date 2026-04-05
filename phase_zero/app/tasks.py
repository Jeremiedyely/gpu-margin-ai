"""
Celery tasks — GPU Gross Margin Visibility.

Wires the component pipeline into executable Celery tasks:

  run_analysis_pipeline(session_id)
    Called by: /api/analyze endpoint after Analysis Dispatcher succeeds.
    Flow: AE Run Receiver → Telemetry Aggregator → Cost Rate Reader →
          IAM Resolver → Type A Builder → Identity Broken Builder →
          Closure Rule Enforcer → Cost Revenue Calculator → Grain Writer →
          AE Completion Emitter
          ─── parallel ───
          RE Run Receiver → Check 1 + Check 2 (+ Check 3 if AE succeeded) →
          RE Result Aggregator → RE Result Writer → RE Completion Emitter
          ─── then ───
          Engine Completion Collector → UPLOADED→ANALYZED Executor →
          UI Cache Aggregation (KPI + Customer + Region)

  run_approval_pipeline(session_id)
    Called by: /api/approve endpoint.
    Flow: Transition Receiver → Validator → ANALYZED→APPROVED Executor →
          Approved Result Writer → Session Closer

  close_approved_sessions()
    Called by: Celery Beat (every 60s).
    Finds APPROVED sessions with write_result=SUCCESS that aren't TERMINAL yet
    and closes them.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.celery_app import celery_app
from app.api.deps import get_engine

logger = logging.getLogger(__name__)


# ── Allocation Engine Pipeline ────────────────────────────────────────

def _run_allocation_engine(conn, session_id: UUID):
    """
    Execute the full Allocation Engine pipeline.

    Returns AllocationEngineResult (SUCCESS or FAIL).
    """
    from app.allocation.run_receiver import RunSignal, receive_run_signal
    from app.allocation.telemetry_aggregator import aggregate_telemetry
    from app.allocation.billing_period_deriver import derive_billing_periods
    from app.allocation.cost_rate_reader import read_cost_rates
    from app.allocation.iam_resolver import resolve_iam
    from app.allocation.type_a_builder import build_type_a_records
    from app.allocation.identity_broken_builder import build_identity_broken_records
    from app.allocation.closure_rule_enforcer import enforce_closure_rule
    from app.allocation.cost_revenue_calculator import calculate_cost_revenue
    from app.allocation.grain_writer import write_allocation_grain
    from app.allocation.completion_emitter import emit_completion

    # Step 0: Run Receiver
    signal = RunSignal(trigger="ANALYZE", session_id=session_id)
    receiver = receive_run_signal(signal)
    if receiver.result != "READY":
        from app.allocation.completion_emitter import AllocationEngineResult
        return AllocationEngineResult.failed(session_id=session_id, error=receiver.error)

    # Step 1: Aggregate telemetry
    telemetry = aggregate_telemetry(conn, session_id)
    if telemetry.result != "SUCCESS":
        from app.allocation.completion_emitter import AllocationEngineResult
        return AllocationEngineResult.failed(session_id=session_id, error=telemetry.error)

    # Step 2: Derive billing periods (enrich with YYYY-MM)
    enriched = derive_billing_periods(telemetry.records)
    if enriched.result != "SUCCESS":
        from app.allocation.completion_emitter import AllocationEngineResult
        return AllocationEngineResult.failed(session_id=session_id, error=enriched.error)

    # Step 3: Read cost rates
    cost_rates = read_cost_rates(conn, session_id)
    if cost_rates.result != "SUCCESS":
        from app.allocation.completion_emitter import AllocationEngineResult
        return AllocationEngineResult.failed(session_id=session_id, error=cost_rates.error)

    # Step 4: IAM resolve — classify tenants
    iam_result = resolve_iam(conn, session_id, enriched.records)
    if iam_result.result != "SUCCESS":
        from app.allocation.completion_emitter import AllocationEngineResult
        return AllocationEngineResult.failed(session_id=session_id, error=iam_result.error)

    # Step 5: Build Type A records
    type_a = build_type_a_records(iam_result.type_a, cost_rates.records)
    if type_a.result != "SUCCESS":
        from app.allocation.completion_emitter import AllocationEngineResult
        return AllocationEngineResult.failed(session_id=session_id, error=type_a.error)

    # Step 6: Build Identity Broken records
    identity_broken = build_identity_broken_records(
        iam_result.identity_broken, cost_rates.records,
    )
    if identity_broken.result != "SUCCESS":
        from app.allocation.completion_emitter import AllocationEngineResult
        return AllocationEngineResult.failed(session_id=session_id, error=identity_broken.error)

    # Step 7: Enforce closure rule (capacity idle)
    closure = enforce_closure_rule(
        type_a=type_a.records,
        identity_broken=identity_broken.records,
        cost_rates=cost_rates.records,
    )
    if closure.result != "SUCCESS":
        from app.allocation.completion_emitter import AllocationEngineResult
        return AllocationEngineResult.failed(session_id=session_id, error=closure.error)

    # Step 8: Calculate cost/revenue for all record types
    calc = calculate_cost_revenue(
        type_a=type_a.records,
        identity_broken=identity_broken.records,
        capacity_idle=closure.capacity_idle,
    )
    if calc.result != "SUCCESS":
        from app.allocation.completion_emitter import AllocationEngineResult
        return AllocationEngineResult.failed(session_id=session_id, error=calc.error)

    # Step 9: Write allocation grain
    grain_write = write_allocation_grain(conn, session_id, calc.records)

    # Step 10: Emit completion
    return emit_completion(grain_write)


# ── Reconciliation Engine Pipeline ────────────────────────────────────

def _run_reconciliation_engine(conn, session_id: UUID, ae_result):
    """
    Execute the full Reconciliation Engine pipeline.

    Returns ReconciliationEngineResult (SUCCESS or FAIL).
    """
    from app.reconciliation.run_receiver import RERunSignal, receive_re_run_signal
    from app.reconciliation.ae_completion_listener import listen_for_ae_completion
    from app.reconciliation.check1_executor import execute_check1
    from app.reconciliation.check2_executor import execute_check2
    from app.reconciliation.check3_executor import execute_check3
    from app.reconciliation.result_aggregator import aggregate_results
    from app.reconciliation.result_writer import write_reconciliation_results
    from app.reconciliation.completion_emitter import emit_re_completion

    # Step 0: Run Receiver
    signal = RERunSignal(trigger="ANALYZE", session_id=session_id)
    receiver = receive_re_run_signal(signal)
    if receiver.result != "READY":
        from app.reconciliation.completion_emitter import ReconciliationEngineResult
        return ReconciliationEngineResult.failed(
            session_id=session_id, error=receiver.error,
        )

    # Step 1: Check 1 — Capacity vs Usage
    check1 = execute_check1(conn, session_id)

    # Step 2: Check 2 — Usage vs Tenant Mapping
    check2 = execute_check2(conn, session_id)

    # Step 3: AE Completion Listener — gates Check 3
    listener = listen_for_ae_completion(ae_result)

    # Step 4: Check 3 — Computed vs Billed vs Posted (only if AE succeeded)
    if listener.result == "READY":
        check3 = execute_check3(conn, session_id)
    else:
        # AE failed — Check 3 forced to FAIL
        from app.reconciliation.check3_executor import Check3Result
        check3 = Check3Result(
            result="FAIL",
            verdict="FAIL",
            failing_count=0,
            error=f"AE failed — Check 3 blocked: {listener.error}",
        )

    # Step 5: Aggregate results
    aggregated = aggregate_results(check1, check2, check3, session_id)

    # FATAL aggregation — skip writer
    if aggregated.result == "FATAL":
        return emit_re_completion(aggregated=aggregated, session_id=session_id)

    # Step 6: Write reconciliation results
    write_result = write_reconciliation_results(conn, aggregated, session_id)

    # Step 7: Emit completion
    return emit_re_completion(write_result=write_result, session_id=session_id)


# ── UI Cache Aggregation ──────────────────────────────────────────────

def _run_ui_cache_aggregation(conn, session_id: UUID):
    """
    Pre-compute and cache UI aggregator data at ANALYZED time.
    """
    from app.ui.kpi_data_aggregator import aggregate_kpis
    from app.ui.customer_data_aggregator import aggregate_customers
    from app.ui.region_data_aggregator import aggregate_regions

    kpi = aggregate_kpis(conn, session_id)
    if kpi.result != "SUCCESS":
        logger.warning("KPI aggregation failed for %s: %s", session_id, kpi.error)

    customers = aggregate_customers(conn, session_id)
    if customers.result != "SUCCESS":
        logger.warning("Customer aggregation failed for %s: %s", session_id, customers.error)

    # Regions are computed on-demand (no cache), but we call to warm logs
    regions = aggregate_regions(conn, session_id)
    if regions.result != "SUCCESS":
        logger.warning("Region aggregation failed for %s: %s", session_id, regions.error)

    return kpi, customers, regions


# ══════════════════════════════════════════════════════════════════════
# CELERY TASKS
# ══════════════════════════════════════════════════════════════════════


@celery_app.task(name="app.tasks.run_analysis_pipeline", bind=True, max_retries=0)
def run_analysis_pipeline(self, session_id_str: str):
    """
    Full analysis pipeline: Allocation Engine + Reconciliation Engine +
    State Transition + UI Cache.

    Called after Analysis Dispatcher sets analysis_status = ANALYZING.
    """
    from app.state_machine.engine_completion_collector import (
        EngineResult,
        collect_engine_results,
    )
    from app.state_machine.uploaded_to_analyzed_executor import (
        execute_uploaded_to_analyzed,
    )

    session_id = UUID(session_id_str)
    engine = get_engine()

    with engine.connect() as conn:
        with conn.begin():
            # ── Phase 1: Run both engines ──────────────────────────
            ae_result = _run_allocation_engine(conn, session_id)

            logger.info(
                "AE complete for %s: %s", session_id, ae_result.result,
            )

            re_result = _run_reconciliation_engine(conn, session_id, ae_result)

            logger.info(
                "RE complete for %s: %s", session_id, re_result.result,
            )

            # ── Phase 2: Collect results ───────────────────────────
            ae_engine_result = EngineResult(
                engine="ALLOCATION",
                result=ae_result.result,
                session_id=session_id,
                error=ae_result.error,
            )
            re_engine_result = EngineResult(
                engine="RECONCILIATION",
                result=re_result.result,
                session_id=session_id,
                error=re_result.error,
            )

            collection = collect_engine_results(
                conn, ae_engine_result, re_engine_result,
            )

            logger.info(
                "Engine collection for %s: %s", session_id, collection.result,
            )

            # ── Phase 3: State transition ──────────────────────────
            if collection.result == "SUCCESS":
                transition = execute_uploaded_to_analyzed(conn, collection)

                logger.info(
                    "UPLOADED→ANALYZED for %s: %s",
                    session_id, transition.result,
                )

                # ── Phase 4: UI cache aggregation ──────────────────
                if transition.result == "SUCCESS":
                    _run_ui_cache_aggregation(conn, session_id)
                    logger.info("UI cache populated for %s", session_id)
            else:
                logger.warning(
                    "Engine collection FAILED for %s: %s",
                    session_id, collection.errors,
                )

    return {
        "session_id": session_id_str,
        "result": collection.result,
    }


@celery_app.task(name="app.tasks.run_approval_pipeline", bind=True, max_retries=0)
def run_approval_pipeline(self, session_id_str: str):
    """
    Approval pipeline: Validate → ANALYZED→APPROVED Executor →
    Approved Result Writer → Session Closer.

    Called after Approve Confirmation Dialog fires.
    """
    from app.state_machine.transition_request_receiver import (
        TransitionSignal,
        receive_transition_signal,
    )
    from app.state_machine.transition_validator import validate_transition
    from app.state_machine.analyzed_to_approved_executor import (
        execute_analyzed_to_approved,
    )
    from app.state_machine.approved_result_writer import write_approved_result
    from app.state_machine.session_closer import close_session

    session_id = UUID(session_id_str)
    engine = get_engine()

    with engine.connect() as conn:
        with conn.begin():
            # Step 1: Receive transition signal
            signal = TransitionSignal(
                requested_transition="ANALYZED→APPROVED",
                source="APPROVAL_DIALOG",
                session_id=session_id,
            )
            receiver = receive_transition_signal(conn, signal)

            if receiver.result == "ALREADY_COMPLETE":
                logger.info("Approval already complete for %s", session_id)
                return {"session_id": session_id_str, "result": "ALREADY_COMPLETE"}

            if receiver.result != "FORWARD":
                logger.error(
                    "Approval rejected for %s: %s", session_id, receiver.error,
                )
                return {"session_id": session_id_str, "result": "REJECTED", "error": receiver.error}

            # Step 2: Validate transition
            validation = validate_transition(receiver.transition_request)

            if validation.result != "VALID":
                logger.error(
                    "Approval validation failed for %s: %s",
                    session_id, validation.error,
                )
                return {"session_id": session_id_str, "result": "INVALID", "error": validation.error}

            # Step 3: Execute ANALYZED → APPROVED
            approval = execute_analyzed_to_approved(validation)

            if approval.result != "SUCCESS":
                logger.error(
                    "Approval execution failed for %s: %s",
                    session_id, approval.error,
                )
                return {"session_id": session_id_str, "result": "FAIL", "error": approval.error}

            # Step 4: Approved Result Writer (atomic grain copy + APPROVED state)
            write_result = write_approved_result(conn, approval)

            if write_result.result != "SUCCESS":
                logger.error(
                    "Approved result write failed for %s: %s",
                    session_id, write_result.error,
                )
                return {"session_id": session_id_str, "result": "FAIL", "error": write_result.error}

            # Note: Session Closer is NOT called inline. The session stays
            # APPROVED (non-TERMINAL) so the UI can display export controls.
            # The user triggers TERMINAL via POST /api/session/close, or
            # Celery Beat closes it automatically after the retention window.

            logger.info(
                "Session %s approved — awaiting export or close",
                session_id,
            )

    return {
        "session_id": session_id_str,
        "result": "SUCCESS",
        "approved_at": str(write_result.approved_at),
        "row_count": write_result.row_count,
    }


@celery_app.task(name="app.tasks.close_approved_sessions")
def close_approved_sessions():
    """
    Periodic task (Celery Beat — every 60s).

    Finds APPROVED sessions with write_result = SUCCESS that are not yet
    TERMINAL and closes them. Safety net for sessions where the closer
    didn't fire inline during approval.
    """
    from sqlalchemy import text
    from app.state_machine.approved_result_writer import ApprovedWriteResult
    from app.state_machine.session_closer import close_session

    engine = get_engine()

    with engine.connect() as conn:
        with conn.begin():
            # Find APPROVED + SUCCESS sessions that aren't TERMINAL
            rows = conn.execute(text("""
                SELECT session_id
                FROM dbo.state_store
                WHERE application_state = 'APPROVED'
                  AND write_result = 'SUCCESS'
                  AND session_status != 'TERMINAL'
            """)).fetchall()

            closed = 0
            for row in rows:
                sid = row.session_id
                # Build a synthetic ApprovedWriteResult for the closer
                write_result = ApprovedWriteResult(
                    result="SUCCESS",
                    session_id=sid,
                )
                result = close_session(conn, write_result)
                if result.result == "SUCCESS":
                    closed += 1
                    logger.info("Beat closed session %s", sid)
                else:
                    logger.warning(
                        "Beat failed to close session %s: %s",
                        sid, result.error,
                    )

    return {"closed": closed, "found": len(rows)}
