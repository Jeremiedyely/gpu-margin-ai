---
role: stabilization-register
layer: L2 Production Stabilization + L1 Run 3 Residuals + L1 Run 4
session: 2026-03-27
scope: GPU Gross Margin Visibility Application — All 6 Modules
findings-total: 62
findings-applied: 62
findings-skipped: 0
last-updated: 2026-03-27 (L1 Run 4 — 9 findings applied)
---

# Layer 2 Production Stabilization Register
## GPU Gross Margin Visibility Application

> Generated: 2026-03-27
> Last updated: 2026-03-27 — L1 Run 3 residuals and previously skipped items applied
> Protocol: solution-architect.md — Layer 2 Production Stabilization
> Direction: Forward (Ingestion → Export)
> Dimensions analyzed per module: Scale · Maintainability · Workflow · Consistency

---

## Register Summary

| Module | File | P1 | P2 | P3 | Applied | Skipped |
|--------|------|----|----|----|---------|---------|
| 1 — Ingestion | ingestion-module-design.md | 2 | 5 | 0 | 8 | 0 |
| 2 — Allocation Engine | allocation-engine-design.md | 4 | 6 | 0 | 13 | 0 |
| 3 — Reconciliation Engine | reconciliation-engine-design.md | 4 | 4 | 0 | 10 | 0 |
| 4 — State Machine | state-machine-design.md | 5 | 5 | 1 | 14 | 0 |
| 5 — UI Screen | ui-screen-design.md | 2 | 5 | 1 | 9 | 0 |
| 6 — Export | export-module-design.md | 2 | 5 | 0 | 8 | 0 |
| **TOTAL (L2 + L1 Runs 3–4)** | | **19** | **30** | **2** | **62** | **0** |
| *L1 Run 4 additions (9)* | | | | | *+9* | |
| *— W-3: Export C1 reason_code* | export-module-design.md | | | | | |
| *— W-4: SM summary rows 2+9* | state-machine-design.md | | | | | |
| *— W-5: DISPATCH_MAX_RETRIES* | state-machine-design.md · allocation-engine-design.md | | | | | |
| *— W-6: Ingestion Commit PRE-SCAN* | ingestion-module-design.md | | | | | |
| *— I-1: UI count 13→14* | ui-screen-design.md | | | | | |
| *— I-2: AE count 10→11* | allocation-engine-design.md | | | | | |
| *— I-3: RE count 7→8* | reconciliation-engine-design.md | | | | | |
| *— I-4: AE C5 Feeds note* | allocation-engine-design.md | | | | | |

> Run 3 additions applied (9 items):
>   W-1 (SM summary table row 8) · W-2 (RE summary table row 3)
>   P1 #12 (AE Grain Writer DB transaction rollback prescription)
>   P1 #25 (SM APPROVED Session Closer scheduled retry)
>   P1 #27 (SM Export Gate Enforcer NULL dead code reorder)
>   P2 #24 (SM State Store trigger enumeration + log completeness)
>   P2 #25 (SM Engine Completion Collector partial-arrival handling)
>   P2 #27 (SM Export Gate Enforcer reason_code enum)
>   P3 #28 (SM Transition Request Receiver idempotency contract)
> Previously skipped items (Module 4): all 4 applied. Skipped count = 0.
>
> L1 Run 4 additions applied (9 items — 2026-03-27):
>   W-3 (Export APPROVED State Gate reason_code programmatic branching)
>   W-4 (SM summary table Row 9 + Row 2 feed corrections)
>   W-5 (DISPATCH_MAX_RETRIES named parameter — SM + AE + config register)
>   W-6 (Ingestion Commit PRE-SCAN step declaration)
>   I-1 (UI front matter component count: 13 → 14)
>   I-2 (AE front matter + STEP 4 component count: 10 → 11)
>   I-3 (RE front matter + STEP 4 component count: 7 → 8)
>   I-4 (AE Component 5 Feeds misleading note removed)
>   Deployment config register: DISPATCH_MAX_RETRIES added (default: 3)

---

## Module 1 — Ingestion
**File:** `ingestion-module-design.md`

### P1 Findings

