-- ============================================================
-- TEST: V10 — dbo.reconciliation_results
-- 9 CHECK constraints, 2 indexes, 1 UNIQUE
-- Bidirectional check_name ↔ check_order mapping
-- ============================================================

DECLARE @pass INT = 0, @fail INT = 0, @test NVARCHAR(200);

DECLARE @sid UNIQUEIDENTIFIER = NEWID();
INSERT INTO raw.ingestion_log (session_id, source_files, status)
VALUES (@sid, '["recon.csv"]', 'COMMITTED');

------------------------------------------------------------
-- TABLE EXISTS
------------------------------------------------------------
SET @test = 'V10-01: dbo.reconciliation_results table exists';
IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'reconciliation_results'
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- VALID INSERT — all 3 checks (PASS, PASS, FAIL)
------------------------------------------------------------
SET @test = 'V10-02: Valid insert — Check 1 PASS';
BEGIN TRY
    INSERT INTO dbo.reconciliation_results
        (session_id, check_name, check_order, verdict, fail_subtype, failing_count, detail)
    VALUES
        (@sid, 'Capacity vs Usage', 1, 'PASS', NULL, NULL, NULL);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

SET @test = 'V10-03: Valid insert — Check 2 PASS';
BEGIN TRY
    INSERT INTO dbo.reconciliation_results
        (session_id, check_name, check_order, verdict, fail_subtype, failing_count, detail)
    VALUES
        (@sid, 'Usage vs Tenant Mapping', 2, 'PASS', NULL, NULL, NULL);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

SET @test = 'V10-04: Valid insert — Check 3 FAIL with FAIL-1 subtype';
BEGIN TRY
    INSERT INTO dbo.reconciliation_results
        (session_id, check_name, check_order, verdict, fail_subtype, failing_count, detail)
    VALUES
        (@sid, 'Computed vs Billed vs Posted', 3, 'FAIL', 'FAIL-1', 5, 'Revenue mismatch on 5 tenants');
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- CHK_recon_check_name: invalid name rejected
------------------------------------------------------------
SET @test = 'V10-05: REJECT invalid check_name';
BEGIN TRY
    DECLARE @sid2 UNIQUEIDENTIFIER = NEWID();
    INSERT INTO raw.ingestion_log (session_id, source_files, status)
    VALUES (@sid2, '["recon2.csv"]', 'COMMITTED');

    INSERT INTO dbo.reconciliation_results
        (session_id, check_name, check_order, verdict, fail_subtype, failing_count, detail)
    VALUES
        (@sid2, 'Invalid Check Name', 1, 'PASS', NULL, NULL, NULL);
    SET @fail += 1; PRINT 'FAIL: ' + @test;

    DELETE FROM raw.ingestion_log WHERE session_id = @sid2;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
    BEGIN TRY DELETE FROM raw.ingestion_log WHERE session_id = @sid2; END TRY BEGIN CATCH END CATCH;
END CATCH;

------------------------------------------------------------
-- CHK_recon_check_order_mapping: mismatched name + order
------------------------------------------------------------
SET @test = 'V10-06: REJECT check_name/check_order mismatch (Capacity vs Usage with order=2)';
BEGIN TRY
    DECLARE @sid3 UNIQUEIDENTIFIER = NEWID();
    INSERT INTO raw.ingestion_log (session_id, source_files, status)
    VALUES (@sid3, '["recon3.csv"]', 'COMMITTED');

    INSERT INTO dbo.reconciliation_results
        (session_id, check_name, check_order, verdict, fail_subtype, failing_count, detail)
    VALUES
        (@sid3, 'Capacity vs Usage', 2, 'PASS', NULL, NULL, NULL);
    SET @fail += 1; PRINT 'FAIL: ' + @test;

    DELETE FROM raw.ingestion_log WHERE session_id = @sid3;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
    BEGIN TRY DELETE FROM raw.ingestion_log WHERE session_id = @sid3; END TRY BEGIN CATCH END CATCH;
END CATCH;

