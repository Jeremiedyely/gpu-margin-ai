-- ============================================================
-- TEST: V14 — dbo.kpi_cache
-- 6 CHECK constraints, 1 trigger (THROW 51001)
-- Complement integrity: idle_gpu_cost_pct + cost_allocation_rate = 100
-- Immutable: UPDATE + DELETE both blocked
-- ============================================================

DECLARE @pass INT = 0, @fail INT = 0, @test NVARCHAR(200);

DECLARE @sid UNIQUEIDENTIFIER = NEWID();
INSERT INTO raw.ingestion_log (session_id, source_files, status)
VALUES (@sid, '["kpi.csv"]', 'COMMITTED');

------------------------------------------------------------
-- TABLE EXISTS
------------------------------------------------------------
SET @test = 'V14-01: dbo.kpi_cache table exists';
IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'kpi_cache'
)
BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
ELSE
BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test; END;

------------------------------------------------------------
-- VALID INSERT — 30% idle, 70% allocated
------------------------------------------------------------
SET @test = 'V14-02: Valid insert (30/70 split)';
BEGIN TRY
    INSERT INTO dbo.kpi_cache
        (session_id, gpu_revenue, gpu_cogs, idle_gpu_cost, idle_gpu_cost_pct, cost_allocation_rate)
    VALUES
        (@sid, 10000.00, 7000.00, 2100.00, 30.00, 70.00);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- VALID — edge case: 0% idle, 100% allocated
------------------------------------------------------------
DECLARE @sid2 UNIQUEIDENTIFIER = NEWID();
INSERT INTO raw.ingestion_log (session_id, source_files, status)
VALUES (@sid2, '["kpi2.csv"]', 'COMMITTED');

SET @test = 'V14-03: Valid insert (0/100 edge)';
BEGIN TRY
    INSERT INTO dbo.kpi_cache
        (session_id, gpu_revenue, gpu_cogs, idle_gpu_cost, idle_gpu_cost_pct, cost_allocation_rate)
    VALUES
        (@sid2, 5000.00, 3000.00, 0.00, 0.00, 100.00);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- VALID — edge case: 100% idle, 0% allocated
------------------------------------------------------------
DECLARE @sid3 UNIQUEIDENTIFIER = NEWID();
INSERT INTO raw.ingestion_log (session_id, source_files, status)
VALUES (@sid3, '["kpi3.csv"]', 'COMMITTED');

SET @test = 'V14-04: Valid insert (100/0 edge)';
BEGIN TRY
    INSERT INTO dbo.kpi_cache
        (session_id, gpu_revenue, gpu_cogs, idle_gpu_cost, idle_gpu_cost_pct, cost_allocation_rate)
    VALUES
        (@sid3, 0.00, 5000.00, 5000.00, 100.00, 0.00);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- CHK_kpi_revenue_nonneg: negative rejected
