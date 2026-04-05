-- ============================================================
-- TEST: V12 — dbo.state_history
-- 5 CHECK constraints, 1 index
-- Self-transition guard, timestamp sanity
-- ============================================================

DECLARE @pass INT = 0, @fail INT = 0, @test NVARCHAR(200);

DECLARE @sid UNIQUEIDENTIFIER = NEWID();
INSERT INTO raw.ingestion_log (session_id, source_files, status)
VALUES (@sid, '["history.csv"]', 'COMMITTED');

------------------------------------------------------------
-- TABLE EXISTS
------------------------------------------------------------
SET @test = 'V12-01: dbo.state_history table exists';
IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'state_history'
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- VALID INSERT — EMPTY → UPLOADED
------------------------------------------------------------
SET @test = 'V12-02: Valid transition EMPTY → UPLOADED';
BEGIN TRY
    INSERT INTO dbo.state_history
        (session_id, from_state, to_state, transition_trigger)
    VALUES
        (@sid, 'EMPTY', 'UPLOADED', 'INGESTION_COMPLETE');
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- VALID INSERT — UPLOADED → ANALYZED
------------------------------------------------------------
SET @test = 'V12-03: Valid transition UPLOADED → ANALYZED';
BEGIN TRY
    INSERT INTO dbo.state_history
        (session_id, from_state, to_state, transition_trigger)
    VALUES
        (@sid, 'UPLOADED', 'ANALYZED', 'ENGINES_COMPLETE');
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- VALID INSERT — ANALYZED → APPROVED
------------------------------------------------------------
SET @test = 'V12-04: Valid transition ANALYZED → APPROVED';
BEGIN TRY
    INSERT INTO dbo.state_history
        (session_id, from_state, to_state, transition_trigger)
    VALUES
        (@sid, 'ANALYZED', 'APPROVED', 'CFO_APPROVAL');
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- VALID — SYSTEM_RECOVERY self-transition (exception to guard)
------------------------------------------------------------
SET @test = 'V12-05: Valid self-transition with SYSTEM_RECOVERY';
BEGIN TRY
    INSERT INTO dbo.state_history
        (session_id, from_state, to_state, transition_trigger)
    VALUES
        (@sid, 'UPLOADED', 'UPLOADED', 'SYSTEM_RECOVERY');
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- DEFAULT: transitioned_at defaults to SYSUTCDATETIME()
------------------------------------------------------------
SET @test = 'V12-06: DEFAULT transitioned_at is populated';
BEGIN TRY
    DECLARE @ts DATETIME2;
    SELECT TOP 1 @ts = transitioned_at FROM dbo.state_history WHERE session_id = @sid ORDER BY id DESC;
    IF @ts IS NOT NULL
    BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
    ELSE
    BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test + ' — transitioned_at is NULL'; END
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- CHK_history_from_state: invalid enum
------------------------------------------------------------
SET @test = 'V12-07: REJECT invalid from_state (PENDING)';
BEGIN TRY
    INSERT INTO dbo.state_history
        (session_id, from_state, to_state, transition_trigger)
    VALUES
        (@sid, 'PENDING', 'UPLOADED', 'INGESTION_COMPLETE');
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_history_to_state: invalid enum
------------------------------------------------------------
SET @test = 'V12-08: REJECT invalid to_state (DELETED)';
BEGIN TRY
    INSERT INTO dbo.state_history
        (session_id, from_state, to_state, transition_trigger)
    VALUES
        (@sid, 'EMPTY', 'DELETED', 'SESSION_CLOSED');
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_history_trigger: invalid enum
------------------------------------------------------------
SET @test = 'V12-09: REJECT invalid transition_trigger (MANUAL_OVERRIDE)';
BEGIN TRY
    INSERT INTO dbo.state_history
        (session_id, from_state, to_state, transition_trigger)
    VALUES
        (@sid, 'EMPTY', 'UPLOADED', 'MANUAL_OVERRIDE');
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_history_no_self_transition: self-transition without SYSTEM_RECOVERY
------------------------------------------------------------
SET @test = 'V12-10: REJECT self-transition UPLOADED → UPLOADED with ENGINES_COMPLETE';
BEGIN TRY
    INSERT INTO dbo.state_history
        (session_id, from_state, to_state, transition_trigger)
    VALUES
        (@sid, 'UPLOADED', 'UPLOADED', 'ENGINES_COMPLETE');
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_history_timestamp: future timestamp rejected
------------------------------------------------------------
SET @test = 'V12-11: REJECT future transitioned_at';
BEGIN TRY
    INSERT INTO dbo.state_history
        (session_id, from_state, to_state, transition_trigger, transitioned_at)
    VALUES
        (@sid, 'EMPTY', 'UPLOADED', 'INGESTION_COMPLETE', DATEADD(DAY, 1, SYSUTCDATETIME()));
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- FK: invalid session_id rejected
------------------------------------------------------------
SET @test = 'V12-12: REJECT invalid session_id (FK)';
BEGIN TRY
    INSERT INTO dbo.state_history
        (session_id, from_state, to_state, transition_trigger)
    VALUES
        (NEWID(), 'EMPTY', 'UPLOADED', 'INGESTION_COMPLETE');
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- INDEX EXISTS
------------------------------------------------------------
SET @test = 'V12-13: IX_history_session_timeline exists';
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_history_session_timeline' AND object_id = OBJECT_ID('dbo.state_history'))
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- INDEX includes id as tiebreaker
------------------------------------------------------------
SET @test = 'V12-14: IX_history_session_timeline includes id tiebreaker';
IF EXISTS (
    SELECT 1 FROM sys.index_columns ic
    JOIN sys.indexes i ON ic.object_id = i.object_id AND ic.index_id = i.index_id
    JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
    WHERE i.name = 'IX_history_session_timeline'
      AND i.object_id = OBJECT_ID('dbo.state_history')
      AND c.name = 'id'
      AND ic.is_included_column = 0
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- CLEANUP
------------------------------------------------------------
DELETE FROM dbo.state_history WHERE session_id = @sid;
DELETE FROM raw.ingestion_log WHERE session_id = @sid;

PRINT '';
PRINT '============================================================';
PRINT 'V12 dbo.state_history: ' + CAST(@pass AS VARCHAR) + ' passed, ' + CAST(@fail AS VARCHAR) + ' failed';
PRINT '============================================================';
