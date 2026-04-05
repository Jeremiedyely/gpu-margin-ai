-- ============================================================
-- TEST: V9 — dbo.allocation_grain
-- 15 CHECK constraints, 9 indexes, 1 trigger (THROW 51003)
-- Path A: CHAR(7) billing_period
-- ============================================================

DECLARE @pass INT = 0, @fail INT = 0, @test NVARCHAR(200);

DECLARE @sid UNIQUEIDENTIFIER = NEWID();
INSERT INTO raw.ingestion_log (session_id, source_files, status)
VALUES (@sid, '["grain.csv"]', 'COMMITTED');

------------------------------------------------------------
-- TABLE EXISTS + CHAR(7) PATH A
------------------------------------------------------------
SET @test = 'V9-01: dbo.allocation_grain table exists';
IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'allocation_grain'
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

SET @test = 'V9-02: billing_period is CHAR(7)';
IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'allocation_grain'
      AND COLUMN_NAME = 'billing_period'
      AND DATA_TYPE = 'char' AND CHARACTER_MAXIMUM_LENGTH = 7
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- VALID TYPE A INSERT (tenant allocation)
-- revenue = ROUND(100 * 4.5, 2) = 450.00
-- cogs = ROUND(100 * 2.5, 2) = 250.00
-- gross_margin = 450.00 - 250.00 = 200.00
------------------------------------------------------------
SET @test = 'V9-03: Valid Type A insert';
BEGIN TRY
    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-a', '2025-03-01', '2025-03', 'tenant-1',
         NULL, NULL,
         100.000000, 2.500000, 4.500000, 450.00, 250.00, 200.00);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- VALID TYPE B INSERT — capacity_idle
-- revenue = 0, contracted_rate = NULL, cogs > 0
-- gross_margin = 0 - 50.00 = -50.00
------------------------------------------------------------
SET @test = 'V9-04: Valid Type B capacity_idle insert';
BEGIN TRY
    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-a', '2025-03-01', '2025-03', 'unallocated',
         'capacity_idle', NULL,
         20.000000, 2.500000, NULL, 0.00, 50.00, -50.00);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- VALID TYPE B INSERT — identity_broken
------------------------------------------------------------
SET @test = 'V9-05: Valid Type B identity_broken insert';
BEGIN TRY
    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-a', '2025-03-01', '2025-03', 'unallocated',
         'identity_broken', 'orphan-tenant-1',
         5.000000, 2.500000, NULL, 0.00, 12.50, -12.50);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- CHK_grain_unallocated_type: invalid enum
------------------------------------------------------------
SET @test = 'V9-06: REJECT invalid unallocated_type (UNKNOWN)';
BEGIN TRY
    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-b', '2025-03-01', '2025-03', 'unallocated',
         'UNKNOWN', NULL,
         10.000000, 2.500000, NULL, 0.00, 25.00, -25.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_grain_type_a_no_subtype: Type A must have NULL unallocated_type
------------------------------------------------------------
SET @test = 'V9-07: REJECT Type A with unallocated_type set';
BEGIN TRY
    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-b', '2025-03-01', '2025-03', 'tenant-x',
         'capacity_idle', NULL,
         10.000000, 2.500000, 4.500000, 45.00, 25.00, 20.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_grain_type_b_must_classify: Type B must have non-NULL unallocated_type
------------------------------------------------------------
SET @test = 'V9-08: REJECT Type B with NULL unallocated_type';
BEGIN TRY
    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-b', '2025-03-01', '2025-03', 'unallocated',
         NULL, NULL,
         10.000000, 2.500000, NULL, 0.00, 25.00, -25.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_grain_type_a_rate_required: Type A must have contracted_rate
------------------------------------------------------------
SET @test = 'V9-09: REJECT Type A with NULL contracted_rate';
BEGIN TRY
    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-b', '2025-03-01', '2025-03', 'tenant-y',
         NULL, NULL,
         10.000000, 2.500000, NULL, 0.00, 25.00, -25.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_grain_type_b_zero_revenue: Type B must have revenue = 0
------------------------------------------------------------
SET @test = 'V9-10: REJECT Type B with revenue > 0';
BEGIN TRY
    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-b', '2025-03-01', '2025-03', 'unallocated',
         'capacity_idle', NULL,
         10.000000, 2.500000, NULL, 100.00, 25.00, 75.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_grain_type_b_negative_margin: Type B margin must be < 0
------------------------------------------------------------
SET @test = 'V9-11: REJECT Type B with gross_margin >= 0';
BEGIN TRY
    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-b', '2025-03-01', '2025-03', 'unallocated',
         'capacity_idle', NULL,
         10.000000, 2.500000, NULL, 0.00, 25.00, 0.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_grain_identity_broken_requires_ftid
------------------------------------------------------------
SET @test = 'V9-12: REJECT identity_broken with NULL failed_tenant_id';
BEGIN TRY
    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-b', '2025-03-01', '2025-03', 'unallocated',
         'identity_broken', NULL,
         10.000000, 2.500000, NULL, 0.00, 25.00, -25.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_grain_capacity_idle_null_ftid
------------------------------------------------------------
SET @test = 'V9-13: REJECT capacity_idle with non-NULL failed_tenant_id';
BEGIN TRY
    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-b', '2025-03-01', '2025-03', 'unallocated',
         'capacity_idle', 'some-tenant',
         10.000000, 2.500000, NULL, 0.00, 25.00, -25.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_grain_type_a_null_ftid
------------------------------------------------------------
SET @test = 'V9-14: REJECT Type A with non-NULL failed_tenant_id';
BEGIN TRY
    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-b', '2025-03-01', '2025-03', 'tenant-z',
         NULL, 'some-tenant',
         10.000000, 2.500000, 4.500000, 45.00, 25.00, 20.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_grain_billing_period: format validation