| ID | Finding | Component(s) | Status |
|----|---------|-------------|--------|
| L2 P1 #1 | **Batched Ingestion Commit** — above row threshold, STEP 2 splits into per-table batched commits with session-scoped fence. All-or-nothing preserved. | Ingestion Commit · architecture-diagram.mermaid (I_CMT node) | ✅ Applied |
| L2 P1 #7 | **tenant_id format validation** — regex pattern check added to Telemetry File Validator after non-null check. Prevents silent identity_broken misclassification from malformed IDs. | Telemetry File Validator | ✅ Applied |

### P2 Findings

| ID | Finding | Component(s) | Status |
|----|---------|-------------|--------|
| L2 P2 #2 | **Connection isolation deployment requirement** — snapshot isolation or read replica required for all concurrent raw.telemetry readers. Noted in Layer 3 header. | Ingestion Commit (Layer 3 header) | ✅ Applied |
| L2 P2 #3 | **Validator Compliance Declaration table** — mandatory declaration for new validators added to Layer 1 header. | Telemetry File Validator (Layer 1 header) | ✅ Applied |
| L2 P2 #4 | **session_id HARD DEPENDENCY contract** — explicit dependency note added to all 5 Raw Table Writer input blocks. | Raw Table Writer (all 5 instances) | ✅ Applied |
| L2 P2 #5 | **STEP 1 failure message enhancement** — surfaces both current and prior session_ids in conflict message. | Ingestion Commit STEP 1 | ✅ Applied |
| L2 P2 #6 | **Manual cleanup runbook** — 5-step operator procedure for double-fail (promote + drop) scenario. | Ingestion Commit failure path | ✅ Applied |

---

## Module 2 — Allocation Engine
**File:** `allocation-engine-design.md`

### P1 Findings

| ID | Finding | Component(s) | Status |
|----|---------|-------------|--------|
| L2 P1 #8 | **Composite index deployment prerequisite** — index on raw.iam (tenant_id, billing_period) required before IAM Resolver executes at scale. | IAM Resolver | ✅ Applied |
| L2 P1 #11 | **Record Builder Required Field Checklist** — mandatory declaration for new builders: failed_tenant_id, unallocated_type, allocation_target must be explicitly handled. | Module-level section (before Component Summary) | ✅ Applied |
| L2 P1 #12 | **Allocation Grain Writer — DB transaction ROLLBACK** — Rollback on write failure must use DB transaction ROLLBACK, not DELETE. DELETE that fails mid-loop leaves partial rows; Check 3 reads wrong grain and emits spurious FAIL-1 verdicts with no system error. Implementation contract and operator CRITICAL alert added. | Allocation Grain Writer (Component 9) | ✅ Applied (Run 3 · 2026-03-27) |
| L2 P1 #15 | **Completion Emitter ACK contract** — delivery acknowledgment required from both consumers (State Machine + RE Listener) before Emitter releases. | Completion Emitter · Reconciliation Engine AE Completion Listener | ✅ Applied |
| L2 P1 #17 | **Snapshot isolation deployment requirement** — all raw.telemetry readers must use snapshot isolation or read replica. | Telemetry Aggregator | ✅ Applied |

### P2 Findings

| ID | Finding | Component(s) | Status |
|----|---------|-------------|--------|
| L2 P2 #9 | **Date-range chunking threshold** — above row threshold, Telemetry Aggregator splits read into date-range chunks to prevent memory pressure. | Telemetry Aggregator | ✅ Applied |
| L2 P2 #10 | **Explicit write timeout** — Allocation Grain Writer has configurable write timeout; surfaces named error on expiry. | Allocation Grain Writer | ✅ Applied |
| L2 P2 #12 | **ISO 8601 date assumption contract** — IAM Resolver and Billing Period Deriver assume ISO 8601 date format. Deviation causes silent misclassification. | Billing Period Deriver | ✅ Applied |
| L2 P2 #13 | **Source-labeled error message format** — Closure Rule Enforcer error messages include component source prefix for disambiguation. | Closure Rule Enforcer | ✅ Applied |
| L2 P2 #14 | **Pass-through invariant** — Cost & Revenue Calculator must pass all input fields unchanged; no field may be dropped or defaulted. | Cost & Revenue Calculator | ✅ Applied |
| L2 P2 #22 | **billing_period derivation coupling contract** — LEFT(date, 7) logic is shared across Check 2, IAM Resolver, Check 3, and Billing Period Deriver. Changes to one require simultaneous update to all. | IAM Resolver | ✅ Applied |

