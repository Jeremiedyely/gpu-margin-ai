-- ============================================================
-- TEST: V7 — raw.billing
-- 1 CHECK constraint, 2 indexes, 1 UNIQUE
-- Path A: CHAR(7) · R12 accepted risk (negative allowed)
-- ============================================================

DECLARE @pass INT = 0, @fail INT = 0, @test NVARCHAR(200);

DECLARE @sid UNIQUEIDENTIFIER = NEWID();
INSERT INTO raw.ingestion_log (session_id, source_files, status)
VALUES (@sid, '["billing.csv"]', 'COMMITTED');

------------------------------------------------------------
-- TABLE EXISTS
------------------------------------------------------------
SET @test = 'V7-01: raw.billing table exists';
IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'raw' AND TABLE_NAME = 'billing'
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- CHAR(7) PATH A
------------------------------------------------------------
SET @test = 'V7-02: billing_period is CHAR(7)';
IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'raw' AND TABLE_NAME = 'billing'
      AND COLUMN_NAME = 'billing_period'
      AND DATA_TYPE = 'char' AND CHARACTER_MAXIMUM_LENGTH = 7
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- VALID INSERT
------------------------------------------------------------
SET @test = 'V7-03: Valid insert';
BEGIN TRY
    INSERT INTO raw.billing (session_id, tenant_id, billing_period, billable_amount)
    VALUES (@sid, 'tenant-1', '2025-03', 1500.00);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- R12: negative billable_amount accepted (credit memo)
------------------------------------------------------------
SET @test = 'V7-04: ACCEPT negative billable_amount (credit memo — R12)';
BEGIN TRY
    INSERT INTO raw.billing (session_id, tenant_id, billing_period, billable_amount)
    VALUES (@sid, 'tenant-2', '2025-03', -200.00);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- CHK_billing_billing_period: YYYY-MM format
------------------------------------------------------------
SET @test = 'V7-05: REJECT billing_period = 2025-13';
BEGIN TRY
    INSERT INTO raw.billing (session_id, tenant_id, billing_period, billable_amount)
    VALUES (@sid, 'tenant-3', '2025-13', 100.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — insert should have been rejected';
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- UQ_billing_natural_key: duplicate rejected
------------------------------------------------------------
SET @test = 'V7-06: REJECT duplicate (session, tenant, billing_period)';
BEGIN TRY
    INSERT INTO raw.billing (session_id, tenant_id, billing_period, billable_amount)
    VALUES (@sid, 'tenant-1', '2025-03', 999.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — insert should have been rejected';
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- INDEXES EXIST
------------------------------------------------------------
SET @test = 'V7-07: IX_billing_session exists';
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_billing_session' AND object_id = OBJECT_ID('raw.billing'))
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

SET @test = 'V7-08: IX_billing_check3 exists';
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_billing_check3' AND object_id = OBJECT_ID('raw.billing'))
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- CLEANUP
------------------------------------------------------------
DELETE FROM raw.billing WHERE session_id = @sid;
DELETE FROM raw.ingestion_log WHERE session_id = @sid;

PRINT '';
PRINT '============================================================';
PRINT 'V7 raw.billing: ' + CAST(@pass AS VARCHAR) + ' passed, ' + CAST(@fail AS VARCHAR) + ' failed';
PRINT '============================================================';
