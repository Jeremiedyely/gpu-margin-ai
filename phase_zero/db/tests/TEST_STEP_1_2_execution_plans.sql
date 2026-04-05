-- ============================================================
-- STEP 1.2 — Index Execution Plan Verification
-- Run in SSMS with "Include Actual Execution Plan" (Ctrl+M) ON
-- After execution, check the Execution Plan tab for each query.
-- PASS = Index Seek on the named index
-- FAIL = Clustered Index Scan or Table Scan
-- ============================================================

-- Seed data for optimizer (needs rows to generate meaningful plans)
DECLARE @sid UNIQUEIDENTIFIER = NEWID();
INSERT INTO raw.ingestion_log (session_id, source_files, status)
VALUES (@sid, '["plan-test.csv"]', 'COMMITTED');

-- Seed raw.iam (50 rows)
DECLARE @i INT = 1;
WHILE @i <= 50
BEGIN
    INSERT INTO raw.iam (session_id, tenant_id, billing_period, contracted_rate)
    VALUES (@sid, 'tenant-' + CAST(@i AS VARCHAR), '2025-03', 4.500000);
    SET @i += 1;
END;

-- Seed raw.telemetry (50 rows)
SET @i = 1;
WHILE @i <= 50
BEGIN
    INSERT INTO raw.telemetry (session_id, region, gpu_pool_id, date, tenant_id, gpu_hours_consumed)
    VALUES (@sid, 'us-east-1', 'pool-a', '2025-03-01', 'tenant-' + CAST(@i AS VARCHAR), 10.000000);
    SET @i += 1;
END;

-- Seed raw.cost_management (1 row)
INSERT INTO raw.cost_management
    (session_id, region, gpu_pool_id, date, reserved_gpu_hours, cost_per_gpu_hour)
VALUES
    (@sid, 'us-east-1', 'pool-a', '2025-03-01', 500.000000, 2.500000);

-- Seed dbo.allocation_grain (50 Type A rows)
SET @i = 1;
WHILE @i <= 50
BEGIN
    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-a', '2025-03-01', '2025-03',
         'tenant-' + CAST(@i AS VARCHAR),
         NULL, NULL,
         10.000000, 2.500000, 4.500000, 45.00, 25.00, 20.00);
    SET @i += 1;
END;

PRINT '=== DATA SEEDED — CHECK EXECUTION PLANS BELOW ===';
PRINT '';
GO

-- ============================================================
-- QUERY 1: IAM Resolver — IX_iam_resolver
-- Pattern: Session-scoped LEFT JOIN ON (tenant_id, billing_period)
-- Expect: Index Seek on IX_iam_resolver
-- ============================================================
DECLARE @sid1 UNIQUEIDENTIFIER = (SELECT TOP 1 session_id FROM raw.iam);

SELECT i.tenant_id, i.billing_period, i.contracted_rate
FROM raw.iam i
WHERE i.session_id = @sid1
  AND i.tenant_id = 'tenant-25'
  AND i.billing_period = '2025-03';
GO

-- ============================================================
-- QUERY 2: Telemetry Aggregator — IX_telemetry_grain
-- Pattern: GROUP BY grain dimensions within session
-- Expect: Index Seek on IX_telemetry_grain
-- ============================================================
DECLARE @sid2 UNIQUEIDENTIFIER = (SELECT TOP 1 session_id FROM raw.telemetry);

SELECT t.region, t.gpu_pool_id, t.date, t.tenant_id,
       SUM(t.gpu_hours_consumed) AS total_hours
FROM raw.telemetry t
WHERE t.session_id = @sid2
GROUP BY t.region, t.gpu_pool_id, t.date, t.tenant_id;
GO

-- ============================================================
-- QUERY 3: RE Check 3 — IX_grain_check3 (filtered index)
-- Pattern: Type A revenue aggregation by tenant + billing_period
-- Expect: Index Seek on IX_grain_check3
-- ============================================================
DECLARE @sid3 UNIQUEIDENTIFIER = (SELECT TOP 1 session_id FROM dbo.allocation_grain);

SELECT g.allocation_target, g.billing_period, SUM(g.revenue) AS total_revenue
FROM dbo.allocation_grain g
WHERE g.session_id = @sid3
  AND g.allocation_target <> 'unallocated'
GROUP BY g.allocation_target, g.billing_period;
GO

-- ============================================================
-- QUERY 4: Cost Rate Reader — IX_cost_mgmt_grain_lookup
-- Pattern: Lookup by session + region + pool + date
-- Expect: Index Seek on IX_cost_mgmt_grain_lookup
-- ============================================================
DECLARE @sid4 UNIQUEIDENTIFIER = (SELECT TOP 1 session_id FROM raw.cost_management);

SELECT c.reserved_gpu_hours, c.cost_per_gpu_hour
FROM raw.cost_management c
WHERE c.session_id = @sid4
  AND c.region = 'us-east-1'
  AND c.gpu_pool_id = 'pool-a'
  AND c.date = '2025-03-01';
GO

-- ============================================================
-- CLEANUP
-- ============================================================
DECLARE @sid5 UNIQUEIDENTIFIER = (SELECT TOP 1 session_id FROM raw.iam WHERE tenant_id = 'tenant-1' AND billing_period = '2025-03');

DELETE FROM dbo.allocation_grain WHERE session_id = @sid5;
DELETE FROM raw.telemetry WHERE session_id = @sid5;
DELETE FROM raw.cost_management WHERE session_id = @sid5;
DELETE FROM raw.iam WHERE session_id = @sid5;
DELETE FROM raw.ingestion_log WHERE session_id = @sid5;

PRINT '';
PRINT '=== CLEANUP COMPLETE — CHECK 4 EXECUTION PLAN TABS ===';
PRINT 'Query 1: IX_iam_resolver         — expect Index Seek';
PRINT 'Query 2: IX_telemetry_grain      — expect Index Seek';
PRINT 'Query 3: IX_grain_check3         — expect Index Seek';
PRINT 'Query 4: IX_cost_mgmt_grain_lookup — expect Index Seek';
GO
