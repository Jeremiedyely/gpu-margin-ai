-- V4__create_raw_telemetry.sql
-- Table 1: raw.telemetry — Consumption Source
-- One row = one metering record for one tenant at one pool on one day.
-- Grain relationship: FEEDS the grain — consumption dimension.
-- Producer: Telemetry Raw Table Writer (Component 11)
-- Deployment prerequisite: Snapshot isolation (V1) MUST be enabled before concurrent AE+RE reads.
CREATE TABLE raw.telemetry (
    id                  BIGINT              NOT NULL    IDENTITY(1,1),
    session_id          UNIQUEIDENTIFIER    NOT NULL,
    region              NVARCHAR(100)       NOT NULL,
    gpu_pool_id         NVARCHAR(100)       NOT NULL,
    date                DATE                NOT NULL,
    tenant_id           NVARCHAR(255)       NOT NULL,
    gpu_hours_consumed  DECIMAL(18,6)       NOT NULL,
    CONSTRAINT PK_telemetry
        PRIMARY KEY (id),
    CONSTRAINT FK_telemetry_session
        FOREIGN KEY (session_id)
        REFERENCES raw.ingestion_log(session_id),
    -- Positive consumption only — zero-hour metering records rejected at ingestion
    CONSTRAINT CHK_telemetry_gpu_hours
        CHECK (gpu_hours_consumed > 0)
);
------------------------------------------------------------
-- INDEX 1 — Session scoping (K1 contract)
-- First filter on all reads
------------------------------------------------------------
CREATE INDEX IX_telemetry_session
    ON raw.telemetry (session_id);
------------------------------------------------------------
-- INDEX 2 — Allocation Engine Aggregator
-- GROUP BY (region, gpu_pool_id, date, tenant_id)
-- Covering index avoids base table scan
------------------------------------------------------------
CREATE INDEX IX_telemetry_grain
    ON raw.telemetry
       (session_id, region, gpu_pool_id, date, tenant_id)
    INCLUDE (gpu_hours_consumed);
------------------------------------------------------------
-- INDEX 3 — Reconciliation Engine Checks
-- Check 1: SUM(consumed) vs reserved per pool-day
-- Check 2: tenant_id resolution
------------------------------------------------------------
CREATE INDEX IX_telemetry_pool_day
    ON raw.telemetry
       (session_id, region, gpu_pool_id, date)
    INCLUDE (gpu_hours_consumed, tenant_id);
