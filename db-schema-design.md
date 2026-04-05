---
role: schema-design
reads-from: database-architect.md · requirements.md · ingestion-module-design.md · allocation-engine-design.md
feeds-into: implementation · Flyway T-SQL migrations
confirmed: 2026-03-28
revised: 2026-03-28
grain: Region × GPU Pool × Day × Allocation Target
tables: 13
indexes: 28
check-constraints: 51
filtered-unique-indexes: 6
immutability-triggers: 4
physical-fk-chains: 1
coupling-contracts: 7
deployment-prerequisites: 10
---

# Database Schema Design — GPU Gross Margin Visibility Application

> See: business.md — WHY layer · CFO problem definition
> See: requirements.md — WHAT layer · grain · computation contract · Closure Rule
> See: database-architect.md — grain-first design sequence · row anatomy · mapping behaviors
> See: allocation-engine-design.md — record builder chain · field producers · Required Field Checklist

---

## Grain Declaration (Anchor)

**The grain is:** `Region × GPU Pool × Day × Allocation Target`

Every table in this schema is in exactly one of six relationships to the grain:

| Relationship | Tables | One Row = |
|---|---|---|
| IS the grain | `allocation_grain` · `final.allocation_result` | One grain cell |
| FEEDS the grain | `raw.telemetry` · `raw.cost_management` · `raw.iam` | One source record |
| CHECKS the grain | `raw.billing` · `raw.erp` · `reconciliation_results` | One boundary verdict |
| CONTROLS the grain | `state_store` · `state_history` | One lifecycle state |
| ANCHORS the grain | `raw.ingestion_log` | One session registration |
| CACHES the grain | `kpi_cache` · `identity_broken_tenants` | One pre-computed read artifact |

A column that cannot be placed in one of these relationships is an architectural anomaly.
Name it before writing it. (database-architect.md — Behavioral Law 1)

---

## Five Source Identities Confirmed

Grain-First Design Sequence (Steps 1–6 from database-architect.md) applied to each source.

---

### Source 1 — Telemetry & Metering → `raw.telemetry`

**Grain role:** FEEDS the grain — CONSUMPTION dimension.
Answers: WHO consumed HOW MANY gpu_hours at WHICH pool on WHICH day.

**Structural identity — what makes this source unique:**
- `tenant_id` is UNVALIDATED at ingestion. It is a physical measurement, not a confirmed customer.
  It becomes `allocation_target = tenant_id` (Type A) if IAM resolves it, or
  `allocation_target = 'unallocated'` / `unallocated_type = 'identity_broken'` / `failed_tenant_id = tenant_id`
  if IAM resolution fails. This table does not know which outcome applies.
- `billing_period` is NOT present. It is derived downstream by `LEFT(date, 7)`.
  The Billing Period Deriver (AE Component 2) owns this derivation.
  All downstream joins on billing_period use this exact derivation — cross-module coupling contract.
- No cost fields. No rate fields. This source exclusively owns consumption volume.

**Natural key:** `(session_id, tenant_id, region, gpu_pool_id, date)`
Not enforced as UNIQUE at DB level — multiple metering intervals within one grain cell are valid and
are aggregated by the AE Telemetry Aggregator (GROUP BY) before any grain row is written.

**Grain-to-source mapping:**
```
raw.telemetry
  → AE Telemetry Aggregator: GROUP BY (tenant_id, region, gpu_pool_id, date)
  → AE Billing Period Deriver: billing_period = LEFT(date, 7)
  → AE IAM Resolver: LEFT JOIN raw.iam ON (tenant_id, billing_period)
      Match found    → Type A Record Builder  → allocation_grain (Type A row)
      No match found → IB Record Builder      → allocation_grain (identity_broken row)
```

