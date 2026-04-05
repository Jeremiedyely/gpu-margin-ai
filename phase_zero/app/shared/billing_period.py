"""
Billing Period Derivation — Shared Constant Module.

Contract 1: All components that derive or compare billing_period
must import from this module. No inline derivation permitted.

Coupled components:
  - Billing Period Deriver (Allocation Engine, Component 2)
  - IAM Resolver (Allocation Engine, Component 4)
  - Check 2 Executor (Reconciliation Engine)
  - Check 3 Executor (Reconciliation Engine)

Derivation: YYYY-MM truncation from ISO 8601 date.
  2026-03-15 → "2026-03"

Spec: allocation-engine-design.md — Billing Period Contract (S1)
      software-system-design.md — Contract 1
"""

from __future__ import annotations

from datetime import date


def derive_billing_period(d: date) -> str:
    """
    Derive billing_period from a date.

    Parameters
    ----------
    d : date
        ISO 8601 date (YYYY-MM-DD).

    Returns
    -------
    str
        YYYY-MM truncation (first 7 characters of ISO representation).
    """
    return d.isoformat()[:7]
