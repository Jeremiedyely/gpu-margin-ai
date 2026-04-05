-- ============================================================
-- TEST: V3 — raw.ingestion_log
-- 2 CHECK constraints, 0 indexes, 0 triggers
-- ============================================================

DECLARE @pass INT = 0, @fail INT = 0, @test NVARCHAR(200);
DECLARE @sid UNIQUEIDENTIFIER = NEWID();

------------------------------------------------------------
-- TABLE EXISTS
------------------------------------------------------------
SET @test = 'V3-01: raw.ingestion_log table exists';
IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'raw' AND TABLE_NAME = 'ingestion_log'
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- VALID INSERT (DEFAULT status = 'FAILED')
------------------------------------------------------------
SET @test = 'V3-02: Valid insert with DEFAULT status';
BEGIN TRY
    INSERT INTO raw.ingestion_log (session_id, source_files)
    VALUES (@sid, '["file1.csv"]');
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

SET @test = 'V3-03: DEFAULT status is FAILED';
IF EXISTS (
    SELECT 1 FROM raw.ingestion_log
    WHERE session_id = @sid AND status = 'FAILED'
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- CHK_ingestion_log_status: only COMMITTED or FAILED
------------------------------------------------------------
SET @test = 'V3-04: REJECT invalid status (PENDING)';
BEGIN TRY
    INSERT INTO raw.ingestion_log (session_id, source_files, status)
    VALUES (NEWID(), '["file.csv"]', 'PENDING');
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — insert should have been rejected';
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

SET @test = 'V3-05: ACCEPT status = COMMITTED';
DECLARE @sid2 UNIQUEIDENTIFIER = NEWID();
BEGIN TRY
    INSERT INTO raw.ingestion_log (session_id, source_files, status)
    VALUES (@sid2, '["file.csv"]', 'COMMITTED');
    SET @pass += 1; PRINT 'PASS: ' + @test;
    DELETE FROM raw.ingestion_log WHERE session_id = @sid2;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- CHK_ingestion_source_files_json: must be valid JSON
------------------------------------------------------------
SET @test = 'V3-06: REJECT invalid JSON in source_files';
BEGIN TRY
    INSERT INTO raw.ingestion_log (session_id, source_files)
    VALUES (NEWID(), 'not-json');
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — insert should have been rejected';
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- PK: duplicate session_id rejected
------------------------------------------------------------
SET @test = 'V3-07: REJECT duplicate session_id';
BEGIN TRY
    INSERT INTO raw.ingestion_log (session_id, source_files)
    VALUES (@sid, '["dup.csv"]');
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — insert should have been rejected';
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CLEANUP
------------------------------------------------------------
DELETE FROM raw.ingestion_log WHERE session_id = @sid;

------------------------------------------------------------
-- SUMMARY
------------------------------------------------------------
PRINT '';
PRINT '============================================================';
PRINT 'V3 raw.ingestion_log: ' + CAST(@pass AS VARCHAR) + ' passed, ' + CAST(@fail AS VARCHAR) + ' failed';
PRINT '============================================================';
