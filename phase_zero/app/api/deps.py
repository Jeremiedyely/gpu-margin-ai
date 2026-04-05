"""
Shared API dependencies — database engine + connection factory.

All API routes use get_connection() as a FastAPI dependency.
Connection is created per-request and closed after response.
"""

from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine, Connection
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool


DEFAULT_URL = (
    "mssql+pyodbc://sa:1Liquidagents99!@localhost:1433"
    "/gpu_margin?driver=ODBC+Driver+17+for+SQL+Server&encrypt=no"
)

_engine: Engine | None = None


def get_engine() -> Engine:
    """Lazy-create a single engine for the application lifetime."""
    global _engine
    if _engine is None:
        url = os.environ.get("DATABASE_URL", DEFAULT_URL)
        _engine = create_engine(url, future=True, pool_size=5)
    return _engine


def get_connection() -> Generator[Connection, None, None]:
    """
    FastAPI dependency — yields a connection per request.

    No automatic commit — read-only endpoints.
    Write endpoints (approve, upload) manage their own transactions.
    """
    engine = get_engine()
    conn = engine.connect()
    try:
        yield conn
    finally:
        conn.close()