------------------------------------------------------------
SET @test = 'V14-05: REJECT negative gpu_revenue';
BEGIN TRY
    DECLARE @sid4 UNIQUEIDENTIFIER = NEWID();
    INSERT INTO raw.ingestion_log (session_id, source_files, status)
    VALUES (@sid4, '["kpi4.csv"]', 'COMMITTED');

    INSERT INTO dbo.kpi_cache
        (session_id, gpu_revenue, gpu_cogs, idle_gpu_cost, idle_gpu_cost_pct, cost_allocation_rate)
    VALUES
        (@sid4, -1.00, 7000.00, 2100.00, 30.00, 70.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;

    DELETE FROM raw.ingestion_log WHERE session_id = @sid4;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
    BEGIN TRY DELETE FROM raw.ingestion_log WHERE session_id = @sid4; END TRY BEGIN CATCH END CATCH;
END CATCH;

------------------------------------------------------------
-- CHK_kpi_cogs_nonneg: negative rejected
------------------------------------------------------------
SET @test = 'V14-06: REJECT negative gpu_cogs';
BEGIN TRY
    DECLARE @sid5 UNIQUEIDENTIFIER = NEWID();
    INSERT INTO raw.ingestion_log (session_id, source_files, status)
    VALUES (@sid5, '["kpi5.csv"]', 'COMMITTED');

    INSERT INTO dbo.kpi_cache
        (session_id, gpu_revenue, gpu_cogs, idle_gpu_cost, idle_gpu_cost_pct, cost_allocation_rate)
    VALUES
        (@sid5, 10000.00, -1.00, 2100.00, 30.00, 70.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;

    DELETE FROM raw.ingestion_log WHERE session_id = @sid5;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
    BEGIN TRY DELETE FROM raw.ingestion_log WHERE session_id = @sid5; END TRY BEGIN CATCH END CATCH;
END CATCH;

------------------------------------------------------------
-- CHK_kpi_idle_nonneg: negative rejected
------------------------------------------------------------
SET @test = 'V14-07: REJECT negative idle_gpu_cost';
BEGIN TRY
    DECLARE @sid6 UNIQUEIDENTIFIER = NEWID();
    INSERT INTO raw.ingestion_log (session_id, source_files, status)
    VALUES (@sid6, '["kpi6.csv"]', 'COMMITTED');

    INSERT INTO dbo.kpi_cache
        (session_id, gpu_revenue, gpu_cogs, idle_gpu_cost, idle_gpu_cost_pct, cost_allocation_rate)
    VALUES
        (@sid6, 10000.00, 7000.00, -1.00, 30.00, 70.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;

    DELETE FROM raw.ingestion_log WHERE session_id = @sid6;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
    BEGIN TRY DELETE FROM raw.ingestion_log WHERE session_id = @sid6; END TRY BEGIN CATCH END CATCH;
END CATCH;

------------------------------------------------------------
-- CHK_kpi_idle_pct: > 100 rejected
------------------------------------------------------------
SET @test = 'V14-08: REJECT idle_gpu_cost_pct = 101';
BEGIN TRY
    DECLARE @sid7 UNIQUEIDENTIFIER = NEWID();
    INSERT INTO raw.ingestion_log (session_id, source_files, status)
    VALUES (@sid7, '["kpi7.csv"]', 'COMMITTED');

    INSERT INTO dbo.kpi_cache
        (session_id, gpu_revenue, gpu_cogs, idle_gpu_cost, idle_gpu_cost_pct, cost_allocation_rate)
    VALUES
        (@sid7, 10000.00, 7000.00, 2100.00, 101.00, -1.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;

    DELETE FROM raw.ingestion_log WHERE session_id = @sid7;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
    BEGIN TRY DELETE FROM raw.ingestion_log WHERE session_id = @sid7; END TRY BEGIN CATCH END CATCH;
END CATCH;

------------------------------------------------------------
-- CHK_kpi_allocation_rate: negative rejected
------------------------------------------------------------
SET @test = 'V14-09: REJECT cost_allocation_rate = -1';
BEGIN TRY
    DECLARE @sid8 UNIQUEIDENTIFIER = NEWID();
    INSERT INTO raw.ingestion_log (session_id, source_files, status)
    VALUES (@sid8, '["kpi8.csv"]', 'COMMITTED');

    INSERT INTO dbo.kpi_cache
        (session_id, gpu_revenue, gpu_cogs, idle_gpu_cost, idle_gpu_cost_pct, cost_allocation_rate)
    VALUES
        (@sid8, 10000.00, 7000.00, 2100.00, 101.00, -1.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;

    DELETE FROM raw.ingestion_log WHERE session_id = @sid8;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
    BEGIN TRY DELETE FROM raw.ingestion_log WHERE session_id = @sid8; END TRY BEGIN CATCH END CATCH;
END CATCH;

------------------------------------------------------------
-- CHK_kpi_complement: sum != 100 rejected
------------------------------------------------------------
SET @test = 'V14-10: REJECT complement violation (40 + 70 = 110)';
BEGIN TRY
    DECLARE @sid9 UNIQUEIDENTIFIER = NEWID();
    INSERT INTO raw.ingestion_log (session_id, source_files, status)
    VALUES (@sid9, '["kpi9.csv"]', 'COMMITTED');

    INSERT INTO dbo.kpi_cache
        (session_id, gpu_revenue, gpu_cogs, idle_gpu_cost, idle_gpu_cost_pct, cost_allocation_rate)
    VALUES
        (@sid9, 10000.00, 7000.00, 2100.00, 40.00, 70.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;

    DELETE FROM raw.ingestion_log WHERE session_id = @sid9;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
    BEGIN TRY DELETE FROM raw.ingestion_log WHERE session_id = @sid9; END TRY BEGIN CATCH END CATCH;
END CATCH;

------------------------------------------------------------
-- CHK_kpi_complement: tolerance edge — 0.01 accepted
------------------------------------------------------------
DECLARE @sid10 UNIQUEIDENTIFIER = NEWID();
INSERT INTO raw.ingestion_log (session_id, source_files, status)
VALUES (@sid10, '["kpi10.csv"]', 'COMMITTED');

SET @test = 'V14-11: ACCEPT complement within 0.01 tolerance (30.01 + 70.00)';
BEGIN TRY
    INSERT INTO dbo.kpi_cache
        (session_id, gpu_revenue, gpu_cogs, idle_gpu_cost, idle_gpu_cost_pct, cost_allocation_rate)
    VALUES
        (@sid10, 10000.00, 7000.00, 2100.00, 30.01, 70.00);
    SET @pass += 1; PRINT 'PASS: ' + @test;
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- TRIGGER: THROW 51001 — UPDATE blocked
------------------------------------------------------------
SET @test = 'V14-12: TRIGGER blocks UPDATE (THROW 51001)';
BEGIN TRY
    UPDATE dbo.kpi_cache SET gpu_revenue = 999.99 WHERE session_id = @sid;
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — update should have been blocked';
END TRY
BEGIN CATCH
    IF ERROR_NUMBER() = 51001
    BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
    ELSE
    BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test + ' — wrong error: ' + CAST(ERROR_NUMBER() AS VARCHAR); END
END CATCH;

------------------------------------------------------------
-- TRIGGER: THROW 51001 — DELETE blocked
------------------------------------------------------------
SET @test = 'V14-13: TRIGGER blocks DELETE (THROW 51001)';
BEGIN TRY
    DELETE FROM dbo.kpi_cache WHERE session_id = @sid;
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — delete should have been blocked';
END TRY
BEGIN CATCH
    IF ERROR_NUMBER() = 51001
    BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
    ELSE
    BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test + ' — wrong error: ' + CAST(ERROR_NUMBER() AS VARCHAR); END
END CATCH;

------------------------------------------------------------
-- PK: duplicate session_id rejected
------------------------------------------------------------
SET @test = 'V14-14: REJECT duplicate session_id (PK)';
BEGIN TRY
    INSERT INTO dbo.kpi_cache
        (session_id, gpu_revenue, gpu_cogs, idle_gpu_cost, idle_gpu_cost_pct, cost_allocation_rate)
    VALUES
        (@sid, 5000.00, 3000.00, 900.00, 30.00, 70.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- FK: invalid session_id rejected
------------------------------------------------------------
SET @test = 'V14-15: REJECT invalid session_id (FK)';
BEGIN TRY
    INSERT INTO dbo.kpi_cache
        (session_id, gpu_revenue, gpu_cogs, idle_gpu_cost, idle_gpu_cost_pct, cost_allocation_rate)
    VALUES
        (NEWID(), 10000.00, 7000.00, 2100.00, 30.00, 70.00);
    SET @fail += 1; PRINT 'FAIL: ' + @test;
END TRY
BEGIN CATCH
    SET @pass += 1; PRINT 'PASS: ' + @test;
END CATCH;

------------------------------------------------------------
-- DEFAULT: computed_at populated
------------------------------------------------------------
SET @test = 'V14-16: DEFAULT computed_at is populated';
BEGIN TRY
    DECLARE @cat DATETIME2;
    SELECT @cat = computed_at FROM dbo.kpi_cache WHERE session_id = @sid;
    IF @cat IS NOT NULL
    BEGIN SET @pass += 1; PRINT 'PASS: ' + @test; END
    ELSE
    BEGIN SET @fail += 1; PRINT 'FAIL: ' + @test + ' — computed_at is NULL'; END
END TRY
BEGIN CATCH
    SET @fail += 1; PRINT 'FAIL: ' + @test + ' — ' + ERROR_MESSAGE();
END CATCH;

------------------------------------------------------------
-- CLEANUP — must disable trigger to delete test data
------------------------------------------------------------
DISABLE TRIGGER TR_kpi_cache_prevent_mutation ON dbo.kpi_cache;
DELETE FROM dbo.kpi_cache WHERE session_id IN (@sid, @sid2, @sid3, @sid10);
ENABLE TRIGGER TR_kpi_cache_prevent_mutation ON dbo.kpi_cache;
DELETE FROM raw.ingestion_log WHERE session_id IN (@sid, @sid2, @sid3, @sid10);

PRINT '';
PRINT '============================================================';
PRINT 'V14 dbo.kpi_cache: ' + CAST(@pass AS VARCHAR) + ' passed, ' + CAST(@fail AS VARCHAR) + ' failed';
PRINT '============================================================';
