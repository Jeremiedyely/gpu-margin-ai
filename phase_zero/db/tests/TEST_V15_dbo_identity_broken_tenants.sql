-- ============================================================
-- TEST: V15 — dbo.identity_broken_tenants
-- 1 CHECK constraint, 1 index, 1 trigger (THROW 51002)
-- Composite PK (session_id, failed_tenant_id)
-- Immutable: UPDATE + DELETE both blocked
-- ============================================================

DECLARE @pass INT = 0, @fail INT = 0, @test NVARCHAR(200);

DECLARE @sid UNIQUEIDENTIFIER = NEWID();
INSERT INTO raw.ingestion_log (session_id, source_files, status)
VALUES (@sid, '["ibt.csv"]', 'COMMITTED');

------------------------------------------------------------
-- TABLE EXISTS
------------------------------------------------------------
SET @test = 'V15-01: dbo.identity_broken_tenants table exists';
IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'identity_broken_tenants'
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- VALID INSERT
------------------------------------------------------------
SET @test = 'V15-02: Valid insert';
BEGIN TRY
    INSERT INTO dbo.identity_broken_tenants (session_id, failed_tenant_id)
    VALUES (@sid, 'orphan-tenant-001');
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- VALID — multiple tenants per session
------------------------------------------------------------
SET @test = 'V15-03: Valid second tenant same session';
BEGIN TRY
    INSERT INTO dbo.identity_broken_tenants (session_id, failed_tenant_id)
    VALUES (@sid, 'orphan-tenant-002');
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- CHK_ibt_tenant_not_empty: empty string rejected
------------------------------------------------------------
SET @test = 'V15-04: REJECT empty failed_tenant_id';
BEGIN TRY
    INSERT INTO dbo.identity_broken_tenants (session_id, failed_tenant_id)
    VALUES (@sid, '');
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- CHK_ibt_tenant_not_empty: whitespace-only rejected
------------------------------------------------------------
SET @test = 'V15-05: REJECT whitespace-only failed_tenant_id';
BEGIN TRY
    INSERT INTO dbo.identity_broken_tenants (session_id, failed_tenant_id)
    VALUES (@sid, '   ');
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- PK: duplicate composite key rejected
------------------------------------------------------------
SET @test = 'V15-06: REJECT duplicate (session_id, failed_tenant_id)';
BEGIN TRY
    INSERT INTO dbo.identity_broken_tenants (session_id, failed_tenant_id)
    VALUES (@sid, 'orphan-tenant-001');
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- FK: invalid session_id rejected
------------------------------------------------------------
SET @test = 'V15-07: REJECT invalid session_id (FK)';
BEGIN TRY
    INSERT INTO dbo.identity_broken_tenants (session_id, failed_tenant_id)
    VALUES (NEWID(), 'orphan-tenant-001');
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- TRIGGER: THROW 51002 — UPDATE blocked
------------------------------------------------------------
SET @test = 'V15-08: TRIGGER blocks UPDATE (THROW 51002)';
BEGIN TRY
    UPDATE dbo.identity_broken_tenants
    SET failed_tenant_id = 'changed'
    WHERE session_id = @sid AND failed_tenant_id = 'orphan-tenant-001';
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — update should have been blocked';
END TRY
BEGIN CATCH
    IF ERROR_NUMBER() = 51002
    BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
    ELSE
    BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test + ' — wrong error: ' + CAST(ERROR_NUMBER() AS VARCHAR); END
END CATCH;

------------------------------------------------------------
-- TRIGGER: THROW 51002 — DELETE blocked
------------------------------------------------------------
SET @test = 'V15-09: TRIGGER blocks DELETE (THROW 51002)';
BEGIN TRY
    DELETE FROM dbo.identity_broken_tenants
    WHERE session_id = @sid AND failed_tenant_id = 'orphan-tenant-001';
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — delete should have been blocked';
END TRY
BEGIN CATCH
    IF ERROR_NUMBER() = 51002
    BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
    ELSE
    BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test + ' — wrong error: ' + CAST(ERROR_NUMBER() AS VARCHAR); END
END CATCH;

------------------------------------------------------------
-- INDEX EXISTS
------------------------------------------------------------
SET @test = 'V15-10: IX_ibt_session_lookup exists';
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ibt_session_lookup' AND object_id = OBJECT_ID('dbo.identity_broken_tenants'))
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- CLEANUP — must disable trigger to delete test data
------------------------------------------------------------
DISABLE TRIGGER TR_identity_broken_tenants_prevent_mutation ON dbo.identity_broken_tenants;
DELETE FROM dbo.identity_broken_tenants WHERE session_id = @sid;
ENABLE TRIGGER TR_identity_broken_tenants_prevent_mutation ON dbo.identity_broken_tenants;
DELETE FROM raw.ingestion_log WHERE session_id = @sid;

PRINT '';
PRINT '============================================================';
PRINT 'V15 dbo.identity_broken_tenants: ' + CAST(@pass AS VARCHAR) + ' passed, ' + CAST(@fail AS VARCHAR) + ' failed';
PRINT '============================================================';
