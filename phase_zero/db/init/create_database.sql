-- create_database.sql
-- Runs on SQL Server startup before Flyway connects.
-- Creates the gpu_margin database if it does not already exist.
-- This script runs against the 'master' database.

IF NOT EXISTS (SELECT 1 FROM sys.databases WHERE name = 'gpu_margin')
BEGIN
    CREATE DATABASE gpu_margin;
    PRINT 'Database gpu_margin created.';
END
ELSE
BEGIN
    PRINT 'Database gpu_margin already exists — skipping.';
END
GO
