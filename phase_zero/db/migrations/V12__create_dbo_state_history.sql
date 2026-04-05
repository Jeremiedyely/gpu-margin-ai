-- V12__create_dbo_state_history.sql
-- Table 9: dbo.state_history — Lifecycle Audit Trail
-- One row = one state transition event.
-- Grain relationship: CONTROLS the grain — append-only audit of every lifecycle change.
-- Producer: SM State Persist (written atomically with every state_store update).
-- Consumers: Operator diagnostics · session reconstruction · compliance audit.
CREATE TABLE dbo.state_history (
    id                      BIGINT              NOT NULL    IDENTITY(1,1),
    session_id              UNIQUEIDENTIFIER    NOT NULL,
    from_state              NVARCHAR(10)        NOT NULL,
    to_state                NVARCHAR(10)        NOT NULL,
    transition_trigger      NVARCHAR(50)        NOT NULL,
    transitioned_at         DATETIME2           NOT NULL    DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_state_history
        PRIMARY KEY (id),
    CONSTRAINT FK_history_session
        FOREIGN KEY (session_id)
        REFERENCES raw.ingestion_log(session_id),
    ------------------------------------------------------------
    -- ENUM CONSTRAINTS
    ------------------------------------------------------------
    CONSTRAINT CHK_history_from_state
        CHECK (
            from_state IN ('EMPTY', 'UPLOADED', 'ANALYZED', 'APPROVED')
        ),
    CONSTRAINT CHK_history_to_state
        CHECK (
            to_state IN ('EMPTY', 'UPLOADED', 'ANALYZED', 'APPROVED')
        ),
    CONSTRAINT CHK_history_trigger
        CHECK (
            transition_trigger IN (
                'INGESTION_COMPLETE',
                'ANALYSIS_DISPATCHED',
                'ENGINES_COMPLETE',
                'CFO_APPROVAL',
                'ANALYSIS_FAILED',
                'SESSION_CLOSED',
                'SYSTEM_RECOVERY'
            )
        ),
    ------------------------------------------------------------
    -- SELF-TRANSITION GUARD
    ------------------------------------------------------------
    CONSTRAINT CHK_history_no_self_transition
        CHECK (
            from_state <> to_state
            OR transition_trigger = 'SYSTEM_RECOVERY'
        ),
    ------------------------------------------------------------
    -- TIMESTAMP SANITY (NEW HARDENING)
    ------------------------------------------------------------
    CONSTRAINT CHK_history_timestamp
        CHECK (transitioned_at <= SYSUTCDATETIME())
);
------------------------------------------------------------
-- INDEX 1 — Session timeline reconstruction
------------------------------------------------------------
CREATE INDEX IX_history_session_timeline
    ON dbo.state_history (session_id, transitioned_at, id);
