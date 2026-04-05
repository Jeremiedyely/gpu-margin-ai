"""
Tests for Reconciliation Result Aggregator — Component 5/7.

Pure logic tests — no DB. Validates three-row assembly, check_name values,
verdict pass-through, detail serialization, and fatal error detection.

Assertions: RA-01 through RA-12
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from app.reconciliation.check1_executor import Check1FailingRecord, Check1Result
from app.reconciliation.check2_executor import Check2Result, UnresolvedPair
from app.reconciliation.check3_executor import Check3FailingRecord, Check3Result
from app.reconciliation.result_aggregator import aggregate_results


# ── Helpers ──────────────────────────────────────────────────────────

def _check1_pass(sid):
    return Check1Result.passed(session_id=sid)


def _check1_fail(sid):
    rec = Check1FailingRecord(
        region="us-east-1", gpu_pool_id="pool-A",
        date="2026-03-15", consumed=Decimal("120"),
        reserved=Decimal("100"), excess=Decimal("20"),
    )
    return Check1Result.failed(session_id=sid, records=[rec])


def _check1_fatal(sid):
    return Check1Result.error(
        session_id=sid,
        detail="Check 1 could not execute — source unreadable: raw.telemetry",
    )


def _check2_pass(sid):
    return Check2Result.passed(session_id=sid)


def _check2_fail(sid):
    pair = UnresolvedPair(tenant_id="tenant-X", billing_period="2026-03")
    return Check2Result.failed(session_id=sid, pairs=[pair])


def _check2_fatal(sid):
    return Check2Result.error(
        session_id=sid,
        detail="Check 2 could not execute — source unreadable: raw.iam",
    )


def _check3_pass(sid):
    return Check3Result.passed(session_id=sid)


def _check3_fail(sid):
    rec = Check3FailingRecord(
        allocation_target="tenant-1", billing_period="2026-03",
        fail_type="FAIL-1", computed=Decimal("100"),
        billed=Decimal("90"), posted=Decimal("90"),
    )
    return Check3Result.failed(session_id=sid, records=[rec])


def _check3_fatal(sid):
    return Check3Result.error(
        session_id=sid,
        detail="Check 3 could not execute — source unreadable: allocation_grain",
    )


# ── RA-01: All PASS → SUCCESS with 3 rows ───────────────────────────

def test_all_pass_success():
    sid = uuid4()
    result = aggregate_results(
        _check1_pass(sid), _check2_pass(sid), _check3_pass(sid), sid,
    )
    assert result.result == "SUCCESS"                        # RA-01a
    assert len(result.rows) == 3                             # RA-01b


# ── RA-02: check_name values match spec exactly ─────────────────────

def test_check_name_values():
    sid = uuid4()
    result = aggregate_results(
        _check1_pass(sid), _check2_pass(sid), _check3_pass(sid), sid,
    )
    assert result.rows[0].check_name == "Capacity vs Usage"             # RA-02a
    assert result.rows[1].check_name == "Usage vs Tenant Mapping"       # RA-02b
    assert result.rows[2].check_name == "Computed vs Billed vs Posted"  # RA-02c


# ── RA-03: Verdicts passed through correctly ─────────────────────────

def test_verdicts_passed_through():
    sid = uuid4()
    result = aggregate_results(
        _check1_fail(sid), _check2_pass(sid), _check3_fail(sid), sid,
    )
    assert result.rows[0].verdict == "FAIL"                  # RA-03a
    assert result.rows[1].verdict == "PASS"                  # RA-03b
    assert result.rows[2].verdict == "FAIL"                  # RA-03c


# ── RA-04: session_id on every row ───────────────────────────────────

def test_session_id_on_every_row():
    sid = uuid4()
    result = aggregate_results(
        _check1_pass(sid), _check2_pass(sid), _check3_pass(sid), sid,
    )
    assert all(row.session_id == sid for row in result.rows)  # RA-04


# ── RA-05: failing_count passed through ──────────────────────────────

def test_failing_count_passed_through():
    sid = uuid4()
    result = aggregate_results(
        _check1_fail(sid), _check2_fail(sid), _check3_pass(sid), sid,
    )
    assert result.rows[0].failing_count == 1                 # RA-05a
    assert result.rows[1].failing_count == 1                 # RA-05b
    assert result.rows[2].failing_count is None              # RA-05c


# ── RA-06: PASS rows have no detail ─────────────────────────────────

def test_pass_rows_no_detail():
    sid = uuid4()
    result = aggregate_results(
        _check1_pass(sid), _check2_pass(sid), _check3_pass(sid), sid,
    )
    assert all(row.detail is None for row in result.rows)    # RA-06


# ── RA-07: FAIL rows have serialized detail ──────────────────────────

def test_fail_rows_have_detail():
    sid = uuid4()
    result = aggregate_results(
        _check1_fail(sid), _check2_fail(sid), _check3_fail(sid), sid,
    )
    # Check 1 detail — deserializable JSON with failing record fields
    detail1 = json.loads(result.rows[0].detail)
    assert detail1[0]["region"] == "us-east-1"               # RA-07a

    # Check 2 detail — unresolved pairs
    detail2 = json.loads(result.rows[1].detail)
    assert detail2[0]["tenant_id"] == "tenant-X"             # RA-07b

    # Check 3 detail — failing records with fail_type
    detail3 = json.loads(result.rows[2].detail)
    assert detail3[0]["fail_type"] == "FAIL-1"               # RA-07c


# ── RA-08: Fatal check1 → FATAL ─────────────────────────────────────

def test_fatal_check1():
    sid = uuid4()
    result = aggregate_results(
        _check1_fatal(sid), _check2_pass(sid), _check3_pass(sid), sid,
    )
    assert result.result == "FATAL"                          # RA-08a
    assert "Check 1" in result.error                         # RA-08b


# ── RA-09: Fatal check2 → FATAL ─────────────────────────────────────

def test_fatal_check2():
    sid = uuid4()
    result = aggregate_results(
        _check1_pass(sid), _check2_fatal(sid), _check3_pass(sid), sid,
    )
    assert result.result == "FATAL"                          # RA-09a
    assert "Check 2" in result.error                         # RA-09b


# ── RA-10: Fatal check3 → FATAL ─────────────────────────────────────

def test_fatal_check3():
    sid = uuid4()
    result = aggregate_results(
        _check1_pass(sid), _check2_pass(sid), _check3_fatal(sid), sid,
    )
    assert result.result == "FATAL"                          # RA-10a
    assert "Check 3" in result.error                         # RA-10b


# ── RA-11: Multiple fatals → all named in error ─────────────────────

def test_multiple_fatals():
    sid = uuid4()
    result = aggregate_results(
        _check1_fatal(sid), _check2_fatal(sid), _check3_pass(sid), sid,
    )
    assert result.result == "FATAL"                          # RA-11a
    assert "Check 1" in result.error                         # RA-11b
    assert "Check 2" in result.error                         # RA-11c


# ── RA-12: FATAL has no rows ────────────────────────────────────────

def test_fatal_has_no_rows():
    sid = uuid4()
    result = aggregate_results(
        _check1_fatal(sid), _check2_pass(sid), _check3_pass(sid), sid,
    )
    assert result.rows == []                                 # RA-12