---

## Module 3 — Reconciliation Engine
**File:** `reconciliation-engine-design.md`

### P1 Findings

| ID | Finding | Component(s) | Status |
|----|---------|-------------|--------|
| L2 P1 #15 | **AE Completion Listener ACK contract** — delivery acknowledgment to Completion Emitter added. Paired with AE-side ACK contract. | Allocation Engine Completion Listener | ✅ Applied |
| L2 P1 #17 | **Snapshot isolation deployment requirement** — Check 1 Executor and Check 2 Executor must use snapshot isolation or read replica. | Check 1 Executor · Check 2 Executor | ✅ Applied |
| L2 P1 #18 | **CONTRACT BOUNDARY label** — WHERE allocation_target ≠ 'unallocated' in Check 3 labeled as explicit contract boundary. Removal causes silent spurious FAIL-1. | Check 3 Executor | ✅ Applied |
| L2 P1 #20 | **Aggregator wait timeout with FATAL emission** — Reconciliation Result Aggregator has configurable wait timeout; emits FATAL on expiry rather than hanging. | Reconciliation Result Aggregator | ✅ Applied |

### P2 Findings

| ID | Finding | Component(s) | Status |
|----|---------|-------------|--------|
| L2 P2 #16 | **RE timeout derivation basis** — RE timeout is derived from AE completion time (2× P95), not hardcoded. Noted in Check 3. | Check 3 Executor | ✅ Applied |
| L2 P2 #19 | **Cross-module billing_period coupling note** — billing_period derivation coupling documented in Check 3 alongside AE and IAM Resolver. | Check 3 Executor | ✅ Applied |
| L2 P2 #21 | **Zone 3 FAIL escalation path** — surfaces "Contact data team with Session ID: [session_id]" on any Check FAIL. | Zone 3 Renderer (UI) | ✅ Applied |
| L2 P2 #22 | **billing_period coupling contract** — LEFT(date, 7) coupling documented in Check 2 Executor. | Check 2 Executor | ✅ Applied |

---

## Module 4 — State Machine
**File:** `state-machine-design.md`

### P1 Findings

| ID | Finding | Component(s) | Status |
|----|---------|-------------|--------|
| L2 P1 #23 | **Configurable AE_TIMEOUT** — Engine Completion Collector timeout changed from hardcoded 5 minutes to configurable parameter. Derivation basis: 2× P95 AE completion time. | Engine Completion Collector | ✅ Applied |
| L2 P1 #25 | **APPROVED Session Closer scheduled retry** — Replaced "retry on next request" (which never fires post-APPROVED) with scheduled background retry: CLOSER_RETRY_INTERVAL × CLOSER_MAX_RETRIES. After max retries, operator alert. | APPROVED Session Closer | ✅ Applied (Run 3 · 2026-03-27) |
| L2 P1 #26 | **Atomic write invariant** — application_state + write_result must be written in a single transaction to State Store. No partial writes. | Approved Result Writer | ✅ Applied |
| L2 P1 #27 | **Export Gate Enforcer NULL condition reorder** — NULL condition moved before ≠ SUCCESS to eliminate dead code. Previously NULL ≠ SUCCESS = TRUE caused NULL case to be caught by wrong condition with wrong reason message. | Export Gate Enforcer | ✅ Applied (Run 3 · 2026-03-27) |
| L2 P1 #29 | **Dispatch ACK contract** — Analysis Dispatcher requires delivery acknowledgment from both engines (AE + RE) within DISPATCH_ACK_TIMEOUT (configurable, default 10s). | Analysis Dispatcher | ✅ Applied (Dispatcher only) |

### P2/P3 Findings — (previously skipped · all now applied)

