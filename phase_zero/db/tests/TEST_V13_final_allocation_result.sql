-- ============================================================
-- TEST: V13 — final.allocation_result
-- 15 CHECK constraints, 5 indexes, 1 trigger (THROW 51000)
-- Path A: CHAR(7) billing_period, math integrity
-- Immutable: UPDATE + DELETE both blocked
-- ============================================================

DECLARE @pass INT = 0, @fail INT = 0, @test NVARCHAR(200);

DECLARE @sid UNIQUEIDENTIFIER = NEWID();
INSERT INTO raw.ingestion_log (session_id, source_files, status)
VALUES (@sid, '["final.csv"]', 'COMMITTED');

------------------------------------------------------------
-- TABLE EXISTS + CHAR(7) PATH A
------------------------------------------------------------
SET @test = 'V13-01: final.allocation_result table exists';
IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'final' AND TABLE_NAME = 'allocation_result'
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

SET @test = 'V13-02: billing_period is CHAR(7)';
IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'final' AND TABLE_NAME = 'allocation_result'
      AND COLUMN_NAME = 'billing_period'
      AND DATA_TYPE = 'char' AND CHARACTER_MAXIMUM_LENGTH = 7
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- VALID TYPE A INSERT
-- revenue = ROUND(100 * 4.5, 2) = 450.00
-- gross_margin = 450.00 - 250.00 = 200.00
------------------------------------------------------------
SET @test = 'V13-03: Valid Type A insert';
BEGIN TRY
    INSERT INTO final.allocation_result
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
-- VALID TYPE B — capacity_idle
------------------------------------------------------------
SET @test = 'V13-04: Valid Type B capacity_idle insert';
BEGIN TRY
    INSERT INTO final.allocation_result
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
-- VALID TYPE B — identity_broken
------------------------------------------------------------
SET @test = 'V13-05: Valid Type B identity_broken insert';
BEGIN TRY
    INSERT INTO final.allocation_result
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
-- CHK_final_unallocated_type: invalid enum
------------------------------------------------------------
SET @test = 'V13-06: REJECT invalid unallocated_type';
BEGIN TRY
    INSERT INTO final.allocation_result
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
-- CHK_final_type_a_no_subtype
------------------------------------------------------------
SET @test = 'V13-07: REJECT Type A with unallocated_type set';
BEGIN TRY
    INSERT INTO final.allocation_result
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
-- CHK_final_type_b_must_classify
------------------------------------------------------------
SET @test = 'V13-08: REJECT Type B with NULL unallocated_type';
BEGIN TRY
    INSERT INTO final.allocation_result
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
-- CHK_final_type_a_rate_required
------------------------------------------------------------
SET @test = 'V13-09: REJECT Type A with NULL contracted_rate';
BEGIN TRY
    INSERT INTO final.allocation_result
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
-- CHK_final_type_b_zero_revenue
------------------------------------------------------------
SET @test = 'V13-10: REJECT Type B with revenue > 0';
BEGIN TRY
    INSERT INTO final.allocation_result
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
-- CHK_final_type_b_negative_margin
------------------------------------------------------------
SET @test = 'V13-11: REJECT Type B with gross_margin >= 0';
BEGIN TRY
    INSERT INTO final.allocation_result
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
-- CHK_final_identity_broken_requires_ftid
------------------------------------------------------------
SET @test = 'V13-12: REJECT identity_broken with NULL failed_tenant_id';
BEGIN TRY
    INSERT INTO final.allocation_result
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
-- CHK_final_capacity_idle_null_ftid
------------------------------------------------------------
SET @test = 'V13-13: REJECT capacity_idle with non-NULL failed_tenant_id';
BEGIN TRY
    INSERT INTO final.allocation_result
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
-- CHK_final_type_a_null_ftid
------------------------------------------------------------
SET @test = 'V13-14: REJECT Type A with non-NULL failed_tenant_id';
BEGIN TRY
    INSERT INTO final.allocation_result
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
-- CHK_final_billing_period: format
------------------------------------------------------------
SET @test = 'V13-15: REJECT billing_period = 2025-13';
BEGIN TRY
    INSERT INTO final.allocation_result
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
-- CHK_final_gpu_hours_positive
------------------------------------------------------------
SET @test = 'V13-16: REJECT gpu_hours = 0';
BEGIN TRY
    INSERT INTO final.allocation_result
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
-- CHK_final_cost_per_hour_positive
------------------------------------------------------------
SET @test = 'V13-17: REJECT cost_per_gpu_hour = 0';
BEGIN TRY
    INSERT INTO final.allocation_result
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
-- CHK_final_cogs_positive
------------------------------------------------------------
SET @test = 'V13-18: REJECT cogs = 0';
BEGIN TRY
    INSERT INTO final.allocation_result
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
-- CHK_final_revenue_math
------------------------------------------------------------
SET @test = 'V13-19: REJECT Type A with wrong revenue math';
BEGIN TRY
    INSERT INTO final.allocation_result
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
-- CHK_final_margin_math
------------------------------------------------------------
SET @test = 'V13-20: REJECT wrong gross_margin math';
BEGIN TRY
    INSERT INTO final.allocation_result
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
-- TRIGGER: THROW 51000 — UPDATE blocked
------------------------------------------------------------
SET @test = 'V13-21: TRIGGER blocks UPDATE (THROW 51000)';
BEGIN TRY
    UPDATE final.allocation_result SET revenue = 999.99 WHERE session_id = @sid;
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — update should have been blocked';
END TRY
BEGIN CATCH
    IF ERROR_NUMBER() = 51000
    BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
    ELSE
    BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test + ' — wrong error: ' + CAST(ERROR_NUMBER() AS VARCHAR); END