**Cross-module exposure:**
- AE Telemetry Aggregator (reads)
- RE Check 1 (reads — concurrent with AE → snapshot isolation required, P1 #17)
- RE Check 2 (reads tenant_id + billing_period for mapping check — concurrent, P1 #17)

---

### Source 2 — Cost Management / FinOps → `raw.cost_management`

**Grain role:** FEEDS the grain — CAPACITY and COST dimension.
Answers: How many gpu_hours were RESERVED at this pool on this day, and what did each hour cost?

**Structural identity — what makes this source unique:**
- NO `tenant_id`. This is the only source with no tenant dimension.
  Cost is assigned to a pool, not to a customer. The Closure Rule makes this precise:
  every reserved gpu_hour becomes either a customer row (Type A) or an unallocated row (Type B).
  The pool bears the cost regardless of who (or whether anyone) consumed it.
- `reserved_gpu_hours` is the Closure Rule DENOMINATOR:
  `SUM(grain.gpu_hours per pool per day) = reserved_gpu_hours`. Violation → AE FAIL.
- `cost_per_gpu_hour` is copied into EVERY grain row for that pool-day — both Type A and Type B.
  This is the cost formula input shared across all three record types.
- Natural key `(region, gpu_pool_id, date)` is UNIQUE per session — enforced at ingestion and DB level.

**Natural key:** `(session_id, region, gpu_pool_id, date)` — UNIQUE constraint at DB level.

**Grain-to-source mapping:**
```
raw.cost_management
  → AE Cost Rate Reader: indexed lookup by (region, gpu_pool_id, date)
      → cost_per_gpu_hour → copied to ALL grain rows for that pool-day
      → reserved_gpu_hours → Closure Rule denominator
  → AE Closure Rule Enforcer: idle = reserved_gpu_hours − SUM(consumed)
      idle > 0 → capacity_idle row forced
      idle < 0 → AE FAIL
```

**Cross-module exposure:**
- AE Cost Rate Reader (reads)
- RE Check 1 (reads `reserved_gpu_hours` for capacity vs usage comparison)

---

### Source 3 — IAM / Tenant Management → `raw.iam`

**Grain role:** FEEDS the grain — IDENTITY and RATE dimension.
Answers: Is this tenant_id a confirmed customer in this billing period, and at what contracted rate?

**Structural identity — what makes this source unique:**
- This is the identity resolution authority. A tenant_id from Telemetry is unconfirmed
  until it resolves here. No match → identity_broken.
- `billing_period` YYYY-MM is the JOIN KEY for IAM resolution. The Billing Period Deriver
  derives the same format from Telemetry's `date` via LEFT(date, 7).
  Format mismatch → silent JOIN failure → every tenant becomes identity_broken
  with no structural error raised. YYYY-MM enforced at ingestion validator and DB CHECK.
- `contracted_rate` is the REVENUE formula input for Type A rows ONLY:
  `revenue = gpu_hours × contracted_rate`. Type B rows carry `contracted_rate = NULL`.
- Natural key `(tenant_id, billing_period)` is UNIQUE per session.

**Natural key:** `(session_id, tenant_id, billing_period)` — UNIQUE constraint at DB level.

**CRITICAL deployment prerequisite (P1 #8):**
Composite index on `(tenant_id, billing_period)` MUST exist before first analysis run.
Without index: full table scan per row in IAM Resolver → O(n) → AE_TIMEOUT breach at 100K+ rows.
Validate: SSMS Execution Plan must show INDEX SEEK — not TABLE SCAN.

**Grain-to-source mapping:**
```
raw.iam
  → AE IAM Resolver: LEFT JOIN ON (tenant_id, billing_period) [composite index required]
      Match found    → contracted_rate copied to Type A grain row
      No match found → failed_tenant_id = tenant_id → identity_broken grain row
```

**Cross-module exposure:**
- AE IAM Resolver (reads — composite index required, P1 #8)
- RE Check 2 (reads for tenant mapping validation)
- billing_period format is a cross-module coupling contract shared with:
  AE Billing Period Deriver · AE IAM Resolver · RE Check 2 · RE Check 3

---

### Source 4 — Billing System → `raw.billing`

**Grain role:** CHECKS the grain — INVOICED dimension.
Answers: What amount was invoiced to this tenant in this billing period?

**Structural identity — what makes this source unique:**
- Used EXCLUSIVELY by RE Check 3 FAIL-1 (computed ≠ billed). Never read by AE.
- `billable_amount` is compared to `SUM(allocation_grain.revenue)` per tenant per billing_period
  (WHERE allocation_target ≠ 'unallocated' — contract boundary, P1 #18).
- Natural key `(tenant_id, billing_period)` is UNIQUE per session.
- `billing_period` YYYY-MM enforced at ingestion and DB CHECK.

**Natural key:** `(session_id, tenant_id, billing_period)` — UNIQUE constraint at DB level.

**Grain-to-source mapping:**
```
raw.billing
  → RE Check 3 Executor: JOIN allocation_grain ON (allocation_target, billing_period)
      WHERE allocation_target ≠ 'unallocated'
      FAIL-1: SUM(grain.revenue) ≠ billable_amount → FAIL-1 verdict
```

---

### Source 5 — ERP / General Ledger → `raw.erp`

**Grain role:** CHECKS the grain — POSTED dimension.
Answers: What amount was posted to the general ledger for this tenant in this billing period?

**Structural identity — what makes this source unique:**
- Used EXCLUSIVELY by RE Check 3 FAIL-2 (billed ≠ posted). Never read by AE.
- `amount_posted` is compared to `raw.billing.billable_amount` per tenant per billing_period.
- Natural key `(tenant_id, billing_period)` is UNIQUE per session.
- `billing_period` YYYY-MM enforced at ingestion and DB CHECK.

**Natural key:** `(session_id, tenant_id, billing_period)` — UNIQUE constraint at DB level.

**Grain-to-source mapping:**
```
raw.erp
  → RE Check 3 Executor: JOIN raw.billing ON (tenant_id, billing_period)
      FAIL-2: billable_amount ≠ amount_posted → FAIL-2 verdict
      (FAIL-1 takes precedence if both FAIL-1 and FAIL-2 fire for same tenant+period)
```

---

## Recommended Relationship Architecture

### Physical FK: One Chain, All Tables

All tables carry `session_id` as a FK to `raw.ingestion_log(session_id)`.
This is the ONLY physical FK in the schema.

```
raw.ingestion_log (session_id PK)
  ← raw.telemetry.session_id
  ← raw.cost_management.session_id
  ← raw.iam.session_id
  ← raw.billing.session_id
  ← raw.erp.session_id
  ← dbo.allocation_grain.session_id
  ← dbo.reconciliation_results.session_id
  ← dbo.state_store.session_id
  ← dbo.state_history.session_id
  ← final.allocation_result.session_id
  ← dbo.kpi_cache.session_id
  ← dbo.identity_broken_tenants.session_id
```

**Why physical FKs between raw tables and `allocation_grain` are architecturally impossible:**

1. `capacity_idle` rows in `allocation_grain` have NO corresponding `raw.telemetry` rows.
   A FK from grain to telemetry would structurally prevent capacity_idle records from being written.

2. Many `raw.telemetry` rows aggregate into one Type A grain row via GROUP BY.
   A FK requires 1:1 row mapping — which does not exist after Telemetry Aggregator runs.

3. The Allocation Engine is a computational intermediary, not a copy mechanism.
   It reads, transforms, classifies, and writes. It does not store row-level FK references.

**The session_id FK is the correct and sufficient physical relationship** because:
- It anchors every row to a confirmed, log-registered ingestion session.
- It scopes all engine reads to the active session (defense in depth).
- It is the K1 cross-module coupling contract carried through all 6 modules.

### Logical Relationships (Coupling Contracts — Not Physical FKs)

| Source | Grain Connection | Join Key | Consumer |
|---|---|---|---|
| raw.telemetry | → allocation_grain (Type A + identity_broken) | (session_id, region, gpu_pool_id, date) via GROUP BY | AE Telemetry Aggregator |
| raw.cost_management | → allocation_grain (all types — cost_per_gpu_hour) | (session_id, region, gpu_pool_id, date) lookup | AE Cost Rate Reader |
| raw.iam | → allocation_grain (Type A — contracted_rate) | (session_id, tenant_id, billing_period) LEFT JOIN | AE IAM Resolver |
| raw.billing | → reconciliation_results (Check 3 FAIL-1) | (session_id, tenant_id, billing_period) JOIN | RE Check 3 |
| raw.erp | → reconciliation_results (Check 3 FAIL-2) | (session_id, tenant_id, billing_period) JOIN | RE Check 3 |
| allocation_grain | → reconciliation_results (Check 3 computed) | (session_id, allocation_target, billing_period) JOIN | RE Check 3 |
| allocation_grain | → final.allocation_result | Copied at APPROVED by SM Approved Result Writer (C9) | Export |
| allocation_grain | → kpi_cache | Pre-computed at ANALYZED by KPI Data Aggregator | UI Zone 1 |
| allocation_grain | → identity_broken_tenants | Pre-computed at ANALYZED from failed_tenant_id | UI Zone 2R |

### Natural Key UNIQUE Constraints (Ingestion Integrity at DB Level)

| Table | UNIQUE Constraint | Rationale |
|---|---|---|
| raw.cost_management | (session_id, region, gpu_pool_id, date) | One capacity record per pool-day — Closure Rule requires exactly one denominator |
| raw.iam | (session_id, tenant_id, billing_period) | One rate per tenant per period — duplicate rates corrupt revenue formula |
| raw.billing | (session_id, tenant_id, billing_period) | One invoice per tenant per period — duplicate invoices corrupt Check 3 FAIL-1 |
| raw.erp | (session_id, tenant_id, billing_period) | One GL posting per tenant per period — duplicate postings corrupt Check 3 FAIL-2 |
| reconciliation_results | (session_id, check_name) | Exactly three verdict rows per session — one per check |

---

## Full T-SQL Schema — 13 Tables

SQL Server dialect · SQLAlchemy + pyodbc (`mssql+pyodbc://`)
Managed via Flyway versioned T-SQL migration scripts (`flyway validate` required as CI gate)

---

### Schema Namespaces

```sql
CREATE SCHEMA raw;      -- Session anchor + 5 source tables
CREATE SCHEMA dbo;      -- Grain, state machine, cache artifacts
CREATE SCHEMA final;    -- Immutable approved result (write-once)
```

---

### INSTEAD OF Trigger Error Number Registry

All THROW error numbers claimed by INSTEAD OF triggers in this schema are declared here.
User-defined THROW numbers occupy the range 50001–2147483647.
Any new trigger added to this schema MUST claim its number in this registry before writing the DDL.
Assigning a number not listed here risks collision with an existing trigger.

| THROW # | Trigger | Table | Added |
|---|---|---|---|
| 51000 | `TR_final_allocation_result_prevent_mutation` | `final.allocation_result` | Round 2/3 |
| 51001 | `TR_kpi_cache_prevent_mutation` | `dbo.kpi_cache` | Round 11 (R11-W-1) |
| 51002 | `TR_identity_broken_tenants_prevent_mutation` | `dbo.identity_broken_tenants` | Round 11 (R11-W-2) |
| 51003 | `TR_allocation_grain_prevent_update` | `dbo.allocation_grain` | Round 14 (R14-W-1) |

Next available number: **51004** (R14-REC-1 fix)

---

### Table 0: `raw.ingestion_log` — Session Anchor

**One row = one ingestion session.**
**Grain relationship:** ANCHORS the grain. All 12 other tables FK to this table's session_id.
**Producer:** Ingestion Log Writer (Component 18) — fires only after Ingestion Commit = SUCCESS.

```sql
CREATE TABLE raw.ingestion_log (
    session_id      UNIQUEIDENTIFIER    NOT NULL,
    source_files    NVARCHAR(MAX)       NOT NULL,   -- JSON array: ["file1.csv",...,"file5.csv"]
                                                    -- queried by Export Session Metadata Appender
    ingested_at     DATETIME2           NOT NULL    DEFAULT SYSUTCDATETIME(),
    status          NVARCHAR(20)        NOT NULL,

    CONSTRAINT PK_ingestion_log
        PRIMARY KEY (session_id),

    -- Binary state: committed or failed — no ambiguous intermediate states
    CONSTRAINT CHK_ingestion_log_status
        CHECK (status IN ('COMMITTED', 'FAILED')),

    -- JSON array structure validation — Export Session Metadata Appender reads source_files as JSON
    -- ISJSON() rejects structurally malformed JSON at ingestion write time (Component 18)
    -- Closes the gap where a Component 18 bug stores malformed JSON that fails at export runtime
    -- Performance: ISJSON() on NVARCHAR(MAX) adds ~0.5ms per INSERT
    -- Acceptable: ingestion is batch-once per session, not a transactional write pattern
    --
    -- DESIGN DECISION (R6-REC-1): ISJSON() validates structural JSON only — NOT element type or content.
    -- The following values all pass ISJSON() = 1 and would be accepted by this constraint:
    --   [null, null, null, null, null]           — valid JSON, all null elements
    --   [1, 2, 3, 4, 5]                          — valid JSON, integers not filenames
    --   ["file1.csv", null, "file3.csv", ...]    — valid JSON, mixed null and string
    -- The Export Session Metadata Appender reads source_files expecting an array of non-null
    -- NVARCHAR filename strings. Null elements or non-string elements cause runtime failure
    -- in the Appender — at export time, not at ingestion time. Root cause diagnosis is harder
    -- because the bad data was written sessions earlier.
    --
    -- Why content-type enforcement is not added at DB level:
    -- SQL Server CHECK constraints cannot inspect JSON element types natively. Enforcing element
    -- content would require a scalar UDF (e.g., checking JSON_VALUE for each index) or computed
    -- columns — both adding maintenance overhead and constraint-function coupling. The correct
    -- guard is in the Ingestion Validator (Component 18) before the INSERT: validate that
    -- source_files is a JSON array, that it contains exactly 5 elements, and that every element
    -- is a non-null string. This is a content contract owned by the ingestion layer, not by the DB.
    -- The DB layer enforces structural JSON validity only. (R6-REC-1 fix)
    CONSTRAINT CHK_ingestion_source_files_json
        CHECK (ISJSON(source_files) = 1)
);

-- DESIGN DECISION (R5-W-2): FAILED session data isolation is NOT enforced at DB level.
-- raw.ingestion_log.status accepts 'COMMITTED' and 'FAILED'. The FK chain anchors all 12 downstream
-- tables to session_id but does not prevent raw rows (raw.telemetry, raw.iam, etc.) from existing
-- under a FAILED session_id.
--
-- How FAILED session data enters raw tables:
-- Component 11 (Telemetry Raw Table Writer) stages rows to raw.telemetry BEFORE the ingestion commit
-- decision is finalized. If the session ultimately FAILs (e.g., one of the 5 source files is rejected),
-- the previously staged rows persist in raw tables under the FAILED session_id.
-- The status = 'FAILED' flag is set in ingestion_log but no cascade cleanup fires automatically.
--
-- Risk: AE and RE engines scope all reads by session_id but do NOT filter on ingestion_log.status.
-- If a FAILED session's raw rows are never purged and a new session covers the same billing period,
-- both session_ids coexist in raw tables. A query not strictly scoped to the COMMITTED session_id
-- will aggregate FAILED session data alongside COMMITTED data — producing incorrect grain results
-- with no structural error raised.
--
-- Why DB-level isolation is not enforced here:
-- A CHECK constraint cannot reference other tables. A trigger that prevents staging writes when
-- status = 'FAILED' would require a trigger on every raw table (5 triggers) and a JOIN to
-- ingestion_log at staging time — adding latency to a write path that must be fast.
-- The FK ON DELETE behavior is NO ACTION (SQL Server default). Adding CASCADE DELETE would cause
-- a FAILED ingestion_log.session_id DELETE to cascade through all 12 downstream tables —
-- acceptable for cleanup but dangerous if triggered prematurely before failure is confirmed.
--
-- Correct isolation strategy (application layer):
-- (1) Ingestion Orchestrator must run a FAILED session cleanup job after status = 'FAILED' is set:
--     DELETE FROM raw.telemetry WHERE session_id = @failed_session_id (and all other raw tables).
-- (2) AE and RE engine queries MAY add a JOIN to ingestion_log filtering status = 'COMMITTED'
--     as defense-in-depth, even if session_id scoping already isolates the active session.
-- (3) If cascade cleanup is preferred: add ON DELETE CASCADE to all 12 FK constraints.
--     This requires Flyway migration and validation that no FAILED session_id is ever re-used.
-- Decision: application-layer cleanup is the correct owner. Schema accepts the risk. (R5-W-2 fix)
```

---

### Table 1: `raw.telemetry` — Consumption Source

**One row = one metering record for one tenant at one pool on one day.**
**Grain relationship:** FEEDS the grain — consumption dimension.
**Producer:** Telemetry Raw Table Writer (Component 11) — session-tagged, staged before Ingestion Commit.

```sql
CREATE TABLE raw.telemetry (
    id                  BIGINT              NOT NULL    IDENTITY(1,1),
    session_id          UNIQUEIDENTIFIER    NOT NULL,
    region              NVARCHAR(100)       NOT NULL,
    gpu_pool_id         NVARCHAR(100)       NOT NULL,
    date                DATE                NOT NULL,   -- ISO 8601 YYYY-MM-DD required
    tenant_id           NVARCHAR(255)       NOT NULL,   -- unvalidated at ingestion
                                                        -- resolved to Type A or identity_broken by AE
    gpu_hours_consumed  DECIMAL(18,6)       NOT NULL,

    CONSTRAINT PK_telemetry
        PRIMARY KEY (id),

    CONSTRAINT FK_telemetry_session
        FOREIGN KEY (session_id) REFERENCES raw.ingestion_log(session_id),

    -- Positive consumption only — zero-hour metering records are rejected at ingestion
    -- DESIGN DECISION (W-2): gpu_hours_consumed > 0 assumes all telemetry rows represent
    -- actual consumption. Some telemetry sources emit sub-interval heartbeat records
    -- with 0.0 consumed hours. These are structurally rejected here.
    -- If the source system emits legitimate zero-hour records, the ingestion validator
    -- (Component 11) must filter or aggregate them before write — not the DB.
    -- Changing this to >= 0 would require the AE Telemetry Aggregator to handle
    -- zero-sum grain cells (gpu_hours = 0) which violates the Closure Rule semantics.
    -- Decision: accepted trade-off. > 0 is structurally correct for this application.
    CONSTRAINT CHK_telemetry_gpu_hours
        CHECK (gpu_hours_consumed > 0)

    -- NOTE: Natural key (session_id, tenant_id, region, gpu_pool_id, date) is NOT UNIQUE
    -- at DB level. Multiple metering intervals per grain cell are valid and expected.
    -- AE Telemetry Aggregator performs GROUP BY before writing any grain row.
);

-- DEPLOYMENT PREREQUISITE (P1 #17):
-- Snapshot isolation MUST be enabled before production.
-- AE Telemetry Aggregator + RE Check 1 + RE Check 2 read this table concurrently.
-- Default READ COMMITTED → dirty reads between AE and RE → wrong grain aggregation.
-- Flyway migration:
--   ALTER DATABASE [gpu_margin_db] SET ALLOW_SNAPSHOT_ISOLATION ON;
-- Connection-level (applied by SQLAlchemy session config):
--   SET TRANSACTION ISOLATION LEVEL SNAPSHOT;
-- Validation: run concurrent AE + RE load test in staging. Verify no dirty aggregation.

-- Session scoping — all three engine reads filter by session_id first
CREATE INDEX IX_telemetry_session
    ON raw.telemetry (session_id);

-- AE Telemetry Aggregator: GROUP BY (tenant_id, region, gpu_pool_id, date)
CREATE INDEX IX_telemetry_grain
    ON raw.telemetry (session_id, tenant_id, region, gpu_pool_id, date)
    INCLUDE (gpu_hours_consumed);

-- RE Check 1: SUM(consumed) vs reserved per pool-day
-- RE Check 2: tenant_id resolution per session
CREATE INDEX IX_telemetry_pool_day
    ON raw.telemetry (session_id, region, gpu_pool_id, date)
    INCLUDE (gpu_hours_consumed, tenant_id);
```

---

### Table 2: `raw.cost_management` — Capacity & Cost Source

**One row = one capacity reservation record for one pool on one day.**
**Grain relationship:** FEEDS the grain — capacity and cost dimension.
**Producer:** Cost Management Raw Table Writer (Component 12).

```sql
CREATE TABLE raw.cost_management (
    id                  BIGINT              NOT NULL    IDENTITY(1,1),
    session_id          UNIQUEIDENTIFIER    NOT NULL,
    region              NVARCHAR(100)       NOT NULL,
    gpu_pool_id         NVARCHAR(100)       NOT NULL,
    date                DATE                NOT NULL,   -- ISO 8601 YYYY-MM-DD
    reserved_gpu_hours  DECIMAL(18,6)       NOT NULL,   -- Closure Rule denominator
    cost_per_gpu_hour   DECIMAL(18,6)       NOT NULL,   -- copied into ALL grain rows for this pool-day

    CONSTRAINT PK_cost_management
        PRIMARY KEY (id),

    CONSTRAINT FK_cost_management_session
        FOREIGN KEY (session_id) REFERENCES raw.ingestion_log(session_id),

    -- One capacity record per pool per day per session — Closure Rule requires unique denominator
    CONSTRAINT UQ_cost_management_natural_key
        UNIQUE (session_id, region, gpu_pool_id, date),

    -- Both cost fields must be positive — zero or negative values violate cost semantics
    CONSTRAINT CHK_cost_management_reserved
        CHECK (reserved_gpu_hours > 0),

    CONSTRAINT CHK_cost_management_cost
        CHECK (cost_per_gpu_hour > 0)
    -- DESIGN DECISION (W-3): cost_per_gpu_hour is a single flat rate per pool per day.
    -- Real GPU infrastructure may use tiered pricing (spot vs reserved), burst pricing,
    -- or intra-day rate changes. This schema does not support multi-tier pricing:
    -- the UNIQUE constraint on (session_id, region, gpu_pool_id, date) rejects multiple
    -- rate records for the same pool-day.
    -- If the source cost management system provides multiple rates per pool-day,
    -- they must be pre-aggregated (weighted average or latest rate) before ingestion.
    -- This aggregation is a source-system ETL concern, not a schema concern.
    -- Changing this to support multi-rate would require: removing the UNIQUE constraint,
    -- adding a time_range or rate_tier column, and rewriting the AE Cost Rate Reader.
    -- Decision: accepted trade-off. Flat rate per pool-day is correct for current scope.
);

-- Session scoping
CREATE INDEX IX_cost_mgmt_session
    ON raw.cost_management (session_id);

-- AE Cost Rate Reader lookup (O(1) per pool-day)
-- RE Check 1: reserved_gpu_hours per pool-day
CREATE INDEX IX_cost_mgmt_grain_lookup
    ON raw.cost_management (session_id, region, gpu_pool_id, date)
    INCLUDE (reserved_gpu_hours, cost_per_gpu_hour);
```

---

### Table 3: `raw.iam` — Identity & Rate Source

**One row = one contracted rate for one tenant in one billing period.**
**Grain relationship:** FEEDS the grain — identity and rate dimension.
**Producer:** IAM Raw Table Writer (Component 13).

```sql
CREATE TABLE raw.iam (
    id              BIGINT              NOT NULL    IDENTITY(1,1),
    session_id      UNIQUEIDENTIFIER    NOT NULL,
    tenant_id       NVARCHAR(255)       NOT NULL,
    billing_period  NVARCHAR(7)         NOT NULL,   -- YYYY-MM format required
    contracted_rate DECIMAL(18,6)       NOT NULL,   -- revenue formula input for Type A only

    CONSTRAINT PK_iam
        PRIMARY KEY (id),

    CONSTRAINT FK_iam_session
        FOREIGN KEY (session_id) REFERENCES raw.ingestion_log(session_id),

    -- One rate per tenant per billing period per session
    CONSTRAINT UQ_iam_natural_key
        UNIQUE (session_id, tenant_id, billing_period),

    -- YYYY-MM format — cross-module coupling contract (K2)
    -- AE Billing Period Deriver derives the same format via LEFT(date, 7)
    -- IAM Resolver joins on this exact format
    -- Format mismatch → silent LEFT JOIN failure → every tenant becomes identity_broken
    -- LIKE handles structure; SUBSTRING enforces month range 01–12
    -- (LIKE alone permits 2026-00 and 2026-13 through 2026-19)
    CONSTRAINT CHK_iam_billing_period
        CHECK (
            billing_period LIKE '[0-9][0-9][0-9][0-9]-[0-1][0-9]'
            AND SUBSTRING(billing_period, 6, 2) BETWEEN '01' AND '12'
        ),

    -- contracted_rate must be non-negative
    -- >= 0 permits zero-rate tenants (promotional / free-trial periods)
    -- contracted_rate = 0 → revenue = 0 for that Type A row (allocated, zero billable)
    -- contracted_rate > 0 (previous constraint) caused zero-rate tenants to produce
    -- no IAM match → identity_broken classification → false Risk flag for valid customers
    --
    -- ZERO-RATE UI CONTRACT (C-NEW-3):
    -- contracted_rate = 0 produces revenue = 0 at the grain level.
    -- GM% formula at UI: (revenue − cogs) / revenue × 100 — undefined when revenue = 0.
    -- UI must handle revenue = 0 explicitly before computing GM%:
    --   IF revenue = 0 THEN display GM% = −100% (all cost, no revenue) or 'N/A'
    -- Applies to: Zone 1 KPI GM% · Zone 2L Region GM% · Zone 2R Customer GM% bar
    -- This is a UI computation contract, not a schema constraint.
    -- The schema is structurally correct — the UI formula must guard the zero-denominator case.
    CONSTRAINT CHK_iam_rate
        CHECK (contracted_rate >= 0)
);

-- DEPLOYMENT PREREQUISITE (P1 #8):
-- This index MUST exist before the first analysis run in production.
-- AE IAM Resolver: LEFT JOIN ON (tenant_id, billing_period) for every telemetry record.
-- Without index: full table scan per record → O(n) per row → AE_TIMEOUT breach at 100K+ rows.
-- Validation: SSMS Execution Plan must show INDEX SEEK (not TABLE SCAN) on this query.
CREATE INDEX IX_iam_resolver
    ON raw.iam (tenant_id, billing_period)
    INCLUDE (contracted_rate);

-- Session scoping
CREATE INDEX IX_iam_session
    ON raw.iam (session_id);
```

---

### Table 4: `raw.billing` — Invoice Source

**One row = one invoice record for one tenant in one billing period.**
**Grain relationship:** CHECKS the grain — invoiced dimension (RE Check 3 FAIL-1 only).
**Producer:** Billing Raw Table Writer (Component 14).

```sql
CREATE TABLE raw.billing (
    id              BIGINT              NOT NULL    IDENTITY(1,1),
    session_id      UNIQUEIDENTIFIER    NOT NULL,
    tenant_id       NVARCHAR(255)       NOT NULL,
    billing_period  NVARCHAR(7)         NOT NULL,   -- YYYY-MM format required
    billable_amount DECIMAL(18,2)       NOT NULL,   -- compared to SUM(grain.revenue) in Check 3

    CONSTRAINT PK_billing
        PRIMARY KEY (id),

    CONSTRAINT FK_billing_session
        FOREIGN KEY (session_id) REFERENCES raw.ingestion_log(session_id),

    -- One invoice per tenant per billing period per session
    CONSTRAINT UQ_billing_natural_key
        UNIQUE (session_id, tenant_id, billing_period),

    -- YYYY-MM — same format contract as raw.iam
    -- Check 3 joins raw.billing + allocation_grain on (tenant_id + billing_period)
    -- Format mismatch → missed joins → false FAIL-1 verdicts with no structural error
    -- LIKE handles structure; SUBSTRING enforces month range 01–12
    CONSTRAINT CHK_billing_billing_period
        CHECK (
            billing_period LIKE '[0-9][0-9][0-9][0-9]-[0-1][0-9]'
            AND SUBSTRING(billing_period, 6, 2) BETWEEN '01' AND '12'
        )

    -- DESIGN DECISION (R4-W-3 · ESCALATED R11 · FORMALLY ACCEPTED R12): billable_amount sign
    -- is not constrained at DB level. This decision was open through 8 diagnostic rounds
    -- without requirements confirmation. The Round 12 deadline (declared R11) has passed.
    -- The risk is now formally accepted as a permanent production risk.
    --
    -- Risk as accepted: a negative billable_amount (credit memo) is technically valid in billing
    -- systems and is accepted by this schema without rejection or operator signal. If ingested,
    -- it produces a false Check 3 FAIL-1 verdict (SUM(grain.revenue) ≠ negative billable_amount)
    -- that is structurally indistinguishable from a genuine reconciliation failure. RE Check 3
    -- Executor receives no DB-layer signal that the FAIL-1 was caused by a credit memo vs a real
    -- revenue discrepancy. The operator cannot distinguish the two cases from the verdict row alone.
    --
    -- Resolution paths (available when requirements confirmation is obtained — no deadline):
    --   If OUT of scope (credit memos are not valid input):
    --     ADD CONSTRAINT CHK_billing_billable_nonneg CHECK (billable_amount >= 0)
    --     Flyway: V[n]__add_billing_billable_nonneg_constraint.sql
    --     Deployment Prerequisite: SELECT COUNT(*) FROM raw.billing WHERE billable_amount < 0
    --       MUST return 0 before constraint is applied.
    --   If IN scope (credit memos are valid input):
    --     RE Check 3 Executor FAIL-1 logic must handle signed amounts explicitly.
    --     Update this comment to declare credit memo handling as an explicit design contract.
    --   Joint scope decision: must be confirmed simultaneously with raw.erp.amount_posted.
);

-- Session scoping
CREATE INDEX IX_billing_session
    ON raw.billing (session_id);

-- RE Check 3 FAIL-1: JOIN on (tenant_id, billing_period), read billable_amount
CREATE INDEX IX_billing_check3
    ON raw.billing (session_id, tenant_id, billing_period)
    INCLUDE (billable_amount);
```

---

### Table 5: `raw.erp` — GL Posting Source

**One row = one GL posting for one tenant in one billing period.**
**Grain relationship:** CHECKS the grain — posted dimension (RE Check 3 FAIL-2 only).
**Producer:** ERP Raw Table Writer (Component 15).

```sql
CREATE TABLE raw.erp (
    id              BIGINT              NOT NULL    IDENTITY(1,1),
    session_id      UNIQUEIDENTIFIER    NOT NULL,
    tenant_id       NVARCHAR(255)       NOT NULL,
    billing_period  NVARCHAR(7)         NOT NULL,   -- YYYY-MM format required
    amount_posted   DECIMAL(18,2)       NOT NULL,   -- compared to raw.billing.billable_amount

    CONSTRAINT PK_erp
        PRIMARY KEY (id),

    CONSTRAINT FK_erp_session
        FOREIGN KEY (session_id) REFERENCES raw.ingestion_log(session_id),

    -- One GL posting per tenant per billing period per session
    CONSTRAINT UQ_erp_natural_key
        UNIQUE (session_id, tenant_id, billing_period),

    -- YYYY-MM — same format contract as raw.iam and raw.billing
    -- LIKE handles structure; SUBSTRING enforces month range 01–12
    CONSTRAINT CHK_erp_billing_period
        CHECK (
            billing_period LIKE '[0-9][0-9][0-9][0-9]-[0-1][0-9]'
            AND SUBSTRING(billing_period, 6, 2) BETWEEN '01' AND '12'
        )

    -- DESIGN DECISION (R4-W-3 · ESCALATED R11 · FORMALLY ACCEPTED R12): amount_posted sign
    -- is not constrained at DB level. Same escalation and acceptance status as
    -- raw.billing.billable_amount — both decisions were open 8 diagnostic rounds without
    -- requirements confirmation. The Round 12 deadline (declared R11) has passed.
    -- The risk is now formally accepted as a permanent production risk.
    --
    -- Risk as accepted: a negative amount_posted (GL credit entry / reversal) is technically
    -- valid in general ledger systems and is accepted by this schema without rejection or operator
    -- signal. If ingested, it produces a false Check 3 FAIL-2 verdict (billable_amount ≠ negative
    -- amount_posted) that is structurally indistinguishable from a genuine GL posting discrepancy.
    -- RE Check 3 Executor receives no DB-layer signal that the FAIL-2 was caused by a GL credit
    -- vs a real posting mismatch. The operator cannot distinguish the two cases from the verdict
    -- row alone.
    --
    -- Resolution paths (available when requirements confirmation is obtained — no deadline):
    --   If OUT of scope (GL credits are not valid input):
    --     ADD CONSTRAINT CHK_erp_amount_posted_nonneg CHECK (amount_posted >= 0)
    --     Flyway: V[n]__add_erp_amount_posted_nonneg_constraint.sql
    --     Deployment Prerequisite: SELECT COUNT(*) FROM raw.erp WHERE amount_posted < 0
    --       MUST return 0 before constraint is applied.
    --   If IN scope (GL credits are valid input):
    --     RE Check 3 Executor FAIL-2 logic must handle signed comparison explicitly.
    --     Update this comment to declare GL credit handling as an explicit design contract.
    --   Joint scope decision: MUST be confirmed and resolved simultaneously with
    --   raw.billing.billable_amount — the two sign decisions are inseparable at Check 3.
);

-- Session scoping
CREATE INDEX IX_erp_session
    ON raw.erp (session_id);

-- RE Check 3 FAIL-2: JOIN on (tenant_id, billing_period), read amount_posted
CREATE INDEX IX_erp_check3
    ON raw.erp (session_id, tenant_id, billing_period)
    INCLUDE (amount_posted);
```

---

### Table 6: `dbo.allocation_grain` — The Grain Table

**One row = one grain cell = (region, gpu_pool_id, date, allocation_target).**
**Grain relationship:** IS the grain. Central source of truth for all UI, RE Check 3, and Export.
**Producer:** AE Allocation Grain Writer (Component 9) — atomic DB transaction, ROLLBACK on failure.
**Consumers:** UI KPI/Region/Customer Aggregators · RE Check 3 · Export Source Reader · SM Approved Result Writer

```sql
CREATE TABLE dbo.allocation_grain (
    id                  BIGINT              NOT NULL    IDENTITY(1,1),
    session_id          UNIQUEIDENTIFIER    NOT NULL,

    -- ── GRAIN DIMENSIONS (all four required) ────────────────────────────────────

    region              NVARCHAR(100)       NOT NULL,
    gpu_pool_id         NVARCHAR(100)       NOT NULL,
    date                DATE                NOT NULL,   -- ISO 8601 YYYY-MM-DD

    -- Derived from date by AE Billing Period Deriver: LEFT(date, 7) → YYYY-MM
    -- Cross-module coupling contract: IAM Resolver · RE Check 2 · RE Check 3 join on this
    -- Any change to this derivation requires simultaneous update of all three consumers
    billing_period      NVARCHAR(7)         NOT NULL,

    -- Fourth grain dimension
    -- Type A: tenant_id (resolved customer)
    -- Type B: 'unallocated' (idle capacity or identity failure)
    allocation_target   NVARCHAR(255)       NOT NULL,

    -- ── RECORD TYPE CLASSIFICATION ───────────────────────────────────────────────

    -- NULL for Type A rows
    -- 'capacity_idle'    for Type B reserved-but-unused rows
    -- 'identity_broken'  for Type B consumed-but-unresolved rows
    -- Case-sensitive — Output Verifier Check 4 rejects uppercase (P1 #43)
    unallocated_type    NVARCHAR(20)        NULL,

    -- The original tenant_id that failed IAM resolution
    -- NULL for Type A and capacity_idle rows (explicit NULL — not absent)
    -- Non-NULL for identity_broken rows ONLY
    -- Pass-through invariant: must survive full 7-component chain (P1 #10)
    -- IB Builder → Calculator → Grain Writer → identity_broken_tenants SET → Zone 2R Risk flag
    failed_tenant_id    NVARCHAR(255)       NULL,

    -- ── COMPUTED VALUES ──────────────────────────────────────────────────────────

    -- SUM(gpu_hours_consumed) from Telemetry Aggregator (Type A, identity_broken)
    -- OR idle = reserved − consumed from Closure Rule Enforcer (capacity_idle)
    gpu_hours           DECIMAL(18,6)       NOT NULL,

    -- From raw.cost_management — same value for all rows in same pool-day
    cost_per_gpu_hour   DECIMAL(18,6)       NOT NULL,

    -- From raw.iam — Type A only; NULL for all Type B rows
    contracted_rate     DECIMAL(18,6)       NULL,

    -- Type A: gpu_hours × contracted_rate
    -- Type B: 0 (always — no revenue offset on unallocated records)
    revenue             DECIMAL(18,2)       NOT NULL,

    -- All types: gpu_hours × cost_per_gpu_hour
    cogs                DECIMAL(18,2)       NOT NULL,

    -- Type A: revenue − cogs (may be positive or negative)
    -- Type B: −cogs (always negative — always a cost, never 0)
    gross_margin        DECIMAL(18,2)       NOT NULL,

    CONSTRAINT PK_allocation_grain
        PRIMARY KEY (id),

    CONSTRAINT FK_grain_session
        FOREIGN KEY (session_id) REFERENCES raw.ingestion_log(session_id),

    -- ── RECORD TYPE INTEGRITY CONSTRAINTS ────────────────────────────────────────
    -- These constraints replicate the Required Field Checklist (P1 #10) at DB level.
    -- They ensure no grain row can be written that violates the Type A / Type B contract
    -- even if application code has a bug in a record builder.

    -- unallocated_type: exact enum (case-sensitive) or NULL
    -- 'CAPACITY_IDLE' uppercase passes application check but fails BI tools (P1 #43)
    CONSTRAINT CHK_grain_unallocated_type
        CHECK (
            unallocated_type IS NULL
            OR unallocated_type = 'capacity_idle'
            OR unallocated_type = 'identity_broken'
        ),

    -- Type A must have NULL unallocated_type
    CONSTRAINT CHK_grain_type_a_no_subtype
        CHECK (allocation_target = 'unallocated' OR unallocated_type IS NULL),

    -- Type B must have non-NULL unallocated_type — no ambiguous unallocated rows
    CONSTRAINT CHK_grain_type_b_must_classify
        CHECK (allocation_target <> 'unallocated' OR unallocated_type IS NOT NULL),

    -- Type A must have non-NULL contracted_rate (revenue formula input)
    CONSTRAINT CHK_grain_type_a_rate_required
        CHECK (allocation_target = 'unallocated' OR contracted_rate IS NOT NULL),

    -- Type B: revenue = 0 AND contracted_rate = NULL (no billing on unallocated records)
    CONSTRAINT CHK_grain_type_b_zero_revenue
        CHECK (
            allocation_target <> 'unallocated'
            OR (revenue = 0 AND contracted_rate IS NULL)
        ),

    -- Type B: gross_margin must be strictly negative (= −cogs)
    -- CHK_grain_cogs_positive enforces cogs > 0 after DECIMAL(18,2) rounding.
    -- With cogs > 0, Type B gross_margin = revenue − cogs = 0 − cogs = −cogs < 0 always.
    -- (See R4-W-1 fix — cogs > 0 closes the DECIMAL rounding-to-zero gap in this chain.)
    CONSTRAINT CHK_grain_type_b_negative_margin
        CHECK (allocation_target <> 'unallocated' OR gross_margin < 0),

    -- identity_broken: failed_tenant_id MUST be non-NULL (pass-through invariant, P1 #10)
    -- If NULL here, the Risk flag silences for this tenant with no error raised
    CONSTRAINT CHK_grain_identity_broken_requires_ftid
        CHECK (
            unallocated_type <> 'identity_broken'
            OR failed_tenant_id IS NOT NULL
        ),

    -- capacity_idle: failed_tenant_id MUST be NULL (no failed tenant — unutilized capacity)
    CONSTRAINT CHK_grain_capacity_idle_null_ftid
        CHECK (unallocated_type <> 'capacity_idle' OR failed_tenant_id IS NULL),

    -- Type A: failed_tenant_id MUST be NULL (allocation succeeded — no identity failure)
    CONSTRAINT CHK_grain_type_a_null_ftid
        CHECK (allocation_target = 'unallocated' OR failed_tenant_id IS NULL),

    -- billing_period format — same contract as all source tables
    -- LIKE handles structure; SUBSTRING enforces month range 01–12
    CONSTRAINT CHK_grain_billing_period
        CHECK (
            billing_period LIKE '[0-9][0-9][0-9][0-9]-[0-1][0-9]'
            AND SUBSTRING(billing_period, 6, 2) BETWEEN '01' AND '12'
        ),

    -- Positive consumption / idle hours
    CONSTRAINT CHK_grain_gpu_hours_positive
        CHECK (gpu_hours > 0),

    -- Positive cost rate — 0 cost would produce gross_margin = revenue (misleading)
    CONSTRAINT CHK_grain_cost_per_hour_positive
        CHECK (cost_per_gpu_hour > 0),

    -- cogs must be strictly positive (R4-W-1 fix):
    -- cogs = gpu_hours × cost_per_gpu_hour. Both inputs are constrained > 0 above,
    -- but the product is stored as DECIMAL(18,2). In micro-precision scenarios
    -- (e.g., 0.000001 hours × 0.000001 per hour = 0.000000000001), the product
    -- rounds to 0.00 after DECIMAL(18,2) storage. If cogs = 0.00, then:
    --   Type B gross_margin = revenue − cogs = 0 − 0.00 = 0.00
    --   CHK_grain_type_b_negative_margin (gross_margin < 0) fires — misleading error.
    -- This constraint catches the rounding-to-zero case at the correct layer (cogs)
    -- with a clear signal, and makes CHK_grain_type_b_negative_margin structurally sound.
    CONSTRAINT CHK_grain_cogs_positive
        CHECK (cogs > 0)
);

-- DESIGN DECISION (R13-W-1 · UPDATED R14-W-1): dbo.allocation_grain has an INSTEAD OF
-- UPDATE trigger (TR_allocation_grain_prevent_update — see below) but intentionally does
-- NOT have an INSTEAD OF DELETE trigger. This is a partial divergence from the three
-- write-once cache tables (final.allocation_result · dbo.kpi_cache ·
-- dbo.identity_broken_tenants), each of which has INSTEAD OF UPDATE, DELETE. The DELETE
-- asymmetry exists for a precise architectural reason declared below.
--
-- WHY INSTEAD OF DELETE IS NOT APPLIED — Ingestion Commit structural constraint:
-- The Ingestion Commit (architecture-diagram.mermaid, ING subgraph) performs:
--   STEP 1 → DROP all prior active rows (session replacement)
--   STEP 2 → PROMOTE new session atomically
-- For dbo.allocation_grain, STEP 1 executes DELETE scoped to the prior committed
-- session_id. An INSTEAD OF DELETE trigger would intercept and block this step,
-- preventing session replacement. The Ingestion Commit would fail at STEP 1 — the prior
-- session's stale grain rows would coexist with the new session's grain rows. Reads
-- scoped by session_id would isolate them, but the schema's session replacement guarantee
-- would be silently violated. INSTEAD OF DELETE is architecturally incompatible with the
-- Ingestion Commit's replacement model.
--
-- WHY INSTEAD OF UPDATE IS NOW ENFORCED AT DB LEVEL (R14-W-1 fix):
-- No application component has a legitimate UPDATE path on grain rows. The AE Allocation
-- Grain Writer (C9) performs INSERT-only within an atomic transaction (ROLLBACK on failure).
-- No state machine path, no RE component, no UI aggregator, and no export reader issues
-- UPDATE statements on this table. The UPDATE-only trigger (not touching DELETE) is
-- architecturally valid and closes the four-consumer blast radius with no friction on
-- any correct application code path.
--
-- ACCEPTED RISK — individual row DELETE during ANALYZED state:
-- INSTEAD OF DELETE cannot be applied (see above). A targeted DELETE of an individual
-- grain row (not a session_id-scoped Ingestion Commit replacement) passes silently.
-- The mutation propagates through the same four consumers as an UPDATE would have:
--   (1) RE Check 3 FAIL-1 reads allocation_grain.revenue — missing row shifts Check 3 verdict
--   (2) Zone 1 KPI pre-compute reads allocation_grain.cogs — wrong kpi_cache values at ANALYZED
--   (3) Zone 2L/2R aggregators read allocation_grain — wrong UI display to CFO
--   (4) SM Approved Result Writer (C9) copies allocation_grain to final.allocation_result —
--       deleted rows are absent from the immutable approved copy permanently
-- Mitigation: application service account MUST NOT be granted DELETE on dbo.allocation_grain
-- except through the Ingestion Commit session_id-scoped replacement path.
-- Role-based access control is the primary protection boundary. SQL Server Audit trace
-- on DML against this table is the detection layer. This risk class is identical to the
-- TRUNCATE TABLE bypass on the three cache tables (R6-W-2 / R11-W-1 / R11-W-2):
-- a DBA-class operation that bypasses the trigger pattern. Same infrastructure controls
-- apply here. (R13-W-1 min fix → R14-W-1 UPDATE enforcement added)

-- UPDATE IMMUTABILITY DDL ENFORCEMENT (R14-W-1 fix)
-- Enforces write-once per grain row at the DB engine layer for UPDATE operations.
-- INSTEAD OF DELETE is intentionally excluded — Ingestion Commit STEP 1 requires DELETE
-- for session replacement (see DESIGN DECISION above). DELETE is NOT blocked here.
-- @@TRANCOUNT guard: prevents secondary error 3902 when trigger fires inside an outer
-- BEGIN TRAN block (same pattern as TR_final_allocation_result_prevent_mutation R3-W-3/R3-REC-1).
-- THROW 51003: claimed in INSTEAD OF Trigger Error Number Registry (R14-REC-1 fix).
-- No application component has a legitimate UPDATE path on grain rows — the trigger
-- adds zero friction to any correct code path and closes the full UPDATE blast radius.
CREATE TRIGGER TR_allocation_grain_prevent_update
    ON dbo.allocation_grain
    INSTEAD OF UPDATE
AS
BEGIN
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW 51003,
        'dbo.allocation_grain is write-once per grain row. UPDATE is not permitted. The AE Allocation Grain Writer (C9) is the sole producer and operates INSERT-only. No application component has a legitimate UPDATE path. Grain row mutation silently corrupts RE Check 3 verdict, Zone 1 KPI cache, Zone 2L/2R UI display, and the final.allocation_result immutable approved copy.',
        1;
END;

-- ── INDEXES ──────────────────────────────────────────────────────────────────────

-- Session scoping — first filter on all reads (defense in depth, K1 contract)
CREATE INDEX IX_grain_session
    ON dbo.allocation_grain (session_id);

-- Closure Rule verification: SUM(gpu_hours per region+pool+date) = reserved_gpu_hours
-- Used by AE Closure Rule Enforcer at write time and diagnostic validation queries
CREATE INDEX IX_grain_closure_rule
    ON dbo.allocation_grain (session_id, region, gpu_pool_id, date)
    INCLUDE (gpu_hours);

-- RE Check 3: JOIN on (allocation_target, billing_period) — Type A rows only
-- Filtered index excludes Type B rows (WHERE allocation_target <> 'unallocated')
-- This is the formal contract boundary (P1 #18) — Type B has no billing/ERP counterpart
CREATE INDEX IX_grain_check3
    ON dbo.allocation_grain (session_id, allocation_target, billing_period)
    INCLUDE (revenue)
    WHERE allocation_target <> 'unallocated';

-- Zone 2L — Region Data Aggregator: GROUP BY region, read revenue + cogs per allocation type
CREATE INDEX IX_grain_region_aggregator
    ON dbo.allocation_grain (session_id, region, allocation_target)
    INCLUDE (revenue, cogs, gpu_hours, unallocated_type);

-- Zone 2R — Customer Data Aggregator: GROUP BY allocation_target (tenant_id), read revenue + cogs
CREATE INDEX IX_grain_customer_aggregator
    ON dbo.allocation_grain (session_id, allocation_target)
    INCLUDE (revenue, cogs, failed_tenant_id);

-- identity_broken_tenants SET pre-computation at ANALYZED time (P2 #31)
-- Filtered — only reads identity_broken rows
CREATE INDEX IX_grain_identity_broken_set
    ON dbo.allocation_grain (session_id, unallocated_type)
    INCLUDE (failed_tenant_id)
    WHERE unallocated_type = 'identity_broken';

-- ── GRAIN NATURAL KEY UNIQUENESS (C-3 FIX) ───────────────────────────────────
-- Enforces one grain row per grain cell per record type.
-- Three filtered UNIQUE indexes required because:
--   (1) The grain has three structurally distinct record types with different key shapes
--   (2) T-SQL inline UNIQUE constraints cannot carry WHERE filters — CREATE INDEX required
--   (3) A single 5-column UNIQUE on (session_id, region, gpu_pool_id, date, allocation_target)
--       would block multiple identity_broken rows (same pool-day, different failed tenants
--       all share allocation_target = 'unallocated')
-- Together these three indexes give full duplicate protection with no false rejections.

-- Type A: one row per resolved tenant per pool-day
-- allocation_target = tenant_id (unique per customer per pool-day)
CREATE UNIQUE INDEX UQ_grain_type_a_natural_key
    ON dbo.allocation_grain (session_id, region, gpu_pool_id, date, allocation_target)
    WHERE allocation_target <> 'unallocated';

-- capacity_idle: one row per pool-day
-- failed_tenant_id is always NULL here — no tenant dimension on idle rows
CREATE UNIQUE INDEX UQ_grain_capacity_idle_natural_key
    ON dbo.allocation_grain (session_id, region, gpu_pool_id, date, unallocated_type)
    WHERE unallocated_type = 'capacity_idle';

-- identity_broken: one row per failed tenant per pool-day
-- failed_tenant_id guaranteed non-NULL by CHK_grain_identity_broken_requires_ftid
CREATE UNIQUE INDEX UQ_grain_identity_broken_natural_key
    ON dbo.allocation_grain (session_id, region, gpu_pool_id, date, failed_tenant_id)
    WHERE unallocated_type = 'identity_broken';
```

---

### Table 7: `dbo.reconciliation_results` — Boundary Integrity Verdicts

**One row = one reconciliation check verdict for one session.**
**Grain relationship:** CHECKS the grain — three boundary checks, exactly three rows per session.
**Producer:** RE Result Writer (Component 7) — atomic write, all 3 rows or none.
**Consumer:** UI Zone 3 Reconciliation Result Reader (PASS/FAIL display — no drill-down, no detail)

```sql
CREATE TABLE dbo.reconciliation_results (
    id              BIGINT              NOT NULL    IDENTITY(1,1),
    session_id      UNIQUEIDENTIFIER    NOT NULL,
    check_name      NVARCHAR(50)        NOT NULL,
    verdict         NVARCHAR(4)         NOT NULL,   -- 'PASS' | 'FAIL'
    fail_subtype    NVARCHAR(6)         NULL,       -- 'FAIL-1' | 'FAIL-2' (Check 3 only)
    failing_count   INT                 NULL,       -- operator field — NOT surfaced to CFO
                                                    -- DESIGN DECISION (W-5): presentation boundary
                                                    -- enforced at UI layer, not at DB layer.
                                                    -- Structural enforcement would require a VIEW
                                                    -- exposing only (check_name, verdict) to CFO roles.
                                                    -- Accepted trade-off: UI contract governs CFO exposure.
    -- DESIGN DECISION (R10-W-1): detail content contract is owned entirely by the application layer.
    -- RE Result Writer (C7) is the sole producer of this column.
    -- The DB layer enforces only that detail is NULL or any NVARCHAR string — no format, structure,
    -- or maximum length is enforced by the schema. This is intentional:
    --   (1) detail carries diagnostic prose for operator use. Format changes with RE logic evolution.
    --       A DB-level CHECK (e.g., ISJSON or LEN bound) would couple every C7 format iteration
    --       to a Flyway migration — the same class of coupling avoided in the W-5 design decision.
    --   (2) The CFO-layer exposure boundary is enforced at the UI layer (W-5):
    --       Zone 3 surfaces only check_name and verdict. detail is visible to operators only.
    --   (3) If C7's diagnostic message format is versioned (e.g., structured JSON), operator tools
    --       that parse detail must treat format as an application-layer contract, not a schema contract.
    --       Format regressions surface at the operator tool layer, not at the DB write layer.
    -- Risk accepted: a C7 bug that writes NULL when a non-NULL diagnostic string is expected
    -- is undetectable at DB level. Detection relies on C7 unit tests and operator query review.
    -- If a future requirement mandates structured detail (e.g., ISJSON = 1), add the CHECK
    -- via Flyway migration after confirming all existing rows conform. (R10-W-1 fix)
    detail          NVARCHAR(MAX)       NULL,       -- operator field — NOT surfaced to CFO (same contract as W-5)

    CONSTRAINT PK_reconciliation_results
        PRIMARY KEY (id),

    CONSTRAINT FK_recon_session
        FOREIGN KEY (session_id) REFERENCES raw.ingestion_log(session_id),

    -- Exactly one verdict per check per session
    CONSTRAINT UQ_recon_check_per_session
        UNIQUE (session_id, check_name),

    -- check_name enumerated — exactly the three system checks
    CONSTRAINT CHK_recon_check_name
        CHECK (check_name IN (
            'Capacity vs Usage',
            'Usage vs Tenant Mapping',
            'Computed vs Billed vs Posted'
        )),

    -- Binary verdict — no intermediate states
    CONSTRAINT CHK_recon_verdict
        CHECK (verdict IN ('PASS', 'FAIL')),

    -- fail_subtype values
    CONSTRAINT CHK_recon_fail_subtype_values
        CHECK (fail_subtype IS NULL OR fail_subtype IN ('FAIL-1', 'FAIL-2')),

    -- fail_subtype rule — one constraint covering both conditions atomically:
    -- (1) fail_subtype applies only to Check 3 (not Check 1 or Check 2)
    -- (2) fail_subtype requires a FAIL verdict (PASS rows always carry NULL fail_subtype)
    -- Two separate constraints (previous design) covered the same semantic rule
    -- and could drift independently if one was modified without the other.
    -- Single combined constraint eliminates that maintenance gap.
    CONSTRAINT CHK_recon_fail_subtype_rule
        CHECK (
            fail_subtype IS NULL
            OR (verdict = 'FAIL' AND check_name = 'Computed vs Billed vs Posted')
        ),

    -- Unified failing_count semantics (R4-W-2 → R8-REC-1 → R9-W-1/R9-REC-2 fix):
    -- This single constraint replaces two prior partial guards:
    --   CHK_recon_failing_count_nonneg (R4-W-2): failing_count >= 0 when non-NULL.
    --   CHK_recon_failing_count_on_fail (R8-REC-1): failing_count IS NOT NULL on FAIL verdicts.
    -- Those two constraints were applied independently across rounds and left two gaps:
    --   (1) FAIL + failing_count = 0 passed (IS NOT NULL but 0 is logically contradictory
    --       — a check cannot FAIL if zero records failed). (R9-W-1 gap)
    --   (2) PASS + failing_count IS NOT NULL passed (a PASS verdict with a non-NULL count
    --       is logically contradictory — PASS means no records failed). (R9-REC-2 gap)
    -- This unified constraint closes both gaps simultaneously:
    --   PASS verdict: failing_count MUST be NULL (no failures → no count).
    --   FAIL verdict: failing_count MUST be > 0 (at least one record failed for FAIL to exist).
    -- The > 0 floor on FAIL rows subsumes the prior >= 0 and IS NOT NULL requirements.
    -- Existing environments: DROP CHK_recon_failing_count_nonneg + CHK_recon_failing_count_on_fail,
    -- then ADD this constraint. Pre-migration validation required — see Deployment Prerequisite #9.
    CONSTRAINT CHK_recon_failing_count_semantics
        CHECK (
            (verdict = 'PASS' AND failing_count IS NULL)
            OR (verdict = 'FAIL' AND failing_count > 0)
        ),

    -- fail_subtype must be non-NULL when Check 3 verdict is FAIL (R9-REC-1 fix):
    -- CHK_recon_fail_subtype_rule permits fail_subtype only for Check 3 FAIL rows —
    -- it does NOT require it when those conditions hold.
    -- A Check 3 FAIL row with fail_subtype = NULL passes all constraints but leaves
    -- the operator unable to distinguish FAIL-1 (computed ≠ billed) from FAIL-2 (billed ≠ posted)
    -- without a secondary query. RE Result Writer (C7) always computes fail_subtype per the
    -- FAIL-1 precedence rule (Source 4 / Source 5 grain mapping). This constraint converts
    -- that application-layer invariant into a DB-layer rejection.
    -- Existing environments: ALTER TABLE ADD CONSTRAINT — see Deployment Prerequisite #10.
    CONSTRAINT CHK_recon_fail_subtype_on_check3_fail
        CHECK (
            check_name <> 'Computed vs Billed vs Posted'
            OR verdict = 'PASS'
            OR fail_subtype IS NOT NULL
        )
);

CREATE INDEX IX_recon_session
    ON dbo.reconciliation_results (session_id);
```

---

### Table 8: `dbo.state_store` — Lifecycle Control

**One row = one session's lifecycle state.**
**Grain relationship:** CONTROLS the grain — gates analysis, approval, and export.
**Producer:** SM Approved Result Writer (C9) — writes APPROVED + write_result in ONE atomic transaction (P1 #26).
**Consumers:** Export Gate Enforcer · UI Screen Router · UI Footer Control Manager

```sql
CREATE TABLE dbo.state_store (
    session_id          UNIQUEIDENTIFIER    NOT NULL,
    application_state   NVARCHAR(10)        NOT NULL,
    session_status      NVARCHAR(10)        NOT NULL,
    analysis_status     NVARCHAR(10)        NOT NULL,   -- display signal only — not a state gate
    write_result        NVARCHAR(10)        NULL,       -- NULL until APPROVED atomic write
    retry_count         INT                 NOT NULL    DEFAULT 0,

    CONSTRAINT PK_state_store
        PRIMARY KEY (session_id),

    CONSTRAINT FK_state_store_session
        FOREIGN KEY (session_id) REFERENCES raw.ingestion_log(session_id),

    CONSTRAINT CHK_state_application
        CHECK (application_state IN ('EMPTY', 'UPLOADED', 'ANALYZED', 'APPROVED')),

    CONSTRAINT CHK_state_session_status
        CHECK (session_status IN ('ACTIVE', 'TERMINAL')),

    CONSTRAINT CHK_state_analysis_status
        CHECK (analysis_status IN ('IDLE', 'ANALYZING')),

    CONSTRAINT CHK_state_write_result
        CHECK (write_result IS NULL OR write_result IN ('SUCCESS', 'FAIL')),

    -- CRITICAL ATOMIC WRITE ENFORCEMENT (P1 #26):
    -- application_state = APPROVED cannot exist in state_store without write_result set.
    -- This prevents the crash window scenario where:
    --   (1) C8 writes application_state = APPROVED (old design — two separate transactions)
    --   (2) crash occurs before C9 writes write_result
    --   (3) SM restarts — state = APPROVED, write_result = NULL
    --   (4) Export Gate Enforcer evaluates: NULL ≠ SUCCESS → BLOCKED permanently
    -- C9 performs ONE atomic transaction writing BOTH fields simultaneously.
    -- C8 does NOT write to state_store at all.
    -- This constraint rejects any write that sets APPROVED without write_result.
    CONSTRAINT CHK_state_approved_requires_write_result
        CHECK (application_state <> 'APPROVED' OR write_result IS NOT NULL),

    -- TERMINAL session_status is only valid after APPROVED state
    CONSTRAINT CHK_state_terminal_requires_approved
        CHECK (session_status <> 'TERMINAL' OR application_state = 'APPROVED'),

    -- analysis_status = 'ANALYZING' is only valid while analysis dispatch is in progress
    -- application_state = 'UPLOADED' = engines dispatched, not yet complete
    -- Once application_state advances to ANALYZED or APPROVED, analysis_status must be 'IDLE'
    -- Prevents divergent display state: UI showing 'ANALYZING' while state is already 'ANALYZED'
    CONSTRAINT CHK_state_analysis_status_scope
        CHECK (analysis_status = 'IDLE' OR application_state = 'UPLOADED'),

    -- retry_count bounded — hard ceiling regardless of ANALYSIS_MAX_RETRIES config value
    -- A runaway retry loop would otherwise be invisible at DB level
    -- Ceiling = 100: well above any legitimate ANALYSIS_MAX_RETRIES configuration.
    -- COUPLING WARNING: if ANALYSIS_MAX_RETRIES is ever configured above 100,
    -- the DB rejects the retry_count INCREMENT → state machine cannot record the retry
    -- → SM enters inconsistent state (retried in code, not recorded in DB).
    -- Resolution: ceiling must always exceed ANALYSIS_MAX_RETRIES by at least 2×.
    -- Changing this ceiling requires a Flyway migration AND coordinated config update.
    CONSTRAINT CHK_state_retry_count
        CHECK (retry_count >= 0 AND retry_count <= 100),

    -- Symmetric enforcement of the atomic write invariant (R8-W-1 fix):
    -- CHK_state_approved_requires_write_result enforces: APPROVED → write_result IS NOT NULL.
    -- This constraint enforces the reverse: write_result IS NOT NULL → APPROVED.
    -- Together they form a bidirectional equivalence: APPROVED ↔ write_result IS NOT NULL.
    -- Without this constraint the schema accepts write_result = 'SUCCESS'/'FAIL' alongside
    -- application_state = 'ANALYZED', 'UPLOADED', or 'EMPTY' — a logically inconsistent row
    -- that passes all other CHK constraints silently.
    -- Export Gate integrity is not directly compromised (Export Gate evaluates BOTH fields),
    -- but a C9 component bug that stages write_result before state advances to APPROVED
    -- is undetectable at DB level without this constraint.
    -- Root cause (R8-W-1): original constraint was written defensively against the crash window
    -- scenario (APPROVED without write_result). The reverse risk was not surfaced at design time.
    CONSTRAINT CHK_state_write_result_requires_approved
        CHECK (write_result IS NULL OR application_state = 'APPROVED')
);

-- DESIGN DECISION (R6-W-1): application_state = 'APPROVED' with write_result = 'FAIL'
-- is structurally permitted by the schema. CHK_state_approved_requires_write_result enforces
-- write_result IS NOT NULL when APPROVED — it does NOT enforce write_result = 'SUCCESS'.
--
-- What this state represents:
-- C9 completed the atomic write transaction (state transitioned to APPROVED) but recorded that
-- the grain copy to final.allocation_result failed (write_result = 'FAIL'). The session is
-- marked APPROVED in the lifecycle but the grain data was not durably written. This state
-- is structurally valid at the schema level — it represents a real failure mode worth preserving
-- in the audit trail for forensic diagnosis.
--
-- Why write_result = 'SUCCESS' is NOT enforced at the schema level:
-- Strengthening the constraint to CHECK (application_state <> 'APPROVED' OR write_result = 'SUCCESS')
-- would prevent C9 from writing APPROVED + write_result = 'FAIL' — losing the forensic audit record.
-- If C9 must write APPROVED atomically with the grain copy, a FAIL result could only be expressed
-- as: (a) not writing to state_store at all (leaves ANALYZED — but session is truly approved),
-- or (b) rolling back the entire transaction (loses the state transition record entirely).
-- Neither alternative preserves the audit trail as well as APPROVED + FAIL.
--
-- CRITICAL Export Gate contract:
-- The Export Gate Enforcer MUST evaluate: application_state = 'APPROVED' AND write_result = 'SUCCESS'.
-- Evaluating ONLY application_state = 'APPROVED' opens the export gate on APPROVED + FAIL sessions.
-- The export reads from final.allocation_result, which is empty or partial on FAIL — delivering
-- a blank or incomplete export to the CFO with no structural error raised.
-- This is a MANDATORY application-layer contract. The schema cannot enforce it. (R6-W-1 fix)
```

---

### Table 9: `dbo.state_history` — Audit Trail

**One row = one state transition event.**
**Grain relationship:** CONTROLS the grain — append-only audit of every lifecycle change.
**Producer:** SM State Persist — written atomically with every state_store update.
**Consumer:** Operator diagnostics · session reconstruction · compliance audit

```sql
CREATE TABLE dbo.state_history (
    id          BIGINT              NOT NULL    IDENTITY(1,1),
    session_id  UNIQUEIDENTIFIER    NOT NULL,
    from_state          NVARCHAR(10)        NOT NULL,
    to_state            NVARCHAR(10)        NOT NULL,
    -- Renamed from 'trigger' — SQL Server reserved keyword requires [trigger] bracket
    -- notation in every query reference. Renamed to avoid query authoring errors.
    transition_trigger  NVARCHAR(50)        NOT NULL,
    -- Renamed from 'timestamp' — SQL Server reserved keyword (synonym for the rowversion data type).
    -- Without rename: CREATE INDEX on (session_id, timestamp) fails at Flyway migration parse time.
    -- T-SQL parser interprets 'timestamp' as the rowversion type keyword, not a column identifier,
    -- causing a DDL syntax error — identical in class to the prior 'trigger' rename (C-4, Round 1).
    -- All query references also require [timestamp] bracket notation without rename.
    -- Renamed to transitioned_at — consistent with approved_at naming in final.allocation_result.
    -- Existing environments: sp_rename migration required (Deployment Prerequisite #7). (R5-C-1 fix)
    transitioned_at     DATETIME2           NOT NULL    DEFAULT SYSUTCDATETIME(),

    CONSTRAINT PK_state_history
        PRIMARY KEY (id),

    CONSTRAINT FK_history_session
        FOREIGN KEY (session_id) REFERENCES raw.ingestion_log(session_id),

    CONSTRAINT CHK_history_from_state
        CHECK (from_state IN ('EMPTY', 'UPLOADED', 'ANALYZED', 'APPROVED')),

    CONSTRAINT CHK_history_to_state
        CHECK (to_state IN ('EMPTY', 'UPLOADED', 'ANALYZED', 'APPROVED')),

    -- Prevent self-transitions — a transition must move the session to a different state
    -- Exception: SYSTEM_RECOVERY may log a same-state re-entry as a forensic audit record
    -- (e.g., ANALYZED → ANALYZED with trigger = SYSTEM_RECOVERY = "system confirmed this state on restart")
    -- All other triggers: from_state = to_state is a state machine bug, not a lifecycle event
    CONSTRAINT CHK_history_no_self_transition
        CHECK (from_state <> to_state OR transition_trigger = 'SYSTEM_RECOVERY'),

    -- Enumerated transition_trigger values — exactly 7 (P2 #24)
    -- Non-enumerated triggers are rejected at DB level.
    -- An unreliable trigger field breaks session reconstruction from audit history.
    -- Sessions cannot be diagnosed from partial audit trails.
    CONSTRAINT CHK_history_trigger
        CHECK (transition_trigger IN (
            'INGESTION_COMPLETE',
            'ANALYSIS_DISPATCHED',
            'ENGINES_COMPLETE',
            'CFO_APPROVAL',
            'ANALYSIS_FAILED',
            'SESSION_CLOSED',
            'SYSTEM_RECOVERY'
        ))
);

-- DESIGN DECISION (R3-W-4): Forward-only transition direction is NOT enforced at DB level.
-- CHK_history_from_state and CHK_history_to_state each validate the state enum independently
-- but impose no restriction on the (from_state, to_state) pairing.
-- A record of (from_state='APPROVED', to_state='EMPTY') passes all current CHECK constraints.
--
-- Why direction enforcement belongs at the application layer, not the DB layer:
-- A CHECK constraint enforcing the transition matrix would require hardcoding all valid
-- (from_state, to_state, transition_trigger) triplets in T-SQL. Any change to the state
-- machine's transition graph then requires a Flyway migration just to update the constraint —
-- coupling DB schema versioning to state machine logic versioning. The State Machine module
-- is the authoritative owner of transition direction. It enforces forward-only progression
-- (EMPTY → UPLOADED → ANALYZED → APPROVED) in application code, not at the DB engine.
--
-- What prevents corrupt audit records:
-- The State Machine cannot produce a reverse-transition record without a code-layer bug.
-- The P1 #32 integration test (7-step chain) includes state sequence validation as a
-- mandatory CI gate. Reverse-transition records are a state machine bug symptom, not a
-- data entry risk. Application-layer enforcement + integration test coverage is the
-- correct control structure for this constraint class.
--
-- Trade-off accepted: reverse-transition records are structurally accepted at DB level.
-- If a state machine bug produces one, it will be stored without a DB-level rejection signal.
-- Detection relies on the integration test suite and operator diagnostic queries.
-- The alternative (DB-level transition matrix) tightly couples schema to SM logic.
-- This is the lesser risk for this application's change velocity. (R3-W-4 fix)

-- Session timeline — ordered audit reconstruction
CREATE INDEX IX_history_session_timeline
    ON dbo.state_history (session_id, transitioned_at);
```

---

### Table 10: `final.allocation_result` — Immutable Approved Result

**One row = one approved grain cell (copied from allocation_grain at APPROVED).**
**Grain relationship:** IS the grain (write-once immutable copy).
**Producer:** SM Approved Result Writer (C9) — single atomic transaction with APPROVED state write.
**Consumers:** Export Source Reader · File Delivery Handler (all three export formats read this only)

```sql
CREATE TABLE final.allocation_result (
    id                  BIGINT              NOT NULL    IDENTITY(1,1),
    -- DESIGN DECISION (R6-REC-2): NEWSEQUENTIALID() used instead of NEWID() for row_id.
    -- NEWID() generates cryptographically random GUIDs — each INSERT causes a ~50% probability
    -- page split on UQ_final_row_id (the UNIQUE index on this column) because random GUIDs
    -- scatter across the sorted index structure. This produces high index fragmentation and
    -- elevated write-time disk I/O on the approval batch write.
    -- NEWSEQUENTIALID() generates monotonically increasing GUIDs per SQL Server instance restart,
    -- eliminating page splits on the unique index. Functional behavior is identical:
    -- uniqueness is guaranteed, per-row export traceability is preserved.
    -- Trade-off accepted: NEWSEQUENTIALID() cannot be used in client-generated values or
    -- cross-server GUID comparisons requiring strict randomness. For a server-generated DEFAULT
    -- on a write-once immutable table read only by IX_final_session, NEWSEQUENTIALID() is correct.
    -- The Export Source Reader path uses session_id (IX_final_session), not row_id — the UNIQUE
    -- index on row_id is a duplicate-prevention guard, not a read access path. (R6-REC-2 fix)
    row_id              UNIQUEIDENTIFIER    NOT NULL    DEFAULT NEWSEQUENTIALID(),   -- per-row export traceability
    session_id          UNIQUEIDENTIFIER    NOT NULL,
    -- DESIGN DECISION (W-11): approved_at captures DB write time, not CFO click time.
    -- If SM Approved Result Writer has latency between CFO confirmation and DB write,
    -- approved_at overstates approval time by that latency.
    -- For precise CFO click time, the SM C9 component must pass the click timestamp
    -- explicitly rather than relying on SYSUTCDATETIME() at INSERT time.
    -- Accepted trade-off: server-time is simpler and sufficient for current audit requirements.
    -- If compliance requirements tighten, this field becomes a passed value, not a DEFAULT.
    approved_at         DATETIME2           NOT NULL    DEFAULT SYSUTCDATETIME(),

    -- Grain fields (copied verbatim from allocation_grain at APPROVED)
    region              NVARCHAR(100)       NOT NULL,
    gpu_pool_id         NVARCHAR(100)       NOT NULL,
    date                DATE                NOT NULL,
    billing_period      NVARCHAR(7)         NOT NULL,
    allocation_target   NVARCHAR(255)       NOT NULL,
    unallocated_type    NVARCHAR(20)        NULL,
    failed_tenant_id    NVARCHAR(255)       NULL,
    gpu_hours           DECIMAL(18,6)       NOT NULL,
    cost_per_gpu_hour   DECIMAL(18,6)       NOT NULL,
    contracted_rate     DECIMAL(18,6)       NULL,
    revenue             DECIMAL(18,2)       NOT NULL,
    cogs                DECIMAL(18,2)       NOT NULL,
    gross_margin        DECIMAL(18,2)       NOT NULL,

    CONSTRAINT PK_final_result
        PRIMARY KEY (id),

    -- row_id uniqueness — prevents duplicate row delivery in export
    CONSTRAINT UQ_final_row_id
        UNIQUE (row_id),

    CONSTRAINT FK_final_session
        FOREIGN KEY (session_id) REFERENCES raw.ingestion_log(session_id),

    -- Same grain integrity constraints as allocation_grain (enforces copy fidelity)
    CONSTRAINT CHK_final_unallocated_type
        CHECK (
            unallocated_type IS NULL
            OR unallocated_type = 'capacity_idle'
            OR unallocated_type = 'identity_broken'
        ),

    -- LIKE handles structure; SUBSTRING enforces month range 01–12
    CONSTRAINT CHK_final_billing_period
        CHECK (
            billing_period LIKE '[0-9][0-9][0-9][0-9]-[0-1][0-9]'
            AND SUBSTRING(billing_period, 6, 2) BETWEEN '01' AND '12'
        ),

    CONSTRAINT CHK_final_type_b_zero_revenue
        CHECK (
            allocation_target <> 'unallocated'
            OR (revenue = 0 AND contracted_rate IS NULL)
        ),

    -- ── COPY FIDELITY CONSTRAINTS (W-9 FIX) ──────────────────────────────────────
    -- Replicate the full allocation_grain record type integrity at the final table.
    -- Purpose: a write that bypasses allocation_grain entirely is caught here.
    -- Principle: copy fidelity argument covers steady state; these constraints
    --            cover the failure path (SM Result Writer bug, direct SQL injection).

    -- Type A must have NULL unallocated_type
    CONSTRAINT CHK_final_type_a_no_subtype
        CHECK (allocation_target = 'unallocated' OR unallocated_type IS NULL),

    -- Type B must have non-NULL unallocated_type — no ambiguous unallocated rows
    CONSTRAINT CHK_final_type_b_must_classify
        CHECK (allocation_target <> 'unallocated' OR unallocated_type IS NOT NULL),

    -- Type A must have non-NULL contracted_rate (revenue formula input)
    CONSTRAINT CHK_final_type_a_rate_required
        CHECK (allocation_target = 'unallocated' OR contracted_rate IS NOT NULL),

    -- Type B: gross_margin must be strictly negative (= −cogs)
    -- CHK_final_cogs_positive (below) enforces cogs > 0 after DECIMAL(18,2) rounding.
    -- With cogs > 0, Type B gross_margin = −cogs < 0 always. (R4-W-1 fix)
    CONSTRAINT CHK_final_type_b_negative_margin
        CHECK (allocation_target <> 'unallocated' OR gross_margin < 0),

    -- identity_broken: failed_tenant_id MUST be non-NULL (pass-through invariant, P1 #10)
    -- An export row with NULL failed_tenant_id for identity_broken loses tenant traceability
    CONSTRAINT CHK_final_identity_broken_requires_ftid
        CHECK (
            unallocated_type <> 'identity_broken'
            OR failed_tenant_id IS NOT NULL
        ),

    -- capacity_idle: failed_tenant_id MUST be NULL
    CONSTRAINT CHK_final_capacity_idle_null_ftid
        CHECK (unallocated_type <> 'capacity_idle' OR failed_tenant_id IS NULL),

    -- Type A: failed_tenant_id MUST be NULL (allocation succeeded — no identity failure)
    CONSTRAINT CHK_final_type_a_null_ftid
        CHECK (allocation_target = 'unallocated' OR failed_tenant_id IS NULL),

    -- Positive consumption / idle hours
    CONSTRAINT CHK_final_gpu_hours_positive
        CHECK (gpu_hours > 0),

    -- Positive cost rate — 0 cost produces gross_margin = revenue (misleading export)
    CONSTRAINT CHK_final_cost_per_hour_positive
        CHECK (cost_per_gpu_hour > 0),

    -- cogs must be strictly positive — mirrors CHK_grain_cogs_positive (R4-W-1 fix).
    -- Enforces copy fidelity on cogs at the final export layer:
    -- a write that bypasses allocation_grain with a zero or negative cogs is caught here.
    -- Also makes CHK_final_type_b_negative_margin structurally sound
    -- against DECIMAL(18,2) rounding-to-zero on micro-precision inputs.
    CONSTRAINT CHK_final_cogs_positive
        CHECK (cogs > 0)

    -- IMMUTABILITY CONTRACT:
    -- No UPDATE or DELETE on this table is permitted.
    -- Enforced at application level (State Machine APPROVED = terminal, no further writes).
    -- row_id UNIQUE prevents duplicate row inserts for the same approved row.
    -- Enforced at DB level: GRANT SELECT on final.allocation_result to export roles ONLY.
    -- No GRANT UPDATE or DELETE on this table.
    --
    -- DESIGN DECISION (R6-W-2): TRUNCATE TABLE bypasses the INSTEAD OF trigger.
    -- INSTEAD OF triggers fire on row-level DML (INSERT, UPDATE, DELETE). TRUNCATE TABLE
    -- is a DDL operation — it does NOT fire any DML trigger. A TRUNCATE on this table
    -- runs silently, deletes all approved grain rows, and the immutability trigger never fires.
    --
    -- TRUNCATE TABLE is controlled by ALTER TABLE permission — not DELETE permission.
    -- Withholding GRANT DELETE from export roles does NOT prevent TRUNCATE. A DB account
    -- with ALTER TABLE on this schema (typically schema owners and DBA accounts) can TRUNCATE.
    --
    -- Why DENY ALTER TABLE is not added to the DDL:
    -- TRUNCATE is a DBA-class operation. Application roles are granted only SELECT on this table.
    -- No application code path executes TRUNCATE — this is not an ORM-reachable operation under
    -- correct role configuration. The risk is confined to: (a) DBA error, (b) malicious DBA action,
    -- or (c) schema ownership misconfiguration. These are infrastructure/audit-layer concerns:
    --   - SQL Server Audit trace on DDL operations against final.allocation_result.
    --   - Principle of least privilege: schema owner role not granted to application service accounts.
    --   - Separation of duties: DBA who can TRUNCATE is not the DBA who approves export results.
    --
    -- If formal enforcement is required: DENY ALTER ON SCHEMA::final TO [dba_role] scoped
    -- to application DBA roles. Note: ALTER TABLE is object-level permission syntax; ALTER is
    -- the correct schema-level permission class for DENY ON SCHEMA::. This requires a coordinated
    -- permissions migration and must be validated against any legitimate DDL operations (index
    -- maintenance, statistics updates) that DBAs perform on this table in production. (R6-W-2 fix · R7-REC-1 fix)
);

-- Export Source Reader: reads ALL rows for this session
CREATE INDEX IX_final_session
    ON final.allocation_result (session_id);

-- Operator audit: time-ordered session history
CREATE INDEX IX_final_approved_at
    ON final.allocation_result (approved_at);

-- ── GRAIN NATURAL KEY UNIQUENESS — COPY FIDELITY FROM allocation_grain (R7-W-1 FIX) ──────────
-- W-9 copy fidelity pass (Round 1) replicated all 13 CHECK constraints from dbo.allocation_grain
-- into final.allocation_result but did NOT replicate the three filtered UNIQUE indexes.
-- Without these indexes, a C9 double-write (e.g., SM Approved Result Writer called twice for
-- the same session) inserts duplicate grain rows with different row_ids — all 13 CHECK constraints
-- pass, all four non-unique indexes pass, and the Export Source Reader delivers doubled financials
-- to the CFO with no structural error raised at any layer.
--
-- These three indexes mirror UQ_grain_type_a_natural_key, UQ_grain_capacity_idle_natural_key,
-- and UQ_grain_identity_broken_natural_key on dbo.allocation_grain exactly. The grain natural key
-- is: Region × GPU Pool × Day × Allocation Target (with type disambiguation for Type B rows).
-- The filter predicates match the two-record-type model enforced by CHK constraints on both tables.
--
-- Trade-off accepted: filtered UNIQUE indexes increase INSERT cost on C9 writes (one index probe
-- per row per index). For write-once approved data this is a one-time cost per session, not a
-- recurring write-path cost. The duplicate-prevention value exceeds the INSERT overhead.

-- Type A rows: allocation_target identifies the tenant (not 'unallocated')
CREATE UNIQUE INDEX UQ_final_type_a_natural_key
    ON final.allocation_result (session_id, region, gpu_pool_id, date, allocation_target)
    WHERE allocation_target <> 'unallocated';

-- Type B subtype: capacity_idle rows (unallocated_type = 'capacity_idle')
CREATE UNIQUE INDEX UQ_final_capacity_idle_natural_key
    ON final.allocation_result (session_id, region, gpu_pool_id, date, unallocated_type)
    WHERE unallocated_type = 'capacity_idle';

-- Type B subtype: identity_broken rows (unallocated_type = 'identity_broken')
-- failed_tenant_id included because multiple identity_broken rows per pool/day are permitted
-- (each failed_tenant_id is a distinct broken identity event within that pool/day grain cell)
CREATE UNIQUE INDEX UQ_final_identity_broken_natural_key
    ON final.allocation_result (session_id, region, gpu_pool_id, date, failed_tenant_id)
    WHERE unallocated_type = 'identity_broken';

-- ── IMMUTABILITY DDL ENFORCEMENT (W-10 FIX · R3-W-3/R3-REC-1 FIX) ───────────
-- Enforces write-once at the DB engine layer — not only at application/GRANT level.
-- GRANT SELECT to export roles remains required for read access control.
-- INSTEAD OF trigger fires BEFORE the operation — no row is modified, error is raised.
-- This closes the gap where a DB admin or misconfigured ORM could update approved rows.
--
-- R3-W-3/R3-REC-1 fix — two changes from original W-10 implementation:
-- (1) @@TRANCOUNT guard before ROLLBACK TRANSACTION:
--     ROLLBACK TRANSACTION inside a trigger rolls back to the OUTERMOST transaction.
--     If called from within an application BEGIN TRAN block, the outer transaction is
--     rolled back and @@TRANCOUNT drops to 0. The caller's subsequent COMMIT then raises
--     error 3902 (COMMIT with no corresponding BEGIN TRAN) — a secondary error on top of
--     the immutability signal. IF @@TRANCOUNT > 0 guard ensures ROLLBACK only fires when
--     an active outer transaction exists, cleanly terminating it before the error is raised.
-- (2) RAISERROR → THROW:
--     THROW is the SQL Server 2012+ standard for raising terminating errors.
--     RAISERROR (severity 16) is legacy. THROW produces a re-throwable exception with
--     a clean error number (51000 = user-defined range), no severity/state complexity,
--     and consistent behavior with TRY/CATCH blocks in calling application code.
CREATE TRIGGER TR_final_allocation_result_prevent_mutation
    ON final.allocation_result
    INSTEAD OF UPDATE, DELETE
AS
BEGIN
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW 51000,
        'final.allocation_result is immutable. UPDATE and DELETE are not permitted on approved grain rows. This table is written once at APPROVED state by SM Approved Result Writer (C9) and locked permanently.',
        1;
END;
```

---

### Table 11: `dbo.kpi_cache` — Zone 1 KPI Pre-Computed Cache

**One row = one session's five Zone 1 KPI values.**
**Grain relationship:** CACHES the grain — pre-computed at ANALYZED, immutable per session_id.
**Producer:** KPI Data Aggregator — fires at ANALYZED time, reads allocation_grain.
**Consumer:** UI Zone 1 KPI Card Renderer (read on every render — no re-aggregation from grain)

```sql
CREATE TABLE dbo.kpi_cache (
    session_id              UNIQUEIDENTIFIER    NOT NULL,
    gpu_revenue             DECIMAL(18,2)       NOT NULL,   -- SUM(Type A revenue)
    gpu_cogs                DECIMAL(18,2)       NOT NULL,   -- SUM(Type A cogs)
    idle_gpu_cost           DECIMAL(18,2)       NOT NULL,   -- SUM(Type B cogs)
    idle_gpu_cost_pct       DECIMAL(5,2)        NOT NULL,   -- idle_gpu_cost / (gpu_cogs + idle_gpu_cost) × 100
    cost_allocation_rate    DECIMAL(5,2)        NOT NULL,   -- gpu_cogs / (gpu_cogs + idle_gpu_cost) × 100
    computed_at             DATETIME2           NOT NULL    DEFAULT SYSUTCDATETIME(),

    CONSTRAINT PK_kpi_cache
        PRIMARY KEY (session_id),

    CONSTRAINT FK_kpi_session
        FOREIGN KEY (session_id) REFERENCES raw.ingestion_log(session_id),

    -- Percentages bounded to [0, 100]
    CONSTRAINT CHK_kpi_idle_pct
        CHECK (idle_gpu_cost_pct BETWEEN 0 AND 100),

    CONSTRAINT CHK_kpi_allocation_rate
        CHECK (cost_allocation_rate BETWEEN 0 AND 100),

    -- Monetary KPI guardrails (R4-W-4 fix):
    -- All three monetary columns are sums of non-negative grain values.
    -- After C-2 fix: contracted_rate >= 0 → Type A revenue >= 0 → gpu_revenue >= 0 always.
    -- After R4-W-1 fix: cogs > 0 per grain row → gpu_cogs >= 0 and idle_gpu_cost >= 0 always.
    -- These constraints protect against a KPI aggregator bug writing negative monetary values,
    -- which would silently corrupt the complement percentage calculation.
    -- No valid dataset can produce negative values here — these are pure guardrails.
    CONSTRAINT CHK_kpi_revenue_nonneg
        CHECK (gpu_revenue >= 0),

    CONSTRAINT CHK_kpi_cogs_nonneg
        CHECK (gpu_cogs >= 0),

    CONSTRAINT CHK_kpi_idle_nonneg
        CHECK (idle_gpu_cost >= 0),

    -- Complement relationship: idle% + allocation rate = 100%
    -- Tolerance of 0.01 accommodates DECIMAL(5,2) rounding.
    -- <= 0.01 (not < 0.01): idle_gpu_cost_pct and cost_allocation_rate are each
    -- independently computed and rounded to DECIMAL(5,2) by the application layer.
    -- In edge rounding cases (e.g., 33.34 + 66.67 = 100.01 or 66.66 + 33.33 = 99.99),
    -- the sum deviates from 100.00 by exactly 0.01. Strict < 0.01 rejects this as a
    -- constraint violation → KPI cache INSERT fails → ANALYZED milestone blocked with
    -- no self-recovery path. <= 0.01 accepts the maximum possible DECIMAL rounding
    -- deviation and is the structurally correct boundary. (R3-C-1 fix)
    CONSTRAINT CHK_kpi_complement
        CHECK (ABS((idle_gpu_cost_pct + cost_allocation_rate) - 100.00) <= 0.01)

    -- DESIGN DECISION (R5-REC-1): KPI percentage zero-denominator is NOT guarded at DB level.
    -- Formula: idle_gpu_cost_pct = idle_gpu_cost / (gpu_cogs + idle_gpu_cost) × 100
    --          cost_allocation_rate = gpu_cogs / (gpu_cogs + idle_gpu_cost) × 100
    -- If (gpu_cogs + idle_gpu_cost) = 0, the KPI aggregator encounters a division-by-zero
    -- before the INSERT — the schema-level CHK_kpi_complement cannot fire because no INSERT
    -- is attempted. The ANALYZED milestone write crashes at the application layer.
    --
    -- Can (gpu_cogs + idle_gpu_cost) = 0 on valid data?
    -- Structurally: No. CHK_grain_cogs_positive enforces cogs > 0 per grain row.
    -- The Closure Rule (reserved_gpu_hours > 0) guarantees at least one grain row per session.
    -- Therefore at least one row's cogs contributes to either gpu_cogs (Type A) or
    -- idle_gpu_cost (Type B), making the denominator > 0 on all structurally valid data.
    -- The risk is a KPI aggregator bug that writes gpu_cogs = 0 AND idle_gpu_cost = 0
    -- — not a valid-data path. CHK_kpi_cogs_nonneg and CHK_kpi_idle_nonneg (R4-W-4) allow
    -- both to be 0 simultaneously, so a bugged aggregator passes those constraints.
    --
    -- Why DB-level guard is not added here:
    -- A CHECK constraint cannot enforce a joint lower bound on two columns that individually
    -- allow 0. Adding CHECK (gpu_cogs + idle_gpu_cost > 0) would be structurally sound
    -- but would reject any aggregator write where the intermediate values are 0 before
    -- final computation — not an issue on valid data, but adds friction to test scenarios.
    -- The correct guard is in the KPI aggregator: validate denominator > 0 before
    -- computing percentages, raise an explicit error if zero (indicating a cogs-chain bug),
    -- and halt the ANALYZED write with a diagnostic message rather than a silent crash.
    -- This is the same class as the C-NEW-3 zero-denominator UI contract for revenue = 0:
    -- the schema captures the structural fact, the application layer owns the guard.
    -- Decision: application-layer validation is the correct owner. (R5-REC-1 fix)

    -- Diagnostic driver: P2 #30
    -- Without cache: full-table SUM on allocation_grain at 500K+ rows per render
    -- under concurrent CFO access → throughput collapse.
    -- Cache is immutable per session_id. A new session produces a new row.
    -- Previous session cache rows retained per MAX_HISTORY_SESSIONS / HISTORY_RETENTION_DAYS.

    -- IMMUTABILITY CONTRACT (R11-W-1 fix):
    -- No UPDATE or DELETE on this table is permitted after the initial ANALYZED write.
    -- Enforced at DB level by TR_kpi_cache_prevent_mutation (INSTEAD OF trigger below).
    -- PK on session_id blocks duplicate INSERT — but does NOT block UPDATE of an existing row.
    -- Without the trigger: a state machine double-dispatch bug could cause the KPI Data Aggregator
    -- to run a second time for the same session_id — the INSERT is rejected (PK) but an UPDATE
    -- would silently overwrite cached KPIs. Zone 1 KPI Card Renderer would deliver values that
    -- do not correspond to the grain that was analyzed. CFO approval decision is made on
    -- inconsistent metrics.
    -- TRUNCATE TABLE bypasses INSTEAD OF triggers (same class as R6-W-2 on final.allocation_result).
    -- TRUNCATE is controlled by ALTER TABLE permission. Mitigation: least-privilege role assignment
    -- and SQL Server Audit trace on DDL operations against this table.
);

-- IMMUTABILITY DDL ENFORCEMENT (R11-W-1 fix)
-- Mirrors TR_final_allocation_result_prevent_mutation on final.allocation_result.
-- INSTEAD OF triggers fire before the DML operation — no row is modified, error is raised.
-- @@TRANCOUNT guard ensures ROLLBACK fires only when an active outer transaction exists.
-- THROW 51001: user-defined error range (50001–2147483647). 51000 is reserved for final.allocation_result.
CREATE TRIGGER TR_kpi_cache_prevent_mutation
    ON dbo.kpi_cache
    INSTEAD OF UPDATE, DELETE
AS
BEGIN
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW 51001,
        'dbo.kpi_cache is immutable. UPDATE and DELETE are not permitted on cached KPI rows. This table is written once at ANALYZED state by the KPI Data Aggregator and locked permanently per session_id.',
        1;
END;
```

---

### Table 12: `dbo.identity_broken_tenants` — Risk Flag SET Cache

**One row = one failed_tenant_id in the current session.**
**Grain relationship:** CACHES the grain — pre-computed SET of identity_broken tenant_ids.
**Producer:** SET pre-builder — fires at ANALYZED, reads allocation_grain WHERE unallocated_type = 'identity_broken'.
**Consumer:** UI Zone 2R Customer Data Aggregator — Risk FLAG if allocation_target ∈ identity_broken_tenants

```sql
CREATE TABLE dbo.identity_broken_tenants (
    session_id          UNIQUEIDENTIFIER    NOT NULL,
    failed_tenant_id    NVARCHAR(255)       NOT NULL,

    CONSTRAINT PK_identity_broken_tenants
        PRIMARY KEY (session_id, failed_tenant_id),

    CONSTRAINT FK_ibt_session
        FOREIGN KEY (session_id) REFERENCES raw.ingestion_log(session_id)

    -- SOURCE: allocation_grain.failed_tenant_id WHERE unallocated_type = 'identity_broken'
    -- CRITICAL (P1 #10, P1 #32):
    -- If failed_tenant_id was NULLed anywhere in the 7-component pass-through chain
    -- (IAM Resolver → IB Builder → Calculator → Grain Writer → this SET → Zone 2R),
    -- this table will be missing entries. The Risk flag silently under-fires.
    -- The CFO approves without identity integrity signal for affected tenants.
    -- The 7-step integration test (P1 #32) is the CI gate that validates this chain.
    -- It is a MANDATORY pre-deployment gate — not a development test.

    -- IMMUTABILITY CONTRACT (R11-W-2 fix):
    -- No UPDATE or DELETE on this table is permitted after the initial ANALYZED write.
    -- Enforced at DB level by TR_identity_broken_tenants_prevent_mutation (INSTEAD OF trigger below).
    -- PK on (session_id, failed_tenant_id) blocks duplicate INSERT — but does NOT block DELETE.
    -- Without the trigger: an application bug or ORM misfire that DELETEs entries from this table
    -- silently clears the Risk flag SET for affected tenants. Zone 2R produces no Risk indicator.
    -- The CFO approves a session with identity_broken tenants and no identity integrity signal.
    -- The failure is invisible at every layer — no structural rejection, no application error.
    -- This is the highest blast-radius mutation risk on any cache table in this schema.
    -- TRUNCATE TABLE bypasses INSTEAD OF triggers. Same mitigation as kpi_cache (R11-W-1) and
    -- final.allocation_result (R6-W-2): least-privilege role assignment + SQL Server Audit trace.
);

CREATE INDEX IX_ibt_session_lookup
    ON dbo.identity_broken_tenants (session_id);

-- IMMUTABILITY DDL ENFORCEMENT (R11-W-2 fix)
-- Mirrors TR_final_allocation_result_prevent_mutation on final.allocation_result.
-- Highest blast radius of the two ANALYZED-time cache tables:
-- a deleted entry silences the CFO Risk flag for an identity_broken tenant with no structural signal.
-- @@TRANCOUNT guard: prevents secondary error 3902 when trigger fires inside an outer BEGIN TRAN.
-- THROW 51002: distinct error number from 51000 (final.allocation_result) and 51001 (kpi_cache).
CREATE TRIGGER TR_identity_broken_tenants_prevent_mutation
    ON dbo.identity_broken_tenants
    INSTEAD OF UPDATE, DELETE
AS
BEGIN
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW 51002,
        'dbo.identity_broken_tenants is immutable. UPDATE and DELETE are not permitted on Risk flag SET entries. This table is written once at ANALYZED state by the SET pre-builder and locked permanently per session_id. Deletion suppresses the CFO Risk flag for identity_broken tenants without structural error.',
        1;
END;
```

---

## Schema-to-Grain Traceability Map

Every column in `dbo.allocation_grain` traced to its producer, grain role, and per-type value:

| Column | Producer | Grain Role | Type A | capacity_idle | identity_broken |
|---|---|---|---|---|---|
| `session_id` | Ingestion Orchestrator (K1) | Session anchor | same | same | same |
| `region` | raw.telemetry / raw.cost_management | Dimension 1 | from telemetry | from cost_mgmt | from telemetry |
| `gpu_pool_id` | raw.telemetry / raw.cost_management | Dimension 2 | from telemetry | from cost_mgmt | from telemetry |
| `date` | raw.telemetry | Dimension 3 | from telemetry | from cost_mgmt | from telemetry |
| `billing_period` | AE Billing Period Deriver LEFT(date,7) | Derived dimension (cross-module contract) | derived | derived | derived |
| `allocation_target` | Type A Builder / IB Builder / Closure Enforcer | Dimension 4 | tenant_id | 'unallocated' | 'unallocated' |
| `unallocated_type` | IB Builder / Closure Enforcer | Type B subclassification | NULL | 'capacity_idle' | 'identity_broken' |
| `failed_tenant_id` | IB Record Builder — mandatory pass-through (P1 #10) | Identity integrity signal | NULL | NULL | original tenant_id |
| `gpu_hours` | Telemetry Aggregator SUM / Closure Enforcer (reserved − consumed) | Volume | consumed | idle | consumed (unresolved) |
| `cost_per_gpu_hour` | Cost Rate Reader — from raw.cost_management | Cost formula input | from cost_mgmt | from cost_mgmt | from cost_mgmt |
| `contracted_rate` | IAM Resolver — from raw.iam | Revenue formula input | from raw.iam | NULL | NULL |
| `revenue` | Cost & Revenue Calculator | gpu_hours × contracted_rate | positive or zero (zero if contracted_rate = 0 — see C-2 / C-NEW-3) | 0 | 0 |
| `cogs` | Cost & Revenue Calculator | gpu_hours × cost_per_gpu_hour | positive | positive | positive |
| `gross_margin` | Cost & Revenue Calculator | revenue − cogs (A) / −cogs (B) | + or − | always − | always − |

---

## Index Register — All 28 Indexes with Diagnostic Traceability

| Index | Table | Key Columns | Purpose | Finding |
|---|---|---|---|---|
| IX_telemetry_session | raw.telemetry | session_id | Session scoping | K1 |
| IX_telemetry_grain | raw.telemetry | session_id, tenant_id, region, gpu_pool_id, date | AE GROUP BY | P1 #17 |
| IX_telemetry_pool_day | raw.telemetry | session_id, region, gpu_pool_id, date | RE Check 1 + Check 2 | P1 #17 |
| IX_cost_mgmt_session | raw.cost_management | session_id | Session scoping | K1 |
| IX_cost_mgmt_grain_lookup | raw.cost_management | session_id, region, gpu_pool_id, date | AE Cost Rate Reader + RE Check 1 | Architecture |
| IX_iam_resolver | raw.iam | tenant_id, billing_period | IAM LEFT JOIN — INDEX SEEK required | **P1 #8** |
| IX_iam_session | raw.iam | session_id | Session scoping | K1 |
| IX_billing_session | raw.billing | session_id | Session scoping | K1 |
| IX_billing_check3 | raw.billing | session_id, tenant_id, billing_period | RE Check 3 FAIL-1 | P1 #18 |
| IX_erp_session | raw.erp | session_id | Session scoping | K1 |
| IX_erp_check3 | raw.erp | session_id, tenant_id, billing_period | RE Check 3 FAIL-2 | P1 #18 |
| IX_grain_session | dbo.allocation_grain | session_id | Session scoping | K1 |
| IX_grain_closure_rule | dbo.allocation_grain | session_id, region, gpu_pool_id, date | Closure Rule SUM verification | P1 #9 |
| IX_grain_check3 | dbo.allocation_grain | session_id, allocation_target, billing_period (filtered: Type A) | RE Check 3 computed revenue | P1 #18 |
| IX_grain_region_aggregator | dbo.allocation_grain | session_id, region, allocation_target | Zone 2L Region aggregation | P2 #30 |
| IX_grain_customer_aggregator | dbo.allocation_grain | session_id, allocation_target | Zone 2R Customer aggregation | P2 #30 |
| IX_grain_identity_broken_set | dbo.allocation_grain | session_id, unallocated_type (filtered: identity_broken) | SET pre-computation | P2 #31 |
| UQ_grain_type_a_natural_key | dbo.allocation_grain | session_id, region, gpu_pool_id, date, allocation_target (filtered: Type A) | Grain natural key uniqueness — Type A | C-3 |
| UQ_grain_capacity_idle_natural_key | dbo.allocation_grain | session_id, region, gpu_pool_id, date, unallocated_type (filtered: capacity_idle) | Grain natural key uniqueness — capacity_idle | C-3 |
| UQ_grain_identity_broken_natural_key | dbo.allocation_grain | session_id, region, gpu_pool_id, date, failed_tenant_id (filtered: identity_broken) | Grain natural key uniqueness — identity_broken | C-3 |
| IX_recon_session | dbo.reconciliation_results | session_id | Session scoping | K1 |
| IX_history_session_timeline | dbo.state_history | session_id, transitioned_at | Audit reconstruction | P2 #24 |
| IX_final_session | final.allocation_result | session_id | Export Source Reader | K1 |
| IX_final_approved_at | final.allocation_result | approved_at | Operator session audit | Architecture |
| UQ_final_type_a_natural_key | final.allocation_result | session_id, region, gpu_pool_id, date, allocation_target (filtered: Type A) | Grain natural key uniqueness — Type A (copy fidelity from allocation_grain) | R7-W-1 |
| UQ_final_capacity_idle_natural_key | final.allocation_result | session_id, region, gpu_pool_id, date, unallocated_type (filtered: capacity_idle) | Grain natural key uniqueness — capacity_idle (copy fidelity from allocation_grain) | R7-W-1 |
| UQ_final_identity_broken_natural_key | final.allocation_result | session_id, region, gpu_pool_id, date, failed_tenant_id (filtered: identity_broken) | Grain natural key uniqueness — identity_broken (copy fidelity from allocation_grain) | R7-W-1 |
| IX_ibt_session_lookup | dbo.identity_broken_tenants | session_id | Zone 2R Risk flag lookup | P1 #32 |

---

## Deployment Prerequisites (Database Level)

| # | Scope | Action | T-SQL | Validation | Finding |
|---|---|---|---|---|---|
| 1 | Database config | Snapshot isolation | `ALTER DATABASE [gpu_margin_db] SET ALLOW_SNAPSHOT_ISOLATION ON;` | Concurrent AE + RE load test in staging — no dirty aggregation | P1 #17 |
| 2 | Index | IAM resolver composite index | `CREATE INDEX IX_iam_resolver ON raw.iam (tenant_id, billing_period) INCLUDE (contracted_rate);` | SSMS Execution Plan: INDEX SEEK (not TABLE SCAN) | P1 #8 |
| 3 | Migration | Flyway dry-run before prod deploy | `flyway validate` | CI pipeline gate — blocks deployment on failure | Architecture |
| 4 | Constraint | state_history.transition_trigger enumeration | CHK_history_trigger in Table 9 DDL | Insert non-enumerated trigger → rejected at DB write | P2 #24 |
| 5 | Constraint | state_store APPROVED atomic write | CHK_state_approved_requires_write_result in Table 8 DDL | Write APPROVED without write_result → rejected at DB write | P1 #26 |
| 6 | Column rename — breaking change | Rename state_history.trigger → transition_trigger on ALL existing environments | `EXEC sp_rename 'dbo.state_history.trigger', 'transition_trigger', 'COLUMN';` — Flyway: `V[n]__rename_state_history_trigger_column.sql` — Must run BEFORE application code referencing `transition_trigger` is deployed. Fresh installs: CREATE TABLE DDL sufficient. Existing environments: sp_rename only — never DROP/ADD (data loss). | `SELECT transition_trigger FROM dbo.state_history` succeeds. Prior audit rows accessible under new name. | C-4 |
| 7 | Column rename — breaking change | Rename state_history.timestamp → transitioned_at on ALL existing environments | `EXEC sp_rename 'dbo.state_history.timestamp', 'transitioned_at', 'COLUMN';` — Flyway: `V[n]__rename_state_history_timestamp_column.sql` — Must run BEFORE application code referencing `transitioned_at` is deployed AND before the CREATE INDEX IX_history_session_timeline migration runs. Fresh installs: CREATE TABLE DDL sufficient — column is already named transitioned_at. Existing environments: sp_rename only — never DROP/ADD (data loss on audit rows). Run after prerequisite #6 if both renames are being applied to the same environment. | `SELECT transitioned_at FROM dbo.state_history` succeeds. `CREATE INDEX IX_history_session_timeline ON dbo.state_history (session_id, transitioned_at)` succeeds without parser error. | R5-C-1 |
| 8 | Constraint — breaking change on existing envs | Add CHK_state_write_result_requires_approved to dbo.state_store | Pre-migration validation: `SELECT COUNT(*) FROM dbo.state_store WHERE write_result IS NOT NULL AND application_state <> 'APPROVED';` — MUST return 0 before proceeding. In a correctly operating system this count is always 0 (C9 is sole writer of write_result and writes it only at APPROVED). If non-zero: diagnose state machine bug before applying constraint. Migration: `ALTER TABLE dbo.state_store ADD CONSTRAINT CHK_state_write_result_requires_approved CHECK (write_result IS NULL OR application_state = 'APPROVED');` — Flyway: `V[n]__add_state_store_write_result_approved_constraint.sql`. Fresh installs: CREATE TABLE DDL sufficient. | Validation query returns 0. ALTER TABLE succeeds without error. Write ANALYZED + write_result='SUCCESS' → rejected. | R8-W-1 |
| 9 | Constraint — breaking change on existing envs | Replace CHK_recon_failing_count_nonneg + CHK_recon_failing_count_on_fail with unified CHK_recon_failing_count_semantics in dbo.reconciliation_results | Pre-migration validation: `SELECT COUNT(*) FROM dbo.reconciliation_results WHERE (verdict = 'FAIL' AND (failing_count IS NULL OR failing_count <= 0)) OR (verdict = 'PASS' AND failing_count IS NOT NULL);` — MUST return 0. Remediate any violating rows before proceeding. Migration: `ALTER TABLE dbo.reconciliation_results DROP CONSTRAINT CHK_recon_failing_count_nonneg; ALTER TABLE dbo.reconciliation_results DROP CONSTRAINT CHK_recon_failing_count_on_fail; ALTER TABLE dbo.reconciliation_results ADD CONSTRAINT CHK_recon_failing_count_semantics CHECK ((verdict = 'PASS' AND failing_count IS NULL) OR (verdict = 'FAIL' AND failing_count > 0));` — Flyway: `V[n]__replace_recon_failing_count_constraints.sql`. Fresh installs: CREATE TABLE DDL sufficient. | Validation query returns 0. All three ALTER TABLEs succeed. FAIL+NULL and FAIL+0 rejected. PASS+non-NULL rejected. | R9-W-1/R9-REC-2 |
| 10 | Constraint — breaking change on existing envs | Add CHK_recon_fail_subtype_on_check3_fail to dbo.reconciliation_results | Pre-migration validation: `SELECT COUNT(*) FROM dbo.reconciliation_results WHERE check_name = 'Computed vs Billed vs Posted' AND verdict = 'FAIL' AND fail_subtype IS NULL;` — MUST return 0. If non-zero: RE Result Writer has written Check 3 FAIL rows without fail_subtype — diagnose and remediate before applying constraint. Migration: `ALTER TABLE dbo.reconciliation_results ADD CONSTRAINT CHK_recon_fail_subtype_on_check3_fail CHECK (check_name <> 'Computed vs Billed vs Posted' OR verdict = 'PASS' OR fail_subtype IS NOT NULL);` — Flyway: `V[n]__add_recon_fail_subtype_required_constraint.sql`. Run after prerequisite #9 in same migration. Fresh installs: CREATE TABLE DDL sufficient. | Validation query returns 0. ALTER TABLE succeeds. Check 3 FAIL + NULL fail_subtype rejected. | R9-REC-1 |

---

## Cross-Module Coupling Contracts at Schema Level

A change to any field listed here requires simultaneous update of ALL listed consumers in the same Flyway migration and same application PR:

| Contract | Schema Enforcement | All Consumers |
|---|---|---|
| `billing_period = YYYY-MM` | CHK on raw.iam · raw.billing · raw.erp · allocation_grain · final.allocation_result | AE Billing Period Deriver · AE IAM Resolver · RE Check 2 · RE Check 3 |
| `session_id` FK chain | FK → raw.ingestion_log on all 12 tables | All 6 modules |
| `failed_tenant_id` pass-through | allocation_grain column · identity_broken_tenants PK | IB Builder → Calculator → Grain Writer → SET artifact → Zone 2R Risk flag |
| `unallocated_type` enum | CHK_grain_unallocated_type · CHK_final_unallocated_type | Output Verifier Check 4 · Region pills · Export |
| `APPROVED + write_result` atomic | CHK_state_approved_requires_write_result (enforces `write_result IS NOT NULL` — not `= 'SUCCESS'`). APPROVED + write_result = 'FAIL' is structurally permitted for forensic audit purposes. See DESIGN DECISION (R6-W-1) in state_store DDL. | SM C9 (sole atomic writer — writes APPROVED and write_result atomically) · Export Gate Enforcer — MUST evaluate `application_state = 'APPROVED' AND write_result = 'SUCCESS'`. Checking only application_state = 'APPROVED' opens the export gate on APPROVED + FAIL sessions and delivers an empty export to the CFO. |
| `contracted_rate = 0` zero-rate UI contract | CHK_iam_rate (>= 0) · CHK_grain_type_a_rate_required (IS NOT NULL) | UI Zone 1 · Zone 2L · Zone 2R GM% formula must guard `revenue = 0` denominator — display −100% or N/A, never divide by zero |
| `EXPORT_COLUMN_ORDER` | No column-level schema enforcement — ordering is a DDL-layer constant. Export projection is 13 grain columns only (infrastructure columns excluded): `region, gpu_pool_id, date, billing_period, allocation_target, unallocated_type, failed_tenant_id, gpu_hours, cost_per_gpu_hour, contracted_rate, revenue, cogs, gross_margin`. Infrastructure columns `id, row_id, session_id, approved_at` are NOT exported to the CFO. All four generator consumers MUST use this exact 13-column named projection in this exact order. A new grain column added to final.allocation_result requires simultaneous update of all four consumers in the same Flyway migration and application PR. A silent column-order or column-scope divergence between consumers produces an export that passes Check 3's row-count validation but delivers wrong or missing columns to the CFO. See: export-module-design.md for authoritative column list confirmation. (R5-W-1 fix · R9-REC-3 fix) |

---

*GPU Gross Margin Visibility Application · Database Schema Design · 2026-03-28*
*Revised: 2026-03-28 — Round 1 + Round 2 + Round 3 + Round 4 + Round 5 diagnostic fixes from solution-data-architecture-database.md*
*13 tables · 28 indexes (22 explicit + 6 filtered UNIQUE) · 51 CHECK constraints · 4 INSTEAD OF triggers · 1 physical FK chain · 7 coupling contracts · 10 deployment prerequisites*
*Grain: Region × GPU Pool × Day × Allocation Target · All diagnostic findings resolved · 0 open*
*Round 1: C-1 billing_period month range · C-2 contracted_rate zero-rate · C-3 grain UNIQUE (3 filtered indexes) · C-4 trigger reserved keyword*
*Round 1: W-4 fail_subtype verdict guard · W-6 retry_count ceiling · W-8 no self-transition · W-9 copy fidelity (9 constraints)*
*Round 2: C-NEW-2 Flyway sp_rename migration note · C-NEW-3 zero-rate UI contract (6th coupling contract)*
*Round 2: W-NEW-1 SYSTEM_RECOVERY self-transition permitted · W-NEW-2 reconciliation constraints combined · W-NEW-3 retry coupling documented*
*Round 2: W-7 analysis_status scope constraint · W-10 INSTEAD OF immutability trigger · W-1 ISJSON validation*
*Round 2: W-11/W-2/W-3/W-5 design decisions documented as explicit schema comments*
*Round 3: R3-C-1 kpi_cache complement tolerance (< → <=) · R3-W-1 Index Register heading (22 → 25) · R3-W-2 revenue traceability map (positive → positive or zero)*
*Round 3: R3-W-3/R3-REC-1 INSTEAD OF trigger (RAISERROR+ROLLBACK → @@TRANCOUNT guard + THROW) · R3-W-4 state_history transition direction (design decision documented)*
*Round 3 cascade: kpi_cache grain declaration corrected (four → five Zone 1 KPI values)*
*Round 4: R4-W-1 cogs positivity (CHK_grain_cogs_positive + CHK_final_cogs_positive) — closes DECIMAL rounding-to-zero trap on Type B gross_margin*
*Round 4: R4-W-2 failing_count non-negativity (CHK_recon_failing_count_nonneg) · R4-W-4 kpi_cache monetary guardrails (CHK_kpi_revenue/cogs/idle_nonneg)*
*Round 4: R4-W-3 billable_amount + amount_posted sign scope documented as DESIGN DECISION (credit memo / GL credit scope TBD by requirements)*
*Round 5: R5-C-1 state_history.timestamp → transitioned_at (reserved keyword rename — same class as C-4) — fixes Flyway CREATE INDEX parse failure*
*Round 5 R5-C-1 cascades: IX_history_session_timeline DDL · Index Register row · Deployment Prerequisite #7 (sp_rename migration)*
*Round 5: R5-W-1 EXPORT_COLUMN_ORDER added as 7th coupling contract (CSV · Excel · Power BI Generator · Output Verifier Check 3)*
*Round 5: R5-W-2 FAILED session data isolation documented as DESIGN DECISION in raw.ingestion_log (application-layer cleanup owns isolation)*
*Round 5: R5-REC-1 KPI percentage zero-denominator documented as DESIGN DECISION in kpi_cache (application-layer aggregator guard owns denominator check)*
*Round 6: R6-W-1 APPROVED+FAIL structural permission documented as DESIGN DECISION in state_store (schema permits write_result='FAIL' for forensic audit; Export Gate MUST check write_result='SUCCESS')*
*Round 6 R6-W-1 cascade: APPROVED+write_result coupling contract entry updated — Export Gate required comparison operator now explicitly specified*
*Round 6: R6-W-2 TRUNCATE TABLE bypass documented as DESIGN DECISION in final.allocation_result (DBA-class risk boundary; ALTER TABLE permission controls TRUNCATE; SQL Audit trace is correct enforcement layer)*
*Round 6: R6-REC-1 ISJSON() content contract gap documented in raw.ingestion_log (structural JSON validated; element type and null content guard owned by Component 18 Ingestion Validator)*
*Round 6: R6-REC-2 NEWID() → NEWSEQUENTIALID() on final.allocation_result.row_id — eliminates UQ_final_row_id page-split fragmentation at APPROVED write time*
*Round 7: R7-W-1 copy fidelity gap — three filtered UNIQUE indexes added to final.allocation_result (UQ_final_type_a_natural_key · UQ_final_capacity_idle_natural_key · UQ_final_identity_broken_natural_key)*
*Round 7 R7-W-1 cascades: Index Register +3 rows · frontmatter indexes 25→28 · filtered-unique-indexes 3→6 · closing tagline updated*
*Round 7: R7-REC-1 T-SQL permission syntax corrected in R6-W-2 DESIGN DECISION comment — DENY ALTER TABLE ON SCHEMA::final → DENY ALTER ON SCHEMA::final (ALTER TABLE is object-level; ALTER is schema-level permission class)*
*Round 8: R8-W-1 atomic write constraint symmetry — CHK_state_write_result_requires_approved added to state_store (write_result IS NOT NULL → application_state = 'APPROVED'; completes bidirectional invariant with CHK_state_approved_requires_write_result)*
*Round 8: R8-REC-1 failing_count non-null on FAIL verdicts — CHK_recon_failing_count_on_fail added to reconciliation_results (FAIL verdict must carry failing_count; PASS verdicts remain NULL)*
*Round 8 R8-W-1/R8-REC-1 cascades: frontmatter check-constraints 49→51 · closing tagline updated*
*Round 8: R8-W-2 Index Register heading corrected (All 25 Indexes → All 28 Indexes — heading not updated in Round 7 when 3 filtered UNIQUE indexes were added)*
*Round 8: R8-META-1 framework frontmatter updated in solution-data-architecture-database.md — 5 contracts → 7 · 2 prerequisites → 7 · Law 6 table extended with APPROVED+write_result and contracted_rate=0 zero-rate UI contracts · Law 8 extended with all 7 prerequisites*
*Round 9: R9-W-1/R9-REC-2 unified failing_count semantics — replaced CHK_recon_failing_count_nonneg (R4-W-2) + CHK_recon_failing_count_on_fail (R8-REC-1) with CHK_recon_failing_count_semantics: (PASS→NULL) OR (FAIL→>0)*
*Round 9: R9-REC-1 fail_subtype required on Check 3 FAIL — CHK_recon_fail_subtype_on_check3_fail added to reconciliation_results (operator cannot distinguish FAIL-1 vs FAIL-2 if NULL)*
*Round 9: R9-W-2 Deployment Prerequisites #8 #9 #10 added — R8-W-1 state_store constraint · R9 reconciliation_results constraint replace · R9-REC-1 fail_subtype constraint (existing env ALTER TABLE migrations with pre-validation steps)*
*Round 9 R9-W-2 cascade: frontmatter deployment-prerequisites 7→10 · closing tagline updated*
*Round 9: R9-REC-3 EXPORT_COLUMN_ORDER projection scope declared — 13 grain columns named explicitly · infrastructure columns (id, row_id, session_id, approved_at) excluded from CFO export · cross-reference to export-module-design.md*
*Round 10: R10-META-1 framework staleness — solution-data-architecture-database.md Law 8 + frontmatter updated: 7 prerequisites → 10 (prerequisites #8 #9 #10 from R9-W-2 were missing from the governing framework document)*
*Round 10: R10-META-1 cascades: framework frontmatter session-context · Law 8 heading · Law 8 body extended with prerequisite #8 (CHK_state_write_result_requires_approved) · #9 (CHK_recon_failing_count_semantics replacement) · #10 (CHK_recon_fail_subtype_on_check3_fail)*
*Round 10: R10-W-1 reconciliation_results.detail content contract — DESIGN DECISION (R10-W-1) comment added declaring C7 as sole producer · application-layer format ownership · no DB-level format enforcement by design · future structured-detail migration path documented*
*Round 10 structural counts unchanged: 13 tables · 28 indexes · 51 CHECK constraints · 7 coupling contracts · 10 deployment prerequisites (R10 fixes are documentation and framework corrections only — no new structural constraints or indexes)*
*Round 11: R11-W-1 kpi_cache immutability enforcement — TR_kpi_cache_prevent_mutation INSTEAD OF UPDATE, DELETE added (THROW 51001 · @@TRANCOUNT guard · immutability comment block added to CREATE TABLE · mirrors TR_final_allocation_result_prevent_mutation pattern)*
*Round 11: R11-W-2 identity_broken_tenants immutability enforcement — TR_identity_broken_tenants_prevent_mutation INSTEAD OF UPDATE, DELETE added (THROW 51002 · @@TRANCOUNT guard · immutability comment block added to CREATE TABLE · highest blast-radius cache table: DELETE silences CFO Risk flag with no structural signal)*
*Round 11 R11-W-1/R11-W-2 cascades: frontmatter immutability-triggers 1→3 · closing tagline 1 INSTEAD OF trigger → 3 INSTEAD OF triggers*
*Round 11: R4-W-3 escalation — DESIGN DECISION (R4-W-3) comments in raw.billing and raw.erp escalated after 7 open rounds: explicit constraint prescription (billable_amount >= 0 / amount_posted >= 0) · pre-validation query template · Round 12 resolution deadline declared · production risk acknowledged if unresolved*
*Round 12: R12-W-1 (CRITICAL) — DESIGN DECISION (R4-W-3 · ESCALATED R11 · FORMALLY ACCEPTED R12) in raw.billing and raw.erp: Round 12 deadline passed without requirements confirmation · expired deadline language removed · risk formally declared permanent production risk · resolution paths (Path A: add non-negative constraint / Path B: signed-amount handling in Check 3) preserved without deadline · joint scope requirement maintained (both fields must be resolved simultaneously)*
*Round 12 R12-W-1 cascades: structural counts unchanged — comment update only · no new constraints or indexes · resolution paths remain open pending requirements confirmation*
*Round 12: R11-REC-3 — architecture-diagram.mermaid Mode 3 consistency check (5 rounds overdue) · 4 divergences identified and resolved:*
*Round 12 R11-REC-3 D1: dbo.kpi_cache added as explicit IMMUTABLE data store node (TR_kpi_cache_prevent_mutation · THROW 51001 · R11-W-1) — was absent from diagram despite being a write-once table with INSTEAD OF trigger*
*Round 12 R11-REC-3 D2: dbo.identity_broken_tenants added as explicit IMMUTABLE data store node (TR_identity_broken_tenants_prevent_mutation · THROW 51002 · R11-W-2) — was absent from diagram despite being the highest blast-radius cache table*
*Round 12 R11-REC-3 D3: two-phase grain→cache→UI flow corrected — prior single composite edge GRAIN→UI_KPI&UI_REG&UI_CUS replaced with: (ANALYZED-time writes) GRAIN→KPI_CACHE · GRAIN→IBT; (render-time reads) KPI_CACHE→UI_KPI · GRAIN→UI_REG · GRAIN→UI_CUS (GM%) · IBT→UI_CUS (Risk flag SET lookup)*
*Round 12 R11-REC-3 D4: FAR node description updated — added 3 filtered UNIQUE grain natural key indexes (R7-W-1) and TR_final_allocation_result_prevent_mutation (THROW 51000) explicit trigger name · schema had 3 indexes on final.allocation_result since Round 7; diagram reflected none of these*
*Round 13: R13-W-1 (WARNING) — DESIGN DECISION (R13-W-1) comment added to dbo.allocation_grain after CREATE TABLE closing paren · declares intentional divergence from the three write-once cache table trigger pattern · documents structural constraint preventing INSTEAD OF DELETE (Ingestion Commit STEP 1 requires DELETE of prior active session rows for session replacement — trigger would block this) · documents application-layer argument against INSTEAD OF UPDATE (AE Writer is INSERT-only; no application component has a legitimate UPDATE path; UPDATE-only trigger deferred pending component owner confirmation) · declares accepted risk (ORM misfire or DBA UPDATE silently corrupts four consumers: RE Check 3 verdict · Zone 1 KPI cache · Zone 2L/2R UI display · SM final copy to final.allocation_result) · specifies role-based access control + SQL Server Audit trace as the primary protection and detection layers*
*Round 13 R13-W-1 cascades: structural counts unchanged — comment-only fix · no new triggers, constraints, or indexes · immutability-triggers remains 3 (allocation_grain intentionally excluded as documented)*
*Round 14: R14-REC-1 (pre-condition) — INSTEAD OF Trigger Error Number Registry section added after Schema Namespaces · declares all four claimed THROW numbers (51000–51003) with trigger name, table, and round added · establishes next available number (51004) · prevents future number collision across all triggers in this schema*
*Round 14: R14-W-1 (WARNING) — TR_allocation_grain_prevent_update INSTEAD OF UPDATE trigger added to dbo.allocation_grain (THROW 51003 · @@TRANCOUNT guard · INSTEAD OF UPDATE only — DELETE intentionally excluded per Ingestion Commit structural constraint) · closes UPDATE blast radius on four consumers: RE Check 3 verdict · Zone 1 KPI cache · Zone 2L/2R UI display · SM final copy to final.allocation_result · no application component has a legitimate UPDATE path — trigger adds zero friction to any correct code path*
*Round 14 R14-W-1 cascades: frontmatter immutability-triggers 3→4 · closing tagline 3→4 INSTEAD OF triggers · DESIGN DECISION comment updated (R13-W-1 → R13-W-1·UPDATED R14-W-1) — UPDATE section changed from "deferred pending confirmation" to "now enforced at DB level" · accepted risk narrowed from UPDATE+DELETE to individual row DELETE only (INSTEAD OF DELETE remains blocked by Ingestion Commit architectural constraint — session replacement requires DELETE of prior active session rows)*
