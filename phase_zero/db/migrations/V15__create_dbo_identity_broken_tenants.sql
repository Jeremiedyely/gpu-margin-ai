-- V15__create_dbo_identity_broken_tenants.sql
CREATE TABLE dbo.identity_broken_tenants (
    session_id          UNIQUEIDENTIFIER    NOT NULL,
    failed_tenant_id    NVARCHAR(255)       NOT NULL,
    CONSTRAINT PK_identity_broken_tenants
        PRIMARY KEY (session_id, failed_tenant_id),
    CONSTRAINT FK_ibt_session
        FOREIGN KEY (session_id)
        REFERENCES raw.ingestion_log(session_id),
    ------------------------------------------------------------
    -- PREVENT EMPTY TENANT IDs (Hardening)
    ------------------------------------------------------------
    CONSTRAINT CHK_ibt_tenant_not_empty
        CHECK (LEN(LTRIM(RTRIM(failed_tenant_id))) > 0)
);
GO
------------------------------------------------------------
-- IMMUTABILITY TRIGGER
------------------------------------------------------------
CREATE TRIGGER TR_identity_broken_tenants_prevent_mutation
    ON dbo.identity_broken_tenants
    INSTEAD OF UPDATE, DELETE
AS
BEGIN
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW 51002,
    'dbo.identity_broken_tenants is immutable. UPDATE and DELETE are not permitted.',
    1;
END;
GO
------------------------------------------------------------
-- INDEX 1 — Zone 2R Risk flag lookup
------------------------------------------------------------
CREATE INDEX IX_ibt_session_lookup
    ON dbo.identity_broken_tenants (session_id);