------------------------------------------------------------
SET @test = 'V9-15: REJECT billing_period = 2025-13';
BEGIN TRY
    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-b', '2025-03-01', '2025-13', 'tenant-z',
         NULL, NULL,
         10.000000, 2.500000, 4.500000, 45.00, 25.00, 20.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_grain_gpu_hours_positive
------------------------------------------------------------
SET @test = 'V9-16: REJECT gpu_hours = 0';
BEGIN TRY
    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-b', '2025-03-01', '2025-03', 'tenant-z',
         NULL, NULL,
         0.000000, 2.500000, 4.500000, 0.00, 0.01, -0.01);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_grain_cost_per_hour_positive
------------------------------------------------------------
SET @test = 'V9-17: REJECT cost_per_gpu_hour = 0';
BEGIN TRY
    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-b', '2025-03-01', '2025-03', 'tenant-z',
         NULL, NULL,
         10.000000, 0.000000, 4.500000, 45.00, 0.01, 44.99);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_grain_cogs_positive
------------------------------------------------------------
SET @test = 'V9-18: REJECT cogs = 0';
BEGIN TRY
    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-b', '2025-03-01', '2025-03', 'tenant-z',
         NULL, NULL,
         10.000000, 2.500000, 4.500000, 45.00, 0.00, 45.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_grain_revenue_math: revenue = ROUND(gpu_hours * contracted_rate, 2)
------------------------------------------------------------
SET @test = 'V9-19: REJECT Type A with wrong revenue math';
BEGIN TRY
    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-b', '2025-03-01', '2025-03', 'tenant-z',
         NULL, NULL,
         10.000000, 2.500000, 4.500000, 999.99, 25.00, 974.99);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_grain_margin_math: gross_margin = revenue - cogs
------------------------------------------------------------
SET @test = 'V9-20: REJECT wrong gross_margin math';
BEGIN TRY
    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-b', '2025-03-01', '2025-03', 'tenant-z',
         NULL, NULL,
         10.000000, 2.500000, 4.500000, 45.00, 25.00, 999.99);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- TRIGGER: THROW 51003 — UPDATE blocked
------------------------------------------------------------
SET @test = 'V9-21: TRIGGER blocks UPDATE (THROW 51003)';
BEGIN TRY
    UPDATE dbo.allocation_grain SET revenue = 999.99 WHERE session_id = @sid;
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — update should have been blocked';
END TRY
BEGIN CATCH
    IF ERROR_NUMBER() = 51003
    BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
    ELSE
    BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test + ' — wrong error: ' + CAST(ERROR_NUMBER() AS VARCHAR); END
END CATCH;

------------------------------------------------------------
-- DELETE is ALLOWED (session replacement)
------------------------------------------------------------
SET @test = 'V9-22: DELETE is permitted (no trigger on DELETE)';
BEGIN TRY
    DECLARE @delcount INT;
    DELETE FROM dbo.allocation_grain WHERE session_id = @sid AND allocation_target = 'tenant-1';
    SET @delcount = @@ROWCOUNT;
    IF @delcount > 0
    BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
    ELSE
    BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test + ' — no rows deleted'; END
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- FILTERED-UNIQUE: Type A duplicate rejected
------------------------------------------------------------
SET @test = 'V9-23: REJECT duplicate Type A natural key';
BEGIN TRY
    -- Insert a Type A then try duplicate
    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-c', '2025-03-01', '2025-03', 'tenant-dup',
         NULL, NULL,
         10.000000, 2.500000, 4.500000, 45.00, 25.00, 20.00);

    INSERT INTO dbo.allocation_grain
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-c', '2025-03-01', '2025-03', 'tenant-dup',
         NULL, NULL,
         5.000000, 2.500000, 4.500000, 22.50, 12.50, 10.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- INDEXES EXIST (all 9)
------------------------------------------------------------
DECLARE @ixnames TABLE (ixname NVARCHAR(200));
INSERT INTO @ixnames VALUES
    ('IX_grain_session'), ('IX_grain_closure_rule'), ('IX_grain_check3'),
    ('IX_grain_region_aggregator'), ('IX_grain_customer_aggregator'),
    ('IX_grain_identity_broken_set'),
    ('UQ_grain_type_a_natural_key'), ('UQ_grain_capacity_idle_natural_key'),
    ('UQ_grain_identity_broken_natural_key');

DECLARE @ixname NVARCHAR(200);
DECLARE ix_cursor CURSOR LOCAL FAST_FORWARD FOR SELECT ixname FROM @ixnames;
OPEN ix_cursor;
FETCH NEXT FROM ix_cursor INTO @ixname;
WHILE @@FETCH_STATUS = 0
BEGIN
    SET @test = 'V9-IX: ' + @ixname + ' exists';
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = @ixname AND object_id = OBJECT_ID('dbo.allocation_grain'))
    BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
    ELSE
    BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;
    FETCH NEXT FROM ix_cursor INTO @ixname;
END;
CLOSE ix_cursor; DEALLOCATE ix_cursor;

------------------------------------------------------------
-- CLEANUP
------------------------------------------------------------
DELETE FROM dbo.allocation_grain WHERE session_id = @sid;
DELETE FROM raw.ingestion_log WHERE session_id = @sid;

PRINT '';
PRINT '============================================================';
PRINT 'V9 dbo.allocation_grain: ' + CAST(@pass AS VARCHAR) + ' passed, ' + CAST(@fail AS VARCHAR) + ' failed';
PRINT '============================================================';
