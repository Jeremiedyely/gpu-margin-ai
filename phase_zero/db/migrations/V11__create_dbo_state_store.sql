-- V11__create_dbo_state_store.sql
-- Table 8: dbo.state_store — Lifecycle Control
-- One row = one session's lifecycle state.
-- Grain relationship: CONTROLS the grain — gates analysis, approval, and export.
-- Producer: SM Approved Result Writer (C9) — writes APPROVED + write_result in ONE atomic transaction (P1 #26).
-- Consumers: Export Gate Enforcer · UI Screen Router · UI Footer Control Manager
CREATE TABLE dbo.state_store (
    session_id          UNIQUEIDENTIFIER    NOT NULL,
    application_state   NVARCHAR(10)        NOT NULL,
    session_status      NVARCHAR(10)        NOT NULL,
    analysis_status     NVARCHAR(10)        NOT NULL,
    write_result        NVARCHAR(10)        NULL,
    retry_count         INT                 NOT NULL DEFAULT 0,
    CONSTRAINT PK_state_store
        PRIMARY KEY (session_id),
    CONSTRAINT FK_state_store_session
        FOREIGN KEY (session_id)
        REFERENCES raw.ingestion_log(session_id),
    ------------------------------------------------------------
    -- ENUM CONSTRAINTS
    ------------------------------------------------------------
    CONSTRAINT CHK_state_application
        CHECK (
            application_state IN
            ('EMPTY', 'UPLOADED', 'ANALYZED', 'APPROVED')
        ),
    CONSTRAINT CHK_state_session_status
        CHECK (
            session_status IN ('ACTIVE', 'TERMINAL')
        ),
    CONSTRAINT CHK_state_analysis_status
        CHECK (
            analysis_status IN ('IDLE', 'ANALYZING')
        ),
    CONSTRAINT CHK_state_write_result
        CHECK (
            write_result IS NULL
            OR write_result IN ('SUCCESS', 'FAIL')
        ),
    ------------------------------------------------------------
    -- STRUCTURAL INVARIANTS
    ------------------------------------------------------------
    -- APPROVED requires write_result
    CONSTRAINT CHK_state_approved_requires_write_result
        CHECK (
            application_state <> 'APPROVED'
            OR write_result IS NOT NULL
        ),
    -- write_result requires APPROVED
    CONSTRAINT CHK_state_write_result_requires_approved
        CHECK (
            write_result IS NULL
            OR application_state = 'APPROVED'
        ),
    -- TERMINAL only valid after APPROVED
    CONSTRAINT CHK_state_terminal_requires_approved
        CHECK (
            session_status <> 'TERMINAL'
            OR application_state = 'APPROVED'
        ),
    ------------------------------------------------------------
    -- ANALYSIS STATUS SCOPE
    ------------------------------------------------------------
    CONSTRAINT CHK_state_analysis_status_scope
        CHECK (
            analysis_status = 'IDLE'
            OR application_state = 'UPLOADED'
        ),
    ------------------------------------------------------------
    -- EMPTY STATE CONSISTENCY (NEW HARDENING)
    ------------------------------------------------------------
    CONSTRAINT CHK_state_empty_consistency
        CHECK (
            application_state <> 'EMPTY'
            OR (
                session_status = 'ACTIVE'
                AND analysis_status = 'IDLE'
                AND write_result IS NULL
            )
        ),
    ------------------------------------------------------------
    -- RETRY CEILING
    ------------------------------------------------------------
    CONSTRAINT CHK_state_retry_count
        CHECK (
            retry_count >= 0
            AND retry_count <= 100
        )
);
------------------------------------------------------------
-- DESIGN DECISION (R6-W-1): APPROVED + FAIL Structural Permission
-- Schema permits application_state = 'APPROVED' with write_result = 'FAIL'.
-- This represents: C9 completed atomic write but grain copy failed.
-- Export gate must enforce BOTH:
--   application_state = 'APPROVED'
--   write_result = 'SUCCESS'
------------------------------------------------------------
