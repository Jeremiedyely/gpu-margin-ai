-- V5__create_raw_cost_management.sql
-- Table 2: raw.cost_management — Capacity & Cost Source
-- One row = one capacity reservation record for one pool on one day.
-- Grain relationship: FEEDS the grain — capacity and cost dimension.
-- Producer: Cost Management Raw Table Writer (Component 12)
-- No tenant_id — cost is assigned to a pool, not a customer.
-- reserved_gpu_hours is the Closure Rule denominator:
--   SUM(grain.gpu_hours per pool per day) = reserved_gpu_hours

CREATE TABLE raw.cost_management (
    id                  BIGINT              NOT NULL    IDENTITY(1,1),
    session_id          UNIQUEIDENTIFIER    NOT NULL,
    region              NVARCHAR(100)       NOT NULL,
    gpu_pool_id         NVARCHAR(100)       NOT NULL,
    date                DATE                NOT NULL,
    reserved_gpu_hours  DECIMAL(18,6)       NOT NULL,
    cost_per_gpu_hour   DECIMAL(18,6)       NOT NULL,

    CONSTRAINT PK_cost_management
        PRIMARY KEY (id),

    CONSTRAINT FK_cost_management_session
        FOREIGN KEY (session_id)
        REFERENCES raw.ingestion_log(session_id),

    -- One capacity record per pool per day per session
    -- Closure Rule requires unique denominator
    CONSTRAINT UQ_cost_management_natural_key
        UNIQUE (session_id, region, gpu_pool_id, date),

    -- Both cost fields must be positive
    CONSTRAINT CHK_cost_management_reserved
        CHECK (reserved_gpu_hours > 0),

    CONSTRAINT CHK_cost_management_cost
        CHECK (cost_per_gpu_hour > 0)
);
------------------------------------------------------------
-- INDEX 1 — Session scoping (K1 contract)
------------------------------------------------------------
CREATE INDEX IX_cost_mgmt_session
    ON raw.cost_management (session_id);
------------------------------------------------------------
-- INDEX 2 — AE Cost Rate Reader + RE Check 1
-- Covering index: reserved_gpu_hours + cost_per_gpu_hour
------------------------------------------------------------
CREATE INDEX IX_cost_mgmt_grain_lookup
    ON raw.cost_management
       (session_id, region, gpu_pool_id, date)
    INCLUDE (reserved_gpu_hours, cost_per_gpu_hour);
