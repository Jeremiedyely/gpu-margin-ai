-- V2__create_schema_namespaces.sql
-- Creates the three schema namespaces used by all 13 tables.
-- raw   — 5 source ingestion tables + ingestion_log (session anchor)
-- dbo   — grain, reconciliation, state, caches (default schema, already exists)
-- final — immutable approved result (write-once, export-only)

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'raw')
    EXEC('CREATE SCHEMA raw');
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'final')
    EXEC('CREATE SCHEMA final');
GO
