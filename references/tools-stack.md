# GPU Gross Margin Visibility — Diagnostic-Informed Tools Stack

> All tool choices traced to diagnostic findings · 71 findings resolved · 0 open · 2026-03-27

**🔴 19 P1 Production Blockers — Applied** · **🟡 30 P2 Reliability Risks — Applied** · **🔵 2 P3 Improvements — Applied** · **✅ 71 / 71 Resolved** · **⚙️ 11 Configurable Parameters**

---

## Technology Layers

*7 layers · each tool annotated with driving diagnostic findings*

### Layer 1 — Presentation Layer
*CFO-facing UI · 2 screens · 3 zones*

**React + TypeScript**
Component framework. Typed contracts enforce gm_color 4-tier enum and reason_code propagation at compile time, preventing runtime type mismatches found in L1 Run 1 and P2 #36.
`P1 #34 button state` `P2 #36 gm_color 4-tier`

**Tailwind CSS**
Utility-first styling. 4-tier GM color system (red/orange/yellow/green) maps directly to Tailwind utilities. Red tier added for GM% < 0 (C-1 Run 1, P2 #36).
`P2 #36 red tier required`

**TanStack Query**
Server-state synchronization. Enforces P1 #34: button states derived from server-side application_state on every render, never from local state or cached values. Prevents approval button activating on stale cache after page reload.
`P1 #34 server-state render` `P2 #30 KPI cache reads` `P2 #31 SET artifact reads`

**Vitest**
Frontend unit tests. Mandatory cases: gm_color red tier render (P2 #36), ALREADY_COMPLETE idempotency (P3 #28), session_id in error and confirmation messages (P2 #33, P3 #35).
`P2 #36 visual encoding` `P3 #28 idempotency` `P3 #35 session_id confirm`

---

### Layer 2 — API / Backend Layer
*Request routing · validation boundary · session management*

**FastAPI**
Async Python web framework. Handles ingestion multipart upload routing and state transition signal dispatch. Async support enables non-blocking engine dispatch while awaiting ACK (P1 #29 — DISPATCH_ACK_TIMEOUT contract).
`P1 #29 dispatch ACK`

**Pydantic v2**
Schema validation at the API boundary. Enforces: billing_period YYYY-MM format (5 ingestion validators), enumerated trigger set for state_history writes (P2 #24), reason_code enum on gate responses (P2 #27), gm_color 4-tier enum (P2 #36), ALREADY_COMPLETE response type (P3 #28). Non-enumerated values rejected at write boundary.
`P2 #24 trigger enum` `P2 #27 reason_code enum` `P2 #36 gm_color enum`

**Python csv stdlib**
CSV parsing at ingestion boundary. Validates delimiter, encoding, column presence before raw table write. Stateless — no shared buffer between sessions, preventing cross-session contamination.
`P1 #1 batch threshold`

**UUID v4 (stdlib)**
session_id generation at Ingestion Orchestrator. Primary cross-module correlation key (K1 contract). Generated once per ingestion, propagated to all 6 modules atomically at registration.
`K1 contract: session_id`

---

### Layer 3 — Computation Engine Layer
*Allocation · Reconciliation · grain production*

**Pandas + NumPy**
Grain computation. Telemetry aggregation, IAM resolution, Type A/B record building, Closure Rule enforcement, KPI and SET pre-computation at ANALYZED time (P2 #30, P2 #31 — immutable session-level cache artifacts). INGESTION_BATCH_THRESHOLD governs chunk size for large uploads.
`P1 #1 batch threshold` `P1 #17 snapshot read` `P2 #30 KPI pre-compute` `P2 #31 SET pre-build`

**Celery**
Async task queue. Powers: (1) AE and RE parallel execution on separate queues, (2) APPROVED Session Closer scheduled background retry (P1 #25 — CLOSER_RETRY_INTERVAL / CLOSER_MAX_RETRIES), (3) Analysis Dispatcher ACK timeout enforcement (P1 #29 — DISPATCH_ACK_TIMEOUT), (4) XLSX generation with timeout ceiling (P2 #38 — XLSX_GENERATION_TIMEOUT).
`P1 #25 scheduled retry` `P1 #29 ACK timeout` `P2 #38 XLSX timeout`

**SQLAlchemy (ORM) + pyodbc**
DB interaction layer using SQL Server dialect via pyodbc driver (`mssql+pyodbc://`). Enforces dedicated write connection per Raw Table Writer (Prerequisite 3). Handles atomic transactions: Ingestion Commit 2-step promote (P1 #1), Component 9 dual-field APPROVED + write_result write (P1 #26 — crash window eliminated), grain ROLLBACK on write failure.
`P1 #26 atomic write` `P1 #1 5 write channels`

---

### Layer 4 — Data Storage Layer
*State · grain · raw tables · session history*

**SQL Server (SSMS)**
Primary relational store. Hosts: 5 raw tables per session, allocation_grain, State Store, state_history. CRITICAL: must be configured with snapshot isolation on raw.telemetry via `ALTER DATABASE ... SET ALLOW_SNAPSHOT_ISOLATION ON` and `SET TRANSACTION ISOLATION LEVEL SNAPSHOT` (P1 #17 — concurrent AE/RE reads cause dirty aggregation). Composite index on raw.iam(tenant_id, billing_period) required (P1 #8 — IAM Resolver full-scan prevention). Managed and monitored via SQL Server Management Studio (SSMS). Both are deployment prerequisites, not code changes.
`P1 #17 snapshot isolation` `P1 #8 composite index` `Prereq: DB config before prod`

**Flyway**
SQL Server schema migration management. Versioned T-SQL migration scripts must cover: (1) `ALLOW_SNAPSHOT_ISOLATION ON` on raw.telemetry database, (2) composite index on raw.iam(tenant_id, billing_period), (3) CHECK constraint enforcing enumerated trigger values on state_history (P2 #24 — DB-level constraint), (4) write_result column on State Store schema (P1 #26). Flyway migration dry-run (`flyway validate`) is a required CI gate before production deployment. Compatible with SQLAlchemy pyodbc dialect.
`Prereq: index + isolation` `P2 #24 trigger constraint` `P1 #26 write_result field`

---

### Layer 5 — Async / Signal Layer
*Engine dispatch · ACK contracts · completion signals*

**Redis**
Message broker and ACK coordination. Powers Celery task queues and enforces two ACK contracts: (1) Analysis Dispatcher → AE/RE run_signal with DISPATCH_ACK_TIMEOUT (P1 #29), (2) AE Completion Emitter → RE Completion Listener + SM Engine Completion Collector with DISPATCH_MAX_RETRIES (W-5 Run 4). 4 distinct arrival scenarios logged with collection_source_hint from Dispatcher (P2 #25).
`P1 #29 dispatch ACK` `P1 #15 completion ACK` `P2 #25 4-scenario labels`

**Celery Beat**
Scheduled task runner. Exclusively required for APPROVED Session Closer retry (P1 #25). Reason: after APPROVED, no further requests arrive for that session_id — retry cannot be triggered by incoming requests. Beat fires at CLOSER_RETRY_INTERVAL (60s) up to CLOSER_MAX_RETRIES (5) before CRITICAL alert.
`P1 #25 terminal retry`

**Prometheus + AlertManager**
Observability and alerting. Required alert channels: (1) CLOSER_MAX_RETRIES exhausted → CRITICAL (silent terminal security gap), (2) signal loss scenario (P2 #25) → infrastructure channel (distinct from engine timeout channel), (3) MAX_EXPORT_RERUNS exhausted (P2 #37) → named error with session_id.
`P1 #25 CRITICAL alert` `P2 #25 scenario routing` `P2 #37 rerun exhaustion`

---

### Layer 6 — Export Generation Layer
*CSV · XLSX · Power BI · dual-gate verification*

**openpyxl**
XLSX generation. Invoked with XLSX_GENERATION_TIMEOUT (P2 #38, default 120s) to prevent indefinite blocking on large datasets. Column order governed by EXPORT_COLUMN_ORDER shared constant (P1 #39) — 15 fields, session_id and source_files last. Timeout triggers named error with CSV fallback suggestion.
`P1 #39 column order constant` `P2 #38 XLSX timeout`

**Python csv stdlib**
CSV generation. Uses EXPORT_COLUMN_ORDER constant (P1 #39) — same 15-field order enforced across all 3 formats. unallocated_type enum validated case-sensitively by Output Verifier Check 4 (P1 #43 — 'CAPACITY_IDLE' uppercase must be rejected).
`P1 #39 shared constant` `P1 #43 enum case check`

**Output Verifier (custom)**
6-check post-generation gate. Check 4 upgraded from presence to enumeration: 'capacity_idle' | 'identity_broken' case-sensitive only (P1 #43). MAX_EXPORT_RERUNS=3 prevents infinite retry (P2 #37). Atomic filepath handoff to Delivery Handler — no intermediate move/rename after verification (P2 #41). BLOCKED reason routing via reason_code enum (P2 #42 + P2 #27).
`P1 #43 enum validation` `P2 #37 MAX_EXPORT_RERUNS` `P2 #41 atomic handoff` `P2 #42 reason routing`

**Export Gate Enforcer (custom)**
Dual-condition gate: state = APPROVED AND write_result = SUCCESS. Condition ordering fixed (P1 #27): NULL evaluated first (C3), explicit FAIL second (C4) — prevents NULL surfacing wrong reason. reason_code enum (P2 #27): GATE_OPEN · GATE_BLOCKED_NOT_APPROVED · GATE_BLOCKED_WRITE_NULL · GATE_BLOCKED_WRITE_FAILED · GATE_BLOCKED_STATE_UNREADABLE. Consumer (APPROVED State Gate) updated simultaneously to consume reason_code (W-3 Run 4).
`P1 #27 condition order` `P2 #27 reason_code enum`

---

### Layer 7 — Infrastructure / Testing / CI Layer
*Containerization · tests · deployment gates*

**Docker + Compose**
Container environment. Compose orchestrates: FastAPI, Celery workers, Celery Beat, Redis, SQL Server. Celery Beat container is mandatory (not optional) — P1 #25 APPROVED Session Closer requires it in production.
`P1 #25 Beat mandatory`

**pytest**
Backend integration tests. Mandatory test cases from diagnostic findings: (1) P1 #32 — 7-step failed_tenant_id propagation chain integration test (pre-deployment CI gate), (2) P1 #26 — State Machine restart after APPROVED, verify Export Gate returns OPEN, (3) P1 #43 — inject 'CAPACITY_IDLE' uppercase, verify Check 4 rejection, (4) P3 #28 — idempotency on duplicate transition signals, (5) P2 #37 — verify MAX_EXPORT_RERUNS halt.
`P1 #32 integration gate` `P1 #26 restart test` `P1 #43 enum injection`

**GitHub Actions**
CI/CD pipeline. Pre-deployment gates: (1) P1 #32 integration test passing, (2) config file review for all 11 parameters present, (3) Flyway migration dry-run (snapshot isolation + composite index), (4) RE timeout validation vs AE P95 + Check 3 P95 (Prereq 6). Pipeline blocks deployment if any gate fails.
`6 deployment prereqs` `11 params in config`

---

## Module Diagnostic Findings

*L2 Production Stabilization · all applied · severity by module*

🔴 P1 = Production Blocker · 🟡 P2 = Reliability Risk · 🔵 P3 = Improvement · ✅ All Applied

---

### Module 1 — Ingestion
**P1 ×4 · P2 ×5**

| ID | Root Cause | Fix |
|----|-----------|-----|
| 🔴 P1 #1 | Ingestion Commit: no batch threshold → single atomic promote of 100K+ rows can corrupt or block. | ✅ INGESTION_BATCH_THRESHOLD — operator-defined at staging scale test |
| 🔴 P1 #2 | billing_period not enforced to YYYY-MM at IAM/Billing/ERP validators. Wrong format → AE Billing Period Deriver produces corrupt grain keys. | ✅ 5 validators each enforce YYYY-MM regex before raw table write |
| 🔴 P1 #7 | Ingestion Orchestrator: session_id generated but not atomically registered before downstream use. | ✅ Atomic session_id registration at Orchestrator boundary |
| 🔴 W-6 R4 | Ingestion Commit error message prescribes [prior_session_ids] but no PRE-SCAN step declared to collect them (prose-only enforcement). | ✅ PRE-SCAN step added; fallback to "UNKNOWN" if pre-scan fails |
| 🟡 P2 #2–#6 | 5 Raw Table Writers sharing connection pool — writes can interleave between sessions. Log Writer format undeclared. State Transition Emitter timing ambiguity. | ✅ Dedicated write connection per writer; Log Writer format declared; emitter timing fixed |

---

### Module 2 — Allocation Engine
**P1 ×5 · P2 ×4**

| ID | Root Cause | Fix |
|----|-----------|-----|
| 🔴 P1 #8 | IAM Resolver full-scan on raw.iam — no index. At scale (100K+ rows), query grows linearly, pushing AE past AE_TIMEOUT. | ✅ Composite index on raw.iam(tenant_id, billing_period) — deployment prerequisite |
| 🔴 P1 #9 | Closure Rule Enforcer: SUM(gpu_hours) ≠ reserved_gpu_hours had no prescribed action — silent variance accepted into grain. | ✅ Closure Rule violation → FAIL AE run; reason surfaced to SM |
| 🔴 P1 #10 | failed_tenant_id pass-through invariant not enforced — IB Builder could drop failed_tenant_id before Cost & Revenue Calculator. | ✅ Required Field Checklist with failed_tenant_id as mandatory pass-through |
| 🔴 P1 #15 | AE Completion signal sent to RE Completion Listener with no ACK contract — signal loss undetectable; RE Check 3 never starts. | ✅ AE Completion ACK contract with DISPATCH_MAX_RETRIES; cross-module coupling contract |
| 🔴 P1 #17 | raw.telemetry read at default isolation — concurrent AE Telemetry Aggregator and RE Check 1 reads collide; AE sees uncommitted RE reads. | ✅ Snapshot isolation on raw.telemetry — deployment prerequisite; cross-module contract |
| 🟡 P2 #11–14 | billing_period derivation LEFT(date,7) not declared at contract boundary. Type B builder missing unallocated_type enum. Grain writer ROLLBACK not prescribed on partial failure. | ✅ LEFT(date,7) declared as cross-module contract; enum enforced; ROLLBACK prescribed |

---

### Module 3 — Reconciliation Engine
**P1 ×2 · P2 ×6**

| ID | Root Cause | Fix |
|----|-----------|-----|
| 🔴 P1 #17 RE | RE Check 1 reads raw.telemetry without snapshot isolation — concurrent with AE Telemetry Aggregator reads cause dirty aggregation. | ✅ Snapshot isolation prerequisite covers RE Check 1 and Check 2 reads |
| 🔴 P1 #18 | Check 3 WHERE clause (allocation_target ≠ 'unallocated') declared only in prose — omission → false FAIL-2. | ✅ CONTRACT BOUNDARY declaration moved to formal Transformation block (Pattern 4) |
| 🟡 P2 #16–22 | RE dynamic timeout formula undocumented. Check 2 billing_period join key not declared as LEFT(date,7) contract. RE Run Receiver (C0) undercounted in session-context (I-3 Run 4). | ✅ Dynamic timeout formula documented; billing_period contract declared; component count corrected to 8 |

---

### Module 4 — State Machine
**P1 ×5 · P2 ×3 · P3 ×1**

| ID | Root Cause | Fix |
|----|-----------|-----|
| 🔴 P1 #23 | AE_TIMEOUT hardcoded to 5 minutes — insufficient at higher data volumes; legitimate AE run times out. | ✅ AE_TIMEOUT = 2× P95 AE completion time; re-derive at each volume milestone |
| 🔴 P1 #25 | APPROVED Session Closer retry triggered by next incoming request — but no request arrives after APPROVED. session_status ≠ TERMINAL indefinitely. | ✅ Celery Beat scheduled retry: CLOSER_RETRY_INTERVAL (60s) × CLOSER_MAX_RETRIES (5); CRITICAL alert after exhaustion |
| 🔴 P1 #26 | C8 wrote application_state=APPROVED; C9 wrote write_result in separate transactions. Crash between writes → APPROVED with write_result=NULL → Export Gate permanently BLOCKED. | ✅ C9 performs ONE atomic transaction writing both fields; C8 no longer writes to State Store |
| 🔴 P1 #27 | Export Gate Enforcer: NULL ≠ SUCCESS = TRUE causes NULL caught by Condition 3 (wrong path); Condition 4 is dead code; NULL surfaces wrong reason. | ✅ Conditions reordered: NULL first (C3), explicit FAIL (C4); reason_code enum added (P2 #27) |
| 🔴 P1 #29 | No delivery ACK on engine dispatch signals — Dispatcher cannot distinguish received vs lost signal; engines may never start or receive duplicates. | ✅ DISPATCH_ACK_TIMEOUT (10s); DISPATCH_MAX_RETRIES (3); engine entry points must be idempotent on duplicate signals |
| 🟡 P2 #24 | state_history trigger field: any string including NULL accepted — audit trail unreliable. | ✅ Enumerated trigger set (7 values); non-enumerated → write rejected; atomic with state persist |
| 🔵 P3 #28 | No idempotency on duplicate transition signals — UI double-click or ACK re-delivery surfaces INVALID rejection for already-completed transition. | ✅ ALREADY_COMPLETE response (safe no-op) when current_state = target; UI treats identically to SUCCESS |

---

### Module 5 — UI Screen
**P1 ×2 · P2 ×4 · P3 ×1**

| ID | Root Cause | Fix |
|----|-----------|-----|
| 🔴 P1 #32 | No end-to-end integration test for failed_tenant_id propagation chain (4 components, 2 modules). NULL regression → Risk flag silently under-fires; CFO approves without identity integrity alert. | ✅ 7-step integration test; mandatory pre-deployment CI gate (not just dev test) |
| 🔴 P1 #34 | Button states read from local UI state or render cache. After page reload, APPROVED session could render [Approve] as ACTIVE — double-approval possible. | ✅ Render invariant: button states from server-side application_state on every render (TanStack Query enforces) |
| 🟡 P2 #30 | KPI aggregations computed on every render from raw allocation_grain — throughput risk at 500K+ rows under concurrent CFO access. | ✅ KPI pre-computed at ANALYZED time; immutable session artifact keyed on session_id |
| 🟡 P2 #31 | identity_broken_tenants SET rebuilt on every render by full scan — delays Risk flag display (CFO's primary identity integrity signal). | ✅ SET pre-built at ANALYZED time; immutable session artifact; same invalidation rule as P2 #30 |
| 🟡 P2 #36 | gm_color 3-tier (green/yellow/orange) — no tier for negative margin. CFO cannot distinguish 15% GM (low) from −5% GM (losing money) visually. | ✅ 4-tier: red (GM% < 0) / orange / yellow / green; producer + consumer updated simultaneously (C-1 Run 1) |
| 🔵 P3 #35 | CFO had no traceability reference after approval — no session_id in confirmation message. | ✅ session_id appended: "Approved. Session ID: [id] — results locked for export." |

---

### Module 6 — Export
**P1 ×2 · P2 ×6**

| ID | Root Cause | Fix |
|----|-----------|-----|
| 🔴 P1 #39 | Each generator maintained its own inline column list; Output Verifier validated against an independently maintained list — schema divergence on column additions. | ✅ EXPORT_COLUMN_ORDER shared constant (15 fields); all 4 components reference it; cross-module coupling contract |
| 🔴 P1 #43 | Output Verifier Check 4: presence check only — 'CAPACITY_IDLE' (uppercase) passes. BI tools matching 'capacity_idle' silently fail to categorize idle records. | ✅ Check 4 = enumeration: 'capacity_idle' \| 'identity_broken' case-sensitive; any other value → FAIL |
| 🟡 P2 #37 | No limit on generator re-runs after verification failure — persistent generation failure triggers infinite retry loop. | ✅ MAX_EXPORT_RERUNS = 3; after limit: named error surfaced with session_id and format |
| 🟡 P2 #38 | No timeout on xlsx generation — large dataset blocks indefinitely. | ✅ XLSX_GENERATION_TIMEOUT = 120s; timeout → named error, CSV fallback suggestion |
| 🟡 P2 #41 | Filepath from Output Verifier could be moved/renamed before delivery — verified file no longer matches delivered file. | ✅ Atomic filepath handoff: verified filepath passed directly to Delivery Handler; no intermediate move/rename |
| 🟡 P2 #42 | All APPROVED State Gate BLOCKED responses returned the same message — "approval not yet given" and "write failed" indistinguishable. | ✅ Distinct messages per reason_code from P2 #27 enum; consumer updated in W-3 Run 4 |

---

## Configurable Parameters Register

*11 parameters · all must be present in deployment config before production launch*

| Parameter | Default | Owning Component | Finding | Tuning Notes |
|-----------|---------|-----------------|---------|--------------|
| `INGESTION_BATCH_THRESHOLD` | operator-defined | Ingestion Commit (C17) | 🔴 P1 #1 | Derive from staging scale test. Session drop triggered on breach. Must be set before first production upload. |
| `AE_TIMEOUT` | 2× P95 AE completion | Engine Completion Collector (SM C7) | 🔴 P1 #23 | Re-derive at each order-of-magnitude volume increase. RE effective timeout also depends on this value. |
| `DISPATCH_ACK_TIMEOUT` | 10 seconds | Analysis Dispatcher (SM C5) · AE Completion Emitter (AE C10) | 🔴 P1 #29 | Governs both dispatch ACK window and AE Completion Emitter ACK window. Tune if infrastructure latency exceeds 10s. |
| `DISPATCH_MAX_RETRIES` | 3 attempts | Analysis Dispatcher (SM C5) · AE Completion Emitter (AE C10) | 🟡 W-5 Run 4 | Governs both dispatch ACK re-send and completion signal re-emit retry counts. After exhaustion → analysis_status = IDLE + FAIL surface. |
| `CLOSER_RETRY_INTERVAL` | 60 seconds | APPROVED Session Closer (SM C12) | 🔴 P1 #25 | Background scheduled retry interval (Celery Beat). A failed session close after APPROVED is a silent security gap. |
| `CLOSER_MAX_RETRIES` | 5 attempts | APPROVED Session Closer (SM C12) | 🔴 P1 #25 | After exhaustion → operator CRITICAL alert. session_status ≠ TERMINAL indefinitely if not alerted. |
| `ANALYSIS_MAX_RETRIES` | 3 | Engine Completion Collector (SM C7) | 🟡 P2 retry policy | Analyst locked after N consecutive analysis failures. Prevents indefinite retry on structurally broken data. |
| `MAX_EXPORT_RERUNS` | 3 | Output Verifier (Export C7) | 🟡 P2 #37 | Tune per export dataset size. Allows transient failures; halts on structural ones. Named error surfaced with session_id on exhaustion. |
| `XLSX_GENERATION_TIMEOUT` | 120 seconds | Excel Generator (Export C5) | 🟡 P2 #38 | Validate at staging with peak dataset (500K+ rows) before production. Timeout triggers named error and CSV fallback suggestion. |
| `MAX_HISTORY_SESSIONS` | 90 sessions | State Store | 🟡 P2 retention | Retain more, not less. Pair with HISTORY_RETENTION_DAYS. Audit and compliance requirement. |
| `HISTORY_RETENTION_DAYS` | 180 days | State Store | 🟡 P2 retention | Pair with MAX_HISTORY_SESSIONS. Both apply; whichever retains more wins. |

---

## Deployment Prerequisites

*6 requirements · not code changes · must be satisfied before production launch*

| # | Scope | Requirement | Validation | Finding |
|---|-------|------------|-----------|---------|
| 1 | Database | Snapshot isolation on raw.telemetry | Concurrent read simulation in staging | L2 P1 #17 · Flyway T-SQL migration: `ALTER DATABASE ... SET ALLOW_SNAPSHOT_ISOLATION ON` |
| 2 | Database | Composite index on raw.iam (tenant_id, billing_period) | Execution plan shows index seek, not table scan (use SSMS Execution Plan viewer) | L2 P1 #8 · Flyway T-SQL migration: `CREATE INDEX on raw.iam` |
| 3 | Application | Dedicated write connection per Raw Table Writer (5 independent channels) | Confirm 5 independent write channels in staging | L2 P2 #2 · SQLAlchemy connection pool config |
| 4 | Infrastructure | All 11 configurable parameters present in deployment config | Config file review before first deployment | All above · CI pipeline gate |
| 5 | Test | End-to-end Risk flag integration test (7-step chain) passing in CI | Known identity_broken tenant → Risk flag fires in Zone 2R | L2 P1 #32 · Pre-deployment gate, not just dev test |
| 6 | Load Testing | RE timeout validated vs AE P95 + Check 3 P95 at peak volume | Peak volume simulation in staging | L2 P2 #16 · Dynamic RE timeout formula: `max(t_dispatch+5, t_ae_complete+5)` |

---

## Cross-Module Coupling Contracts

*7 contracts · changes require simultaneous review of ALL coupled components in the same PR*

| Contract | Coupled Components | Finding | Change Protocol |
|----------|-------------------|---------|----------------|
| `billing_period = LEFT(date,7)` | AE Billing Period Deriver · AE IAM Resolver · RE Check 2 · RE Check 3 | P2 #19 / #22 | Any date truncation format change must update all 4 components simultaneously. Join keys corrupt silently if one diverges. |
| `snapshot isolation on raw.telemetry` | AE Telemetry Aggregator · RE Check 1 · RE Check 2 | P1 #17 | DB configuration, not a code change. Any migration touching raw.telemetry must verify isolation is still enforced. |
| `AE Completion signal ACK` | AE Completion Emitter · RE AE Completion Listener · SM Engine Completion Collector | P1 #15 | Signal schema changes require all 3 components updated simultaneously. ACK contract governs DISPATCH_MAX_RETRIES and collection_source_hint. |
| `Analysis dispatch ACK` | SM Analysis Dispatcher · AE Run Receiver · RE Run Receiver | P1 #29 | DISPATCH_ACK_TIMEOUT and DISPATCH_MAX_RETRIES govern both AE and RE dispatch paths. Engine entry points must be idempotent on duplicate run_signals. |
| `EXPORT_COLUMN_ORDER constant` | CSV Generator · Excel Generator · Power BI Generator · Output Verifier Check 3 | P1 #39 | Must be a code-level constant (not copied strings). Any column addition/reorder requires all 4 components updated in same commit. 15 fields; session_id and source_files last. |
| `gm_color enum (4-tier)` | UI Customer Data Aggregator (producer) · UI Zone 2R Renderer (consumer) | P2 #36 / C-1 Run 1 | red / orange / yellow / green. Both sides must be updated simultaneously when tiers change. Test that red renders in Zone 2R for tenant with GM% < 0. |
| `application_state + write_result atomic write` | SM ANALYZED→APPROVED Executor (C8) · SM Approved Result Writer (C9) | P1 #26 / C-3 Run 2 | C9 is the SOLE atomic writer of both fields. C8 must not write to State Store directly. Export Gate Enforcer reads write_result from State Store — survives SM restarts. |

---

## Systemic Design Patterns

*5 patterns · each future change must be checked against these before a finding can occur*

### Pattern 1 — Summary Table Divergence
**Component block fix ≠ complete without summary table update**

Every time a component block is fixed, the component summary table must be updated in the same commit. Summary tables are the first thing an implementer reads — stale rows are silent instruction defects.

Instances: `W-1 Run 2` `W-2 Run 2` `W-1 Run 3` `W-4 Run 4`

> → Treat component block + summary table row as a single atomic change unit.

---

### Pattern 2 — Undeclared Consumers
**Every field written must have a declared consumer at the write site**

Every field written to the State Store or output from any component must have at least one declared consumer documented at the write site. "Display signal only" fields are not exempt.

Instances: `W-3 Run 3` `C-2 Run 1`

> → For every new field added, add a "declared consumer:" note at the write site before confirming the design.

---

### Pattern 3 — Two-Sided Boundary Mismatch
**Producer fix without consumer update = silent type violation**

When producer and consumer share a contract (enum, interface, schema), changes must be applied to both sides simultaneously. A fix to the producer that leaves the consumer on the old contract creates a silent type violation that may not surface until runtime.

Instances: `C-1 Run 1` `W-1 Run 1` `W-3 Run 4`

> → Grep for all consumers before applying any enum/schema change. Fix is incomplete until all consumers updated.

---

### Pattern 4 — Prose-Only Enforcement
**Constraints in prose are not implementation contracts**

Constraints described only in prose (comments, notes) are not formal contracts. Implementers follow formal block declarations: Input, Transformation, Output, Failure path. Critical constraints must be in these blocks, not in prose.

Instances: `W-1 Run 1` `C-3 Run 2` `P1 #18` `W-6 Run 4`

> → Any constraint with "must", "required", or "mandatory" belongs in a formal contract block — not a comment.

---

### Pattern 5 — Missing Scheduled Mechanisms
**Retry on "next request" fails in terminal states**

Retry logic that depends on "next incoming request" fails silently when no future request arrives. Terminal states (APPROVED, TERMINAL session) have no incoming requests by design. Retry logic that triggers on requests must be replaced with a scheduled background mechanism.

Instances: `P1 #25`

> → For every retry mechanism: "what sends the next request?" If the answer is "the user" — does the user have any reason to send another request after this state?

---

## Key Technology Decisions

*Diagnostic traceability · each decision traced to the finding that drove it*

| Technology Choice | Decision Driver | Finding | Rejected Alternative |
|------------------|----------------|---------|---------------------|
| Celery Beat (mandatory, not optional) | APPROVED Session Closer retry requires background scheduled mechanism. No incoming request arrives after terminal APPROVED state — request-triggered retry fails silently. | P1 #25 (Pattern 5) | Request-triggered retry — fails silently in terminal states |
| SQL Server snapshot isolation on raw.telemetry | AE Telemetry Aggregator and RE Check 1/2 read raw.telemetry concurrently. Default READ COMMITTED isolation causes dirty aggregation. SQL Server SNAPSHOT isolation (ALLOW_SNAPSHOT_ISOLATION ON) eliminates this without blocking writes. | P1 #17 (cross-module contract) | Default read committed — corrupts concurrent AE/RE reads |
| Pydantic v2 enumeration validation | state_history trigger accepted any string including NULL. gm_color 3-tier missing red tier. reason_code required structured routing for gate responses — text-based routing breaks on wording changes. | P2 #24, P2 #27, P2 #36 | Unvalidated string fields — silent corruption, wrong reason routing |
| TanStack Query (server-state render invariant) | Button states from local state or cache → stale APPROVED session renders [Approve] as ACTIVE after page reload. Double-approval is a gross margin integrity failure. | P1 #34 | React useState for button state — unsafe after reload/navigation |
| SQLAlchemy atomic single-transaction APPROVED write | Crash window between C8 (application_state=APPROVED) and C9 (write_result) in separate transactions → APPROVED with write_result=NULL → Export Gate permanently BLOCKED on any SM restart. | P1 #26 / C-3 Run 2 | Two separate transactions — unrecoverable crash window |
| EXPORT_COLUMN_ORDER code-level constant | 4 export components maintaining independent column lists → column added to one generator not others → schema divergence → BI tools break silently with no structural error. | P1 #39 (cross-module contract) | Inline column lists per generator — diverges silently on schema changes |
| Session-level KPI + SET cache artifacts (immutable, pre-computed) | Full-table SUM and SET reconstruction on every render at 500K+ rows → throughput risk under concurrent CFO access and Risk flag display latency. | P2 #30, P2 #31 | Per-render aggregation from raw allocation_grain — unscalable |
| Composite index on raw.iam (tenant_id, billing_period) | IAM Resolver full-scan at 100K+ rows grows linearly → pushes AE past AE_TIMEOUT → analysis fails on legitimate data volumes at production scale. | P1 #8 (deployment prerequisite) | No index — O(n) IAM lookup at production scale |
| DISPATCH_ACK_TIMEOUT + DISPATCH_MAX_RETRIES contract | No ACK on engine dispatch → Dispatcher cannot distinguish received vs lost signal. Engine may never start or receive duplicate signals. Anonymous [N] attempts not tunable per environment. | P1 #29, W-5 Run 4 | Fire-and-forget dispatch — signal loss undetectable |
| Output Verifier Check 4 case-sensitive enum validation | Presence check only → 'CAPACITY_IDLE' uppercase passes Check 4. BI tools matching 'capacity_idle' lowercase silently fail to categorize idle GPU records — invisible to analyst and CFO. | P1 #43 | Non-null presence check — wrong-cased values pass silently |

---

*GPU Gross Margin Visibility Application · Diagnostic-Informed Tools Stack · 2026-03-27*
*Diagnostic runs: L1 ×4 · L2 ×1 · Total findings: 71 (18 L1 · 53 L2) · Open: 0 · Parameters: 11 · Prerequisites: 6 · Contracts: 7*
