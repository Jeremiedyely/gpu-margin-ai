-- ============================================================
-- TEST: V4 — raw.telemetry
-- 1 CHECK constraint, 3 indexes, 0 triggers
-- ============================================================

DECLARE @pass INT = 0, @fail INT = 0, @test NVARCHAR(200);

DECLARE @sid UNIQUEIDENTIFIER = NEWID();
INSERT INTO raw.ingestion_log (session_id, source_files, status)
VALUES (@sid, '["telemetry.csv"]', 'COMMITTED');

------------------------------------------------------------
-- TABLE EXISTS
------------------------------------------------------------
SET @test = 'V4-01: raw.telemetry table exists';
IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'raw' AND TABLE_NAME = 'telemetry'
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- VALID INSERT
------------------------------------------------------------
SET @test = 'V4-02: Valid insert';
BEGIN TRY
    INSERT INTO raw.telemetry (session_id, region, gpu_pool_id, date, tenant_id, gpu_hours_consumed)
    VALUES (@sid, 'us-east-1', 'pool-a', '2025-03-01', 'tenant-1', 100.500000);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- CHK_telemetry_gpu_hours: must be > 0
------------------------------------------------------------
SET @test = 'V4-03: REJECT gpu_hours_consumed = 0';
BEGIN TRY
    INSERT INTO raw.telemetry (session_id, region, gpu_pool_id, date, tenant_id, gpu_hours_consumed)
    VALUES (@sid, 'us-east-1', 'pool-a', '2025-03-01', 'tenant-2', 0);
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — insert should have been rejected';
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

SET @test = 'V4-04: REJECT gpu_hours_consumed = -1';
BEGIN TRY
    INSERT INTO raw.telemetry (session_id, region, gpu_pool_id, date, tenant_id, gpu_hours_consumed)
    VALUES (@sid, 'us-east-1', 'pool-a', '2025-03-01', 'tenant-2', -1);
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — insert should have been rejected';
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- FK: invalid session_id rejected
------------------------------------------------------------
SET @test = 'V4-05: REJECT invalid session_id (FK)';
BEGIN TRY
    INSERT INTO raw.telemetry (session_id, region, gpu_pool_id, date, tenant_id, gpu_hours_consumed)
    VALUES (NEWID(), 'us-east-1', 'pool-a', '2025-03-01', 'tenant-1', 50.000000);
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — insert should have been rejected';
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- INDEXES EXIST
------------------------------------------------------------
SET @test = 'V4-06: IX_telemetry_session exists';
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_telemetry_session' AND object_id = OBJECT_ID('raw.telemetry'))
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

SET @test = 'V4-07: IX_telemetry_grain exists';
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_telemetry_grain' AND object_id = OBJECT_ID('raw.telemetry'))
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

SET @test = 'V4-08: IX_telemetry_pool_day exists';
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_telemetry_pool_day' AND object_id = OBJECT_ID('raw.telemetry'))
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- CLEANUP
------------------------------------------------------------
DELETE FROM raw.telemetry WHERE session_id = @sid;
DELETE FROM raw.ingestion_log WHERE session_id = @sid;

PRINT '';
PRINT '============================================================';
PRINT 'V4 raw.telemetry: ' + CAST(@pass AS VARCHAR) + ' passed, ' + CAST(@fail AS VARCHAR) + ' failed';
PRINT '============================================================';
