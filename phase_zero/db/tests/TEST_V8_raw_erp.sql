-- ============================================================
-- TEST: V8 — raw.erp
-- 1 CHECK constraint, 2 indexes, 1 UNIQUE
-- Path A: CHAR(7) · R12 accepted risk (negative allowed)
-- ============================================================

DECLARE @pass INT = 0, @fail INT = 0, @test NVARCHAR(200);

DECLARE @sid UNIQUEIDENTIFIER = NEWID();
INSERT INTO raw.ingestion_log (session_id, source_files, status)
VALUES (@sid, '["erp.csv"]', 'COMMITTED');

------------------------------------------------------------
-- TABLE EXISTS
------------------------------------------------------------
SET @test = 'V8-01: raw.erp table exists';
IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'raw' AND TABLE_NAME = 'erp'
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- CHAR(7) PATH A
------------------------------------------------------------
SET @test = 'V8-02: billing_period is CHAR(7)';
IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'raw' AND TABLE_NAME = 'erp'
      AND COLUMN_NAME = 'billing_period'
      AND DATA_TYPE = 'char' AND CHARACTER_MAXIMUM_LENGTH = 7
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- VALID INSERT
------------------------------------------------------------
SET @test = 'V8-03: Valid insert';
BEGIN TRY
    INSERT INTO raw.erp (session_id, tenant_id, billing_period, amount_posted)
    VALUES (@sid, 'tenant-1', '2025-03', 1500.00);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- R12: negative amount_posted accepted (credit memo)
------------------------------------------------------------
SET @test = 'V8-04: ACCEPT negative amount_posted (credit memo — R12)';
BEGIN TRY
    INSERT INTO raw.erp (session_id, tenant_id, billing_period, amount_posted)
    VALUES (@sid, 'tenant-2', '2025-03', -200.00);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- CHK_erp_billing_period: YYYY-MM format
------------------------------------------------------------
SET @test = 'V8-05: REJECT billing_period = 2025-00';
BEGIN TRY
    INSERT INTO raw.erp (session_id, tenant_id, billing_period, amount_posted)
    VALUES (@sid, 'tenant-3', '2025-00', 100.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — insert should have been rejected';
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- UQ_erp_natural_key: duplicate rejected
------------------------------------------------------------
SET @test = 'V8-06: REJECT duplicate (session, tenant, billing_period)';
BEGIN TRY
    INSERT INTO raw.erp (session_id, tenant_id, billing_period, amount_posted)
    VALUES (@sid, 'tenant-1', '2025-03', 999.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — insert should have been rejected';
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- INDEXES EXIST
------------------------------------------------------------
SET @test = 'V8-07: IX_erp_session exists';
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_erp_session' AND object_id = OBJECT_ID('raw.erp'))
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

SET @test = 'V8-08: IX_erp_check3 exists';
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_erp_check3' AND object_id = OBJECT_ID('raw.erp'))
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- CLEANUP
------------------------------------------------------------
DELETE FROM raw.erp WHERE session_id = @sid;
DELETE FROM raw.ingestion_log WHERE session_id = @sid;

PRINT '';
PRINT '============================================================';
PRINT 'V8 raw.erp: ' + CAST(@pass AS VARCHAR) + ' passed, ' + CAST(@fail AS VARCHAR) + ' failed';
PRINT '============================================================';
