-- ============================================================
-- TEST: V5 — raw.cost_management
-- 2 CHECK constraints, 2 indexes, 1 UNIQUE
-- ============================================================

DECLARE @pass INT = 0, @fail INT = 0, @test NVARCHAR(200);

DECLARE @sid UNIQUEIDENTIFIER = NEWID();
INSERT INTO raw.ingestion_log (session_id, source_files, status)
VALUES (@sid, '["cost.csv"]', 'COMMITTED');

------------------------------------------------------------
-- TABLE EXISTS
------------------------------------------------------------
SET @test = 'V5-01: raw.cost_management table exists';
IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'raw' AND TABLE_NAME = 'cost_management'
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- VALID INSERT
------------------------------------------------------------
SET @test = 'V5-02: Valid insert';
BEGIN TRY
    INSERT INTO raw.cost_management (session_id, region, gpu_pool_id, date, reserved_gpu_hours, cost_per_gpu_hour)
    VALUES (@sid, 'us-east-1', 'pool-a', '2025-03-01', 500.000000, 2.500000);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- CHK_cost_management_reserved: must be > 0
------------------------------------------------------------
SET @test = 'V5-03: REJECT reserved_gpu_hours = 0';
BEGIN TRY
    INSERT INTO raw.cost_management (session_id, region, gpu_pool_id, date, reserved_gpu_hours, cost_per_gpu_hour)
    VALUES (@sid, 'us-east-1', 'pool-b', '2025-03-01', 0, 2.500000);
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — insert should have been rejected';
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_cost_management_cost: must be > 0
------------------------------------------------------------
SET @test = 'V5-04: REJECT cost_per_gpu_hour = 0';
BEGIN TRY
    INSERT INTO raw.cost_management (session_id, region, gpu_pool_id, date, reserved_gpu_hours, cost_per_gpu_hour)
    VALUES (@sid, 'us-east-1', 'pool-b', '2025-03-01', 500.000000, 0);
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — insert should have been rejected';
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

SET @test = 'V5-05: REJECT cost_per_gpu_hour = -1';
BEGIN TRY
    INSERT INTO raw.cost_management (session_id, region, gpu_pool_id, date, reserved_gpu_hours, cost_per_gpu_hour)
    VALUES (@sid, 'us-east-1', 'pool-b', '2025-03-01', 500.000000, -1);
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — insert should have been rejected';
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- UQ_cost_management_natural_key: duplicate rejected
------------------------------------------------------------
SET @test = 'V5-06: REJECT duplicate natural key (session, region, pool, date)';
BEGIN TRY
    INSERT INTO raw.cost_management (session_id, region, gpu_pool_id, date, reserved_gpu_hours, cost_per_gpu_hour)
    VALUES (@sid, 'us-east-1', 'pool-a', '2025-03-01', 600.000000, 3.000000);
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — insert should have been rejected';
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- INDEXES EXIST
------------------------------------------------------------
SET @test = 'V5-07: IX_cost_mgmt_session exists';
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_cost_mgmt_session' AND object_id = OBJECT_ID('raw.cost_management'))
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

SET @test = 'V5-08: IX_cost_mgmt_grain_lookup exists';
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_cost_mgmt_grain_lookup' AND object_id = OBJECT_ID('raw.cost_management'))
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- CLEANUP
------------------------------------------------------------
DELETE FROM raw.cost_management WHERE session_id = @sid;
DELETE FROM raw.ingestion_log WHERE session_id = @sid;

PRINT '';
PRINT '============================================================';
PRINT 'V5 raw.cost_management: ' + CAST(@pass AS VARCHAR) + ' passed, ' + CAST(@fail AS VARCHAR) + ' failed';
PRINT '============================================================';
