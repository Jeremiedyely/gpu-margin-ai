---
name: implementation-analysis
role: implementation-analysis
reads-from: >
  business.md · requirements.md · software-system-design.md ·
  ingestion-module-design.md · allocation-engine-design.md ·
  reconciliation-engine-design.md · state-machine-design.md ·
  ui-screen-design.md · export-module-design.md ·
  db-schema-design.md · references/stabilization-register.md
session-context: deep implementation analysis — priority order · tool stack · collaboration model · recommendations
created: 2026-03-29
updated: 2026-03-29
---

# Implementation Analysis — GPU Gross Margin Visibility Application

> See: business.md — WHY layer · CFO problem definition
> See: requirements.md — WHAT layer · grain · computation contract · state machine
> See: software-system-design.md — HOW layer · interaction protocol · anti-drift rules
> See: ingestion-module-design.md · allocation-engine-design.md · reconciliation-engine-design.md — Phases 2–4
> See: state-machine-design.md · ui-screen-design.md · export-module-design.md — Phases 5–7
> See: db-schema-design.md — 13 tables · grain relationship · constraints
> See: references/stabilization-register.md — 62 findings applied · finding IDs cited throughout

---

## The Governing Principle

The design was built backward from output. Implementation must be built **forward from the grain** — but in a specific sequence that respects what each layer depends on.

The grain is `Region × GPU Pool × Day × Allocation Target`. Nothing in this system works correctly until that table can be written to, read from, and queried accurately. Every implementation decision flows from that constraint.

```
Before any code:   Infrastructure + DB Schema
Before any engine: Ingestion (the gate)
Before any UI:     Allocation Engine (the grain producer)
Before approval:   Reconciliation Engine (the checker)
Before export:     State Machine (the controller)
After approval:    UI + Export (the surface + delivery)
```

---

## Priority Order — Step by Step

### Phase 0 — Infrastructure (Before Any Code Is Written)

**Why this is first:** Six deployment prerequisites exist that are not code changes. They are database and infrastructure configurations. If these are absent when code runs against them, silent failures occur — wrong aggregations, full-table scans that time out, signal loss, and unrecoverable crash windows. No amount of correct code compensates for a missing database index or wrong isolation level.

**What must be done:**

1. **SQL Server provisioned and accessible.** All 13 tables from `db-schema-design.md` migrated via Flyway. This includes all 28 indexes, 51 check constraints, 6 filtered-unique indexes, and 4 immutability triggers.

2. **Snapshot isolation enabled on `raw.telemetry`.** `ALTER DATABASE ... SET ALLOW_SNAPSHOT_ISOLATION ON`. Without this, the Allocation Engine Telemetry Aggregator and Reconciliation Engine Check 1 and Check 2 run concurrent reads against `raw.telemetry` at default READ COMMITTED isolation — dirty aggregation is guaranteed at production volume. Flyway migration, not a code change.

3. **Composite index on `raw.iam(tenant_id, billing_period)`.** Without it, the IAM Resolver performs a full-table scan on every run. At 100K+ IAM rows, the query becomes linear and pushes the Allocation Engine past `AE_TIMEOUT`. Flyway migration.

4. **Redis provisioned.** Powers all Celery task queues, ACK contracts, and the Dispatch ACK timeout enforcement. Without Redis, engines cannot receive signals and the Analysis Dispatcher cannot confirm receipt.

