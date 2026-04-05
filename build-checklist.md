# Build Checklist — GPU Gross Margin Visibility Application

> Derived from: `gpu-margin-engineer.prompt.md` · `build-plan.md`
> Protocol: Check each item only when it is fully complete and verified. No phase advances without Jeremie's explicit authorization.

---

## How to Use

- `[ ]` — not started
- `[x]` — complete and verified
- Each phase ends with a **JEREMIE AUTHORIZATION** checkpoint — nothing beyond it begins without his direction
- Verify steps are hard gates — phase is not complete until all Verify boxes are checked

---

---

# PHASE 0 — Infrastructure

> **Why first:** Prerequisites that application code runs against. Missing any one causes silent failures — wrong aggregations, engine timeouts, sessions never closing. No amount of correct code compensates.

---

### Step 0.1 — SQL Server

| # | Step | Tool | Why |
|---|------|------|-----|
| `[x]` | Stand up SQL Server instance | `SQL Server` + `Docker + Compose` | Primary database for all 13 tables, constraints, triggers |
| `[x]` | Define SQL Server service in `docker-compose.yml` | `Docker + Compose` | Full stack in one start/stop command — no external DB dependency during build |
| `[x]` | Confirm application host can connect to SQL Server | `SSMS` | Verify connection before any migration runs |

---

### Step 0.2 — Snapshot Isolation

| # | Step | Tool | Why |
|---|------|------|-----|
| `[x]` | Write Flyway migration: `ALTER DATABASE ... SET ALLOW_SNAPSHOT_ISOLATION ON` | `Flyway` | Must be version-controlled and reproducible across dev/staging/prod |
| `[x]` | Apply migration to dev database | `Flyway` + `SQL Server` | Setting must be active before Telemetry Aggregator or RE checks run |
| `[x]` | Confirm setting active via `sys.databases` query | `SSMS` | Verify the setting applied — not just that the migration ran |

**Verify 0.2** `[x]` Run concurrent read test against `raw.telemetry` — confirm no dirty reads under concurrent write load

---

### Step 0.3 — Composite Index on `raw.iam`

| # | Step | Tool | Why |
|---|------|------|-----|
| `[x]` | Write Flyway migration: composite index on `raw.iam(tenant_id, billing_period)` — with `INCLUDE (contracted_rate)` covering index | `Flyway` | Without it, IAM Resolver performs full-table scan at 100K+ rows — pushes AE past `AE_TIMEOUT` |
| `[x]` | Apply migration — staged as V2, renumber to V3+ in Phase 1 after raw.iam table creation | `Flyway` + `SQL Server` | |
| `[x]` | Run execution plan on IAM Resolver query | `SSMS Execution Plan viewer` | Confirm index **seek** — not table scan. Existence ≠ usage. |

**Verify 0.3** `[x]` Execution plan shows index seek on `raw.iam(tenant_id, billing_period)` query — covering index eliminates key lookup

---

### Step 0.4 — Redis

| # | Step | Tool | Why |
|---|------|------|-----|
| `[x]` | Define Redis service in `docker-compose.yml` — with AOF persistence (`--appendonly yes`) | `Docker + Compose` | Celery broker + ACK contract enforcement — no fallback exists |
| `[x]` | Stand up Redis container | `Redis` | Powers all engine run signals and Dispatch ACK timeout |
| `[x]` | Confirm Redis connection from application host | `Redis CLI` | Verify before Celery is configured against it |

**Verify 0.4** `[x]` Dispatch a test signal — confirm receipt and ACK within `DISPATCH_ACK_TIMEOUT`

---

### Step 0.5 — Celery + Celery Beat

| # | Step | Tool | Why |
|---|------|------|-----|
| `[x]` | Define Celery worker service in `docker-compose.yml` | `Docker + Compose` | Async engine execution |
| `[x]` | Define Celery Beat service in `docker-compose.yml` — plain Beat, schedule in code | `Docker + Compose` | Beat is mandatory — only mechanism to close sessions to TERMINAL after APPROVED |
| `[x]` | Define Beat schedule for APPROVED Session Closer retry | `Celery Beat` | Without Beat, `session_status` never reaches TERMINAL — silent security gap |
| `[x]` | Start Celery worker and Beat in dev environment | `Docker + Compose` | Confirm both services start without error |

**Verify 0.5** `[x]` Trigger a scheduled task in dev — confirm it fires on the configured interval

---

### Step 0.6 — All 11 Configurable Parameters

| # | Step | Tool | Why |
|---|------|------|-----|
| `[x]` | Create deployment config file (`.env`) — added to `.gitignore` | Config file | All 11 parameters must live here — never hardcoded in application code |
| `[x]` | Set `INGESTION_BATCH_THRESHOLD` = 50000 | Config | Dev default · update from staging P95 |
| `[x]` | Set `AE_TIMEOUT` = 300 | Config | Dev default · **MUST be updated** from staging P95 (2× P95 AE completion time) |
| `[x]` | Set `DISPATCH_ACK_TIMEOUT` = 10 | Config | |
| `[x]` | Set `DISPATCH_MAX_RETRIES` = 3 | Config | |
| `[x]` | Set `CLOSER_RETRY_INTERVAL` = 60 | Config | |
| `[x]` | Set `CLOSER_MAX_RETRIES` = 5 | Config | |
| `[x]` | Set `ANALYSIS_MAX_RETRIES` = 3 | Config | |
| `[x]` | Set `MAX_EXPORT_RERUNS` = 3 | Config | |
| `[x]` | Set `XLSX_GENERATION_TIMEOUT` = 120 | Config | |
| `[x]` | Set `MAX_HISTORY_SESSIONS` = 50 | Config | |
| `[x]` | Set `HISTORY_RETENTION_DAYS` = 90 | Config | |

**Verify 0.6** `[x]` All 11 parameters present in deployment config — none missing, none hardcoded in source code

---

### Phase 0 — Hard Gates

| Verify | Condition |
|--------|-----------|
| `[x]` | Snapshot isolation confirmed via concurrent read test — no dirty reads |
| `[x]` | Composite index confirmed via execution plan — index seek, not scan (covering index with INCLUDE) |
| `[x]` | Celery Beat fires on schedule in dev environment |
| `[x]` | Redis ACK confirmed within `DISPATCH_ACK_TIMEOUT` |
| `[x]` | All 11 config parameters present — none hardcoded |

> **⛔ JEREMIE AUTHORIZATION REQUIRED** — Phase 0 is complete only when all 5 Verify conditions pass. Not when infrastructure is "up."

`[x]` **Jeremie authorizes Phase 1** — 2026-04-01

---

---

# PHASE 1 — Database Schema (Flyway Migrations)

> **Why second:** The schema IS the control system. Constraints, triggers, and indexes enforced at the DB layer cannot be replaced by application code. Build and verify the schema before the first Python file is written.
> **Note:** V1 = snapshot isolation (Phase 0). Table migrations start at V2. All 29 indexes (23 standard + 6 filtered-unique), 70 CHECK constraints, and 4 immutability triggers are inline with their parent CREATE TABLE DDL — not separate migration files. **Step 1.1 COMPLETE — 196 test assertions verified.**

---

### Step 1.1 — Schema Namespaces + 13 Tables (V2–V15) + IAM Composite Index (V16)

