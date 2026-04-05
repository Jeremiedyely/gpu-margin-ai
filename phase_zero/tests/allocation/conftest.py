"""
Shared fixtures for allocation engine integration tests.

Each test runs inside a transaction that is rolled back after the test,
so no test data persists in the database.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, Connection


DEFAULT_URL = (
    "mssql+pyodbc://sa:1Liquidagents99!@localhost:1433"
    "/gpu_margin?driver=ODBC+Driver+17+for+SQL+Server&encrypt=no"
)


@pytest.fixture(scope="session")
def engine() -> Engine:
    """Create a single engine for the entire test session."""
    url = os.environ.get("TEST_DATABASE_URL", DEFAULT_URL)
    return create_engine(url, future=True)


@pytest.fixture()
def db_connection(engine: Engine):
    """
    Yield a connection wrapped in a transaction.

    After the test, the transaction is rolled back so the database
    stays clean between tests.
    """
    conn = engine.connect()
    txn = conn.begin()
    try:
        yield conn
    finally:
        txn.rollback()
        conn.close()


@pytest.fixture()
def test_session_id(db_connection: Connection) -> uuid.UUID:
    """
    Insert a row into ingestion_log and return its session_id.

    FK constraints on raw tables reference ingestion_log.session_id,
    so every integration test needs a valid session in the log first.
    """
    sid = uuid.uuid4()
    db_connection.execute(
        text("""
            INSERT INTO raw.ingestion_log (session_id, source_files, status)
            VALUES (:sid, :source_files, 'COMMITTED')
        """),
        {"sid": str(sid), "source_files": '["test_fixture.csv"]'},
    )
    return sid