------------------------------------------------------------
-- CHK_recon_verdict: invalid verdict rejected
------------------------------------------------------------
SET @test = 'V10-07: REJECT invalid verdict (WARN)';
BEGIN TRY
    DECLARE @sid4 UNIQUEIDENTIFIER = NEWID();
    INSERT INTO raw.ingestion_log (session_id, source_files, status)
    VALUES (@sid4, '["recon4.csv"]', 'COMMITTED');

    INSERT INTO dbo.reconciliation_results
        (session_id, check_name, check_order, verdict, fail_subtype, failing_count, detail)
    VALUES
        (@sid4, 'Capacity vs Usage', 1, 'WARN', NULL, NULL, NULL);
    SET @fail += 1; PRINT 'FAIL: ' + @test;

    DELETE FROM raw.ingestion_log WHERE session_id = @sid4;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
    BEGIN TRY DELETE FROM raw.ingestion_log WHERE session_id = @sid4; END TRY BEGIN CATCH END CATCH;
END CATCH;

------------------------------------------------------------
-- CHK_recon_fail_subtype_rule: subtype only on Check 3 FAIL
------------------------------------------------------------
SET @test = 'V10-08: REJECT fail_subtype on Check 1 FAIL';
BEGIN TRY
    DECLARE @sid5 UNIQUEIDENTIFIER = NEWID();
    INSERT INTO raw.ingestion_log (session_id, source_files, status)
    VALUES (@sid5, '["recon5.csv"]', 'COMMITTED');

    INSERT INTO dbo.reconciliation_results
        (session_id, check_name, check_order, verdict, fail_subtype, failing_count, detail)
    VALUES
        (@sid5, 'Capacity vs Usage', 1, 'FAIL', 'FAIL-1', 3, 'should not have subtype');
    SET @fail += 1; PRINT 'FAIL: ' + @test;

    DELETE FROM raw.ingestion_log WHERE session_id = @sid5;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
    BEGIN TRY DELETE FROM raw.ingestion_log WHERE session_id = @sid5; END TRY BEGIN CATCH END CATCH;
END CATCH;

------------------------------------------------------------
-- CHK_recon_fail_subtype_on_check3_fail: Check 3 FAIL must have subtype
------------------------------------------------------------
SET @test = 'V10-09: REJECT Check 3 FAIL with NULL fail_subtype';
BEGIN TRY
    DECLARE @sid6 UNIQUEIDENTIFIER = NEWID();
    INSERT INTO raw.ingestion_log (session_id, source_files, status)
    VALUES (@sid6, '["recon6.csv"]', 'COMMITTED');

    INSERT INTO dbo.reconciliation_results
        (session_id, check_name, check_order, verdict, fail_subtype, failing_count, detail)
    VALUES
        (@sid6, 'Computed vs Billed vs Posted', 3, 'FAIL', NULL, 2, 'missing subtype');
    SET @fail += 1; PRINT 'FAIL: ' + @test;

    DELETE FROM raw.ingestion_log WHERE session_id = @sid6;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
    BEGIN TRY DELETE FROM raw.ingestion_log WHERE session_id = @sid6; END TRY BEGIN CATCH END CATCH;
END CATCH;

------------------------------------------------------------
-- CHK_recon_fail_subtype_values: invalid subtype rejected
------------------------------------------------------------
SET @test = 'V10-10: REJECT invalid fail_subtype (FAIL-9)';
BEGIN TRY
    DECLARE @sid7 UNIQUEIDENTIFIER = NEWID();
    INSERT INTO raw.ingestion_log (session_id, source_files, status)
    VALUES (@sid7, '["recon7.csv"]', 'COMMITTED');

    INSERT INTO dbo.reconciliation_results
        (session_id, check_name, check_order, verdict, fail_subtype, failing_count, detail)
    VALUES
        (@sid7, 'Computed vs Billed vs Posted', 3, 'FAIL', 'FAIL-9', 1, 'bad subtype');
    SET @fail += 1; PRINT 'FAIL: ' + @test;

    DELETE FROM raw.ingestion_log WHERE session_id = @sid7;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
    BEGIN TRY DELETE FROM raw.ingestion_log WHERE session_id = @sid7; END TRY BEGIN CATCH END CATCH;
END CATCH;

