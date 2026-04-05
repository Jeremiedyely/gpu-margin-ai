-- V6__create_raw_iam.sql
-- Table 3: raw.iam — Identity & Rate Source
-- One row = one contracted rate for one tenant in one billing period.
-- Grain relationship: FEEDS the grain — identity and rate dimension.
-- Producer: IAM Raw Table Writer (Component 13)
-- Deployment prerequisite P1 #8: IX_iam_resolver MUST exist before first analysis run.
-- Path A: CHAR(7) for billing_period — consistent across all 5 tables (K2 coupling contract)

CREATE TABLE raw.iam (
    id              BIGINT              NOT NULL    IDENTITY(1,1),
    session_id      UNIQUEIDENTIFIER    NOT NULL,
    tenant_id       NVARCHAR(255)       NOT NULL,
    billing_period  CHAR(7)             NOT NULL,
    contracted_rate DECIMAL(18,6)       NOT NULL,

    CONSTRAINT PK_iam
        PRIMARY KEY (id),

    CONSTRAINT FK_iam_session
        FOREIGN KEY (session_id)
        REFERENCES raw.ingestion_log(session_id),

    CONSTRAINT UQ_iam_natural_key
        UNIQUE (session_id, tenant_id, billing_period),

    CONSTRAINT CHK_iam_billing_period
        CHECK (
            billing_period LIKE '[0-9][0-9][0-9][0-9]-[0-1][0-9]'
            AND SUBSTRING(billing_period, 6, 2) BETWEEN '01' AND '12'
        ),

    CONSTRAINT CHK_iam_rate
        CHECK (contracted_rate >= 0)
);
------------------------------------------------------------
-- INDEX 1 — IAM Resolver (Phase 0 covering index, Option B inlined)
-- Session-scoped LEFT JOIN ON (tenant_id, billing_period)
-- INCLUDE (contracted_rate): eliminates key lookup
------------------------------------------------------------
CREATE INDEX IX_iam_resolver
    ON raw.iam (session_id, tenant_id, billing_period)
    INCLUDE (contracted_rate);
------------------------------------------------------------
-- INDEX 2 — Session scoping (K1 contract)
------------------------------------------------------------
CREATE INDEX IX_iam_session
    ON raw.iam (session_id);
