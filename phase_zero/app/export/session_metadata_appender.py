"""
Session Metadata Appender — Component 3/9.

Layer: Export.

Resolves source_files from raw.ingestion_log for the session.
Appends session_id and source_files as the last two columns to each row.

Spec: build-checklist.md — Step 7.3
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, text


_SOURCE_FILES_SQL = text("""
    SELECT source_files
    FROM raw.ingestion_log
    WHERE session_id = :sid
""")


def append_session_metadata(
    conn: Connection,
    session_id: UUID,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Append session_id and source_files to each export row.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection.
    session_id : UUID
        The session being exported.
    rows : list[dict]
        Grain rows from Export Source Reader.

    Returns
    -------
    list[dict]
        Same rows with session_id (str) and source_files (str)
        appended as the last two keys.
    """
    # Resolve source_files from ingestion_log
    result = conn.execute(_SOURCE_FILES_SQL, {"sid": str(session_id)})
    row = result.fetchone()

    if row is None:
        source_files_str = "[]"
    else:
        # source_files is stored as JSON array string
        raw_sf = row[0]
        # Validate it's valid JSON, then store as-is
        try:
            json.loads(raw_sf)
            source_files_str = raw_sf
        except (json.JSONDecodeError, TypeError):
            source_files_str = "[]"

    session_id_str = str(session_id)

    return [
        {**r, "session_id": session_id_str, "source_files": source_files_str}
        for r in rows
    ]
