-- V14__create_dbo_kpi_cache.sql
-- Table 11: dbo.kpi_cache — Zone 1 KPI Pre-Computed Cache
-- One row = one session's five Zone 1 KPI values.
CREATE TABLE dbo.kpi_cache (
    session_id              UNIQUEIDENTIFIER    NOT NULL,
    gpu_revenue             DECIMAL(18,2)       NOT NULL,
    gpu_cogs                DECIMAL(18,2)       NOT NULL,
    idle_gpu_cost           DECIMAL(18,2)       NOT NULL,
    idle_gpu_cost_pct       DECIMAL(5,2)        NOT NULL,
    cost_allocation_rate    DECIMAL(5,2)        NOT NULL,
    computed_at             DATETIME2           NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_kpi_cache
        PRIMARY KEY (session_id),
    CONSTRAINT FK_kpi_session
        FOREIGN KEY (session_id)
        REFERENCES raw.ingestion_log(session_id),
    ------------------------------------------------------------
    -- MONETARY GUARDRAILS
    ------------------------------------------------------------
    CONSTRAINT CHK_kpi_revenue_nonneg
        CHECK (gpu_revenue >= 0),
    CONSTRAINT CHK_kpi_cogs_nonneg
        CHECK (gpu_cogs >= 0),
    CONSTRAINT CHK_kpi_idle_nonneg
        CHECK (idle_gpu_cost >= 0),
    ------------------------------------------------------------
    -- PERCENTAGE BOUNDS
    ------------------------------------------------------------
    CONSTRAINT CHK_kpi_idle_pct
        CHECK (idle_gpu_cost_pct BETWEEN 0 AND 100),
    CONSTRAINT CHK_kpi_allocation_rate
        CHECK (cost_allocation_rate BETWEEN 0 AND 100),
    ------------------------------------------------------------
    -- COMPLEMENT INTEGRITY
    ------------------------------------------------------------
    CONSTRAINT CHK_kpi_complement
        CHECK (
            ABS((idle_gpu_cost_pct + cost_allocation_rate) - 100.00) <= 0.01
        )
);
GO
------------------------------------------------------------
-- IMMUTABILITY TRIGGER
------------------------------------------------------------
CREATE TRIGGER TR_kpi_cache_prevent_mutation
    ON dbo.kpi_cache
    INSTEAD OF UPDATE, DELETE
AS
BEGIN
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW 51001,
    'dbo.kpi_cache is immutable. UPDATE and DELETE are not permitted.',
    1;
END;
GO
