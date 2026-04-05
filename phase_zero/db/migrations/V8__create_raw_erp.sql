-- V8__create_raw_erp.sql
-- Table 5: raw.erp — GL Posting Source
-- One row = one GL posting for one tenant in one billing period.
-- Grain relationship: CHECKS the grain — posted dimension (RE Check 3 FAIL-2 only).
-- Producer: ERP Raw Table Writer (Component 15)

CREATE TABLE raw.erp (
    id              BIGINT              NOT NULL    IDENTITY(1,1),
    session_id      UNIQUEIDENTIFIER    NOT NULL,
    tenant_id       NVARCHAR(255)       NOT NULL,
    billing_period  CHAR(7)             NOT NULL,
    amount_posted   DECIMAL(18,2)       NOT NULL,

    CONSTRAINT PK_erp
        PRIMARY KEY (id),

    CONSTRAINT FK_erp_session
        FOREIGN KEY (session_id)
        REFERENCES raw.ingestion_log(session_id),

    -- One GL posting per tenant per billing period per session
    CONSTRAINT UQ_erp_natural_key
        UNIQUE (session_id, tenant_id, billing_period),

    -- YYYY-MM — same format contract as raw.iam and raw.billing (K2)
    CONSTRAINT CHK_erp_billing_period
        CHECK (
            billing_period LIKE '[0-9][0-9][0-9][0-9]-[0-1][0-9]'
            AND SUBSTRING(billing_period, 6, 2) BETWEEN '01' AND '12'
        )
);

------------------------------------------------------------
-- DESIGN DECISION (R4-W-3 · FORMALLY ACCEPTED R12):
-- amount_posted sign NOT constrained at DB level.
-- Negative values (GL credit entries / reversals) allowed.
-- May produce false FAIL-2 verdicts — accepted risk.
-- Joint scope decision with raw.billing.billable_amount.
------------------------------------------------------------

------------------------------------------------------------
-- INDEX 1 — Session scoping (K1 contract)
------------------------------------------------------------
CREATE INDEX IX_erp_session
    ON raw.erp (session_id);

------------------------------------------------------------
-- INDEX 2 — RE Check 3 FAIL-2
------------------------------------------------------------
CREATE INDEX IX_erp_check3
    ON raw.erp
       (session_id, tenant_id, billing_period)
    INCLUDE (amount_posted);
