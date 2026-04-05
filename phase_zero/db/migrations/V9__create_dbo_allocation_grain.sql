-- V9__create_dbo_allocation_grain.sql
-- Table 6: dbo.allocation_grain — The Grain Table
-- One row = one grain cell = (region, gpu_pool_id, date, allocation_target)
-- Grain relationship: IS the grain. Central source of truth.
-- Producer: AE Allocation Grain Writer (Component 9) — atomic transaction, ROLLBACK on failure.
-- Consumers: UI · RE Check 3 · Export · SM Approved Result Writer (C9)
CREATE TABLE dbo.allocation_grain (
    id                  BIGINT              NOT NULL    IDENTITY(1,1),
    session_id          UNIQUEIDENTIFIER    NOT NULL,
    -- GRAIN DIMENSIONS (all four required)
    region              NVARCHAR(100)       NOT NULL,
    gpu_pool_id         NVARCHAR(100)       NOT NULL,
    date                DATE                NOT NULL,
    billing_period      CHAR(7)             NOT NULL,
    allocation_target   NVARCHAR(255)       NOT NULL,
    -- RECORD TYPE CLASSIFICATION
    unallocated_type    NVARCHAR(20)        NULL,
    failed_tenant_id    NVARCHAR(255)       NULL,
    -- COMPUTED VALUES
    gpu_hours           DECIMAL(18,6)       NOT NULL,
    cost_per_gpu_hour   DECIMAL(18,6)       NOT NULL,
    contracted_rate     DECIMAL(18,6)       NULL,
    revenue             DECIMAL(18,2)       NOT NULL,
    cogs                DECIMAL(18,2)       NOT NULL,
    gross_margin        DECIMAL(18,2)       NOT NULL,
    CONSTRAINT PK_allocation_grain
        PRIMARY KEY (id),
    CONSTRAINT FK_grain_session
        FOREIGN KEY (session_id)
        REFERENCES raw.ingestion_log(session_id),
    ------------------------------------------------------------
    -- RECORD TYPE ENUM
    ------------------------------------------------------------
    CONSTRAINT CHK_grain_unallocated_type
        CHECK (
            unallocated_type IS NULL
            OR unallocated_type = 'capacity_idle'
            OR unallocated_type = 'identity_broken'
        ),
    ------------------------------------------------------------
    -- TYPE A / TYPE B STRUCTURE
    -- Type A: allocation_target <> 'unallocated'
    -- Type B: allocation_target  = 'unallocated'
    ------------------------------------------------------------
    -- Type A must have NULL unallocated_type
    CONSTRAINT CHK_grain_type_a_no_subtype
        CHECK (
            allocation_target = 'unallocated'
            OR unallocated_type IS NULL
        ),
    -- Type B must have non-NULL unallocated_type
    CONSTRAINT CHK_grain_type_b_must_classify
        CHECK (
            allocation_target <> 'unallocated'
            OR unallocated_type IS NOT NULL
        ),
    -- Type A must have non-NULL contracted_rate
    CONSTRAINT CHK_grain_type_a_rate_required
        CHECK (
            allocation_target = 'unallocated'
            OR contracted_rate IS NOT NULL
        ),
    -- Type B must have revenue = 0 and contracted_rate = NULL
    CONSTRAINT CHK_grain_type_b_zero_revenue
        CHECK (
            allocation_target <> 'unallocated'
            OR (revenue = 0 AND contracted_rate IS NULL)
        ),
    -- Type B gross_margin must be strictly negative
    CONSTRAINT CHK_grain_type_b_negative_margin
        CHECK (
            allocation_target <> 'unallocated'
            OR gross_margin < 0
        ),
    -- identity_broken requires failed_tenant_id
    CONSTRAINT CHK_grain_identity_broken_requires_ftid
        CHECK (
            unallocated_type <> 'identity_broken'
            OR failed_tenant_id IS NOT NULL
        ),
    -- capacity_idle must have NULL failed_tenant_id
    CONSTRAINT CHK_grain_capacity_idle_null_ftid
        CHECK (
            unallocated_type <> 'capacity_idle'
            OR failed_tenant_id IS NULL
        ),
    -- Type A must have NULL failed_tenant_id
    CONSTRAINT CHK_grain_type_a_null_ftid
        CHECK (
            allocation_target = 'unallocated'
            OR failed_tenant_id IS NULL
        ),
    ------------------------------------------------------------
    -- FORMAT
    ------------------------------------------------------------
    CONSTRAINT CHK_grain_billing_period
        CHECK (
            billing_period LIKE '[0-9][0-9][0-9][0-9]-[0-1][0-9]'
            AND SUBSTRING(billing_period, 6, 2) BETWEEN '01' AND '12'
        ),
    ------------------------------------------------------------
    -- POSITIVITY
    ------------------------------------------------------------
    CONSTRAINT CHK_grain_gpu_hours_positive
        CHECK (gpu_hours > 0),
    CONSTRAINT CHK_grain_cost_per_hour_positive
        CHECK (cost_per_gpu_hour > 0),
    CONSTRAINT CHK_grain_cogs_positive
        CHECK (cogs > 0),
    ------------------------------------------------------------
    -- MATH INTEGRITY
    ------------------------------------------------------------
    -- Type A revenue must equal rounded gpu_hours × contracted_rate
    CONSTRAINT CHK_grain_revenue_math
        CHECK (
            allocation_target = 'unallocated'
            OR revenue = ROUND(gpu_hours * contracted_rate, 2)
        ),
    -- gross_margin must always equal revenue - cogs
    CONSTRAINT CHK_grain_margin_math
        CHECK (
            gross_margin = revenue - cogs
        )
);
GO
------------------------------------------------------------
-- IMMUTABILITY TRIGGER — UPDATE only
-- DELETE intentionally NOT blocked — session replacement may require
-- session-scoped DELETE upstream.
-- THROW 51003: claimed in trigger error registry.
------------------------------------------------------------
CREATE TRIGGER TR_allocation_grain_prevent_update
    ON dbo.allocation_grain
    INSTEAD OF UPDATE
