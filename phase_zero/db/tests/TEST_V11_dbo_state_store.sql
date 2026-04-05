-- ============================================================
-- TEST: V11 — dbo.state_store
-- 10 CHECK constraints, 0 extra indexes (PK only)
-- Bidirectional APPROVED ↔ write_result
-- EMPTY state hardening, R6-W-1 APPROVED+FAIL permitted
-- ============================================================

DECLARE @pass INT = 0, @fail INT = 0, @test NVARCHAR(200);

DECLARE @sid UNIQUEIDENTIFIER = NEWID();
INSERT INTO raw.ingestion_log (session_id, source_files, status)
VALUES (@sid, '["state.csv"]', 'COMMITTED');

------------------------------------------------------------
-- TABLE EXISTS
------------------------------------------------------------
SET @test = 'V11-01: dbo.state_store table exists';
IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'state_store'
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- VALID INSERT — EMPTY state (initial lifecycle)
------------------------------------------------------------
SET @test = 'V11-02: Valid EMPTY state insert';
BEGIN TRY
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result, retry_count)
    VALUES
        (@sid, 'EMPTY', 'ACTIVE', 'IDLE', NULL, 0);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

-- Clean for next inserts (PK = session_id, so only one row per session)
DELETE FROM dbo.state_store WHERE session_id = @sid;

------------------------------------------------------------
-- VALID — UPLOADED + ANALYZING
------------------------------------------------------------
SET @test = 'V11-03: Valid UPLOADED + ANALYZING insert';
BEGIN TRY
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result, retry_count)
    VALUES
        (@sid, 'UPLOADED', 'ACTIVE', 'ANALYZING', NULL, 0);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

DELETE FROM dbo.state_store WHERE session_id = @sid;

------------------------------------------------------------
-- VALID — APPROVED + SUCCESS (happy path terminal)
------------------------------------------------------------
SET @test = 'V11-04: Valid APPROVED + SUCCESS + TERMINAL';
BEGIN TRY
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result, retry_count)
    VALUES
        (@sid, 'APPROVED', 'TERMINAL', 'IDLE', 'SUCCESS', 0);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

DELETE FROM dbo.state_store WHERE session_id = @sid;

------------------------------------------------------------
-- VALID — R6-W-1: APPROVED + FAIL (forensic audit permitted)
------------------------------------------------------------
SET @test = 'V11-05: Valid APPROVED + FAIL (R6-W-1 design decision)';
BEGIN TRY
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result, retry_count)
    VALUES
        (@sid, 'APPROVED', 'ACTIVE', 'IDLE', 'FAIL', 1);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

DELETE FROM dbo.state_store WHERE session_id = @sid;

------------------------------------------------------------
-- CHK_state_application: invalid enum
------------------------------------------------------------
SET @test = 'V11-06: REJECT invalid application_state (PENDING)';
BEGIN TRY
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result, retry_count)
    VALUES
        (@sid, 'PENDING', 'ACTIVE', 'IDLE', NULL, 0);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_state_session_status: invalid enum
------------------------------------------------------------
SET @test = 'V11-07: REJECT invalid session_status (CLOSED)';
BEGIN TRY
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result, retry_count)
    VALUES
        (@sid, 'EMPTY', 'CLOSED', 'IDLE', NULL, 0);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_state_analysis_status: invalid enum
------------------------------------------------------------
SET @test = 'V11-08: REJECT invalid analysis_status (RUNNING)';
BEGIN TRY
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result, retry_count)
    VALUES
        (@sid, 'UPLOADED', 'ACTIVE', 'RUNNING', NULL, 0);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_state_write_result: invalid enum
------------------------------------------------------------
SET @test = 'V11-09: REJECT invalid write_result (PARTIAL)';
BEGIN TRY
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result, retry_count)
    VALUES
        (@sid, 'APPROVED', 'ACTIVE', 'IDLE', 'PARTIAL', 0);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_state_approved_requires_write_result: APPROVED + NULL write_result
------------------------------------------------------------
SET @test = 'V11-10: REJECT APPROVED with NULL write_result';
BEGIN TRY
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result, retry_count)
    VALUES
        (@sid, 'APPROVED', 'ACTIVE', 'IDLE', NULL, 0);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_state_write_result_requires_approved: write_result on non-APPROVED