------------------------------------------------------------
-- CHK_recon_failing_count_semantics: PASS must have NULL count
------------------------------------------------------------
SET @test = 'V10-11: REJECT PASS with failing_count > 0';
BEGIN TRY
    DECLARE @sid8 UNIQUEIDENTIFIER = NEWID();
    INSERT INTO raw.ingestion_log (session_id, source_files, status)
    VALUES (@sid8, '["recon8.csv"]', 'COMMITTED');

    INSERT INTO dbo.reconciliation_results
        (session_id, check_name, check_order, verdict, fail_subtype, failing_count, detail)
    VALUES
        (@sid8, 'Capacity vs Usage', 1, 'PASS', NULL, 5, NULL);
    SET @fail += 1; PRINT 'FAIL: ' + @test;

    DELETE FROM raw.ingestion_log WHERE session_id = @sid8;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
    BEGIN TRY DELETE FROM raw.ingestion_log WHERE session_id = @sid8; END TRY BEGIN CATCH END CATCH;
END CATCH;

------------------------------------------------------------
-- CHK_recon_failing_count_semantics: FAIL must have count > 0
------------------------------------------------------------
SET @test = 'V10-12: REJECT FAIL with NULL failing_count';
BEGIN TRY
    DECLARE @sid9 UNIQUEIDENTIFIER = NEWID();
    INSERT INTO raw.ingestion_log (session_id, source_files, status)
    VALUES (@sid9, '["recon9.csv"]', 'COMMITTED');

    INSERT INTO dbo.reconciliation_results
        (session_id, check_name, check_order, verdict, fail_subtype, failing_count, detail)
    VALUES
        (@sid9, 'Capacity vs Usage', 1, 'FAIL', NULL, NULL, 'missing count');
    SET @fail += 1; PRINT 'FAIL: ' + @test;

    DELETE FROM raw.ingestion_log WHERE session_id = @sid9;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
    BEGIN TRY DELETE FROM raw.ingestion_log WHERE session_id = @sid9; END TRY BEGIN CATCH END CATCH;
END CATCH;

------------------------------------------------------------
-- CHK_recon_detail_semantics: PASS must have NULL detail
------------------------------------------------------------
SET @test = 'V10-13: REJECT PASS with non-NULL detail';
BEGIN TRY
    DECLARE @sid10 UNIQUEIDENTIFIER = NEWID();
    INSERT INTO raw.ingestion_log (session_id, source_files, status)
    VALUES (@sid10, '["recon10.csv"]', 'COMMITTED');

    INSERT INTO dbo.reconciliation_results
        (session_id, check_name, check_order, verdict, fail_subtype, failing_count, detail)
    VALUES
        (@sid10, 'Capacity vs Usage', 1, 'PASS', NULL, NULL, 'should not have detail on PASS');
    SET @fail += 1; PRINT 'FAIL: ' + @test;

    DELETE FROM raw.ingestion_log WHERE session_id = @sid10;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
    BEGIN TRY DELETE FROM raw.ingestion_log WHERE session_id = @sid10; END TRY BEGIN CATCH END CATCH;
END CATCH;

------------------------------------------------------------
-- UQ_recon_check_per_session: duplicate check_name per session
------------------------------------------------------------
SET @test = 'V10-14: REJECT duplicate check_name per session';
BEGIN TRY
    INSERT INTO dbo.reconciliation_results
        (session_id, check_name, check_order, verdict, fail_subtype, failing_count, detail)
    VALUES
        (@sid, 'Capacity vs Usage', 1, 'PASS', NULL, NULL, NULL);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- FK: invalid session_id rejected
------------------------------------------------------------
SET @test = 'V10-15: REJECT invalid session_id (FK)';
BEGIN TRY
    INSERT INTO dbo.reconciliation_results
        (session_id, check_name, check_order, verdict, fail_subtype, failing_count, detail)
    VALUES
        (NEWID(), 'Capacity vs Usage', 1, 'PASS', NULL, NULL, NULL);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- INDEXES EXIST
------------------------------------------------------------
SET @test = 'V10-16: IX_recon_session exists';
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_recon_session' AND object_id = OBJECT_ID('dbo.reconciliation_results'))
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

SET @test = 'V10-17: IX_recon_session_order exists';
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_recon_session_order' AND object_id = OBJECT_ID('dbo.reconciliation_results'))
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- CLEANUP
------------------------------------------------------------
DELETE FROM dbo.reconciliation_results WHERE session_id = @sid;
DELETE FROM raw.ingestion_log WHERE session_id = @sid;

PRINT '';
PRINT '============================================================';
PRINT 'V10 dbo.reconciliation_results: ' + CAST(@pass AS VARCHAR) + ' passed, ' + CAST(@fail AS VARCHAR) + ' failed';
PRINT '============================================================';
