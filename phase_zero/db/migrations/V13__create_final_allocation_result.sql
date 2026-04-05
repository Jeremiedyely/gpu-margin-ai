-- V13__create_final_allocation_result.sql
-- Table 10: final.allocation_result — Immutable Approved Grain Copy
CREATE TABLE final.allocation_result (
    id                  BIGINT              NOT NULL IDENTITY(1,1),
    row_id              UNIQUEIDENTIFIER    NOT NULL DEFAULT NEWSEQUENTIALID(),
    session_id          UNIQUEIDENTIFIER    NOT NULL,
    approved_at         DATETIME2           NOT NULL DEFAULT SYSUTCDATETIME(),
    ------------------------------------------------------------
    -- GRAIN DIMENSIONS
    ------------------------------------------------------------
    region              NVARCHAR(100)       NOT NULL,
    gpu_pool_id         NVARCHAR(100)       NOT NULL,
    date                DATE                NOT NULL,
    billing_period      CHAR(7)             NOT NULL,
    allocation_target   NVARCHAR(255)       NOT NULL,
    ------------------------------------------------------------
    -- RECORD TYPE
    ------------------------------------------------------------
    unallocated_type    NVARCHAR(20)        NULL,
    failed_tenant_id    NVARCHAR(255)       NULL,
    ------------------------------------------------------------
    -- COMPUTED VALUES
    ------------------------------------------------------------
    gpu_hours           DECIMAL(18,6)       NOT NULL,
    cost_per_gpu_hour   DECIMAL(18,6)       NOT NULL,
    contracted_rate     DECIMAL(18,6)       NULL,
    revenue             DECIMAL(18,2)       NOT NULL,
    cogs                DECIMAL(18,2)       NOT NULL,
    gross_margin        DECIMAL(18,2)       NOT NULL,
    CONSTRAINT PK_final_result
        PRIMARY KEY (id),
    CONSTRAINT UQ_final_row_id
        UNIQUE (row_id),
    CONSTRAINT FK_final_session
        FOREIGN KEY (session_id)
        REFERENCES raw.ingestion_log(session_id),
    ------------------------------------------------------------
    -- TYPE ENUM
    ------------------------------------------------------------
    CONSTRAINT CHK_final_unallocated_type
        CHECK (
            unallocated_type IS NULL
            OR unallocated_type IN ('capacity_idle','identity_broken')
        ),
    ------------------------------------------------------------
    -- TYPE A / TYPE B STRUCTURE
    ------------------------------------------------------------
    -- Type A must have NULL unallocated_type
    CONSTRAINT CHK_final_type_a_no_subtype
        CHECK (
            allocation_target = 'unallocated'
            OR unallocated_type IS NULL
        ),
    -- Type B must have non-NULL unallocated_type
    CONSTRAINT CHK_final_type_b_must_classify
        CHECK (
            allocation_target <> 'unallocated'
            OR unallocated_type IS NOT NULL
        ),
    CONSTRAINT CHK_final_type_a_rate_required
        CHECK (
            allocation_target = 'unallocated'
            OR contracted_rate IS NOT NULL
        ),
    CONSTRAINT CHK_final_type_b_zero_revenue
        CHECK (
            allocation_target <> 'unallocated'
            OR (revenue = 0 AND contracted_rate IS NULL)
        ),
    CONSTRAINT CHK_final_type_b_negative_margin
        CHECK (
            allocation_target <> 'unallocated'
            OR gross_margin < 0
        ),
    CONSTRAINT CHK_final_identity_broken_requires_ftid
        CHECK (
            unallocated_type <> 'identity_broken'
            OR failed_tenant_id IS NOT NULL
        ),
    CONSTRAINT CHK_final_capacity_idle_null_ftid
        CHECK (
            unallocated_type <> 'capacity_idle'
            OR failed_tenant_id IS NULL
        ),
    CONSTRAINT CHK_final_type_a_null_ftid
        CHECK (
            allocation_target = 'unallocated'
            OR failed_tenant_id IS NULL
        ),
    ------------------------------------------------------------
    -- FORMAT
    ------------------------------------------------------------
    CONSTRAINT CHK_final_billing_period
        CHECK (
            billing_period LIKE '[0-9][0-9][0-9][0-9]-[0-1][0-9]'
            AND SUBSTRING(billing_period, 6, 2) BETWEEN '01' AND '12'
        ),
    ------------------------------------------------------------
    -- POSITIVITY
    ------------------------------------------------------------
    CONSTRAINT CHK_final_gpu_hours_positive
        CHECK (gpu_hours > 0),
    CONSTRAINT CHK_final_cost_per_hour_positive
        CHECK (cost_per_gpu_hour > 0),
    CONSTRAINT CHK_final_cogs_positive
        CHECK (cogs > 0),
    ------------------------------------------------------------
    -- MATH INTEGRITY (Added Hardening)
    ------------------------------------------------------------
    CONSTRAINT CHK_final_margin_math
        CHECK (
            gross_margin = revenue - cogs
        ),
    CONSTRAINT CHK_final_revenue_math
        CHECK (
            allocation_target = 'unallocated'
            OR revenue = ROUND(gpu_hours * contracted_rate, 2)
        )
);
GO
------------------------------------------------------------
-- IMMUTABILITY TRIGGER
------------------------------------------------------------
CREATE TRIGGER TR_final_allocation_result_prevent_mutation
ON final.allocation_result
INSTEAD OF UPDATE, DELETE
AS
BEGIN
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW 51000,
    'final.allocation_result is immutable. UPDATE and DELETE not permitted.',
    1;
END;
GO
------------------------------------------------------------
-- INDEX 1 — Session Export
------------------------------------------------------------
CREATE INDEX IX_final_session
ON final.allocation_result (session_id);
------------------------------------------------------------
-- INDEX 2 — Approval Audit
------------------------------------------------------------
CREATE INDEX IX_final_approved_at
ON final.allocation_result (approved_at);
------------------------------------------------------------
-- FILTERED UNIQUE — TYPE A
------------------------------------------------------------
CREATE UNIQUE INDEX UQ_final_type_a_natural_key
ON final.allocation_result
(session_id, region, gpu_pool_id, date, allocation_target)
WHERE allocation_target <> 'unallocated';
------------------------------------------------------------
-- FILTERED UNIQUE — capacity_idle
------------------------------------------------------------
CREATE UNIQUE INDEX UQ_final_capacity_idle_natural_key
ON final.allocation_result
(session_id, region, gpu_pool_id, date, unallocated_type)
WHERE unallocated_type = 'capacity_idle';
------------------------------------------------------------
-- FILTERED UNIQUE — identity_broken
------------------------------------------------------------
CREATE UNIQUE INDEX UQ_final_identity_broken_natural_key
ON final.allocation_result
(session_id, region, gpu_pool_id, date, failed_tenant_id)
WHERE unallocated_type = 'identity_broken';