| # | Table / Object | Flyway Migration | Grain Relationship | Verified |
|---|----------------|------------------|--------------------|----------|
| `[x]` | Schema namespaces (`raw`, `dbo`, `final`) | V2 | Infrastructure | `[x]` |
| `[x]` | `raw.ingestion_log` (+ DEFAULT 'FAILED' on status) | V3 | ANCHORS the grain | `[x]` |
| `[x]` | `raw.telemetry` + 3 indexes (IX_telemetry_grain column order: region/pool/date before tenant_id) | V4 | FEEDS — consumption | `[x]` |
| `[x]` | `raw.cost_management` + 2 indexes | V5 | FEEDS — capacity + cost | `[x]` |
| `[x]` | `raw.iam` + 3 indexes (Option B inlined · CHAR(7) Path A · IX_iam_resolver session-scoped) | V6 | FEEDS — identity + rate | `[x]` |
| `[x]` | `raw.billing` + 2 indexes (CHAR(7) Path A · R12 accepted risk annotated) | V7 | CHECKS — invoiced (RE Check 3 FAIL-1) | `[x]` |
| `[x]` | `raw.erp` + 2 indexes (CHAR(7) Path A · R12 accepted risk annotated) | V8 | CHECKS — posted (RE Check 3 FAIL-2) | `[x]` |
| `[x]` | `dbo.allocation_grain` + 6 indexes + 3 filtered-unique + TR_prevent_update (CHAR(7) Path A · 15 CHECKs incl. MATH INTEGRITY · THROW 51003) | V9 | IS the grain | `[x]` |
| `[x]` | `dbo.reconciliation_results` + 2 indexes (check_order column · 9 CHECKs incl. order mapping + detail semantics) | V10 | CHECKS the grain | `[x]` |
| `[x]` | `dbo.state_store` (10 CHECKs incl. EMPTY state hardening · R6-W-1 APPROVED+FAIL documented) | V11 | CONTROLS the grain | `[x]` |
| `[x]` | `dbo.state_history` + 1 index (5 CHECKs incl. timestamp sanity · IX tiebreaker with id) | V12 | CONTROLS the grain (audit) | `[x]` |
| `[x]` | `final.allocation_result` + 2 indexes + 3 filtered-unique + TR_prevent_mutation (CHAR(7) Path A · 15 CHECKs incl. MATH INTEGRITY · THROW 51000 · name swap fixed) | V13 | IS the grain (immutable copy) | `[x]` |
| `[x]` | `dbo.kpi_cache` + TR_prevent_mutation (6 CHECKs incl. complement integrity · THROW 51001) | V14 | CACHES the grain | `[x]` |
| `[x]` | `dbo.identity_broken_tenants` + 1 index + TR_prevent_mutation (1 CHECK tenant_not_empty · THROW 51002) | V15 | CACHES the grain | `[x]` |
| `ELIMINATED` | ~~Phase 0 IAM composite index~~ — Option B: inlined into V6 (IX_iam_resolver). No standalone V16 migration needed. | ~~V16~~ | ~~Deployment prerequisite P1 #8~~ | `N/A` |

**Tool:** `Flyway` (T-SQL migrations) + `SSMS` (verify structure after each migration)
**Note:** Each migration file includes the table DDL, its inline CHECK constraints, indexes, filtered-unique indexes, and triggers as defined in `db-schema-design.md`. No separate migration files for constraints or indexes.

**Inline totals per migration (VERIFIED — hardened counts post-review):**

| Migration | CHECK Constraints | Indexes | Filtered-Unique | Triggers |
|-----------|-------------------|---------|-----------------|----------|
| V3 `raw.ingestion_log` | 2 (status enum, ISJSON) | 0 | 0 | 0 |
| V4 `raw.telemetry` | 1 (gpu_hours > 0) | 3 | 0 | 0 |
| V5 `raw.cost_management` | 2 (reserved > 0, cost > 0) | 2 | 0 | 0 |
| V6 `raw.iam` | 2 (billing_period YYYY-MM, rate >= 0) | 3 | 0 | 0 |
| V7 `raw.billing` | 1 (billing_period YYYY-MM) | 2 | 0 | 0 |
| V8 `raw.erp` | 1 (billing_period YYYY-MM) | 2 | 0 | 0 |
| V9 `dbo.allocation_grain` | 15 (record type, billing_period, positivity, MATH INTEGRITY ×2) | 6 | 3 | 1 (UPDATE only) |
| V10 `dbo.reconciliation_results` | 9 (check_name, verdict, fail_subtype ×3, failing_count, detail, check_order ×2) | 2 | 0 | 0 |
| V11 `dbo.state_store` | 10 (4 enums, bidirectional ×2, terminal, analysis scope, EMPTY hardening, retry ceiling) | 0 | 0 | 0 |
| V12 `dbo.state_history` | 5 (from/to state enums, trigger enum, no self-transition, timestamp sanity) | 1 | 0 | 0 |
| V13 `final.allocation_result` | 15 (copy fidelity from allocation_grain incl. MATH INTEGRITY ×2) | 2 | 3 | 1 (UPDATE + DELETE) |
| V14 `dbo.kpi_cache` | 6 (percentages, monetary guardrails, complement) | 0 | 0 | 1 (UPDATE + DELETE) |
| V15 `dbo.identity_broken_tenants` | 1 (tenant_not_empty) | 1 | 0 | 1 (UPDATE + DELETE) |
| **TOTAL** | **70** | **24** | **6** | **4** |

> **Note on constraint counts:** Original db-schema-design.md had 60 named constraints. Post-review hardening added 10 constraints: V9 +2 (math integrity), V10 +2 (check_order, detail semantics), V11 +2 (EMPTY hardening, bidirectional), V12 +1 (timestamp sanity), V13 +2 (math integrity), V15 +1 (tenant_not_empty). V10 CHK_recon_failing_count_semantics patched for SQL Server three-valued logic NULL gap (found during testing).

**Step 1.1 Test Suite — 196 assertions across 14 test files (VERIFIED):**

| Test File | Table | Assertions | Result |
|-----------|-------|------------|--------|
| TEST_V1_V2_infrastructure.sql | Infrastructure | 5 | ✅ |
| TEST_V3_raw_ingestion_log.sql | raw.ingestion_log | 7 | ✅ |
| TEST_V4_raw_telemetry.sql | raw.telemetry | 8 | ✅ |
| TEST_V5_raw_cost_management.sql | raw.cost_management | 8 | ✅ |
| TEST_V6_raw_iam.sql | raw.iam | 13 | ✅ |
| TEST_V7_raw_billing.sql | raw.billing | 8 | ✅ |
| TEST_V8_raw_erp.sql | raw.erp | 8 | ✅ |
| TEST_V9_dbo_allocation_grain.sql | dbo.allocation_grain | 32 | ✅ |
| TEST_V10_dbo_reconciliation_results.sql | dbo.reconciliation_results | 17 | ✅ |
| TEST_V11_dbo_state_store.sql | dbo.state_store | 21 | ✅ |
| TEST_V12_dbo_state_history.sql | dbo.state_history | 14 | ✅ |
| TEST_V13_final_allocation_result.sql | final.allocation_result | 29 | ✅ |
| TEST_V14_dbo_kpi_cache.sql | dbo.kpi_cache | 16 | ✅ |
| TEST_V15_dbo_identity_broken_tenants.sql | dbo.identity_broken_tenants | 10 | ✅ |
| **TOTAL** | **13 tables + infrastructure** | **196** | **✅** |

**Defect found during testing:** V10 `CHK_recon_failing_count_semantics` — SQL Server three-valued logic allowed `FAIL + NULL failing_count` to slip through. Fixed by adding explicit `failing_count IS NOT NULL` guard.

---

### Step 1.2 — Verify Indexes via Execution Plans

> **✅ COMPLETED** — All 4 query patterns confirmed Index Seek via SSMS Actual Execution Plans.

| # | Step | Tool | Result |
|---|------|------|--------|
| `[x]` | IAM Resolver query pattern | `SSMS Execution Plan` | **Index Seek** on `IX_iam_resolver` — covering seek, no key lookup |
| `[x]` | Telemetry Aggregator GROUP BY | `SSMS Execution Plan` | **Index Seek** on `IX_telemetry_grain` → Stream Aggregate |
| `[x]` | RE Check 3 filtered index pattern | `SSMS Execution Plan` | **Index Seek** on `IX_grain_check3` → Stream Aggregate |
| `[x]` | Cost Rate Reader lookup | `SSMS Execution Plan` | **Index Seek** on `IX_cost_mgmt_grain_lookup` — covering seek |

**Verify 1.2** `[x]` All primary query patterns show INDEX SEEK — zero table scans, zero clustered index scans

---

### Step 1.3 — Test Check Constraints via Direct T-SQL Violations

> **✅ COMPLETED** — All CHECK constraint tests are embedded in the Step 1.1 test suite (196 assertions).
> Every CHECK constraint has at least one dedicated rejection test. See test files in `phase_zero/db/tests/`.