| ID | Finding | Component(s) | Status |
|----|---------|-------------|--------|
| L2 P2 #24 | **State transition log completeness** — trigger field in state_history is now required from enumerated set (7 named values). trigger = NULL or freeform → write rejected. state_history write is atomic with state persist. | State Store (Component 1) | ✅ Applied (Run 3 · 2026-03-27) |
| L2 P2 #25 | **Engine Completion Collector partial-arrival handling** — 4 distinct arrival scenarios now documented and labeled: both SUCCESS · either FAIL · one timeout (engine ran) · one signal loss (engine never ACKed). Operators receive correct diagnostic label per scenario. | Engine Completion Collector (Component 6) | ✅ Applied (Run 3 · 2026-03-27) |
| L2 P2 #27 | **Export Gate Enforcer structured reason codes** — reason_code enum added to gate_response alongside human-readable reason: GATE_OPEN · GATE_BLOCKED_NOT_APPROVED · GATE_BLOCKED_WRITE_NULL · GATE_BLOCKED_WRITE_FAILED · GATE_BLOCKED_STATE_UNREADABLE. Downstream components and operator tools can branch programmatically without parsing text. | Export Gate Enforcer (Component 11) | ✅ Applied (Run 3 · 2026-03-27) |
| L2 P3 #28 | **Transition Request Receiver idempotency** — Duplicate signals for already-completed transitions return ALREADY_COMPLETE (safe no-op) instead of forwarding to Transition Validator. Handles ACK re-delivery, UI re-submit, and network retry. | Transition Request Receiver (Component 2) | ✅ Applied (Run 3 · 2026-03-27) |

---

## Module 5 — UI Screen
**File:** `ui-screen-design.md`

### P1 Findings

| ID | Finding | Component(s) | Status |
|----|---------|-------------|--------|
| L2 P1 #32 | **End-to-end integration test requirement** — 7-step chain test (Ingestion → Export) documented as mandatory before production deploy. | Customer Data Aggregator | ✅ Applied |
| L2 P1 #34 | **Stateless render invariant** — Footer Control Manager must read button states from State Machine on every render. Never from local state. | View 2 Footer Control Manager | ✅ Applied |

### P2/P3 Findings

| ID | Finding | Component(s) | Status |
|----|---------|-------------|--------|
| L2 P2 #21 | **Zone 3 FAIL escalation path** — session_id surfaced in Zone 3 FAIL message: "Contact data team with Session ID: [session_id]" | Zone 3 Renderer | ✅ Applied |
| L2 P2 #30 | **KPI aggregation cache requirement** — KPI aggregations pre-computed at ANALYZED time and stored as cache artifacts. Not re-computed on render. | KPI Data Aggregator | ✅ Applied |
| L2 P2 #31 | **identity_broken_tenants SET artifact** — SET of identity_broken tenant_ids built at ANALYZED time. Queried at render, not computed live. | Customer Data Aggregator | ✅ Applied |
| L2 P2 #33 | **Screen Router ERROR path session_id** — session_id surfaced in all Screen Router ERROR messages. | Screen Router | ✅ Applied |
| L2 P2 #36 | **Red GM% tier** — GM% < 0 → red bar (new tier). Distinguishes negative margin from low margin. Bar color tiers: red <0% · orange 0-29% · yellow 30-37% · green ≥38%. Also updated architecture-diagram.mermaid UI_CUS node. | Customer Data Aggregator · Zone 2R Renderer · architecture-diagram.mermaid | ✅ Applied |
| L2 P3 #35 | **session_id in Approve Confirmation Dialog** — session_id appended to success confirmation message for traceability. | Approve Confirmation Dialog | ✅ Applied |

---

## Module 6 — Export
**File:** `export-module-design.md`

### P1 Findings

| ID | Finding | Component(s) | Status |
|----|---------|-------------|--------|
| L2 P1 #39 | **EXPORT_COLUMN_ORDER shared constant** — single source of truth for column order across CSV Generator, Excel Generator, Power BI Generator, and Output Verifier Check 3. Added as module-level section. | CSV Generator · Excel Generator · Power BI Generator · Output Verifier · export-module-design.md (module-level) | ✅ Applied |
| L2 P1 #43 | **Output Verifier Check 4 enumeration** — strengthened from presence check to enumeration check. All non-null unallocated_type values must be exactly 'capacity_idle' or 'identity_broken'. Any other non-null value is invalid. | Output Verifier (Check 4) | ✅ Applied |

### P2 Findings

