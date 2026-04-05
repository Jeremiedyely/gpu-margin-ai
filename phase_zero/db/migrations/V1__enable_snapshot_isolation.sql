-- V1__enable_snapshot_isolation.sql
-- Enables snapshot isolation on the GPU Margin database.
-- Required before Telemetry Aggregator (AE) and Check 1/Check 2 Executors (RE)
-- run concurrently against raw.telemetry.
-- Without this: concurrent reads under READ COMMITTED return dirty aggregations.
-- Failure is silent — no error, wrong numbers.

ALTER DATABASE gpu_margin
    SET ALLOW_SNAPSHOT_ISOLATION ON;

ALTER DATABASE gpu_margin
    SET READ_COMMITTED_SNAPSHOT ON
    WITH ROLLBACK IMMEDIATE;