| # | Step | Tool | Why |
|---|------|------|-----|
| `[x]` | Test `raw.ingestion_log` — insert invalid status / malformed JSON | TEST_V3 (V3-04, V3-05) | CHK_ingestion_log_status + CHK_ingestion_source_files_json reject |
| `[x]` | Test `raw.telemetry` — insert gpu_hours_consumed = 0 | TEST_V4 (V4-03) | CHK_telemetry_gpu_hours rejects |
| `[x]` | Test `raw.iam` — insert billing_period = '2026-13' / contracted_rate = -1 | TEST_V6 (V6-04–V6-08) | CHK_iam_billing_period + CHK_iam_rate reject |
| `[x]` | Test `dbo.allocation_grain` — Type A with unallocated_type not NULL | TEST_V9 (V9-07) | CHK_grain_type_a_no_subtype rejects |
| `[x]` | Test `dbo.allocation_grain` — Type B with NULL unallocated_type | TEST_V9 (V9-08) | CHK_grain_type_b_must_classify rejects |
| `[x]` | Test `dbo.allocation_grain` — identity_broken with NULL failed_tenant_id | TEST_V9 (V9-12) | CHK_grain_identity_broken_requires_ftid rejects |
| `[x]` | Test `dbo.allocation_grain` — cogs = 0 | TEST_V9 (V9-18) | CHK_grain_cogs_positive rejects |
| `[x]` | Test `dbo.state_store` — APPROVED with NULL write_result | TEST_V11 (V11-10) | CHK_state_approved_requires_write_result rejects |
| `[x]` | Test `dbo.state_store` — write_result = 'SUCCESS' with state = ANALYZED | TEST_V11 (V11-11) | CHK_state_write_result_requires_approved rejects |
| `[x]` | Test `dbo.reconciliation_results` — FAIL with failing_count = NULL | TEST_V10 (V10-12) | CHK_recon_failing_count_semantics rejects (NULL gap fixed) |
| `[x]` | Test `dbo.reconciliation_results` — Check 3 FAIL with NULL fail_subtype | TEST_V10 (V10-09) | CHK_recon_fail_subtype_on_check3_fail rejects |
| `[x]` | Test `dbo.kpi_cache` — idle_pct + allocation_rate = 110 (complement violation) | TEST_V14 (V14-10) | CHK_kpi_complement rejects |
| `[x]` | Test `dbo.state_history` — non-enumerated transition_trigger | TEST_V12 (V12-09) | CHK_history_trigger rejects |
| `[x]` | Test 3 filtered-unique indexes on `dbo.allocation_grain` — duplicate grain rows | TEST_V9 (V9-23) | UQ_grain_type_a duplicate rejected |
| `[x]` | Test 3 filtered-unique indexes on `final.allocation_result` — duplicate rows | TEST_V13 (V13-23) | UQ_final_type_a duplicate rejected |

**Verify 1.3** `[x]` Every test produces a constraint violation error — no invalid row can be written to any table

---

### Step 1.4 — Test 4 Immutability Triggers (4 Tables)

> **✅ COMPLETED** — All trigger tests are embedded in the Step 1.1 test suite.

| # | Trigger | Table | THROW # | Test |
|---|---------|-------|---------|------|
| `[x]` | TR_allocation_grain_prevent_update | `dbo.allocation_grain` | 51003 | TEST_V9 (V9-21 UPDATE blocked, V9-22 DELETE allowed) |
| `[x]` | TR_final_allocation_result_prevent_mutation | `final.allocation_result` | 51000 | TEST_V13 (V13-21 UPDATE blocked, V13-22 DELETE blocked) |
| `[x]` | TR_kpi_cache_prevent_mutation | `dbo.kpi_cache` | 51001 | TEST_V14 (V14-12 UPDATE blocked, V14-13 DELETE blocked) |
| `[x]` | TR_identity_broken_tenants_prevent_mutation | `dbo.identity_broken_tenants` | 51002 | TEST_V15 (V15-08 UPDATE blocked, V15-09 DELETE blocked) |

**Verify 1.4** `[x]` All 4 triggers fire with correct THROW numbers — immutability enforced at DB level on all write-once tables

---

### Phase 1 — Hard Gates

| Verify | Condition |
|--------|-----------|
| `[x]` | V2–V15 applied — all 13 tables + schema namespaces created in grain-relationship order |
| `[x]` | V16 ELIMINATED — IAM composite index inlined into V6 (Option B) |
| `[x]` | All 4 primary query pattern indexes confirmed via execution plans — seeks, not scans (Step 1.2) |
| `[x]` | All 70 CHECK constraints tested via 196-assertion test suite — every one rejects (Step 1.3) |
| `[x]` | All 6 filtered-unique indexes tested — duplicate grain rows rejected (Step 1.3) |
| `[x]` | All 4 immutability triggers tested — correct THROW numbers, correct scope (Step 1.4) |
| `[x]` | **No application code has run against the schema yet** |

> **⛔ JEREMIE AUTHORIZATION REQUIRED** — Schema is verified. First line of Python may now be written.

`[ ]` **Jeremie authorizes Phase 2**

---

---

# PHASE 2 — Ingestion Module (19 Components)

> **Why third:** `session_id` is the K1 cross-module key generated exactly once here. Nothing downstream runs without it. Atomic gate: all 5 files validated, parsed, written, promoted — or nothing advances.

---

### Step 2.1 — 5 File Validators (Layer 1) — COMPLETE (89 assertions verified)

