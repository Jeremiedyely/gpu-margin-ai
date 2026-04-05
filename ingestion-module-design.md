---
role: module-design
module: Ingestion
layer: Ingestion
reads-from: requirements.md · software-system-design.md
session-context: Ingestion Module design — 19 components — backward from EMPTY → UPLOADED transition
confirmed: 2026-03-27
suggestion-applied: S1 — Session-scoped atomic commit (Ingestion Commit component)
---

# Ingestion Module Design — GPU Gross Margin Visibility Application

> See: business.md — WHY layer · CFO problem definition
> See: requirements.md — WHAT layer · grain · state machine · source files
> See: software-system-design.md — HOW layer · interaction protocol · anti-drift rules

---

## Scope

**Active scope:** Ingestion Module | Layer: Ingestion
**Output expected:** Five validated source files parsed into raw tables with an ingestion log entry anchoring the session. On success, state transitions EMPTY → UPLOADED. On failure, state does not advance and a named error is surfaced.
**Consumed by:** Allocation Engine · Reconciliation Engine (read from raw tables after UPLOADED)
**Failure behavior:** If a corrupted record enters the raw tables, it propagates into the grain, the KPIs, and the CFO's approved number with no alarm. The ingestion boundary is the last point at which schema and type integrity can be enforced before the data enters the computation pipeline.

---

## Backward Dependency Chain

```
State = UPLOADED + ingestion_log written
              ↑
  State Transition Emitter (EMPTY → UPLOADED)
              ↑
  Ingestion Log Writer
              ↑
  Ingestion Commit  ←── atomic promote (SUCCESS) or session drop (FAIL)
              ↑
  Ingestion Orchestrator  ←── generates session_id · collects all write results
              ↑
  ┌─────────────────────────────────────────────────────────────────────┐
  │  Per file (×5): Validator → Parser → Raw Table Writer               │
  │  Each Raw Table Writer tags rows with session_id from Orchestrator  │
  └─────────────────────────────────────────────────────────────────────┘
              ↑
  Five uploaded CSV files (from UI upload slots)
```

**19 components total:**
- 5 File Validators (Layer 1)
- 5 File Parsers (Layer 2)
- 5 Raw Table Writers (Layer 3) — session-tagged
- 1 Ingestion Orchestrator (Layer 4) — generates session_id
- 1 Ingestion Commit (Layer 4b) — atomic promote or session drop
- 1 Ingestion Log Writer (Layer 5)
- 1 State Transition Emitter (Layer 6)

---

## Source File Schemas

```
File 1 — Telemetry & Metering → raw.telemetry
  tenant_id          : varchar   (required · not null)
  region             : varchar   (required · not null)
  gpu_pool_id        : varchar   (required · not null)
  date               : date      (required · ISO 8601 · not null)
  gpu_hours_consumed : decimal   (required · not null)

File 2 — Cost Management / FinOps → raw.cost_management
  region             : varchar   (required · not null)
  gpu_pool_id        : varchar   (required · not null)
  date               : date      (required · ISO 8601 · not null)
  reserved_gpu_hours : decimal   (required · > 0 · not null)
  cost_per_gpu_hour  : decimal   (required · > 0 · not null)
  Natural key: region + gpu_pool_id + date (no duplicates)

File 3 — IAM / Tenant Management → raw.iam
  tenant_id          : varchar   (required · not null)
  contracted_rate    : decimal   (required · > 0 · not null)
  billing_period     : varchar   (required · not null)
  Natural key: tenant_id + billing_period (no duplicates)

File 4 — Billing System → raw.billing
  tenant_id          : varchar   (required · not null)
  billing_period     : varchar   (required · not null)
  billable_amount    : decimal   (required · not null)
  Natural key: tenant_id + billing_period (no duplicates)

File 5 — ERP / General Ledger → raw.erp
  tenant_id          : varchar   (required · not null)
  billing_period     : varchar   (required · not null)
  amount_posted      : decimal   (required · not null)
  Natural key: tenant_id + billing_period (no duplicates)
```

---

## Component Blocks — 19 Components

---

### Layer 1 — Validation (5 Components)

