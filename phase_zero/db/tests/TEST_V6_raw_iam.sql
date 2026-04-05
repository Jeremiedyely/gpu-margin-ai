-- ============================================================
-- TEST: V6 — raw.iam
-- 2 CHECK constraints, 2 indexes, 1 UNIQUE
-- Path A: CHAR(7) billing_period
-- ============================================================

DECLARE @pass INT = 0, @fail INT = 0, @test NVARCHAR(200);

DECLARE @sid UNIQUEIDENTIFIER = NEWID();
INSERT INTO raw.ingestion_log (session_id, source_files, status)
VALUES (@sid, '["iam.csv"]', 'COMMITTED');

------------------------------------------------------------
-- TABLE EXISTS
------------------------------------------------------------
SET @test = 'V6-01: raw.iam table exists';
IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'raw' AND TABLE_NAME = 'iam'
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- CHAR(7) PATH A VERIFICATION
------------------------------------------------------------
SET @test = 'V6-02: billing_period is CHAR(7)';
IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'raw' AND TABLE_NAME = 'iam'
      AND COLUMN_NAME = 'billing_period'
      AND DATA_TYPE = 'char' AND CHARACTER_MAXIMUM_LENGTH = 7
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- VALID INSERT
------------------------------------------------------------
SET @test = 'V6-03: Valid insert';
BEGIN TRY
    INSERT INTO raw.iam (session_id, tenant_id, billing_period, contracted_rate)
    VALUES (@sid, 'tenant-1', '2025-03', 4.500000);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- CHK_iam_billing_period: YYYY-MM format, month 01-12
------------------------------------------------------------
SET @test = 'V6-04: REJECT billing_period = 2025-13';
BEGIN TRY
    INSERT INTO raw.iam (session_id, tenant_id, billing_period, contracted_rate)
    VALUES (@sid, 'tenant-2', '2025-13', 4.500000);
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — insert should have been rejected';
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

SET @test = 'V6-05: REJECT billing_period = 2025-00';
BEGIN TRY
    INSERT INTO raw.iam (session_id, tenant_id, billing_period, contracted_rate)
    VALUES (@sid, 'tenant-2', '2025-00', 4.500000);
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — insert should have been rejected';
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

SET @test = 'V6-06: REJECT billing_period = ABCD-01';
BEGIN TRY
    INSERT INTO raw.iam (session_id, tenant_id, billing_period, contracted_rate)
    VALUES (@sid, 'tenant-2', 'ABCD-01', 4.500000);
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — insert should have been rejected';
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

SET @test = 'V6-07: ACCEPT billing_period = 2025-01';
BEGIN TRY
    INSERT INTO raw.iam (session_id, tenant_id, billing_period, contracted_rate)
    VALUES (@sid, 'tenant-2', '2025-01', 4.500000);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

SET @test = 'V6-08: ACCEPT billing_period = 2025-12';
BEGIN TRY
    INSERT INTO raw.iam (session_id, tenant_id, billing_period, contracted_rate)
    VALUES (@sid, 'tenant-3', '2025-12', 4.500000);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- CHK_iam_rate: must be >= 0
------------------------------------------------------------
SET @test = 'V6-09: REJECT contracted_rate = -1';
BEGIN TRY
    INSERT INTO raw.iam (session_id, tenant_id, billing_period, contracted_rate)
    VALUES (@sid, 'tenant-4', '2025-06', -1.000000);
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — insert should have been rejected';
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

SET @test = 'V6-10: ACCEPT contracted_rate = 0';
BEGIN TRY
    INSERT INTO raw.iam (session_id, tenant_id, billing_period, contracted_rate)
    VALUES (@sid, 'tenant-4', '2025-06', 0.000000);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- UQ_iam_natural_key: duplicate rejected
------------------------------------------------------------
SET @test = 'V6-11: REJECT duplicate (session, tenant, billing_period)';
BEGIN TRY
    INSERT INTO raw.iam (session_id, tenant_id, billing_period, contracted_rate)
    VALUES (@sid, 'tenant-1', '2025-03', 5.000000);
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — insert should have been rejected';
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- INDEXES EXIST
------------------------------------------------------------
SET @test = 'V6-12: IX_iam_resolver exists';
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_iam_resolver' AND object_id = OBJECT_ID('raw.iam'))
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

SET @test = 'V6-13: IX_iam_session exists';
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_iam_session' AND object_id = OBJECT_ID('raw.iam'))
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- CLEANUP
------------------------------------------------------------
DELETE FROM raw.iam WHERE session_id = @sid;
DELETE FROM raw.ingestion_log WHERE session_id = @sid;

PRINT '';
PRINT '============================================================';
PRINT 'V6 raw.iam: ' + CAST(@pass AS VARCHAR) + ' passed, ' + CAST(@fail AS VARCHAR) + ' failed';
PRINT '============================================================';