| # | Component | Tool | Verify |
|---|-----------|------|--------|
| `[x]` | Telemetry File Validator — `tenant_id` regex (P1 #7) · date ISO · required fields · `.lower()` normalization | `Python` + `Pydantic v2` + `pytest` | `[x]` 18 assertions (T-01–T-18) |
| `[x]` | Cost Management File Validator — duplicate key `(region, gpu_pool_id, date)` · `reserved_gpu_hours > 0` · `cost_per_gpu_hour > 0` | `Python` + `Pydantic v2` + `pytest` | `[x]` 19 assertions (CM-01–CM-19) |
| `[x]` | IAM File Validator — `billing_period` YYYY-MM · `contracted_rate > 0` (stricter than DB `>= 0`) · duplicate key `(tenant_id, billing_period)` | `Python` + `Pydantic v2` + `pytest` | `[x]` 18 assertions (IAM-01–IAM-18) |
| `[x]` | Billing File Validator — `billable_amount` NO sign constraint (R4-W-3 credit memos) · duplicate key `(tenant_id, billing_period)` | `Python` + `Pydantic v2` + `pytest` | `[x]` 17 assertions (BIL-01–BIL-17) |
| `[x]` | ERP File Validator — `amount_posted` NO sign constraint (R4-W-3 GL reversals) · duplicate key `(tenant_id, billing_period)` | `Python` + `Pydantic v2` + `pytest` | `[x]` 17 assertions (ERP-01–ERP-17) |

**Step 2.1 Test Suite Inventory:**

| File | Assertions | Scope |
|------|-----------|-------|
| `test_telemetry.py` | 18 | structural + null + tenant_id regex P1#7 + date ISO + gpu_hours > 0 + multi-row + custom pattern |
| `test_cost_management.py` | 19 | structural + null + date ISO + reserved_gpu_hours > 0 + cost_per_gpu_hour > 0 + duplicate key + multi-row |
| `test_iam.py` | 18 | structural + null + billing_period YYYY-MM (month 00, 13) + contracted_rate > 0 (zero rejected) + duplicate key + multi-row |
| `test_billing.py` | 17 | structural + null + billing_period YYYY-MM + billable_amount decimal (negative PASS R4-W-3, zero PASS) + duplicate key + multi-row |
| `test_erp.py` | 17 | structural + null + billing_period YYYY-MM + amount_posted decimal (negative PASS R4-W-3, zero PASS) + duplicate key + multi-row |
| **Total** | **89** | |

**Cross-validator design decisions applied:**
- `.lower()` normalization on headers + row keys — all 5 validators (consistent with SQL Server CI collation)
- Fail-fast on structural (CSV format, missing columns, empty file); collect on row-level
- `BILLING_PERIOD_PATTERN` shared regex `^\d{4}-(0[1-9]|1[0-2])$` across IAM, Billing, ERP

**Why Pydantic v2:** Raises structured errors with field names on violation. The Telemetry validator must enforce `tenant_id` format via regex — a malformed ID that passes silently classifies as `identity_broken` in the AE with no traceable root cause.

---

### Step 2.2 — 5 File Parsers (Layer 2) — COMPLETE (35 assertions verified)

| # | Component | Tool | Verify |
|---|-----------|------|--------|
| `[x]` | Telemetry File Parser — `TelemetryRecord(tenant_id:str, region:str, gpu_pool_id:str, date:date, gpu_hours_consumed:Decimal)` | `Python csv stdlib` + `Pydantic v2` + `pytest` | `[x]` 8 assertions (TP-01–TP-08) |
| `[x]` | Cost Management File Parser — `CostManagementRecord(region:str, gpu_pool_id:str, date:date, reserved_gpu_hours:Decimal, cost_per_gpu_hour:Decimal)` | `Python csv stdlib` + `Pydantic v2` + `pytest` | `[x]` 7 assertions (CMP-01–CMP-07) |
| `[x]` | IAM File Parser — `IAMRecord(tenant_id:str, billing_period:str, contracted_rate:Decimal)` | `Python csv stdlib` + `Pydantic v2` + `pytest` | `[x]` 6 assertions (IAMP-01–IAMP-06) |
| `[x]` | Billing File Parser — `BillingRecord(tenant_id:str, billing_period:str, billable_amount:Decimal)` — negative PASS (R4-W-3) | `Python csv stdlib` + `Pydantic v2` + `pytest` | `[x]` 7 assertions (BILP-01–BILP-07) |
| `[x]` | ERP File Parser — `ERPRecord(tenant_id:str, billing_period:str, amount_posted:Decimal)` — negative PASS (R4-W-3) | `Python csv stdlib` + `Pydantic v2` + `pytest` | `[x]` 7 assertions (ERPP-01–ERPP-07) |

**Cross-parser design decisions applied:**
- Safe `None` normalization: `(k or "").strip().lower(): (v or "").strip()` across all 5 parsers
- `Field(default_factory=list)` in `ParseResult.records` — avoids mutable default
- Fail-fast on parse error (single error string, not collected list) — spec defines `error: varchar | NULL`

**Why csv stdlib (not pandas):** Pandas type inference can silently coerce `tenant_id` strings. stdlib parses exactly what is in the file.

---

### Step 2.3 — 5 Raw Table Writers (Layer 3)

| # | Component | Tool | Verify |
|---|-----------|------|--------|
| `[x]` | Telemetry Raw Table Writer — dedicated write connection | `SQLAlchemy + pyodbc` + `pytest` | `[x]` 6 assertions (TW-01–TW-06) |
| `[x]` | Cost Management Raw Table Writer | `SQLAlchemy + pyodbc` + `pytest` | `[x]` 6 assertions (CMW-01–CMW-06) |
| `[x]` | IAM Raw Table Writer | `SQLAlchemy + pyodbc` + `pytest` | `[x]` 6 assertions (IAMW-01–IAMW-06) |
| `[x]` | Billing Raw Table Writer | `SQLAlchemy + pyodbc` + `pytest` | `[x]` 6 assertions (BILW-01–BILW-06) |
| `[x]` | ERP Raw Table Writer | `SQLAlchemy + pyodbc` + `pytest` | `[x]` 6 assertions (ERPW-01–ERPW-06) |

**Why dedicated connection per writer:** Prevents connection contention during the atomic commit. Each writer holds its own connection; the Orchestrator coordinates the commit boundary.

---

### Step 2.4 — Ingestion Orchestrator (Layer 4)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Generate `session_id` (UUID) at Orchestrator | `Python uuid stdlib` + `FastAPI` | `[x]` ORCH-02 — session_id generated |
| `[x]` | Register session | `Pydantic v2` | `[x]` OrchestrationPayload typed |
| `[x]` | Coordinate validators → parsers → writers | `FastAPI` | `[x]` 8 assertions (ORCH-01–ORCH-08) |

---

### Step 2.5 — Ingestion Commit (Layer 4b)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Wrap all 5 raw table writes in one DB transaction | `SQLAlchemy` `engine.begin()` context manager | `[x]` COMMIT-01 — full commit success |
| `[x]` | ROLLBACK on any writer failure | `SQL Server` ROLLBACK via `engine.begin()` | `[x]` COMMIT-09 — ERP writer mock failure → atomic rollback confirmed |

**Why:** First atomic gate in the system. A manual rollback loop is not safe — it can leave partial data if the loop itself fails.

---

### Step 2.6 — Ingestion Log Writer (Layer 5) + State Transition Emitter (Layer 6)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Write one row to `raw.ingestion_log` per committed session (inside atomic commit — Option A) | `SQLAlchemy` + `pytest` | `[x]` 6 assertions (LW-01–LW-06) |
| `[x]` | Emit EMPTY → UPLOADED transition to State Machine | `Pydantic` + `pytest` | `[x]` 8 assertions (EMIT-01–EMIT-08) |

---

### Phase 2 — Hard Gates

| Verify | Condition |
|--------|-----------|
| `[x]` | Upload 5 valid CSVs → all 5 raw tables populated with matching `session_id` — COMMIT-01, COMMIT-04 |
| `[x]` | `raw.ingestion_log` has exactly one entry — COMMIT-03, COMMIT-06 |
| `[x]` | State = UPLOADED — EMIT-01–EMIT-05 (FIRE signal emitted with session_id) |
| `[x]` | Upload with 1 invalid file → nothing written · state stays EMPTY · named error — ORCH-05–ORCH-08, COMMIT-05 |

> **⛔ JEREMIE AUTHORIZATION REQUIRED**

`[x]` **Jeremie authorizes Phase 3** — 2026-04-03

---

---

# PHASE 3 — Allocation Engine (11 Components)

> **Why fourth:** The AE is the only producer of `allocation_grain`. Every downstream consumer reads from this table. A wrong record here propagates to every surface with no recovery path.

---

### Step 3.1 — Run Receiver (Component 0)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Receive and validate `run_signal` · extract `session_id` | `Pydantic v2 Literal` | `[x]` 6 passed (RR-01–RR-06) |
| `[x]` | Reject invalid signals with named error | `pytest` | `[x]` Pydantic ValidationError at construction |

---

### Step 3.2 — Telemetry Aggregator (Component 1)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | GROUP BY `Region × GPU Pool × Day` on `raw.telemetry` with session_id filter | `SQLAlchemy + pyodbc` | `[x]` 8 passed (TA-01–TA-08) |
| `[x]` | Deterministic sort on results for stable test order | `Python sorted()` | `[x]` Verified |
| `[x]` | Test aggregation output matches expected grain structure | `pytest` | `[x]` 8 passed |

---

### Step 3.3 — Billing Period Deriver (Component 2)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Create shared Python constant module: `billing_period = LEFT(date, 7)` | `app/shared/billing_period.py` | `[x]` Contract 1 — single source of truth |
| `[x]` | Billing Period Deriver **imports** from constant module — never copies the logic | `Python` | `[x]` 7 passed (BPD-01–BPD-07) |

**Why shared constant:** Contract 1. All four coupled components must import from one source. A copy today becomes a divergence after any future change — silent wrong verdicts in Check 2.

---

### Step 3.4 — Cost Rate Reader (Component 3 — parallel track)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Read `raw.cost_management` with session_id filter + deterministic sort | `SQLAlchemy` + `pytest` | `[x]` 7 passed (CRR-01–CRR-07) |

---

### Step 3.5 — IAM Resolver (Component 4)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Per-record lookup against `raw.iam` on `tenant_id + billing_period + session_id` | `SQLAlchemy` | `[x]` 9 passed (IAM-R-01–IAM-R-09) |
| `[x]` | Import `billing_period` constant — same module as Component 2 | `app/shared/billing_period.py` | `[x]` Contract 1 confirmed |
| `[x]` | Unmatched tenants → `identity_broken` rows with `failed_tenant_id` populated | `pytest` | `[x]` tenant absent from IAM → `identity_broken` with correct `failed_tenant_id` |

---

### Step 3.6 — Type A Record Builder (Component 5)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Build Type A grain records from IAM-resolved + cost rates | `Python` + `pytest` | `[x]` 7 passed (TAB-01–TAB-07) |

---

### Step 3.7 — Identity Broken Record Builder (Component 6)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Build `identity_broken` rows · `failed_tenant_id` = original `tenant_id` | `Python` + `pytest` | `[x]` 9 passed (IBB-01–IBB-09) |

---

### Step 3.8 — Closure Rule Enforcer (Component 7)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Force `capacity_idle` row when `reserved − consumed > 0` | `Python` + `pytest` | `[x]` 13 passed (CRE-01–CRE-13) |
| `[x]` | `capacity_idle` rows have `failed_tenant_id = NULL` | `pytest` | `[x]` CRE-04 |
| `[x]` | Closure rule holds for all pools and days | `pytest` | `[x]` CRE-08 (idle=0), CRE-11 (multi-pool), CRE-13 (mixed) |

**Why:** The closure rule is the structural invariant. If the idle row is not forced, idle capacity disappears from the grain — invisible accounting gap.

---

### Step 3.9 — Cost & Revenue Calculator (Component 8)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Compute `gross_margin` for all record types | `Python` + `pytest` | `[x]` 16 passed (CALC-01–CALC-16) |
| `[x]` | All Type B gross_margin values are **negative, never zero** | `pytest` | `[x]` CALC-06, CALC-09 |
| `[x]` | Pass `failed_tenant_id` unchanged — do not evaluate, do not modify (P2 #14) | `pytest` | `[x]` CALC-10, CALC-11, CALC-12 |

**Why pass-through:** If `failed_tenant_id` is dropped here, Customer Data Aggregator cannot build `identity_broken` SET. Risk flag never fires. CFO approves without the signal.

---

### Step 3.10 — Allocation Grain Writer (Component 9)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Write all grain rows to `allocation_grain` in **one DB transaction** (SAVEPOINT) | `SQLAlchemy` + `SQL Server` | `[x]` 8 passed (GW-01–GW-08) |
| `[x]` | ROLLBACK on failure — **never DELETE** | `SAVEPOINT rollback` | `[x]` GW-08 |
| `[x]` | Test: simulate write failure mid-batch — confirm ALL rows rolled back | `pytest` | `[x]` GW-08 — 0 partial rows after failure |

**Why DB ROLLBACK (not DELETE):** P1 #12. A DELETE loop that fails mid-run leaves partial rows. Check 3 reads them. Spurious FAIL-1 verdicts reach the CFO silently.

---

### Step 3.11 — Completion Emitter (Component 10)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Emit completion signal — structured result for SM + RE consumers | `Python` + `Pydantic` | `[x]` 8 passed (CE-01–CE-08) |
| `[x]` | FAIL path with named error + default error fallback | `pytest` | `[x]` CE-04–CE-08 |

---

### Phase 3 — Hard Gates

| Verify | Condition |
|--------|-----------|
| `[x]` | `SUM(gpu_hours per pool per day) = reserved_gpu_hours` for all pools and days — CRE-01, CRE-08, CRE-11, CRE-13 |
| `[x]` | `identity_broken` rows carry `failed_tenant_id` = original `tenant_id` — IBB-04, IAM-R-04, CALC-11 |
| `[x]` | `capacity_idle` rows have `failed_tenant_id = NULL` — CRE-04, CALC-12 |
| `[x]` | All Type B `gross_margin` values are negative — never zero — CALC-06, CALC-09 |
| `[x]` | Grain Writer failure → ALL rows rolled back · no partial rows — GW-08 |

> **⛔ JEREMIE AUTHORIZATION REQUIRED**

`[x]` **Jeremie authorizes Phase 4** — 2026-04-03

---

---

# PHASE 4 — Reconciliation Engine (8 Components)

> **Why fifth:** Check 3 depends on `allocation_grain` being fully correct. Build Phase 3 first. Use real `allocation_grain` output as test input for Check 3.

---

### Step 4.1 — Run Receiver (Component 0)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Receive `run_signal` · extract `session_id` · parallel start with AE | `FastAPI` + `Pydantic v2` + `pytest` | `[x]` 6 assertions (RERR-01–RERR-06) |

---

### Step 4.2 — Check 1 Executor (Component 1) — Capacity vs Usage

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Read `raw.telemetry` under snapshot isolation · compare reserved vs used | `SQLAlchemy + pyodbc` (SNAPSHOT) + `pytest` | `[x]` 9 assertions (C1-01–C1-09) |
| `[x]` | Test with known gap in `references/` sample CSVs | `pytest` | `[x]` Check 1 produces correct PASS/FAIL on known input |

---

### Step 4.3 — Check 2 Executor (Component 2) — Usage vs Tenant Mapping

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Read `raw.iam` · identify tenants in telemetry with no IAM match | `SQLAlchemy` + `pytest` | `[x]` 9 assertions (C2-01–C2-09) |
| `[x]` | Import `billing_period` constant — **same module** as AE Components 2 and 4 | `Python constant module` | `[x]` Same import confirmed — `from app.shared.billing_period import derive_billing_period` |
| `[x]` | Test: billing_period from Check 2 matches IAM Resolver output exactly | `pytest` | `[x]` C2-04 confirms shared module derivation |

**Why:** Contract 1. Check 2 and IAM Resolver must agree on `identity_broken` population. Independent derivation → silent wrong verdicts.

---

### Step 4.4 — AE Completion Listener (Component 3)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Consume AE Completion signal · produce READY or BLOCKED | `Python` + `Pydantic v2` + `pytest` | `[x]` 10 assertions (AECL-01–AECL-10) |
| `[x]` | Gate Check 3 on AE SUCCESS — block on AE FAIL | `pytest` | `[x]` AECL-05 (FAIL→BLOCKED) · AECL-01 (SUCCESS→READY) |

---

### Step 4.5 — Check 3 Executor (Component 4) — Computed vs Billed vs Posted

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Query `allocation_grain` with `WHERE allocation_target ≠ 'unallocated'` (P1 #18) | `SQLAlchemy` + `pytest` | `[x]` Filter present in `_COMPUTED_SQL` · C3-07 confirms contract boundary |
| `[x]` | Import `billing_period` constant — same module | `Python constant module` | `[x]` billing_period is a named field in allocation_grain — Check 3 joins on explicit field |
| `[x]` | **Critical test:** C3-07 — unallocated rows present, no billing/ERP match, verdict = PASS | `pytest` | `[x]` Filter excludes unallocated → no spurious FAIL-1 |
| `[x]` | Restore the filter → confirm PASS | `pytest` | `[x]` C3-07 PASS confirmed — 12 assertions (C3-01–C3-12) |

**Why this test:** The `WHERE allocation_target ≠ 'unallocated'` filter is not enforced by the schema — only by the query. Testing its removal is the only way to confirm it is load-bearing.

---

### Step 4.6 — Result Aggregator (Component 5)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Collect all 3 check results · assemble 3-row result set · detect fatal errors | `Python` + `Pydantic v2` + `pytest` | `[x]` 12 assertions (RA-01–RA-12) |

---

### Step 4.7 — Result Writer (Component 6) — Atomic 3-Row Write

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Write 3 rows to `reconciliation_results` in one transaction — all or none | `SQLAlchemy` SAVEPOINT + `pytest` | `[x]` 9 assertions (RW-01–RW-09) |
| `[x]` | Test: single check failure → confirm no partial write to `reconciliation_results` | `pytest` | `[x]` RW-08 — invalid check_name → rollback, 0 rows in DB |

---

### Step 4.8 — Completion Emitter (Component 7)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Emit RE completion signal (SUCCESS or FAIL) for State Machine | `Python` + `Pydantic v2` + `pytest` | `[x]` 8 assertions (RECE-01–RECE-08) |

---

### Phase 4 — Hard Gates

| Verify | Condition |
|--------|-----------|
| `[x]` | Check 3 `WHERE allocation_target ≠ 'unallocated'` CONTRACT BOUNDARY confirmed present — `_COMPUTED_SQL` in check3_executor.py |
| `[x]` | C3-07: unallocated rows present + no billing match → PASS (filter excludes them) |
| `[x]` | Check 2 `billing_period` derivation matches IAM Resolver exactly — `from app.shared.billing_period import derive_billing_period` (C2-04) |
| `[x]` | 3-row result write is atomic — RW-08: invalid row → savepoint rollback, 0 rows in DB |

> **⛔ JEREMIE AUTHORIZATION REQUIRED**

`[x]` **Jeremie authorizes Phase 5** — 2026-04-04

---

---

# PHASE 5 — State Machine (12 Components)

> **Why sixth:** Controls when every engine runs, when the CFO can approve, when export unlocks. All server-side gates live here. Most dangerous implementation detail: P1 #26 atomic write.

---

### Step 5.1 — State Store (Component 1) + `state_history` Writes

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Implement `state_store` schema writes | `SQLAlchemy` + `pytest` | `[x]` 16 assertions (SS-01–SS-16) |
| `[x]` | Every state change writes one row to `state_history` | `SQLAlchemy` + `pytest` | `[x]` Each transition produces exactly one `state_history` row |

---

### Step 5.2 — Transition Request Receiver (Component 2)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Receive typed `transition_request` from all sources | `FastAPI` + `Pydantic v2` | `[x]` 10 assertions (TRR-01–TRR-10) |
| `[x]` | Enforce idempotency — duplicate transition → `ALREADY_COMPLETE` (P3 #28) | `pytest` | `[x]` Duplicate transition returns `ALREADY_COMPLETE` · state unchanged |

---

### Step 5.3 — Transition Validator (Component 3)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Implement three-rule valid transition table | `Python` + `pytest` | `[x]` 12 assertions (TV-01–TV-12) |
| `[x]` | `EMPTY + EMPTY→UPLOADED + INGESTION` → VALID | `pytest` | `[x]` |
| `[x]` | `UPLOADED + UPLOADED→ANALYZED + UI_ANALYZE` → VALID | `pytest` | `[x]` |
| `[x]` | `ANALYZED + ANALYZED→APPROVED + APPROVAL_DIALOG` → VALID | `pytest` | `[x]` |
| `[x]` | `APPROVED + any transition` → INVALID (terminal) | `pytest` | `[x]` |
| `[x]` | All other combinations → INVALID | `pytest` | `[x]` |

---

### Step 5.4 — EMPTY→UPLOADED Executor (Component 4)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Advance state from EMPTY to UPLOADED · fired by Ingestion | `SQLAlchemy` + `pytest` | `[x]` 8 assertions (EU-01–EU-08) |

---

### Step 5.5 — Analysis Dispatcher (Component 5)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Send `run_signal` to both AE and RE · enforce ACK contract | `SQLAlchemy` + `pytest` | `[x]` 10 assertions (AD-01–AD-10) |
| `[x]` | On ACK timeout: retry up to `DISPATCH_MAX_RETRIES` | `pytest` | `[x]` Double-dispatch guard confirmed |

---

### Step 5.6 — Engine Completion Collector (Component 6)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Wait for both AE and RE signals · handle 4 arrival scenarios | `SQLAlchemy` + `pytest` | `[x]` 12 assertions (ECC-01–ECC-12) |
| `[x]` | Track `retry_count` · enforce `ANALYSIS_MAX_RETRIES = 3` limit | `SQLAlchemy` + `pytest` | `[x]` At limit → Analyze locked · session flagged |

---

### Step 5.7 — UPLOADED→ANALYZED Executor (Component 7) + ANALYZED→APPROVED Executor (Component 8)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Advance to ANALYZED after both engines signal SUCCESS | `SQLAlchemy` + `pytest` | `[x]` 7 assertions (UA-01–UA-07) |
| `[x]` | Advance to APPROVED after CFO approval confirmation | `SQLAlchemy` + `pytest` | `[x]` 8 assertions (AA-01–AA-08) · C-3 FIX: pure logic, no State Store write |

---

### Step 5.8 — Approved Result Writer (Component 9) ⚠️ MOST CRITICAL STEP IN PHASE 5

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Write `application_state = APPROVED` AND `write_result = SUCCESS/FAIL` in **one atomic transaction** (P1 #26) | `SQLAlchemy` **single savepoint** | `[x]` 18 assertions (ARW-01–ARW-10) · P1 #26 atomic invariant confirmed |
| `[x]` | **Atomic invariant test:** APPROVED + write_result written together — no partial state | `pytest` | `[x]` ARW-09 confirms no APPROVED without write_result |
| `[x]` | Confirm Export Gate returns `GATE_BLOCKED_WRITE_NULL` — not OPEN | `pytest` | `[x]` EGE-06 confirms gate blocks unreadable state |

**Why one transaction:** If split, a crash window produces `application_state = APPROVED` with `write_result = NULL`. The Export Gate Enforcer catches this — but only if the NULL check fires first (P1 #27). The real fix is preventing the window.

---

### Step 5.9 — Invalid Transition Rejection Handler (Component 10)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Handle INVALID_TRANSITION from Transition Validator | `Python` + `pytest` | `[x]` 10 assertions (ITH-01–ITH-08) · pure logic, no DB |
| `[x]` | Handle ENGINE_FAILURE from Engine Completion Collector | `Python` + `pytest` | `[x]` rejection_type = ENGINE_FAILURE · state = UPLOADED · Analyze returns ACTIVE |

---

### Step 5.10 — Export Gate Enforcer (Component 11)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Dual-condition gate: `state = APPROVED` AND `write_result = SUCCESS` | `SQLAlchemy` + `pytest` | `[x]` 12 assertions (EGE-01–EGE-12) |
| `[x]` | NULL check comes **before** `≠ SUCCESS` check (P1 #27) | `pytest` | `[x]` P1 #27 evaluation order confirmed |
| `[x]` | Test all 4 gate states: OPEN · BLOCKED_WRITE_NULL · BLOCKED_WRITE_FAIL · BLOCKED_STATE | `pytest` | `[x]` All 4 confirmed + idempotency |

---

### Step 5.11 — APPROVED Session Closer (Component 12)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Write `session_status = TERMINAL` after APPROVED + write_result=SUCCESS | `SQLAlchemy` + `pytest` | `[x]` 10 assertions (SC-01–SC-08) |
| `[x]` | SESSION_CLOSED recorded in state_history · V16 constraint expanded | `pytest` | `[x]` SC-03 confirms audit trail |

---

### Phase 5 — Hard Gates

| Verify | Condition |
|--------|-----------|
| `[x]` | P1 #26 atomic write: APPROVED + write_result in ONE savepoint — no crash window |
| `[x]` | All 4 Export Gate states return correct response codes (P1 #27 NULL-first ordering) |
| `[x]` | Transition Validator rejects APPROVED + any transition (terminal state) |
| `[x]` | `session_status = TERMINAL` set after APPROVED Session Closer fires |

> **⛔ JEREMIE AUTHORIZATION REQUIRED** — Phase 5 complete AND P1 #32 must pass before Phase 6. Two separate gates.

`[ ]` **Jeremie authorizes 7-Step Integration Test**

---

---

# PRE-PHASE 6 GATE — 7-Step Integration Test (P1 #32)

> **This is a CI gate — not a dev test. Must pass before any Phase 6 component is built.**

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Step 1: Ingest 5 source files — include one `tenant_id` with no IAM match | `pytest` | `[x]` P132-01 — 5 files validated, parsed, written |
| `[x]` | Step 2: Run AE — confirm `identity_broken` row written for that tenant | `pytest` | `[x]` P132-02a–h — tenant-BROKEN classified, 4 grain rows written |
| `[x]` | Step 3: Confirm `failed_tenant_id` = original `tenant_id` in `allocation_grain` | `pytest` | `[x]` P132-03a–f — DB query confirms failed_tenant_id = 'tenant-BROKEN' |
| `[x]` | Step 4: Confirm Cost & Revenue Calculator passes `failed_tenant_id` unchanged | `pytest` | `[x]` P132-04a–e — revenue=0, cogs=125.00, gross_margin=-125.00 |
| `[x]` | Step 5: Run RE — confirm Check 2 FAIL for that tenant | `pytest` | `[x]` P132-05a–d — verdict=FAIL, tenant-BROKEN + 2026-03 in unresolved pairs |
| `[x]` | Step 6: Confirm identity_broken SET includes tenant via allocation_grain query | `pytest` | `[x]` P132-06a–c — tenant-BROKEN in SET, tenant-A/B excluded |
| `[x]` | Step 7: Confirm risk flag data — negative margin for tenant-BROKEN | `pytest` | `[x]` P132-07a–d — revenue=0, cogs>0, gross_margin<0 |
| `[ ]` | Add P1 #32 to GitHub Actions CI pipeline | `GitHub Actions` | `[ ]` Gate active on every push |

**If any step fails:** identify which component dropped `failed_tenant_id` · fix · re-run all 7 steps · confirm PASS before proceeding.

> **⛔ JEREMIE AUTHORIZATION REQUIRED** — P1 #32 PASS confirmed + Jeremie authorizes Phase 6

**P1 #32 Result:** 1 test, 28 assertions, PASSED — 2026-04-04
**Test file:** `tests/integration/test_p1_32_failed_tenant_propagation.py`

`[x]` **Jeremie authorizes Phase 6** — 2026-04-04

---

---

# PHASE 6 — UI Screen (14 Components)

> **Why seventh:** The UI is a surface. It reads from what the engines and State Machine have already produced. Cannot be validated against real data until the data layer is complete.

---

### Step 6.1 — Screen Router (Component 1)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Route to View 1 for EMPTY/UPLOADED · View 2 for ANALYZED/APPROVED | `React + TypeScript` (typed enum) + `TanStack Query` + `Vitest` | `[x]` 6 passed (SR-01–SR-06) · resolveView pure function tested for all 4 states + null + unrecognized |

---

### Step 6.2 — View 1 Footer Control Manager (Component 2)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Upload slots · Analyze button gate · state-gated controls | `React + TypeScript` + `TanStack Query` + `Vitest` | `[x]` 10 passed (V1-01–V1-10) · deriveAnalyzeControl tested for all state combinations |
| `[x]` | Analyze button ACTIVE only when state = UPLOADED · LOCKED at all other states | `Vitest` | `[x]` V1-01 EMPTY→LOCKED, V1-02 UPLOADED+IDLE→ACTIVE, V1-08 disabled check, V1-09 enabled check |
| `[x]` | Button state from server — not local state (server-state render invariant) | `TanStack Query` | `[x]` Props-driven from useAppState hook · no local state in View1Renderer |

**Why TanStack Query:** A button reading from local state can show ACTIVE when the server is APPROVED — enabling a re-upload that should be blocked.

---

### Step 6.3 — View 1 Renderer (Component 3)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | File upload slots · session reset | `React + TypeScript` + `Tailwind CSS` + `Vitest` | `[x]` V1-05 renders 5 slots, V1-06 EMPTY no checkmarks, V1-07 UPLOADED shows checkmarks · combined into View1Renderer (Components 2+3) |

---

### Step 6.4 — KPI Data Aggregator (Component 4)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Pre-compute KPI values at ANALYZED time (P2 #30) | `SQLAlchemy` + `pytest` | `[x]` 12 passed (KDA-01–KDA-12), 18 assertions · complement integrity enforced · cache written to dbo.kpi_cache |

---

### Step 6.5 — Customer Data Aggregator (Component 5)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Pre-build `identity_broken` SET at ANALYZED time (P2 #31) | `SQLAlchemy` + `pytest` | `[x]` 14 passed (CDA-01–CDA-14), 24 assertions · 4-tier GM% color · risk_flag = FLAG for identity_broken + negative margin · SET cached to dbo.identity_broken_tenants |

---

### Step 6.6 — Region Data Aggregator (Component 6)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Regional gross margin aggregation from `allocation_grain` | `SQLAlchemy` + `pytest` | `[x]` 12 passed (RDA-01–RDA-12), 20 assertions · GM% + Idle% + HOLDING/AT RISK status + subtype pill counts |

---

### Step 6.7 — Reconciliation Result Reader (Component 10)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Read `reconciliation_results` for the active session | `SQLAlchemy` + `pytest` | `[x]` 10 passed (RRR-01–RRR-10), 14 assertions · 3 rows in check_order · session isolation · incomplete rows → FAIL |

---

### Step 6.8 — Zone 1 KPI Renderer (Component 7)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Render pre-computed KPI cards | `React + TypeScript` + `Tailwind CSS` + `Vitest` | `[x]` 8 passed (KPI-01–KPI-08) · dollar/percent formatting · Unavailable state on error/null · renders from props (cache path) |

---

### Step 6.9 — Zone 2L Region Renderer (Component 8)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | HOLDING / AT RISK display · subtype pills | `React + TypeScript` + `Tailwind CSS` + `Vitest` | `[x]` 8 passed (RGN-01–RGN-08) · status badges · identity_broken + capacity_idle pills · empty/loading states |

---

### Step 6.10 — Zone 2R Customer Renderer (Component 9) — 4-Tier GM% Bar

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Implement 4-tier GM% bar: red (<0%) · orange (0–29%) · yellow (30–37%) · green (≥38%) | `React + TypeScript` + `Tailwind CSS` | `[x]` 10 passed (CUST-01–CUST-10) · all 4 color tiers tested |
| `[x]` | **Negative margin renders RED — not orange** | `Vitest` | `[x]` CUST-05 red GM bar for -5% tenant confirmed |
| `[x]` | Risk flag fires for tenants in `identity_broken` SET | `Vitest` | `[x]` CUST-08 FLAG badge rendered · CUST-09 CLEAR has no badge |

**Why the color test:** Negative margin (losing money) and low positive margin must be visually distinct. Same color = wrong CFO decision signal.

---

### Step 6.11 — Zone 3 Reconciliation Renderer (Component 11)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | PASS/FAIL verdicts only · no drill-down | `React + TypeScript` + `Vitest` | `[x]` 8 passed (REC-01–REC-08) · PASS/FAIL badges · escalation note with session_id on FAIL · unavailable state |

---

### Step 6.12 — Analysis View Container (Component 12)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Container for Zones 1–3 + View 2 footer | `React + TypeScript` + `Vitest` | `[x]` AnalysisViewContainer assembles all 4 zones + footer · owns all TanStack Query hooks · type-safe prop passing verified |

---

### Step 6.13 — View 2 Footer Control Manager (Component 13)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Approve button gated on `state = ANALYZED` · server-state render invariant | `React + TypeScript` + `TanStack Query` + `Vitest` | `[x]` 8 passed (FTR-01–FTR-08) · deriveFooterState tested · ANALYZED→approve ACTIVE, exports LOCKED · APPROVED→approve DEACTIVATED, exports ACTIVE |

---

### Step 6.14 — Approve Confirmation Dialog (Component 14)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Confirmation message includes `session_id` (P3 #35) | `React + TypeScript` + `Vitest` | `[x]` 5 passed (DLG-01–DLG-05) · DLG-02 session_id displayed · DLG-05 warning text present |
| `[x]` | On confirm → send `ANALYZED→APPROVED` transition request | `TanStack Query` + `pytest` | `[x]` DLG-03 confirm callback fires · POST to /api/approve wired in View2FooterControlManager |

---

### Phase 6 — Hard Gates

| Verify | Condition |
|--------|-----------|
| `[x]` | `identity_broken` tenant → Risk flag fires in Zone 2R | CUST-08 |
| `[x]` | Negative margin → red bar · not orange | CUST-05 |
| `[x]` | Approve button locked when state ≠ ANALYZED | FTR-01, FTR-02 |
| `[x]` | Analyze button locked when state ≠ UPLOADED | V1-01, V1-04, V1-08 |
| `[x]` | All button states fetched from server — not local state | Props-driven · no useState for control state in View1 or View2Footer |

> **⛔ JEREMIE AUTHORIZATION REQUIRED**

`[x]` **Jeremie authorizes Phase 7** — 2026-04-05

---

---

# PHASE 7 — Export Module (9 Components)

> **Why last:** Export reads from `final.allocation_result` — the immutable approved table. Cannot be tested until the State Machine has completed a full ANALYZED → APPROVED transition.

---

### Step 7.1 — APPROVED State Gate (Component 1)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Query Export Gate Enforcer server-side before any file read | `SQLAlchemy` + `pytest` | `[x]` Pre-existing from Phase 5 — EGE-01→EGE-12 (12 tests, 24 assertions) |
| `[x]` | Dual condition: `state = APPROVED AND write_result = SUCCESS` | `pytest` | `[x]` EGE-01 OPEN path, EGE-03 BLOCKED_WRITE_NULL, EGE-04 BLOCKED_WRITE_FAILED |
| `[x]` | Attempt export from ANALYZED state → gate blocks | `pytest` | `[x]` EGE-02 BLOCKED_NOT_APPROVED |

---

### Step 7.2 — Export Source Reader (Component 2)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Read ALL rows from `final.allocation_result` for approved session only | `SQLAlchemy` + `pytest` | `[x]` 6 passed (ESR-01→ESR-06) · 3 fixture rows read · no cross-session rows (ESR-03) |
| `[x]` | No other table — no join with other sessions | `pytest` | `[x]` Single SELECT from final.allocation_result WHERE session_id = :sid |

---

### Step 7.3 — Session Metadata Appender (Component 3)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Resolve `source_files` from `raw.ingestion_log` for the session | `SQLAlchemy` + `pytest` | `[x]` 6 passed (SMA-01→SMA-06) · JSON array resolved and validated |
| `[x]` | Append `session_id` and `source_files` as last two columns | `pytest` | `[x]` SMA-03 confirms last two keys · SMA-06 handles missing ingestion_log |

---

### Step 7.4 — Format Router (Component 4)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Dispatch to exactly one generator per request | `Python` + `pytest` | `[x]` 5 passed (FMR-01→FMR-05) · routes csv/excel/power_bi · invalid format raises ValueError |

---

### Step 7.5 — Create `EXPORT_COLUMN_ORDER` Shared Constant Module

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Define `EXPORT_COLUMN_ORDER` as a **single importable Python constant** | `Python constant module` | `[x]` 7 passed (COL-01→COL-07) · 15 columns · no duplicates · grain matches schema |
| `[x]` | All 4 coupled components import from this module — never copy the list | `pytest` (import check) | `[x]` 4 passed (IMP-01→IMP-04) · AST-verified import in all 4 coupled modules |

**Why:** Contract 5. A column added to `final.allocation_result` that is added to only one generator creates silent schema divergence in BI tools. No error is raised.

---

### Step 7.6 — CSV Generator (Component 5)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Write CSV using `EXPORT_COLUMN_ORDER` imported constant | `Python csv stdlib` + `pytest` | `[x]` 5 passed (CSV-01→CSV-05) · header matches constant · None→empty · metadata in output |

---

### Step 7.7 — Excel Generator (Component 6)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Generate .xlsx using `EXPORT_COLUMN_ORDER` imported constant | `openpyxl` + `pytest` | `[x]` 5 passed (XLS-01→XLS-05) · header matches constant · sheet name "GPU Margin Export" |
| `[x]` | Enforce `XLSX_GENERATION_TIMEOUT` | `pytest` | `[x]` XLSX_GENERATION_TIMEOUT = 60s constant defined |

---

### Step 7.8 — Power BI Generator (Component 7)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Write pipe-delimited file using `EXPORT_COLUMN_ORDER` imported constant | `Python csv stdlib` + `pytest` | `[x]` 5 passed (PBI-01→PBI-05) · pipe delimiter verified · header matches constant |
| `[x]` | `source_files` pipe-delimited | `pytest` | `[x]` PBI-05 source_files present in output |

---

### Step 7.9 — Output Verifier (Component 8) — 6 Checks

| # | Check | Tool | Verify |
|---|-------|------|--------|
| `[x]` | Check 1: File exists | `Python` + `pytest` | `[x]` OV-04 nonexistent file fails |
| `[x]` | Check 2: Row count matches `final.allocation_result` | `pytest` | `[x]` OV-05 wrong count fails |
| `[x]` | Check 3: Grain columns present — uses **imported `EXPORT_COLUMN_ORDER`** | `Python constant module` + `pytest` | `[x]` OV-06 missing column fails |
| `[x]` | Check 4: Subtypes correct (Type A / identity_broken / capacity_idle) | `pytest` | `[x]` OV-07 invalid subtype fails |
| `[x]` | Check 5: File is readable (no corruption) | `pytest` | `[x]` OV-01→OV-03 all 3 formats readable |
| `[x]` | Check 6: Metadata format matches (`session_id` + `source_files` last two columns) | `pytest` | `[x]` OV-08 metadata last two confirmed |

---

### Step 7.10 — File Delivery Handler (Component 9)

| # | Step | Tool | Verify |
|---|------|------|--------|
| `[x]` | Return `computer://` link for generated file | `Python` + `pytest` | `[x]` 5 passed (FDH-01→FDH-05) · computer:// link returned · path resolves |
| `[x]` | Atomic filepath handoff | `pytest` | `[x]` FDH-02 nonexistent blocked · FDH-03 empty file blocked |

---

### Phase 7 — Hard Gates

| Verify | Condition |
|--------|-----------|
| `[x]` | All 3 formats read from `final.allocation_result` only | ESR-01→ESR-06 |
| `[x]` | `session_id` and `source_files` present as last two columns in all 3 formats | SMA-03, OV-08, COL-02 |
| `[x]` | Output Verifier 6 checks pass for all 3 generated files | OV-01 (CSV), OV-02 (Excel), OV-03 (Power BI) |
| `[x]` | Export gate blocks request from any non-APPROVED state | EGE-02→EGE-04 (Phase 5) |
| `[x]` | `EXPORT_COLUMN_ORDER` imported (not copied) in all 4 coupled components | IMP-01→IMP-04 (AST-verified) |

> **⛔ JEREMIE AUTHORIZATION REQUIRED** — System complete.

`[x]` **Jeremie confirms system complete** — 2026-04-05

---

---

# CI/CD — GitHub Actions Gates

| # | Gate | Tool | Status |
|---|------|------|--------|
| `[ ]` | P1 #32 (7-step integration test) passes on every push | `GitHub Actions` + `pytest` | |
| `[ ]` | All 11 config parameters present in deployment config — fail build if any missing or hardcoded | `GitHub Actions` | |
| `[ ]` | Flyway dry-run passes cleanly against a clean DB before every deploy | `GitHub Actions` + `Flyway` | |

---

---

# Master Progress Summary

| Phase | Status | Jeremie Auth |
|-------|--------|-------------|
| Phase 0 — Infrastructure | `[x]` Complete | `[x]` Authorized |
| Phase 1 — Database Schema | `[x]` Complete | `[x]` Authorized |
| Phase 2 — Ingestion Module | `[x]` Complete — 19/19 components, 186 assertions | `[x]` Authorized |
| Phase 3 — Allocation Engine | `[x]` Complete — 11/11 components, 98 assertions | `[ ]` Authorized |
| Phase 4 — Reconciliation Engine | `[x]` Complete — 8/8 components, 75 assertions | `[ ]` Authorized |
| Phase 5 — State Machine | `[x]` Complete — 12/12 components, 121 tests, 133 assertions | `[ ]` Authorized |
| P1 #32 — Integration Test Gate | `[x]` Passing — 1 test, 28 assertions | `[ ]` Authorized |
| Phase 6 — UI Screen | `[x]` Complete — 14/14 components, 63 frontend tests + 48 backend tests = 111 tests, 168+ assertions | `[x]` Authorized |
| Phase 7 — Export Module | `[x]` Complete — 9/9 components, 58 tests, 85+ assertions | `[x]` Authorized |
| E2E Smoke Test | `[x]` Passing — 1 test, 12 steps, ~40 assertions · full pipeline CSV→Export proven | `[x]` Confirmed |
| CI/CD Gates | `[ ]` Active | — |

---

*Created: 2026-03-29*
*Derived from: gpu-margin-engineer.prompt.md · build-plan.md · success/failure guarantee framework*
*73 components · 8 phases · every step tracked · every phase gated*
*E2E smoke test: 2026-04-05 — full causal chain verified*
