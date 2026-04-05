"""
Root test configuration — shared engine for all test suites.

One engine, NullPool, session-scoped. Every sub-conftest inherits this
engine and defines its own db_connection + test_session_id fixtures.

NullPool ensures each test gets a truly fresh ODBC connection and no
zombie pooled connections accumulate across modules during a full
pytest run.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool


DEFAULT_URL = (
    "mssql+pyodbc://sa:1Liquidagents99!@localhost:1433"
    "/gpu_margin?driver=ODBC+Driver+17+for+SQL+Server&encrypt=no"
)


@pytest.fixture(scope="session")
def engine() -> Engine:
    """Single shared engine for the entire test session."""
    url = os.environ.get("TEST_DATABASE_URL", DEFAULT_URL)
    eng = create_engine(url, future=True, poolclass=NullPool)
    yield eng
    eng.dispose()