5. **Celery + Celery Beat configured.** Celery Beat is mandatory — not optional. The APPROVED Session Closer retry (P1 #25) depends on it. After APPROVED, no further requests arrive for that session. A Beat-triggered scheduled retry is the only mechanism that closes the session as TERMINAL. Without Beat, `session_status` is never set to TERMINAL — a silent security gap.

6. **All 11 configurable parameters set in deployment config.** `INGESTION_BATCH_THRESHOLD`, `AE_TIMEOUT`, `DISPATCH_ACK_TIMEOUT`, `DISPATCH_MAX_RETRIES`, `CLOSER_RETRY_INTERVAL`, `CLOSER_MAX_RETRIES`, `ANALYSIS_MAX_RETRIES`, `MAX_EXPORT_RERUNS`, `XLSX_GENERATION_TIMEOUT`, `MAX_HISTORY_SESSIONS`, `HISTORY_RETENTION_DAYS`. These must be set before the first staging run.

**Collaboration:** You review and confirm each Flyway migration script and the deployment config before they are applied. I draft them. You approve and apply.

---

### Phase 1 — Database Schema (Flyway Migrations)

**Why before code:** The schema is the structural guarantee. Check constraints enforce enum values at the database level. Immutability triggers prevent `final.allocation_result` from being overwritten. Filtered-unique indexes enforce the closure rule at the storage layer. If code is written before the schema enforces these constraints, silent violations pass through — and they cannot be detected retroactively without a schema migration and data re-run.

**What must be built — all 13 tables in grain-relationship order:**

```
ANCHORS first:    raw.ingestion_log
FEEDS second:     raw.telemetry · raw.cost_management · raw.iam · raw.billing · raw.erp
IS the grain:     allocation_grain · final.allocation_result
CHECKS:           reconciliation_results
CONTROLS:         state_store · state_history
CACHES:           kpi_cache · identity_broken_tenants
```

The immutability triggers on `final.allocation_result` are the most critical structural control. They prevent any UPDATE or DELETE on approved records. Once written, the number is locked. This is not enforced in application code — it is enforced in the database.

**Collaboration:** I draft each migration. We review the check constraints and triggers together — specifically the ones that enforce `unallocated_type` as an enum, the `allocation_target` closure rule, and the `write_result` atomic write constraint on `state_store`.

---

### Phase 2 — Ingestion Module (19 Components)

**Why this is the first code module:** `session_id` is the K1 cross-module correlation key. It is generated once at the Ingestion Orchestrator and propagated to all 6 modules. Nothing in the system — no engine, no check, no export — can execute without a valid `session_id` anchored to a complete ingestion run. The Ingestion Commit is the first structural gate: all five files validated, parsed, written, and promoted atomically, or nothing advances.

**Implementation sequence within the module:**

```
Layer 1:   5 File Validators (enforce YYYY-MM, ISO 8601, required fields, format)
Layer 2:   5 File Parsers
Layer 3:   5 Raw Table Writers (dedicated write connection per writer)
Layer 4:   Ingestion Orchestrator (session_id generation + atomic registration)
Layer 4b:  Ingestion Commit (all-or-nothing promote)
Layer 5:   Ingestion Log Writer
Layer 6:   State Transition Emitter (EMPTY → UPLOADED)
```

**What to test before advancing:** Upload five valid CSV files. Confirm all five raw tables are populated with matching `session_id`. Confirm `raw.ingestion_log` has one entry. Confirm state transitions to UPLOADED. Then test a single invalid file — confirm nothing is written, state stays EMPTY, and the named error identifies which validator failed and which field.

**Critical constraint to verify:** The Telemetry File Validator must enforce `tenant_id` format (P1 #7 — regex pattern check). A malformed `tenant_id` that passes validation will silently classify as `identity_broken` in the Allocation Engine — not because the customer is missing from IAM, but because the ID was never valid. The CFO receives a false identity failure signal with no root cause traceable to the ingestion boundary.

---

### Phase 3 — Allocation Engine (11 Components)

**Why this is third:** The grain cannot exist until validated, session-tagged data exists in the raw tables. The Allocation Engine is the only layer that can produce `allocation_grain`. Every downstream consumer — all four UI data aggregators, all three reconciliation checks, and all three export generators — reads from this table. If the Allocation Engine produces a wrong record, the error propagates to every surface with no recovery path.

**Implementation sequence within the module:**

```
Component 0:  Run Receiver (validate run_signal, extract session_id)
Component 3:  Cost Rate Reader (parallel track — runs simultaneously with 1-2)
Component 1:  Telemetry Aggregator (GROUP BY grain dimensions)
Component 2:  Billing Period Deriver (LEFT(date, 7) → billing_period)
Component 4:  IAM Resolver (LEFT JOIN on tenant_id + billing_period)
Component 5:  Type A Record Builder
Component 6:  Identity Broken Record Builder
Component 7:  Closure Rule Enforcer (force capacity_idle row when idle > 0)
Component 8:  Cost & Revenue Calculator
Component 9:  Allocation Grain Writer (atomic · DB transaction ROLLBACK on failure)
Component 10: Completion Emitter (signals State Machine AND Reconciliation Engine)
```

**What to test before advancing:** Run the engine with the five sample CSVs from `references/`. Confirm `allocation_grain` has one row per grain cell. Confirm `SUM(gpu_hours per pool per day) = reserved_gpu_hours` (closure rule). Confirm `identity_broken` rows carry the original `tenant_id` in `failed_tenant_id`. Confirm `capacity_idle` rows have `failed_tenant_id = NULL`. Confirm gross_margin on all Type B records is always negative, never zero.

**The single most dangerous failure mode in this module:** The DB transaction ROLLBACK on Grain Writer failure (P1 #12). A DELETE-based rollback that fails mid-loop leaves partial rows in `allocation_grain`. Check 3 then reads a partial grain and produces spurious FAIL-1 verdicts for every missing tenant. No system error is raised. The wrong verdict propagates silently to Zone 3 and the CFO. This must be wrapped in a single DB transaction — not a DELETE loop.

---

### Phase 4 — Reconciliation Engine (8 Components)

**Why this is fourth:** Checks 1 and 2 run in parallel with the Allocation Engine and read only from raw tables, but Check 3 depends on `allocation_grain` being fully written. The engine as a whole cannot signal completion until all three checks are done. The State Machine cannot advance to ANALYZED until both engines signal SUCCESS.

**Implementation sequence:**

```
Component 0: Run Receiver (parallel start with AE)
Component 1: Check 1 Executor (Capacity vs Usage — raw tables only)
Component 2: Check 2 Executor (Usage vs Tenant Mapping — same billing_period derivation as AE)
Component 3: AE Completion Listener (gates Check 3 — must ACK within ACK_TIMEOUT)
Component 4: Check 3 Executor (Computed vs Billed vs Posted — gated on AE SUCCESS)
Component 5: Result Aggregator (waits for all three · dynamic timeout · t_ae_complete tracking)
Component 6: Result Writer (atomic · three rows or none)
Component 7: Completion Emitter (signals State Machine)
```

**What to test before advancing:** Confirm Check 3 uses `WHERE allocation_target ≠ 'unallocated'` (CONTRACT BOUNDARY — P1 #18). Remove that filter in a test run and confirm it produces spurious FAIL-1 verdicts for idle and identity_broken rows. Then restore it and confirm PASS. This is the test that validates the most dangerous prose-only constraint in the design.

**Critical cross-module dependency:** Check 2 and IAM Resolver must use the exact same `billing_period` derivation: `LEFT(date, 7)`. If they diverge, Check 2 and IAM Resolver will disagree on which tenants are `identity_broken`. Test this explicitly before advancing.

---

### Phase 5 — State Machine (12 Components)

**Why this is fifth:** The State Machine controls when every engine runs, when the CFO can approve, and when export is unlocked. It is the only component that enforces these gates server-side. But it depends on both engines being able to send it completion signals — which requires Phase 3 and Phase 4 to be complete and stable.

**Implementation sequence:**

```
State Store + state_history writes (foundation)
Transition Request Receiver (idempotency — ALREADY_COMPLETE — P3 #28)
Transition Validator (three-rule valid transition table · VALID/INVALID result)
EMPTY→UPLOADED Executor (fired by Ingestion)
Analysis Dispatcher (sends run_signal to both engines · ACK contract)
Engine Completion Collector (waits for both · 4 arrival scenarios · retry_count)
UPLOADED→ANALYZED Executor
ANALYZED→APPROVED Executor
Approved Result Writer (ONE atomic transaction: application_state + write_result)
Invalid Transition Rejection Handler (named failure path — INVALID_TRANSITION + ENGINE_FAILURE)
Export Gate Enforcer (dual-condition: state=APPROVED AND write_result=SUCCESS)
APPROVED Session Closer (Celery Beat scheduled retry)
```

**The single most critical implementation detail in this module:** The `ANALYZED→APPROVED` transition must write `application_state = APPROVED` and `write_result = SUCCESS/FAIL` in one atomic transaction (P1 #26). If these are separate transactions and the process crashes between them, the system reaches `application_state = APPROVED` with `write_result = NULL`. The Export Gate Enforcer's NULL check must come before the `≠ SUCCESS` check (P1 #27). But the real fix is the atomic write: prevent the crash window from existing.

**What to test before advancing:** Restart the State Machine process immediately after writing `application_state = APPROVED` but before writing `write_result`. Confirm Export Gate returns `GATE_BLOCKED_WRITE_NULL` — not OPEN. This is the P1 #26 crash simulation test.

---

### Phase 6 — UI Screen (14 Components)

**Why this is sixth:** The UI is a surface — it reads from what the engines and State Machine have already produced. Building the UI before the data layer is complete produces components that cannot be validated against real data. Every button state, every KPI value, and every Zone 2 table depends on server-confirmed `application_state` and live `allocation_grain` data.

**Implementation sequence:**

```
Screen Router (state-driven view selection)
View 1 Footer Control Manager (upload slots · Analyze button gate · state-gated controls)
View 1 Renderer (Import View — file upload slots · session reset)
KPI Data Aggregator (pre-computed at ANALYZED time — P2 #30)
Customer Data Aggregator (pre-builds identity_broken SET at ANALYZED time — P2 #31)
Region Data Aggregator
Reconciliation Result Reader
Zone 1 KPI Renderer
Zone 2 Left Region Renderer (HOLDING / AT RISK · subtype pills)
Zone 2 Right Customer Renderer (4-tier GM% bar: red/orange/yellow/green — P2 #36)
Zone 3 Reconciliation Renderer (PASS/FAIL only · no drill-down)
Analysis View Container
View 2 Footer Control Manager (server-state render invariant — TanStack Query)
Approve Confirmation Dialog (session_id in confirmation message — P3 #35)
```

**What to test before advancing:** The 7-step integration test from P1 #32 — inject a known `identity_broken` tenant through Ingestion → Allocation Engine → Reconciliation Engine → UI → confirm Risk flag fires in Zone 2R for that customer. This is the highest-value integration test in the system. If `failed_tenant_id` is silently dropped at any point in the 7-component chain, the Risk flag never fires and the CFO approves without the identity integrity signal.

**The 4-tier GM% bar** must be validated: negative margin renders red, not orange. The visual distinction between a 15% margin (low, orange) and a −5% margin (losing money, red) is a CFO-facing decision signal. If they look the same, the approval decision is made on wrong information.

---

### Phase 7 — Export Module (9 Components)

**Why this is last:** Export is the final output of the entire system. It reads from `final.allocation_result` — the immutable approved table. It cannot be tested meaningfully until the State Machine has been through a full ANALYZED → APPROVED transition and `final.allocation_result` has been written.

**Implementation sequence:**

```
APPROVED State Gate (queries Export Gate Enforcer server-side before any read)
Export Source Reader (reads final.allocation_result)
Session Metadata Appender (resolves source_files from ingestion_log)
Format Router (dispatches to exactly one generator per request)
CSV Generator (Bash write · EXPORT_COLUMN_ORDER constant)
Excel Generator (xlsx skill · XLSX_GENERATION_TIMEOUT · same constant)
Power BI Generator (Bash write · pipe-delimited source_files)
Output Verifier (6 checks: existence · row count · grain · subtypes · readability · metadata format)
File Delivery Handler (computer:// link · atomic filepath handoff)
```

**The EXPORT_COLUMN_ORDER shared constant must be a code-level constant** — not a string copied in each generator. All four components (3 generators + Output Verifier Check 3) reference the same constant. A column added to `final.allocation_result` that is added to only one generator creates silent schema divergence in BI tools with no error raised.

---

## Tool Stack by Phase

```
Phase 0 — Infrastructure
  SQL Server + SSMS               DB host · snapshot isolation · index execution plans
  Flyway                          T-SQL migrations · dry-run validation before deploy
  Docker + Compose                FastAPI · Celery · Beat · Redis · SQL Server in one environment
  Redis                           Message broker for Celery + ACK contracts

Phase 1 — Schema
  Flyway T-SQL migrations         13 tables · 28 indexes · 51 check constraints · 4 triggers
  SSMS Execution Plan viewer      Verify index seeks before production

Phases 2–7 — Application Code
  FastAPI + Pydantic v2           API boundary · schema validation · enum enforcement
  Python csv stdlib               Ingestion parsing · CSV export generation
  Pandas + NumPy                  Grain computation · aggregation · KPI pre-compute
  SQLAlchemy + pyodbc             DB interactions · atomic transactions · snapshot reads
  Celery + Celery Beat            Async engine execution · ACK contracts · scheduled retry
  openpyxl                        Excel generation via xlsx skill
  React + TypeScript              UI components · typed enums
  TanStack Query                  Server-state render invariant for button states
  Tailwind CSS                    4-tier GM% color system

Testing
  pytest                          Backend integration tests · 7-step chain test (P1 #32)
  Vitest                          Frontend unit tests · red-tier render · idempotency
  GitHub Actions                  CI gates: P1 #32 passing · 11 config params present · Flyway dry-run
```

---

## Collaboration Model

Each phase follows this sequence — no deviation:

```
1. Confirm active scope in one line before touching any code
2. State the expected output — what the phase must produce
3. You confirm or correct
4. Build the code for that phase only
5. Run the specified tests for that phase
6. Surface test results and any gaps found
7. You review and direct the next move
```

You are in control of every transition. No phase advances without your explicit instruction — even if the phase tests pass. No next step is suggested unprompted.

**What you direct:**
- Which phase to begin
- Whether a phase result is acceptable before advancing
- Any scope adjustments within a phase
- Priority changes if something surfaces mid-build

**What I produce:**
- Code for the active phase only
- Test results against the specified verification criteria for that phase
- Named gaps if a test reveals a design issue not previously captured
- No suggestions until the code is built and the test results are reviewed

---

## Recommendations

**Recommendation 1 — Build Phase 0 and Phase 1 together, before any Python.**

The database schema and infrastructure are not supporting work — they are the control system. The grain, the closure rule, the immutability triggers, and the check constraints are enforced at the database level. Code written before these are in place can produce valid results on valid inputs and invalid results on edge cases — and the difference is undetectable until a specific combination of data triggers the gap. Build the DB first. Test the constraints directly via SQL before any application code touches them.

**Recommendation 2 — Run the sample CSVs from `references/` against every phase.**

The five sample files (`telemetry.csv`, `cost_management.csv`, `iam.csv`, `billing.csv`, `erp.csv`) are already present. Use them as the known-good input for every phase. The expected outputs at each layer can be derived from the computation contract before any code runs — which means every test can be a pass/fail against a predetermined expected value, not just a "did it run without error" check.

**Recommendation 3 — Implement the 7-step integration test (P1 #32) before Phase 6 begins.**

This test is the highest-leverage single test in the system. It verifies the `failed_tenant_id` propagation chain across 4 components and 2 modules — from Identity Broken Record Builder → Cost & Revenue Calculator → Allocation Grain Writer → Customer Data Aggregator → Zone 2R Renderer. If this test is not written and passing before the UI is built, the Risk flag is unverifiable and the CFO approval surface is incomplete. P1 #32 is a pre-deployment CI gate — not a dev test.

**Recommendation 4 — Do not parallelize Phase 3 and Phase 4.**

The Reconciliation Engine's Check 1 and Check 2 run in parallel with the Allocation Engine at runtime — but in implementation, the RE depends on knowing the exact grain structure, the `billing_period` field, and the closure rule behavior before Check 3 can be correctly tested. Build and validate Phase 3 fully first, then build Phase 4 using the real `allocation_grain` output as the test input for Check 3.

**Recommendation 5 — Derive `INGESTION_BATCH_THRESHOLD` and `AE_TIMEOUT` from staging scale tests, not assumptions.**

These two parameters are marked "operator-defined" in the config register because their correct values depend on the actual hardware and volume at staging. `INGESTION_BATCH_THRESHOLD` determines when the Ingestion Commit splits into batched promotes. `AE_TIMEOUT` must be set to 2× the P95 AE completion time at peak volume. Both must be validated before production. An `AE_TIMEOUT` set too low causes legitimate analysis runs to time out and surface as engine failures with no structural cause.

---

## Priority Stack — Summary

```
PHASE 0 — Infrastructure         SQL Server · Redis · Celery Beat · Docker
PHASE 1 — Database Schema        13 tables · Flyway migrations · constraints · triggers
PHASE 2 — Ingestion              session_id established · atomic gate · state UPLOADED
PHASE 3 — Allocation Engine      grain produced · closure enforced · completion signaled
PHASE 4 — Reconciliation Engine  3 boundary checks · Check 3 gated on AE · state ANALYZED
PHASE 5 — State Machine          approval gate · atomic write · APPROVED terminal state
PHASE 6 — UI Screen              7-step integration test before build · server-state render
PHASE 7 — Export                 3 formats · EXPORT_COLUMN_ORDER constant · Output Verifier
```

Each phase has one clear output. Each output has a defined test. No phase advances without direction. The grain is the anchor at every step.

---

*Created: 2026-03-29*
*Updated: 2026-03-29*
*Source: Deep implementation analysis — GPU Gross Margin Visibility Application*
*Reads from: ingestion-module-design.md · allocation-engine-design.md · reconciliation-engine-design.md · state-machine-design.md · ui-screen-design.md · export-module-design.md · db-schema-design.md · references/stabilization-register.md*
