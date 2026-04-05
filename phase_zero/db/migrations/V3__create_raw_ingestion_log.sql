-- V3__create_raw_ingestion_log.sql
-- Table 0: raw.ingestion_log — Session Anchor
-- One row = one ingestion session.
-- Grain relationship: ANCHORS the grain. All 12 other tables FK to session_id.
-- Producer: Ingestion Log Writer (Component 18) — fires only after Ingestion Commit = SUCCESS.

CREATE TABLE raw.ingestion_log (
    session_id      UNIQUEIDENTIFIER    NOT NULL,
    source_files    NVARCHAR(MAX)       NOT NULL,
    ingested_at     DATETIME2           NOT NULL    DEFAULT SYSUTCDATETIME(),
    status          NVARCHAR(20)        NOT NULL    DEFAULT 'FAILED',

    CONSTRAINT PK_ingestion_log
        PRIMARY KEY (session_id),

    -- Binary state: committed or failed — no ambiguous intermediate states
    CONSTRAINT CHK_ingestion_log_status
        CHECK (status IN ('COMMITTED', 'FAILED')),

    -- JSON array structure validation — Export Session Metadata Appender reads source_files as JSON
    -- ISJSON() rejects structurally malformed JSON at ingestion write time
    -- Content-type enforcement (element type, null elements) owned by Ingestion Validator (Component 18)
    CONSTRAINT CHK_ingestion_source_files_json
        CHECK (ISJSON(source_files) = 1)
);