AS
BEGIN
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW 51003,
        'dbo.allocation_grain is write-once per grain row. UPDATE is not permitted. The AE Allocation Grain Writer (C9) is the sole producer and operates INSERT-only.',
        1;
END;
GO
------------------------------------------------------------
-- INDEX 1 — Session scoping (K1 contract)
------------------------------------------------------------
CREATE INDEX IX_grain_session
    ON dbo.allocation_grain (session_id);
------------------------------------------------------------
-- INDEX 2 — Closure Rule verification
-- SUM(gpu_hours per region+pool+date) = reserved_gpu_hours
------------------------------------------------------------
CREATE INDEX IX_grain_closure_rule
    ON dbo.allocation_grain (session_id, region, gpu_pool_id, date)
    INCLUDE (gpu_hours);
------------------------------------------------------------
-- INDEX 3 — RE Check 3 (Type A rows only)
------------------------------------------------------------
CREATE INDEX IX_grain_check3
    ON dbo.allocation_grain (session_id, allocation_target, billing_period)
    INCLUDE (revenue)
    WHERE allocation_target <> 'unallocated';
------------------------------------------------------------
-- INDEX 4 — Zone 2L Region Data Aggregator
------------------------------------------------------------
CREATE INDEX IX_grain_region_aggregator
    ON dbo.allocation_grain (session_id, region, allocation_target)
    INCLUDE (revenue, cogs, gpu_hours, unallocated_type);
------------------------------------------------------------
-- INDEX 5 — Zone 2R Customer Data Aggregator
------------------------------------------------------------
CREATE INDEX IX_grain_customer_aggregator
    ON dbo.allocation_grain (session_id, allocation_target)
    INCLUDE (revenue, cogs, failed_tenant_id);
------------------------------------------------------------
-- INDEX 6 — identity_broken_tenants SET pre-computation
------------------------------------------------------------
CREATE INDEX IX_grain_identity_broken_set
    ON dbo.allocation_grain (session_id, unallocated_type)
    INCLUDE (failed_tenant_id)
    WHERE unallocated_type = 'identity_broken';
------------------------------------------------------------
-- FILTERED-UNIQUE 1 — Type A: one row per tenant per pool-day
------------------------------------------------------------
CREATE UNIQUE INDEX UQ_grain_type_a_natural_key
    ON dbo.allocation_grain (session_id, region, gpu_pool_id, date, allocation_target)
    WHERE allocation_target <> 'unallocated';
------------------------------------------------------------
-- FILTERED-UNIQUE 2 — capacity_idle: one row per pool-day
------------------------------------------------------------
CREATE UNIQUE INDEX UQ_grain_capacity_idle_natural_key
    ON dbo.allocation_grain (session_id, region, gpu_pool_id, date, unallocated_type)
    WHERE unallocated_type = 'capacity_idle';
------------------------------------------------------------
-- FILTERED-UNIQUE 3 — identity_broken: one row per failed tenant per pool-day
------------------------------------------------------------
CREATE UNIQUE INDEX UQ_grain_identity_broken_natural_key
    ON dbo.allocation_grain (session_id, region, gpu_pool_id, date, failed_tenant_id)
    WHERE unallocated_type = 'identity_broken';