| ID | Finding | Component(s) | Status |
|----|---------|-------------|--------|
| L2 P2 #37 | **Output Verifier max re-run count** — MAX_EXPORT_RERUNS = 3 (configurable). After limit: "Export generation failed after [n] attempts. Contact data team with Session ID: [session_id] and format: [format]." | Output Verifier | ✅ Applied |
| L2 P2 #38 | **Excel Generator invocation timeout** — XLSX_GENERATION_TIMEOUT (configurable, default 120s). On timeout: "Excel generation timed out. Try CSV export for large datasets." | Excel Generator | ✅ Applied |
| L2 P2 #40 | **Format Router source_files format declaration** — each generator route declares its source_files output format (CSV = JSON array · Excel = JSON array · Power BI = pipe-delimited). Declaration passed with routed_dataset. | Format Router | ✅ Applied |
| L2 P2 #41 | **File Delivery Handler atomic filepath handoff** — filepath confirmed in Output Verifier Check 1 passed directly to Delivery Handler. No intermediate move or rename. | File Delivery Handler | ✅ Applied |
| L2 P2 #42 | **APPROVED State Gate distinct BLOCKED messages** — write_result = NULL case surfaces "Export blocked — approval record incomplete. Contact your admin with Session ID: [session_id]" — distinct from state ≠ APPROVED message. | APPROVED State Gate | ✅ Applied |

---

## Cross-Module Coupling Contracts Established

The following contracts span multiple modules. A change to one component requires simultaneous review of all coupled components.

| Contract | Components | Tag |
|----------|-----------|-----|
| billing_period = LEFT(date, 7) | Check 2 Executor (RE) · IAM Resolver (AE) · Check 3 Executor (RE) · Billing Period Deriver (AE) | L2 P2 #19 / #22 |
| snapshot isolation on raw.telemetry | Telemetry Aggregator (AE) · Check 1 Executor (RE) · Check 2 Executor (RE) | L2 P1 #17 |
| Completion Emitter ACK | Completion Emitter (AE) · AE Completion Listener (RE) · State Machine Engine Completion Collector | L2 P1 #15 |
| Analysis Dispatcher ACK | Analysis Dispatcher (SM) · Allocation Engine · Reconciliation Engine | L2 P1 #29 |
| EXPORT_COLUMN_ORDER | CSV Generator · Excel Generator · Power BI Generator · Output Verifier Check 3 | L2 P1 #39 |

---

## Configurable Parameters Introduced (L2)

All configurable parameters must live in deployment config — not hardcoded in component logic.

| Parameter | Default | Component | Tag |
|-----------|---------|-----------|-----|
| INGESTION_BATCH_THRESHOLD | operator-defined | Ingestion Commit | L2 P1 #1 |
| AE_TIMEOUT | 2× P95 AE completion time | Engine Completion Collector | L2 P1 #23 |
| DISPATCH_ACK_TIMEOUT | 10 seconds | Analysis Dispatcher | L2 P1 #29 |
| DISPATCH_MAX_RETRIES | 3 attempts | Analysis Dispatcher · AE Completion Emitter | L1 Run 4 W-5 |
| CLOSER_RETRY_INTERVAL | 60 seconds | APPROVED Session Closer | L2 P1 #25 |
| CLOSER_MAX_RETRIES | 5 attempts | APPROVED Session Closer | L2 P1 #25 |
| ANALYSIS_MAX_RETRIES | 3 | Engine Completion Collector | L2 P2 (retry policy) |
| MAX_EXPORT_RERUNS | 3 | Output Verifier | L2 P2 #37 |
| XLSX_GENERATION_TIMEOUT | 120 seconds | Excel Generator | L2 P2 #38 |

---

## Deployment Prerequisites (L2)

The following infrastructure requirements must be satisfied before the stabilized system is deployed to production.

| Requirement | Scope | Tag |
|-------------|-------|-----|
| Snapshot isolation or read replica for all concurrent raw.telemetry readers | Database layer | L2 P1 #17 / P2 #2 |
| Composite index on raw.iam (tenant_id, billing_period) | Database layer | L2 P1 #8 |
| All configurable L2 parameters present in deployment config | Infrastructure | L2 P1 #23, P2 #37, P2 #38 |

---

*Stabilization Register — L2 Production Stabilization + L1 Runs 3–4 — 2026-03-27*
*L1 Run 4 applied: 2026-03-27 · 9 findings (4W + 4I + 1 deployment parameter)*
*62 findings total · 62 applied · 0 skipped · System fully stabilized*
