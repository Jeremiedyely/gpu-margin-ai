"""
Integration tests for the cost management raw-table writer.
6 assertions: CMW-01 through CMW-06.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.ingestion.parsers.cost_management import CostManagementRecord
from app.ingestion.writers.cost_management import write_cost_management


def test_single_record_success(db_connection, test_session_id):
    records = [
        CostManagementRecord(
            region="us-east-1",
            gpu_pool_id="pool-1",
            date=date(2025, 1, 15),
            reserved_gpu_hours=Decimal("100.0"),
            cost_per_gpu_hour=Decimal("2.50"),
        )
    ]
    result = write_cost_management(db_connection, test_session_id, records)
    assert result.result == "SUCCESS"                           # CMW-01


def test_row_count_matches(db_connection, test_session_id):
    records = [
        CostManagementRecord(
            region=f"region-{i}",
            gpu_pool_id="pool-1",
            date=date(2025, 1, 15),
            reserved_gpu_hours=Decimal("100.0"),
            cost_per_gpu_hour=Decimal("2.50"),
        )
        for i in range(3)
    ]
    result = write_cost_management(db_connection, test_session_id, records)
    assert result.row_count == 3                                # CMW-02


def test_data_round_trip(db_connection, test_session_id):
    records = [
        CostManagementRecord(
            region="us-east-1",
            gpu_pool_id="pool-1",
            date=date(2025, 1, 15),
            reserved_gpu_hours=Decimal("100.5"),
            cost_per_gpu_hour=Decimal("2.75"),
        )
    ]
    write_cost_management(db_connection, test_session_id, records)

    row = db_connection.execute(
        text("SELECT region, gpu_pool_id, date, reserved_gpu_hours, cost_per_gpu_hour "
             "FROM raw.cost_management WHERE session_id = :sid"),
        {"sid": str(test_session_id)},
    ).fetchone()

    assert row[0] == "us-east-1"                                # CMW-03a
    assert row[1] == "pool-1"                                   # CMW-03b
    assert row[2] == date(2025, 1, 15)                          # CMW-03c
    assert row[3] == Decimal("100.500000")                      # CMW-03d
    assert row[4] == Decimal("2.750000")                        # CMW-03e


def test_empty_list_returns_success(db_connection, test_session_id):
    result = write_cost_management(db_connection, test_session_id, [])
    assert result.result == "SUCCESS"                           # CMW-04a
    assert result.row_count == 0                                # CMW-04b


def test_session_id_returned(db_connection, test_session_id):
    records = [
        CostManagementRecord(
            region="us-east-1",
            gpu_pool_id="pool-1",
            date=date(2025, 1, 15),
            reserved_gpu_hours=Decimal("100.0"),
            cost_per_gpu_hour=Decimal("2.50"),
        )
    ]
    result = write_cost_management(db_connection, test_session_id, records)
    assert result.session_id == test_session_id                 # CMW-05


def test_invalid_session_id_returns_fail(db_connection):
    bad_sid = __import__("uuid").uuid4()
    records = [
        CostManagementRecord(
            region="us-east-1",
            gpu_pool_id="pool-1",
            date=date(2025, 1, 15),
            reserved_gpu_hours=Decimal("100.0"),
            cost_per_gpu_hour=Decimal("2.50"),
        )
    ]
    result = write_cost_management(db_connection, bad_sid, records)
    assert result.result == "FAIL"                              # CMW-06a
    assert result.error is not None                             # CMW-06b