VALIDATOR COMPLIANCE DECLARATION (L2 P2 #3 — 2026-03-27):
Any new source file added to the ingestion pipeline requires a new validator.
Before that validator is accepted, it must explicitly declare:
  (a) Does this source file contain billing_period?
  (b) If YES: is YYYY-MM format enforcement implemented in this validator?
A validator that omits this declaration is incomplete.

Current billing_period posture by validator:
  Telemetry File Validator    — billing_period NOT in source · enforcement N/A (correct)
  Cost Mgmt File Validator    — billing_period NOT in source · enforcement N/A (correct)
  IAM File Validator          — billing_period IN source · YYYY-MM enforced (correct)
  Billing File Validator      — billing_period IN source · YYYY-MM enforced (correct)
  ERP File Validator          — billing_period IN source · YYYY-MM enforced (correct)

This table must be updated whenever a new source file and validator are added.

---

```
Component:       Telemetry File Validator
Layer:           Ingestion
Input:           uploaded_file_1 : {filename : varchar, content : raw_csv}
                 — from UI Slot 1 (Telemetry & Metering)
Transformation:  IF file format is not valid CSV
                   → validation_result = FAIL · error = "File is not valid CSV"
                 IF any required column is absent:
                   required: tenant_id · region · gpu_pool_id · date · gpu_hours_consumed
                   → validation_result = FAIL · error = "Missing column: [name]"
                 IF any required column contains NULL in any row
                   → validation_result = FAIL · error = "Null value in required field: [name]"
                 IF tenant_id does not match the canonical format pattern
                   → validation_result = FAIL
                   · error = "tenant_id format invalid — found: [value]"
                   Note: The canonical tenant_id format pattern must be documented
                   at deployment time (e.g. UUID v4, alphanumeric-only, etc.) and
                   configured in this validator. The IAM Resolver joins on
                   tenant_id + billing_period — a malformed tenant_id that passes
                   non-null silently fails the IAM join and the row becomes an
                   identity_broken record when it should be Type A. Format
                   rejection at ingestion prevents silent misclassification.
                   (L2 P1 #7 — 2026-03-27)
                 IF gpu_hours_consumed is not castable to decimal
                   → validation_result = FAIL · error = "Type error: gpu_hours_consumed"
                 IF date is not castable to ISO date (YYYY-MM-DD)
                   → validation_result = FAIL · error = "Type error: date"
                 IF file is empty (zero data rows)
                   → validation_result = FAIL · error = "File contains no data rows"
                 IF all checks pass → validation_result = PASS
Output:          telemetry_validation : {result : enum{PASS, FAIL}, error : varchar | NULL}
Feeds:           Telemetry File Parser
Failure path:    IF validation_result = FAIL
                   → do not pass file to parser
                   → surface named error to UI
                   → state remains EMPTY
                   → ingestion does not proceed for any file
```

---

```
Component:       Cost Management File Validator
Layer:           Ingestion
Input:           uploaded_file_2 : {filename : varchar, content : raw_csv}
                 — from UI Slot 2 (Cost Management / FinOps)
Transformation:  IF file format is not valid CSV
                   → validation_result = FAIL · error = "File is not valid CSV"
                 IF any required column is absent:
                   required: region · gpu_pool_id · date · reserved_gpu_hours · cost_per_gpu_hour
                   → validation_result = FAIL · error = "Missing column: [name]"
                 IF any required column contains NULL in any row
                   → validation_result = FAIL · error = "Null value in required field: [name]"
                 IF reserved_gpu_hours or cost_per_gpu_hour not castable to decimal
                   → validation_result = FAIL · error = "Type error: [field]"
                 IF reserved_gpu_hours ≤ 0 in any row
                   → validation_result = FAIL · error = "reserved_gpu_hours must be > 0"
                 IF cost_per_gpu_hour ≤ 0 in any row
                   → validation_result = FAIL · error = "cost_per_gpu_hour must be > 0"
                 IF duplicate natural key (region + gpu_pool_id + date) found
                   → validation_result = FAIL · error = "Duplicate key: region + gpu_pool_id + date"
                 IF file is empty → validation_result = FAIL · error = "File contains no data rows"
                 IF all checks pass → validation_result = PASS
Output:          cost_mgmt_validation : {result : enum{PASS, FAIL}, error : varchar | NULL}
Feeds:           Cost Management File Parser
Failure path:    IF validation_result = FAIL
                   → do not pass file to parser · surface named error · state remains EMPTY
```

---

```
Component:       IAM File Validator
Layer:           Ingestion
Input:           uploaded_file_3 : {filename : varchar, content : raw_csv}
                 — from UI Slot 3 (IAM / Tenant Management)
Transformation:  IF file format is not valid CSV
                   → validation_result = FAIL · error = "File is not valid CSV"
                 IF any required column is absent:
                   required: tenant_id · contracted_rate · billing_period
                   → validation_result = FAIL · error = "Missing column: [name]"
                 IF any required column contains NULL in any row
                   → validation_result = FAIL · error = "Null value in required field: [name]"
                 IF contracted_rate not castable to decimal
                   → validation_result = FAIL · error = "Type error: contracted_rate"
                 IF contracted_rate ≤ 0 in any row
                   → validation_result = FAIL · error = "contracted_rate must be > 0"
                 IF any billing_period value does not match YYYY-MM format
                   → validation_result = FAIL
                   · error = "billing_period must be YYYY-MM format — found: [value]"
                   (enforces system-wide billing_period contract required by
                    IAM Resolver in Allocation Engine — S1 confirmed 2026-03-27)
                 IF duplicate natural key (tenant_id + billing_period) found
                   → validation_result = FAIL · error = "Duplicate key: tenant_id + billing_period"
                 IF file is empty → validation_result = FAIL · error = "File contains no data rows"
                 IF all checks pass → validation_result = PASS
Output:          iam_validation : {result : enum{PASS, FAIL}, error : varchar | NULL}
Feeds:           IAM File Parser
Failure path:    IF validation_result = FAIL
                   → do not pass file to parser · surface named error · state remains EMPTY
```

---

```
Component:       Billing File Validator
Layer:           Ingestion
Input:           uploaded_file_4 : {filename : varchar, content : raw_csv}
                 — from UI Slot 4 (Billing System)
Transformation:  IF file format is not valid CSV
                   → validation_result = FAIL · error = "File is not valid CSV"
                 IF any required column is absent:
                   required: tenant_id · billing_period · billable_amount
                   → validation_result = FAIL · error = "Missing column: [name]"
                 IF any required column contains NULL in any row
                   → validation_result = FAIL · error = "Null value in required field: [name]"
                 IF billable_amount not castable to decimal
                   → validation_result = FAIL · error = "Type error: billable_amount"
                 IF any billing_period value does not match YYYY-MM format
                   → validation_result = FAIL
                   · error = "billing_period must be YYYY-MM format — found: [value]"
                   (enforces system-wide billing_period contract required by
                    Check 3 Executor in Reconciliation Engine — confirmed 2026-03-27)
                 IF duplicate natural key (tenant_id + billing_period) found
                   → validation_result = FAIL · error = "Duplicate key: tenant_id + billing_period"
                 IF file is empty → validation_result = FAIL · error = "File contains no data rows"
                 IF all checks pass → validation_result = PASS
Output:          billing_validation : {result : enum{PASS, FAIL}, error : varchar | NULL}
Feeds:           Billing File Parser
Failure path:    IF validation_result = FAIL
                   → do not pass file to parser · surface named error · state remains EMPTY
```

---

```
Component:       ERP File Validator
Layer:           Ingestion
Input:           uploaded_file_5 : {filename : varchar, content : raw_csv}
                 — from UI Slot 5 (ERP / General Ledger)
Transformation:  IF file format is not valid CSV
                   → validation_result = FAIL · error = "File is not valid CSV"
                 IF any required column is absent:
                   required: tenant_id · billing_period · amount_posted
                   → validation_result = FAIL · error = "Missing column: [name]"
                 IF any required column contains NULL in any row
                   → validation_result = FAIL · error = "Null value in required field: [name]"
                 IF amount_posted not castable to decimal
                   → validation_result = FAIL · error = "Type error: amount_posted"
                 IF any billing_period value does not match YYYY-MM format
                   → validation_result = FAIL
                   · error = "billing_period must be YYYY-MM format — found: [value]"
                   (enforces system-wide billing_period contract required by
                    Check 3 Executor in Reconciliation Engine — confirmed 2026-03-27)
                 IF duplicate natural key (tenant_id + billing_period) found
                   → validation_result = FAIL · error = "Duplicate key: tenant_id + billing_period"
                 IF file is empty → validation_result = FAIL · error = "File contains no data rows"
                 IF all checks pass → validation_result = PASS
Output:          erp_validation : {result : enum{PASS, FAIL}, error : varchar | NULL}
Feeds:           ERP File Parser
Failure path:    IF validation_result = FAIL
                   → do not pass file to parser · surface named error · state remains EMPTY
```

---

### Layer 2 — Parsing (5 Components)

---

```
Component:       Telemetry File Parser
Layer:           Ingestion
Input:           telemetry_validation = PASS · uploaded_file_1 : raw_csv
Transformation:  Parse each row and cast to typed record:
                   tenant_id          : varchar
                   region             : varchar
                   gpu_pool_id        : varchar
                   date               : date (ISO 8601)
                   gpu_hours_consumed : decimal
                 IF any row fails casting after validation pass
                   → parsing_result = FAIL · error = "Parse error at row [n]: [field]"
                 IF all rows parse → parsing_result = PASS
Output:          telemetry_parsed : {
                   result  : enum{PASS, FAIL},
                   records : [{tenant_id, region, gpu_pool_id, date, gpu_hours_consumed}],
                   error   : varchar | NULL
                 }
Feeds:           Telemetry Raw Table Writer
Failure path:    IF parsing_result = FAIL
                   → do not pass records to writer · surface named error · state remains EMPTY
```

---

```
Component:       Cost Management File Parser
Layer:           Ingestion
Input:           cost_mgmt_validation = PASS · uploaded_file_2 : raw_csv
Transformation:  Parse each row and cast to typed record:
                   region             : varchar
                   gpu_pool_id        : varchar
                   date               : date (ISO 8601)
                   reserved_gpu_hours : decimal
                   cost_per_gpu_hour  : decimal
                 IF any row fails casting → parsing_result = FAIL · error = "Parse error at row [n]: [field]"
                 IF all rows parse → parsing_result = PASS
Output:          cost_mgmt_parsed : {
                   result  : enum{PASS, FAIL},
                   records : [{region, gpu_pool_id, date, reserved_gpu_hours, cost_per_gpu_hour}],
                   error   : varchar | NULL
                 }
Feeds:           Cost Management Raw Table Writer
Failure path:    IF parsing_result = FAIL → do not pass records · surface named error · state remains EMPTY
```

---

```
Component:       IAM File Parser
Layer:           Ingestion
Input:           iam_validation = PASS · uploaded_file_3 : raw_csv
Transformation:  Parse each row and cast to typed record:
                   tenant_id       : varchar
                   contracted_rate : decimal
                   billing_period  : varchar
                 IF any row fails casting → parsing_result = FAIL · error = "Parse error at row [n]: [field]"
                 IF all rows parse → parsing_result = PASS
Output:          iam_parsed : {
                   result  : enum{PASS, FAIL},
                   records : [{tenant_id, contracted_rate, billing_period}],
                   error   : varchar | NULL
                 }
Feeds:           IAM Raw Table Writer
Failure path:    IF parsing_result = FAIL → do not pass records · surface named error · state remains EMPTY
```

---

```
Component:       Billing File Parser
Layer:           Ingestion
Input:           billing_validation = PASS · uploaded_file_4 : raw_csv
Transformation:  Parse each row and cast to typed record:
                   tenant_id       : varchar
                   billing_period  : varchar
                   billable_amount : decimal
                 IF any row fails casting → parsing_result = FAIL · error = "Parse error at row [n]: [field]"
                 IF all rows parse → parsing_result = PASS
Output:          billing_parsed : {
                   result  : enum{PASS, FAIL},
                   records : [{tenant_id, billing_period, billable_amount}],
                   error   : varchar | NULL
                 }
Feeds:           Billing Raw Table Writer
Failure path:    IF parsing_result = FAIL → do not pass records · surface named error · state remains EMPTY
```

---

```
Component:       ERP File Parser
Layer:           Ingestion
Input:           erp_validation = PASS · uploaded_file_5 : raw_csv
Transformation:  Parse each row and cast to typed record:
                   tenant_id      : varchar
                   billing_period : varchar
                   amount_posted  : decimal
                 IF any row fails casting → parsing_result = FAIL · error = "Parse error at row [n]: [field]"
                 IF all rows parse → parsing_result = PASS
Output:          erp_parsed : {
                   result  : enum{PASS, FAIL},
                   records : [{tenant_id, billing_period, amount_posted}],
                   error   : varchar | NULL
                 }
Feeds:           ERP Raw Table Writer
Failure path:    IF parsing_result = FAIL → do not pass records · surface named error · state remains EMPTY
```

---

### Layer 3 — Raw Table Writes (5 Components)

All five writers receive session_id from the Ingestion Orchestrator.
Every row written is tagged with session_id — staged, not yet active.

DEPLOYMENT REQUIREMENT (L2 P2 #2 — 2026-03-27):
Each writer must target its own dedicated raw table with an independent write
connection. No shared connection path between the 5 writers. If writers share a
connection pool or compete for the same write channel, throughput degrades to
effectively serial — the slowest writer (typically Telemetry, the largest table)
determines total ingestion window. Confirm connection isolation before production
deployment.

---

```
Component:       Telemetry Raw Table Writer
Layer:           Ingestion
Input:           telemetry_parsed : {result = PASS, records},
                 session_id : uuid — from Ingestion Orchestrator
                 Contract: session_id is a HARD DEPENDENCY for this writer.
                 Writing without session_id is a contract violation — all staged
                 rows must carry session_id from write time. session_id is generated
                 and passed by the Ingestion Orchestrator. If this writer is ever
                 independently deployed or refactored, session_id must be explicitly
                 re-declared as an input. (L2 P2 #4 — 2026-03-27)
Transformation:  IF telemetry_parsed.result = PASS
                   → write all records to raw.telemetry
                     tagged with session_id (staged · not yet active)
                   → write is atomic: all rows written or none
                   → write_result = SUCCESS · row_count = n
                 ELSE → do not execute write
Output:          telemetry_write : {result : enum{SUCCESS, FAIL},
                                    session_id : uuid, row_count : integer}
Feeds:           Ingestion Orchestrator
Failure path:    IF write fails mid-execution
                   → attempt rollback of any partial rows for this session_id
                   → write_result = FAIL · error = "Write failed: raw.telemetry"
                   → Ingestion Orchestrator triggers session drop via Ingestion Commit
```

---

```
Component:       Cost Management Raw Table Writer
Layer:           Ingestion
Input:           cost_mgmt_parsed : {result = PASS, records} · session_id : uuid
                 Contract: session_id is a HARD DEPENDENCY. Writing without it is a
                 contract violation. Passed by Ingestion Orchestrator. (L2 P2 #4)
Transformation:  IF result = PASS → write all records to raw.cost_management
                   tagged with session_id (staged) · atomic · write_result = SUCCESS
                 ELSE → do not execute write
Output:          cost_mgmt_write : {result : enum{SUCCESS, FAIL}, session_id : uuid, row_count : integer}
Feeds:           Ingestion Orchestrator
Failure path:    IF write fails → write_result = FAIL · error = "Write failed: raw.cost_management"
                   → Orchestrator triggers session drop
```

---

```
Component:       IAM Raw Table Writer
Layer:           Ingestion
Input:           iam_parsed : {result = PASS, records} · session_id : uuid
                 Contract: session_id is a HARD DEPENDENCY. Writing without it is a
                 contract violation. Passed by Ingestion Orchestrator. (L2 P2 #4)
Transformation:  IF result = PASS → write all records to raw.iam
                   tagged with session_id (staged) · atomic · write_result = SUCCESS
                 ELSE → do not execute write
Output:          iam_write : {result : enum{SUCCESS, FAIL}, session_id : uuid, row_count : integer}
Feeds:           Ingestion Orchestrator
Failure path:    IF write fails → write_result = FAIL · error = "Write failed: raw.iam"
                   → Orchestrator triggers session drop
```

---

```
Component:       Billing Raw Table Writer
Layer:           Ingestion
Input:           billing_parsed : {result = PASS, records} · session_id : uuid
                 Contract: session_id is a HARD DEPENDENCY. Writing without it is a
                 contract violation. Passed by Ingestion Orchestrator. (L2 P2 #4)
Transformation:  IF result = PASS → write all records to raw.billing
                   tagged with session_id (staged) · atomic · write_result = SUCCESS
                 ELSE → do not execute write
Output:          billing_write : {result : enum{SUCCESS, FAIL}, session_id : uuid, row_count : integer}
Feeds:           Ingestion Orchestrator
Failure path:    IF write fails → write_result = FAIL · error = "Write failed: raw.billing"
                   → Orchestrator triggers session drop
```

---

```
Component:       ERP Raw Table Writer
Layer:           Ingestion
Input:           erp_parsed : {result = PASS, records} · session_id : uuid
                 Contract: session_id is a HARD DEPENDENCY. Writing without it is a
                 contract violation. Passed by Ingestion Orchestrator. (L2 P2 #4)
Transformation:  IF result = PASS → write all records to raw.erp
                   tagged with session_id (staged) · atomic · write_result = SUCCESS
                 ELSE → do not execute write
Output:          erp_write : {result : enum{SUCCESS, FAIL}, session_id : uuid, row_count : integer}
Feeds:           Ingestion Orchestrator
Failure path:    IF write fails → write_result = FAIL · error = "Write failed: raw.erp"
                   → Orchestrator triggers session drop
```

---

### Layer 4 — Orchestration

---

```
Component:       Ingestion Orchestrator
Layer:           Ingestion
Input:           telemetry_write · cost_mgmt_write · iam_write
                 · billing_write · erp_write — all five write results
Note:            session_id is generated HERE before any writes begin.
                 It is passed to all five Raw Table Writers so every
                 staged row carries it from write time.
Transformation:  Generate session_id : uuid BEFORE writes begin
                 IF ALL five write results = SUCCESS
                   → orchestration_result = SUCCESS
                   → pass session_id + source_files to Ingestion Commit
                 IF ANY write result = FAIL
                   → orchestration_result = FAIL
                   → pass session_id to Ingestion Commit for session drop
                   → collect all named errors · surface consolidated list to UI
Output:          orchestration_payload : {
                   result       : enum{SUCCESS, FAIL},
                   session_id   : uuid,
                   source_files : [varchar × 5] | NULL,
                   errors       : [varchar] | NULL
                 }
Feeds:           Ingestion Commit
Failure path:    IF session_id cannot be generated
                   → orchestration_result = FAIL · error = "Session ID generation failed"
                   → do not initiate any writes · state remains EMPTY
```

---

```
Component:       Ingestion Commit
Layer:           Ingestion
Input:           orchestration_payload : {result, session_id, source_files, errors}
Transformation:  IF orchestration_result = SUCCESS
                   → PRE-SCAN (W-6 FIX — L1 Run 4 · 2026-03-27):
                     Before issuing STEP 1, query all five raw tables to identify
                     any existing active rows NOT tagged with current session_id.
                     Collect the distinct session_id values found — stored as
                     prior_session_ids : [uuid] (may be empty if no prior active data).
                     This pre-scan is required so that [prior_session_ids] can be
                     surfaced in the STEP 1 failure path error message for operator
                     diagnosis. Without this step, prior_session_ids is unknown at
                     failure time and the operator message is incomplete.
                     If pre-scan itself fails (table unreadable):
                       → prior_session_ids = UNKNOWN
                       → proceed to STEP 1 as normal — failure path uses
                         "prior active sessions: UNKNOWN" if STEP 1 fails
                     (Previously: the failure path error message referenced
                      [prior_session_ids] with no declared read step to produce it.
                      Implementers had no mechanism to populate the value.)
                   → STEP 1 — replacement: drop all existing active rows across
                     all five raw tables that are NOT tagged with current session_id
                     (single atomic operation — all five tables cleared of prior
                     active rows or none are cleared)
                     Guarantee: only one session's data is ever active at a time.
                     This prevents engine reads from aggregating multiple sessions
                     if a prior session's data was promoted but its log write failed.
                     IF prior active row drop fails
                       → commit_result = FAIL
                       · reason = "Prior session cleanup failed — cannot promote
                                   new session [session_id] safely"
                       → do not proceed to STEP 2
                       → state remains EMPTY
                   → STEP 2 — promote all rows tagged with session_id
                     across all five raw tables to active dataset
                   → single atomic operation — all promoted or none
                   → commit_result = SUCCESS
                 IF orchestration_result = FAIL
                   → delete all rows tagged with session_id
                     across all five raw tables
                   → single atomic operation — complete session drop
                   → commit_result = FAIL · reason = "Session [session_id] dropped"
                   → no partial data survives in any raw table
Output:          commit_result : {result : enum{SUCCESS, FAIL},
                                  session_id : uuid,
                                  reason : varchar | NULL}
Feeds:           Ingestion Log Writer (if SUCCESS)
Failure path:    IF prior active row drop fails (STEP 1)
                   → commit_result = FAIL
                   · reason = "Prior session cleanup failed for session [current_session_id]"
                   → state remains EMPTY · do not proceed to log write
                   → surface "Upload could not complete — prior session data
                               could not be cleared. Contact support with
                               current session ID: [current_session_id]
                               and prior active session(s) detected: [prior_session_ids]"
                   Note (L2 P2 #5): [prior_session_ids] = set of session_id values
                   found in active rows across the 5 raw tables at STEP 1 execution
                   time. These are the sessions whose rows were targeted for removal.
                   Both the current and prior session_ids are required for operator
                   cleanup — [current_session_id] identifies the failed new session's
                   staged rows; [prior_session_ids] identifies the orphaned prior data.
                   (L2 P2 #5 — 2026-03-27)
                 IF atomic promotion fails (STEP 2)
                   → attempt session drop of new session's staged rows
                   → if drop also fails
                     → surface "Critical: manual cleanup required for session [session_id]"
                   → state remains EMPTY · do not proceed to log write
Manual cleanup runbook (L2 P2 #6 — 2026-03-27):
                 When promote fails AND drop also fails, an operator must clean up
                 manually before the analyst can re-upload. Steps:
                   Step 1: Identify all rows WHERE session_id = [failed_session_id]
                           across all 5 raw tables (raw.telemetry · raw.cost_management
                           · raw.iam · raw.billing · raw.erp)
                   Step 2: Confirm none of these rows are in active (promoted) state
                           — they should be staged rows only. If any are active,
                           escalate before proceeding.
                   Step 3: DELETE all staged rows for session_id = [failed_session_id]
                           from all 5 tables. Confirm row count = 0 in each table
                           for that session_id after deletion.
                   Step 4: Confirm raw.ingestion_log has NO entry for [failed_session_id].
                           If a log entry exists, it must also be removed to prevent
                           a ghost session from appearing in export metadata.
                   Step 5: State remains EMPTY. Confirm application_state = EMPTY in
                           State Store. The analyst may now re-upload cleanly.
                 After runbook completion: notify analyst that re-upload is clear.
Scale note:      At production row counts (e.g. 50M+ telemetry rows), atomic
                 promotion across 5 tables simultaneously holds write locks for
                 the full insert duration — lock duration grows linearly with row
                 count and may exceed DB lock timeout.
                 THRESHOLD: When any single raw table exceeds [T] rows in the
                 current session, split STEP 2 into batched commits per table
                 (e.g. batch size = 1M rows). The threshold value must be
                 documented and tuned per deployment environment.
                 Session-scoped fence: fence is removed only after all 5 tables
                 confirm batch completion — all-or-nothing semantics are
                 preserved at the session level.
                 Lock duration per table is bounded to batch size, not total rows.
                 STEP 1 (drop prior active rows) is not batched — it targets rows
                 by session_id WHERE clause and is fast regardless of table size.
                 (L2 P1 #1 — 2026-03-27)
```

---

### Layer 5 — Log Write

---

```
Component:       Ingestion Log Writer
Layer:           Ingestion
Input:           commit_result : {result = SUCCESS, session_id},
                 orchestration_payload : {source_files}
Transformation:  IF commit_result = SUCCESS
                   → write one row to raw.ingestion_log:
                     session_id           : uuid
                     source_files         : varchar (JSON array of filenames)
                     ingestion_timestamp  : timestamp (server time at write)
                     status               : 'SUCCESS'
                   → log_write_result = SUCCESS
                 ELSE → do not write
Output:          log_write : {result : enum{SUCCESS, FAIL},
                              session_id : uuid | NULL}
Feeds:           State Transition Emitter
Failure path:    IF log write fails
                   → log_write_result = FAIL
                   · error = "Ingestion log write failed"
                   → surface error to UI · state remains EMPTY
                   → raw table writes are NOT rolled back
                     (data is present — log failure is recoverable on retry)
```

---

### Layer 6 — State Transition

---

```
Component:       State Transition Emitter (EMPTY → UPLOADED)
Layer:           Ingestion
Input:           log_write : {result = SUCCESS, session_id : uuid}
Transformation:  IF log_write.result = SUCCESS
                   → emit state_transition_signal:
                     {signal               = 'FIRE',
                      requested_transition = 'EMPTY→UPLOADED',
                      source               = 'INGESTION',
                      session_id           = log_write.session_id}
                   → forward to State Machine (Transition Request Receiver)
                 ELSE → do not emit · do not contact State Machine
                        failure surfaced directly to UI (see Failure path)
Output:          state_transition_signal : {
                   signal               : enum{FIRE},
                   requested_transition : varchar,
                   source               : varchar,
                   session_id           : uuid
                 }
                 — emitted ONLY when log_write.result = SUCCESS
                 — no signal emitted on FAIL · State Machine is not contacted
Feeds:           State Machine (Transition Request Receiver) — on FIRE only
Failure path:    IF log_write.result = FAIL
                   → do not emit state_transition_signal
                   → do not contact State Machine
                   → surface error directly to UI:
                     "Ingestion did not complete — re-upload files"
                   → state remains EMPTY
```

---

## STEP 4 — Problem-to-Design Analysis

```
Problem:          GPU gross margin is corrupted because upstream systems
                  each look clean in isolation — but when their outputs are
                  combined across system boundaries, inconsistencies flow
                  directly into the gross margin calculation. The ingestion
                  boundary is where those five independent sources first
                  make contact. If a corrupted record enters the raw tables,
                  it propagates into the grain, the KPIs, and the CFO's
                  approved number with no alarm.

Required output:  Five clean, typed raw tables — one per source system —
                  with an immutable ingestion log entry binding all five
                  to a single session_id. If any file fails at any layer,
                  the state does not advance and a named error is surfaced.
                  No partial ingestion. No silent failures.

Design produces:  19 components across six layers. Validation fires before
                  parsing. Parsing fires before writing. Writing is
                  session-tagged (staged, not yet active). The Orchestrator
                  generates session_id before writes begin and collects all
                  five results. The Ingestion Commit promotes atomically on
                  SUCCESS or drops the entire session on FAIL — no partial
                  data survives. The log write anchors the session before
                  state advances. The State Transition Emitter only fires
                  on a confirmed log write.

Gap or match:     MATCH. Gap identified in STEP 4 (undefined rollback
                  ordering) closed by S1 (Ingestion Commit — atomic
                  session-scoped promote or drop).
```

---

## Component Summary

| # | Component | Layer | Feeds |
|---|-----------|-------|-------|
| 1 | Telemetry File Validator | Ingestion | Telemetry File Parser |
| 2 | Cost Management File Validator | Ingestion | Cost Management File Parser |
| 3 | IAM File Validator | Ingestion | IAM File Parser |
| 4 | Billing File Validator | Ingestion | Billing File Parser |
| 5 | ERP File Validator | Ingestion | ERP File Parser |
| 6 | Telemetry File Parser | Ingestion | Telemetry Raw Table Writer |
| 7 | Cost Management File Parser | Ingestion | Cost Management Raw Table Writer |
| 8 | IAM File Parser | Ingestion | IAM Raw Table Writer |
| 9 | Billing File Parser | Ingestion | Billing Raw Table Writer |
| 10 | ERP File Parser | Ingestion | ERP Raw Table Writer |
| 11 | Telemetry Raw Table Writer | Ingestion | Ingestion Orchestrator |
| 12 | Cost Management Raw Table Writer | Ingestion | Ingestion Orchestrator |
| 13 | IAM Raw Table Writer | Ingestion | Ingestion Orchestrator |
| 14 | Billing Raw Table Writer | Ingestion | Ingestion Orchestrator |
| 15 | ERP Raw Table Writer | Ingestion | Ingestion Orchestrator |
| 16 | Ingestion Orchestrator | Ingestion | Ingestion Commit |
| 17 | Ingestion Commit | Ingestion | Ingestion Log Writer |
| 18 | Ingestion Log Writer | Ingestion | State Transition Emitter |
| 19 | State Transition Emitter | Ingestion | State Machine |