END CATCH;

------------------------------------------------------------
-- TRIGGER: THROW 51000 — DELETE blocked
------------------------------------------------------------
SET @test = 'V13-22: TRIGGER blocks DELETE (THROW 51000)';
BEGIN TRY
    DELETE FROM final.allocation_result WHERE session_id = @sid AND allocation_target = 'tenant-1';
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — delete should have been blocked';
END TRY
BEGIN CATCH
    IF ERROR_NUMBER() = 51000
    BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
    ELSE
    BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test + ' — wrong error: ' + CAST(ERROR_NUMBER() AS VARCHAR); END
END CATCH;

------------------------------------------------------------
-- FILTERED-UNIQUE: Type A duplicate rejected
------------------------------------------------------------
SET @test = 'V13-23: REJECT duplicate Type A natural key';
BEGIN TRY
    INSERT INTO final.allocation_result
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (@sid, 'us-east-1', 'pool-a', '2025-03-01', '2025-03', 'tenant-1',
         NULL, NULL,
         50.000000, 2.500000, 4.500000, 225.00, 125.00, 100.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- FK: invalid session_id rejected
------------------------------------------------------------
SET @test = 'V13-24: REJECT invalid session_id (FK)';
BEGIN TRY
    INSERT INTO final.allocation_result
        (session_id, region, gpu_pool_id, date, billing_period, allocation_target,
         unallocated_type, failed_tenant_id,
         gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin)
    VALUES
        (NEWID(), 'us-east-1', 'pool-a', '2025-03-01', '2025-03', 'tenant-1',
         NULL, NULL,
         10.000000, 2.500000, 4.500000, 45.00, 25.00, 20.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- INDEXES EXIST (5)
------------------------------------------------------------
DECLARE @ixnames TABLE (ixname NVARCHAR(200));
INSERT INTO @ixnames VALUES
    ('IX_final_session'), ('IX_final_approved_at'),
    ('UQ_final_type_a_natural_key'), ('UQ_final_capacity_idle_natural_key'),
    ('UQ_final_identity_broken_natural_key');

DECLARE @ixname NVARCHAR(200);
DECLARE ix_cursor CURSOR LOCAL FAST_FORWARD FOR SELECT ixname FROM @ixnames;
OPEN ix_cursor;
FETCH NEXT FROM ix_cursor INTO @ixname;
WHILE @@FETCH_STATUS = 0
BEGIN
    SET @test = 'V13-IX: ' + @ixname + ' exists';
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = @ixname AND object_id = OBJECT_ID('final.allocation_result'))
    BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
    ELSE
    BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;
    FETCH NEXT FROM ix_cursor INTO @ixname;
END;
CLOSE ix_cursor; DEALLOCATE ix_cursor;

------------------------------------------------------------
-- CLEANUP — must disable trigger to delete test data
------------------------------------------------------------
DISABLE TRIGGER TR_final_allocation_result_prevent_mutation ON final.allocation_result;
DELETE FROM final.allocation_result WHERE session_id = @sid;
ENABLE TRIGGER TR_final_allocation_result_prevent_mutation ON final.allocation_result;
DELETE FROM raw.ingestion_log WHERE session_id = @sid;

PRINT '';
PRINT '============================================================';
PRINT 'V13 final.allocation_result: ' + CAST(@pass AS VARCHAR) + ' passed, ' + CAST(@fail AS VARCHAR) + ' failed';
PRINT '============================================================';
