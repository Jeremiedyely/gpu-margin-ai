-- V10__create_dbo_reconciliation_results.sql
-- Table 7: dbo.reconciliation_results — Reconciliation Verdicts
-- One row = one reconciliation check verdict for one session.
-- Grain relationship: CHECKS the grain — three boundary checks, exactly three rows per session.
-- Producer: RE Result Writer (Component 7) — atomic write, all 3 rows or none.
-- Consumer: UI Zone 3 Reconciliation Result Reader (PASS/FAIL display — no drill-down).
CREATE TABLE dbo.reconciliation_results (
    id              BIGINT              NOT NULL    IDENTITY(1,1),
    session_id      UNIQUEIDENTIFIER    NOT NULL,
    check_name      NVARCHAR(50)        NOT NULL,
    check_order     INT                 NOT NULL,
    verdict         NVARCHAR(4)         NOT NULL,
    fail_subtype    NVARCHAR(6)         NULL,
    failing_count   INT                 NULL,
    detail          NVARCHAR(MAX)       NULL,
    CONSTRAINT PK_reconciliation_results
        PRIMARY KEY (id),
    CONSTRAINT FK_recon_session
        FOREIGN KEY (session_id)
        REFERENCES raw.ingestion_log(session_id),
    ------------------------------------------------------------
    -- One verdict per check per session
    ------------------------------------------------------------
    CONSTRAINT UQ_recon_check_per_session
        UNIQUE (session_id, check_name),
    ------------------------------------------------------------
    -- CHECK NAME ENUM
    ------------------------------------------------------------
    CONSTRAINT CHK_recon_check_name
        CHECK (check_name IN (
            'Capacity vs Usage',
            'Usage vs Tenant Mapping',
            'Computed vs Billed vs Posted'
        )),
    ------------------------------------------------------------
    -- CHECK ORDER ENUM (deterministic UI ordering)
    ------------------------------------------------------------
    CONSTRAINT CHK_recon_check_order
        CHECK (check_order IN (1,2,3)),
    ------------------------------------------------------------
    -- CHECK NAME + ORDER CONSISTENCY
    ------------------------------------------------------------
    CONSTRAINT CHK_recon_check_order_mapping
        CHECK (
            (check_name = 'Capacity vs Usage' AND check_order = 1)
            OR
            (check_name = 'Usage vs Tenant Mapping' AND check_order = 2)
            OR
            (check_name = 'Computed vs Billed vs Posted' AND check_order = 3)
        ),
    ------------------------------------------------------------
    -- VERDICT ENUM
    ------------------------------------------------------------
    CONSTRAINT CHK_recon_verdict
        CHECK (verdict IN ('PASS', 'FAIL')),
    ------------------------------------------------------------
    -- FAIL SUBTYPE DOMAIN
    ------------------------------------------------------------
    CONSTRAINT CHK_recon_fail_subtype_values
        CHECK (
            fail_subtype IS NULL
            OR fail_subtype IN ('FAIL-1', 'FAIL-2')
        ),
    ------------------------------------------------------------
    -- FAIL SUBTYPE RULE
    ------------------------------------------------------------
    CONSTRAINT CHK_recon_fail_subtype_rule
        CHECK (
            fail_subtype IS NULL
            OR (
                verdict = 'FAIL'
                AND check_name = 'Computed vs Billed vs Posted'
            )
        ),
    ------------------------------------------------------------
    -- CHECK 3 FAIL MUST HAVE SUBTYPE
    ------------------------------------------------------------
    CONSTRAINT CHK_recon_fail_subtype_on_check3_fail
        CHECK (
            check_name <> 'Computed vs Billed vs Posted'
            OR verdict = 'PASS'
            OR fail_subtype IS NOT NULL
        ),
    ------------------------------------------------------------
    -- FAILING COUNT SEMANTICS
    ------------------------------------------------------------
    CONSTRAINT CHK_recon_failing_count_semantics
        CHECK (
            (verdict = 'PASS' AND failing_count IS NULL)
            OR (verdict = 'FAIL' AND failing_count IS NOT NULL AND failing_count > 0)
        ),
    ------------------------------------------------------------
    -- DETAIL SEMANTICS (production improvement)
    ------------------------------------------------------------
    CONSTRAINT CHK_recon_detail_semantics
        CHECK (
            verdict = 'FAIL'
            OR detail IS NULL
        )
);
------------------------------------------------------------
-- INDEX 1 — Session scoping (K1 contract)
------------------------------------------------------------
CREATE INDEX IX_recon_session
    ON dbo.reconciliation_results (session_id);
------------------------------------------------------------
-- INDEX 2 — UI deterministic ordering
------------------------------------------------------------
CREATE INDEX IX_recon_session_order
    ON dbo.reconciliation_results (session_id, check_order);
