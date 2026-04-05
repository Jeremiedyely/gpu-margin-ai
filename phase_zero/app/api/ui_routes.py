"""
UI data API routes — serves aggregator payloads to the frontend.

GET /api/kpi/{session_id}            → KPI payload (Zone 1)
GET /api/customers/{session_id}      → Customer payload (Zone 2R)
GET /api/regions/{session_id}        → Region payload (Zone 2L)
GET /api/reconciliation/{session_id} → Verdict payload (Zone 3)

All endpoints are pure reads from pre-computed cache or DB.
No aggregation at request time (L2 P2 #30, #31).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Connection

from app.api.deps import get_connection
from app.ui.kpi_data_aggregator import read_kpi_cache, KPIPayload
from app.ui.customer_data_aggregator import (
    read_identity_broken_set,
    CustomerRecord,
)
from app.ui.region_data_aggregator import aggregate_regions, RegionRecord
from app.ui.reconciliation_result_reader import (
    read_reconciliation_results,
    ReconciliationRecord,
)

# Re-import the aggregators for the compute-at-ANALYZED-time path
from app.ui.customer_data_aggregator import aggregate_customers

router = APIRouter(prefix="/api", tags=["ui"])


# ── KPI (Zone 1) ────────────────────────────────────────────────────

class KPIResponse(BaseModel):
    """Zone 1 KPI card data."""
    gpu_revenue: Decimal
    gpu_cogs: Decimal
    idle_gpu_cost: Decimal
    idle_gpu_cost_pct: Decimal
    cost_allocation_rate: Decimal


@router.get("/kpi/{session_id}", response_model=KPIResponse)
def get_kpi(
    session_id: UUID,
    conn: Connection = Depends(get_connection),
) -> KPIResponse:
    """Read pre-computed KPI values from cache."""
    result = read_kpi_cache(conn, session_id)
    if result.result != "SUCCESS" or result.payload is None:
        raise HTTPException(
            status_code=404,
            detail=result.error or f"No KPI data for session {session_id}",
        )
    p = result.payload
    return KPIResponse(
        gpu_revenue=p.gpu_revenue,
        gpu_cogs=p.gpu_cogs,
        idle_gpu_cost=p.idle_gpu_cost,
        idle_gpu_cost_pct=p.idle_gpu_cost_pct,
        cost_allocation_rate=p.cost_allocation_rate,
    )


# ── Customers (Zone 2R) ─────────────────────────────────────────────

class CustomerResponse(BaseModel):
    """Zone 2R customer data."""
    payload: list[CustomerRecord]
    identity_broken_tenants: list[str]


@router.get("/customers/{session_id}", response_model=CustomerResponse)
def get_customers(
    session_id: UUID,
    conn: Connection = Depends(get_connection),
) -> CustomerResponse:
    """
    Read customer aggregation data.

    Re-computes per-customer metrics from allocation_grain (the
    identity_broken SET is read from the pre-built cache).
    """
    result = aggregate_customers(conn, session_id)
    if result.result != "SUCCESS":
        raise HTTPException(
            status_code=404,
            detail=result.error or f"No customer data for session {session_id}",
        )
    return CustomerResponse(
        payload=result.payload,
        identity_broken_tenants=sorted(result.identity_broken_set),
    )


# ── Regions (Zone 2L) ───────────────────────────────────────────────

class RegionResponse(BaseModel):
    """Zone 2L region data."""
    payload: list[RegionRecord]


@router.get("/regions/{session_id}", response_model=RegionResponse)
def get_regions(
    session_id: UUID,
    conn: Connection = Depends(get_connection),
) -> RegionResponse:
    """Read regional gross margin aggregation."""
    result = aggregate_regions(conn, session_id)
    if result.result != "SUCCESS":
        raise HTTPException(
            status_code=404,
            detail=result.error or f"No region data for session {session_id}",
        )
    return RegionResponse(payload=result.payload)


# ── Reconciliation (Zone 3) ─────────────────────────────────────────

class VerdictResponse(BaseModel):
    """Zone 3 reconciliation verdict data."""
    payload: list[ReconciliationRecord]
    session_id: UUID


@router.get("/reconciliation/{session_id}", response_model=VerdictResponse)
def get_reconciliation(
    session_id: UUID,
    conn: Connection = Depends(get_connection),
) -> VerdictResponse:
    """Read reconciliation verdicts for the session."""
    result = read_reconciliation_results(conn, session_id)
    if result.result != "SUCCESS":
        raise HTTPException(
            status_code=404,
            detail=result.error or f"No reconciliation data for session {session_id}",
        )
    return VerdictResponse(
        payload=result.payload,
        session_id=session_id,
    )
