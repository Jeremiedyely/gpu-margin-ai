-- V7__create_raw_billing.sql
-- Table 4: raw.billing — Invoice Source
-- One row = one invoice record for one tenant in one billing period.
-- Grain relationship: CHECKS the grain — invoiced dimension (RE Check 3 FAIL-1 only).
-- Producer: Billing Raw Table Writer (Component 14)
CREATE TABLE raw.billing (
    id              BIGINT              NOT NULL    IDENTITY(1,1),
    session_id      UNIQUEIDENTIFIER    NOT NULL,
    tenant_id       NVARCHAR(255)       NOT NULL,
    billing_period  CHAR(7)             NOT NULL,
    billable_amount DECIMAL(18,2)       NOT NULL,
    CONSTRAINT PK_billing
        PRIMARY KEY (id),
    CONSTRAINT FK_billing_session
        FOREIGN KEY (session_id)
        REFERENCES raw.ingestion_log(session_id),
    -- One invoice per tenant per billing period per session
    CONSTRAINT UQ_billing_natural_key
        UNIQUE (session_id, tenant_id, billing_period),
    -- YYYY-MM — same format contract as raw.iam (K2)
    CONSTRAINT CHK_billing_billing_period
        CHECK (
            billing_period LIKE '[0-9][0-9][0-9][0-9]-[0-1][0-9]'
            AND SUBSTRING(billing_period, 6, 2) BETWEEN '01' AND '12'
        )
);
------------------------------------------------------------
-- DESIGN DECISION (R4-W-3 · FORMALLY ACCEPTED R12):
-- billable_amount sign NOT constrained at DB level.
-- Negative values (credit memos) allowed.
-- May produce false FAIL-1 verdicts — accepted risk.
------------------------------------------------------------
------------------------------------------------------------
-- INDEX 1 — Session scoping (K1 contract)
------------------------------------------------------------
CREATE INDEX IX_billing_session
    ON raw.billing (session_id);
------------------------------------------------------------
-- INDEX 2 — RE Check 3 FAIL-1
------------------------------------------------------------
CREATE INDEX IX_billing_check3
    ON raw.billing
       (session_id, tenant_id, billing_period)
    INCLUDE (billable_amount);
