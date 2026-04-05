-- ============================================================
-- TEST: V1 — Snapshot Isolation
-- TEST: V2 — Schema Namespaces
-- Run against: gpu_margin database after Flyway V1-V2
-- ============================================================

DECLARE @pass INT = 0, @fail INT = 0, @test NVARCHAR(200);

------------------------------------------------------------
-- V1: SNAPSHOT ISOLATION
------------------------------------------------------------
SET @test = 'V1-01: READ_COMMITTED_SNAPSHOT is ON';
IF EXISTS (
    SELECT 1 FROM sys.databases
    WHERE name = DB_NAME() AND is_read_committed_snapshot_on = 1
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

SET @test = 'V1-02: ALLOW_SNAPSHOT_ISOLATION is ON';
IF EXISTS (
    SELECT 1 FROM sys.databases
    WHERE name = DB_NAME() AND snapshot_isolation_state = 1
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- V2: SCHEMA NAMESPACES
------------------------------------------------------------
SET @test = 'V2-01: Schema [raw] exists';
IF EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'raw')
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

SET @test = 'V2-02: Schema [final] exists';
IF EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'final')
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

SET @test = 'V2-03: Schema [dbo] exists';
IF EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'dbo')
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- SUMMARY
------------------------------------------------------------
PRINT '';
PRINT '============================================================';
PRINT 'V1-V2 INFRASTRUCTURE: ' + CAST(@pass AS VARCHAR) + ' passed, ' + CAST(@fail AS VARCHAR) + ' failed';
PRINT '============================================================';