------------------------------------------------------------
SET @test = 'V11-11: REJECT write_result on ANALYZED (not APPROVED)';
BEGIN TRY
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result, retry_count)
    VALUES
        (@sid, 'ANALYZED', 'ACTIVE', 'IDLE', 'SUCCESS', 0);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_state_terminal_requires_approved: TERMINAL on non-APPROVED
------------------------------------------------------------
SET @test = 'V11-12: REJECT TERMINAL on UPLOADED state';
BEGIN TRY
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result, retry_count)
    VALUES
        (@sid, 'UPLOADED', 'TERMINAL', 'IDLE', NULL, 0);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_state_analysis_status_scope: ANALYZING only on UPLOADED
------------------------------------------------------------
SET @test = 'V11-13: REJECT ANALYZING on ANALYZED state';
BEGIN TRY
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result, retry_count)
    VALUES
        (@sid, 'ANALYZED', 'ACTIVE', 'ANALYZING', NULL, 0);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_state_empty_consistency: EMPTY with wrong session_status
------------------------------------------------------------
SET @test = 'V11-14: REJECT EMPTY with TERMINAL session_status';
BEGIN TRY
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result, retry_count)
    VALUES
        (@sid, 'EMPTY', 'TERMINAL', 'IDLE', NULL, 0);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_state_empty_consistency: EMPTY with ANALYZING
------------------------------------------------------------
SET @test = 'V11-15: REJECT EMPTY with ANALYZING analysis_status';
BEGIN TRY
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result, retry_count)
    VALUES
        (@sid, 'EMPTY', 'ACTIVE', 'ANALYZING', NULL, 0);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_state_empty_consistency: EMPTY with write_result set
------------------------------------------------------------
SET @test = 'V11-16: REJECT EMPTY with write_result = SUCCESS';
BEGIN TRY
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result, retry_count)
    VALUES
        (@sid, 'EMPTY', 'ACTIVE', 'IDLE', 'SUCCESS', 0);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_state_retry_count: negative rejected
------------------------------------------------------------
SET @test = 'V11-17: REJECT retry_count = -1';
BEGIN TRY
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result, retry_count)
    VALUES
        (@sid, 'EMPTY', 'ACTIVE', 'IDLE', NULL, -1);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_state_retry_count: ceiling exceeded
------------------------------------------------------------
SET @test = 'V11-18: REJECT retry_count = 101';
BEGIN TRY
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result, retry_count)
    VALUES
        (@sid, 'EMPTY', 'ACTIVE', 'IDLE', NULL, 101);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- DEFAULT: retry_count defaults to 0
------------------------------------------------------------
SET @test = 'V11-19: DEFAULT retry_count = 0';
BEGIN TRY
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result)
    VALUES
        (@sid, 'EMPTY', 'ACTIVE', 'IDLE', NULL);

    DECLARE @rc INT;
    SELECT @rc = retry_count FROM dbo.state_store WHERE session_id = @sid;
    IF @rc = 0
    BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
    ELSE
    BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test + ' — got ' + CAST(@rc AS VARCHAR); END
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

DELETE FROM dbo.state_store WHERE session_id = @sid;

------------------------------------------------------------
-- PK: duplicate session_id rejected
------------------------------------------------------------
SET @test = 'V11-20: REJECT duplicate session_id (PK)';
BEGIN TRY
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result)
    VALUES
        (@sid, 'EMPTY', 'ACTIVE', 'IDLE', NULL);
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result)
    VALUES
        (@sid, 'UPLOADED', 'ACTIVE', 'IDLE', NULL);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- FK: invalid session_id rejected
------------------------------------------------------------
SET @test = 'V11-21: REJECT invalid session_id (FK)';
BEGIN TRY
    INSERT INTO dbo.state_store
        (session_id, application_state, session_status, analysis_status, write_result)
    VALUES
        (NEWID(), 'EMPTY', 'ACTIVE', 'IDLE', NULL);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CLEANUP
------------------------------------------------------------
DELETE FROM dbo.state_store WHERE session_id = @sid;
DELETE FROM raw.ingestion_log WHERE session_id = @sid;

PRINT '';
PRINT '============================================================';
PRINT 'V11 dbo.state_store: ' + CAST(@pass AS VARCHAR) + ' passed, ' + CAST(@fail AS VARCHAR) + ' failed';
PRINT '============================================================';
