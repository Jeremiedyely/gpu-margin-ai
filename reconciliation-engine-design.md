---
role: module-design
module: Reconciliation Engine
layer: Reconciliation
reads-from: requirements.md · software-system-design.md
session-context: Reconciliation Engine design — 8 components — three system boundary checks
confirmed: 2026-03-27
suggestion-applied: S2 — billing_period added as explicit field to allocation_grain (Allocation Engine must implement)
cross-module-dependency: Allocation Engine Completion Listener — Check 3 gates on Allocation Engine SUCCESS signal
---

# Reconciliation Engine Design — GPU Gross Margin Visibility Application

> See: business.md — WHY layer · CFO problem definition · identity failure and idle cost distinction
> See: requirements.md — WHAT layer · three reconciliation checks · FAIL conditions · Zone 3 verdicts
> See: software-system-design.md — HOW layer · Reconciliation Engine authoritative definition

---

## Scope

**Active scope:** Reconciliation Engine | Layer: Reconciliation
**Output expected:** Three verdict rows written to `reconciliation_results` — one per system boundary check — each PASS or FAIL, consumed by Zone 3 UI Renderer and Engine Completion Collector (State Machine).
**Consumed by:** Zone 3 Reconciliation Verdicts Renderer (UI) · Engine Completion Collector (State Machine)
**Failure behavior:** If boundary checks are not run before CFO approval, the CFO may approve a margin number that three upstream systems already disagree on — and the application surfaces a clean result while the underlying system integrity is broken.

---

## Execution Structure

```
Checks 1 and 2 — run in parallel with the Allocation Engine
  Read only from raw tables — no dependency on allocation_grain

Check 3 — sequential dependency on Allocation Engine completion
  Reads from allocation_grain — gated by Allocation Engine Completion Listener

All three results collected by Reconciliation Result Aggregator
→ Reconciliation Result Writer writes atomically
→ Reconciliation Engine Completion Emitter signals State Machine
```

---

## Cross-Module Dependency — billing_period (S2)

```
allocation_grain requires a billing_period field for Check 3 to join correctly.

Field:       billing_period : varchar
Derived by:  Allocation Engine at grain construction time
Rule:        YYYY-MM truncation from allocation_grain.date
             e.g. date = 2026-03-15 → billing_period = "2026-03"
Written as:  Named field in allocation_grain — not derived at query time
Used by:     Check 3 Executor as join key against raw.billing and raw.erp

ACTION REQUIRED: Allocation Engine design must include this field.
```

---

## reconciliation_results Table Schema

```
reconciliation_results:
  check_name     : varchar   ('Capacity vs Usage'
                              | 'Usage vs Tenant Mapping'
                              | 'Computed vs Billed vs Posted')
  verdict        : enum{PASS, FAIL}
  session_id     : uuid
  failing_count  : integer | NULL   (internal · not shown in Zone 3)
  detail         : varchar | NULL   (structured detail · internal · not shown in Zone 3)

Zone 3 reads: check_name + verdict only.
No drill-down. No variance. No correction. Verdict only.
```

---

## Backward Dependency Chain

```
reconciliation_engine_result → Engine Completion Collector (State Machine)
              ↑
  Reconciliation Engine Completion Emitter
              ↑
  Reconciliation Result Writer  (atomic — all 3 rows or none)
              ↑
  Reconciliation Result Aggregator
  (waits for all three check results before emitting)
         ↑              ↑              ↑
  Check 1 Executor  Check 2 Executor  Check 3 Executor
  (raw.telemetry +  (raw.telemetry +  (allocation_grain +
   raw.cost_mgmt)    raw.iam)          raw.billing + raw.erp)
        ↑                  ↑                ↑
  Reconciliation Engine Run Receiver  Allocation Engine Completion Listener
  (entry point — receives run_signal  (waits for Allocation Engine SUCCESS signal)
   from Analysis Dispatcher ·
   provides session_id to Check 1
   and Check 2 Executors)
```

---

## Component Blocks — 8 Components

---

### Component 0: Reconciliation Engine Run Receiver (Entry Point)

```
Component:       Reconciliation Engine Run Receiver
Layer:           Reconciliation
Input:           run_signal : {trigger : varchar, session_id : uuid}
                 — received from State Machine Analysis Dispatcher
                   when UPLOADED → ANALYZED transition is requested
Transformation:  IF run_signal.trigger = 'ANALYZE' AND session_id is valid uuid
                   → receiver_result = READY
                   → session_id extracted for use by all downstream components
                 IF trigger is unrecognized OR session_id is absent or invalid
                   → receiver_result = FAIL
                   · error = "Invalid run signal received — Reconciliation Engine cannot start"
Output:          engine_ready : {
                   result     : enum{READY, FAIL},
                   session_id : uuid,
                   error      : varchar | NULL
                 }
Feeds:           Check 1 Executor · Check 2 Executor
                 (both receive session_id from this component)
Failure path:    IF receiver_result = FAIL
                   → surface fatal error to Reconciliation Engine Completion Emitter
                   → engine does not proceed
                   → Emitter signals FAIL to State Machine Engine Completion Collector
```

---

### Component 1: Check 1 Executor (Capacity vs Usage)

```
Component:       Check 1 Executor (Capacity vs Usage)
Layer:           Reconciliation
Grain:           Region × GPU Pool × Day
Input:           raw.telemetry      : {region, gpu_pool_id, date, gpu_hours_consumed}
                 raw.cost_management: {region, gpu_pool_id, date, reserved_gpu_hours}
                 session_id         : uuid
Transformation:  Filter both source tables to current session:
                   raw.telemetry WHERE session_id = current session_id
                   raw.cost_management WHERE session_id = current session_id
                   (defense in depth — scopes check to current session only,
                    prevents contamination from prior sessions in active tables)
                 Per Region × GPU Pool × Day:
                   consumed = SUM(raw.telemetry.gpu_hours_consumed)
                              WHERE region + gpu_pool_id + date match
                              AND session_id = current session_id
                   reserved = raw.cost_management.reserved_gpu_hours
                              for same region + gpu_pool_id + date
                              AND session_id = current session_id

                 IF consumed > reserved for ANY grain record
                   → verdict = FAIL
                   · failing_records = [{region, gpu_pool_id, date,
                                         consumed, reserved,
                                         excess = consumed − reserved}]
                 IF consumed ≤ reserved for ALL grain records
                   → verdict = PASS · failing_records = NULL
                 IF raw.cost_management has no row for a
                   region + gpu_pool_id + date present in telemetry
                   → verdict = FAIL
                   · detail = "No capacity record found for [region + pool + date]"
Output:          check1_result : {
                   verdict         : enum{PASS, FAIL},
                   session_id      : uuid,
                   failing_count   : integer | NULL,
                   failing_records : [{region, gpu_pool_id, date,
                                       consumed, reserved, excess}] | NULL
                 }
Feeds:           Reconciliation Result Aggregator
Deployment req:  raw.telemetry and raw.cost_management reads in this component
                 run concurrently with the Allocation Engine's Telemetry Aggregator
                 (also reads raw.telemetry) and Check 2 (also reads raw.telemetry).
                 Three concurrent readers on raw.telemetry in the same analysis window.
                 All reads MUST use snapshot isolation or a read replica.
                 Readers must not block each other and must not see partial
                 ingestion state. This is a deployment prerequisite.
                 (L2 P1 #17 — 2026-03-27)
Failure path:    IF raw.telemetry or raw.cost_management is unreadable
                   → verdict = FAIL
                   · detail = "Check 1 could not execute — source unreadable: [table]"
                   · failing_count = NULL
                   → surface as engine fatal error to Completion Emitter
```

---

### Component 2: Check 2 Executor (Usage vs Tenant Mapping)

```
Component:       Check 2 Executor (Usage vs Tenant Mapping)
Layer:           Reconciliation
Grain:           Every distinct tenant_id + billing_period in raw.telemetry
Input:           raw.telemetry : {tenant_id, date}
                 raw.iam       : {tenant_id, contracted_rate, billing_period}
                 session_id    : uuid
Note:            billing_period is derived from raw.telemetry.date using the
                 same truncation as the Allocation Engine Billing Period Deriver:
                   billing_period = LEFT(date, 7)  (e.g. 2026-03-15 → "2026-03")
                 Join key: tenant_id + billing_period — aligned with IAM Resolver
                 (Allocation Engine Component 4) so Check 2 catches the same
                 identity_broken condition that produces unallocated records in
                 allocation_grain. A PASS here means every tenant consuming GPU
                 hours has an IAM record for THAT billing_period — not just any
                 billing_period.
Coupling contract (L2 P2 #22 — 2026-03-27):
                 Check 2 and IAM Resolver share the same billing_period derivation:
                 LEFT(date, 7). This alignment is what makes Check 2 catch exactly
                 the same identity_broken condition that the IAM Resolver detects.
                 If IAM Resolver changes its derivation (e.g. fiscal year edge case),
                 Check 2 and the IAM Resolver will disagree — tenants that IAM
                 Resolver considers resolved will appear unresolved to Check 2,
                 or vice versa. MANDATORY: Check 2 and IAM Resolver must share a
                 single billing_period derivation definition. A change to either
                 is a mandatory simultaneous change to the other. This coupling
                 must also be synchronized with the Billing Period Deriver and
                 Check 3 (all four share the same LEFT(date, 7) definition).
Transformation:  Filter both source tables to current session:
                   raw.telemetry WHERE session_id = current session_id
                   raw.iam WHERE session_id = current session_id
                   (defense in depth — scopes check to current session only)
                 For every DISTINCT tenant_id + billing_period in raw.telemetry
                 WHERE session_id = current session_id
                 (billing_period derived as LEFT(date, 7)):
                   LEFT JOIN to raw.iam ON
                     telemetry.tenant_id    = iam.tenant_id
                     AND telemetry.billing_period = iam.billing_period
                     AND iam.session_id = current session_id
                   IF no iam row found → record is unresolved
                     (no IAM mapping for this tenant_id + billing_period)

                 IF ANY unresolved tenant_id + billing_period pair exists
                   → verdict = FAIL
                   · unresolved_pairs = [{tenant_id, billing_period}]
                   · failing_count = COUNT(unresolved pairs)
                 IF ALL tenant_id + billing_period pairs resolve to IAM records
                   → verdict = PASS · unresolved_pairs = NULL
Output:          check2_result : {
                   verdict          : enum{PASS, FAIL},
                   session_id       : uuid,
                   failing_count    : integer | NULL,
                   unresolved_pairs : [{tenant_id, billing_period}] | NULL
                 }
Feeds:           Reconciliation Result Aggregator
Deployment req:  raw.telemetry and raw.iam reads in this component run concurrently
                 with the Allocation Engine's Telemetry Aggregator (also reads
                 raw.telemetry) and Check 1 (also reads raw.telemetry).
                 All reads MUST use snapshot isolation or a read replica.
                 Readers must not block each other and must not see partial
                 ingestion state. Same deployment prerequisite as Check 1.
                 (L2 P1 #17 — 2026-03-27)
Failure path:    IF raw.telemetry or raw.iam is unreadable
                   → verdict = FAIL
                   · detail = "Check 2 could not execute — source unreadable: [table]"
                   · failing_count = NULL
                   → surface as engine fatal error
```

---

### Component 3: Allocation Engine Completion Listener

```
Component:       Allocation Engine Completion Listener
Layer:           Reconciliation
Input:           allocation_engine_result : {result : enum{SUCCESS, FAIL},
                                             session_id}
                 — signal received from Allocation Engine when
                   allocation_grain is written and available
Transformation:  IF allocation_engine_result = SUCCESS
                   → allocation_grain is available for read
                   → listener_result = READY
                 IF allocation_engine_result = FAIL
                   → allocation_grain not available
                   → listener_result = BLOCKED
                   · error = "Allocation Engine failed — Check 3 cannot execute"
Output:          listener_result : {
                   result        : enum{READY, BLOCKED},
                   session_id    : uuid,
                   t_ae_complete : timestamp,  (server time at signal receipt)
                   error         : varchar | NULL
                 }
Feeds:           Check 3 Executor (if READY)
                 Reconciliation Result Aggregator — BOTH paths:
                   READY path:   timing signal with t_ae_complete timestamp
                                 (enables Aggregator to compute dynamic deadline:
                                  max(t_dispatch + 5 min, t_ae_complete + 5 min))
                   BLOCKED path: forced FAIL signal with engine error detail
                                 (check3_result forced to FAIL with listener error)
                 (W-1 FIX — L1 Diagnostic Run 2 · 2026-03-27:
                  Aggregator added as explicit fan-out target on READY path.
                  Previously Feeds only declared Aggregator on BLOCKED path.
                  READY-path timing signal was prescribed in Component 5 but
                  never declared in this component's Feeds. Both paths now
                  explicitly declared. t_ae_complete added to Output schema.)
ACK contract:    Upon receiving the allocation_engine_result signal from the
                 Allocation Engine Completion Emitter, this Listener must
                 acknowledge receipt within ACK_TIMEOUT (same deployment-configured
                 value as Completion Emitter — recommended default: 10 seconds).
                 Failure to ACK causes the Emitter to re-emit to this Listener only.
                 Listener must be idempotent: a re-emitted signal with the same
                 session_id must produce the same listener_result as the original.
                 (L2 P1 #15 — 2026-03-27)
Failure path:    IF Allocation Engine signal does not arrive within 5 minutes
                   → listener_result = BLOCKED
                   · error = "Allocation Engine completion signal timed out —
                               Check 3 cannot execute"
                   → force check3_result = FAIL
```

---

### Component 4: Check 3 Executor (Computed vs Billed vs Posted)

```
Component:       Check 3 Executor (Computed vs Billed vs Posted)
Layer:           Reconciliation
Grain:           allocation_target × billing_period (WHERE allocation_target ≠ 'unallocated')
CONTRACT BOUNDARY: The filter WHERE allocation_target ≠ 'unallocated' is a
                 mandatory contract constraint — not a comment or optimization.
                 This filter must be present in all queries in this component that
                 read from allocation_grain. Removing or relaxing it causes
                 'unallocated' rows (capacity_idle and identity_broken) to attempt
                 billing joins — no billing row is found for 'unallocated' —
                 generating spurious FAIL-1 verdicts for every idle and
                 identity_broken record. This produces silent false positives with
                 no system error — the query executes without failure but produces
                 wrong verdicts. Any refactor of this component must treat this
                 WHERE clause as a contract boundary that cannot be removed.
                 (L2 P1 #18 — 2026-03-27)
Input:           listener_result = READY,
                 allocation_grain : {allocation_target, billing_period, revenue}
                 raw.billing      : {tenant_id, billing_period, billable_amount}
                 raw.erp          : {tenant_id, billing_period, amount_posted}
                 session_id       : uuid
Note:            billing_period in allocation_grain is a named field
                 written by the Allocation Engine (S2 — see cross-module
                 dependency above). Join uses this explicit field.
RE timeout basis (L2 P2 #16): Effective RE timeout = max(5 min, AE + 5 min).
                 Must be validated pre-go-live: verify RE timeout > AE P95 +
                 Check 3 P95 + safety margin at peak volume. Document in config.
Cross-module coupling (L2 P2 #19 — 2026-03-27):
                 billing_period here is derived by AE Billing Period Deriver
                 using LEFT(date, 7). Check 3 joins on this field. A change to
                 the derivation logic in the AE (e.g. fiscal calendar) silently
                 breaks this join — all verdicts become unreliable with no error.
                 MANDATORY: AE billing_period derivation changes require a
                 simultaneous update to Check 3 join logic. Isolated changes
                 to either are not permitted. Also see: IAM Resolver / Check 2.
                 allocation_grain.allocation_target holds the tenant_id value
                 for Type A records. Join key:
                   allocation_grain.allocation_target = raw.billing.tenant_id
                   allocation_grain.allocation_target = raw.erp.tenant_id
Transformation:  Per allocation_target × billing_period
                 WHERE allocation_target ≠ 'unallocated':
                   computed = SUM(allocation_grain.revenue)
                              WHERE allocation_target ≠ 'unallocated'
                              AND allocation_target + billing_period match
                   billed   = raw.billing.billable_amount
                              for same tenant_id + billing_period
                              (join: allocation_target = tenant_id)
                   posted   = raw.erp.amount_posted
                              for same tenant_id + billing_period
                              (join: allocation_target = tenant_id)

                   FAIL-1 check:
                     IF computed ≠ billed → fail_type = FAIL-1

                   FAIL-2 check:
                     IF billed ≠ posted   → fail_type = FAIL-2

                   Precedence rule:
                     IF FAIL-1 AND FAIL-2 both present for same
                     allocation_target + period → record FAIL-1 only

                 Verdict aggregation:
                   IF ANY allocation_target + period has FAIL-1 or FAIL-2
                     → verdict = FAIL
                     · failing_records = [{allocation_target, billing_period,
                                           fail_type, computed, billed, posted}]
                   IF ALL pass both checks → verdict = PASS

                 IF no billing or ERP row found for an allocation_target + billing_period
                 present in allocation_grain (WHERE allocation_target ≠ 'unallocated'):
                   → verdict = FAIL
                   · detail = "No billing or ERP record for [allocation_target + billing_period]"
Output:          check3_result : {
                   verdict         : enum{PASS, FAIL},
                   session_id      : uuid,
                   failing_count   : integer | NULL,
                   failing_records : [{allocation_target, billing_period, fail_type,
                                       computed, billed, posted}] | NULL
                 }
Feeds:           Reconciliation Result Aggregator
Failure path:    IF allocation_grain, raw.billing, or raw.erp is unreadable
                   → verdict = FAIL
                   · detail = "Check 3 could not execute — source unreadable: [table]"
                   → surface as engine fatal error
                 IF listener_result = BLOCKED
                   → check3_result = FAIL · detail inherited from listener error
```

---

### Component 5: Reconciliation Result Aggregator

```
Component:       Reconciliation Result Aggregator
Layer:           Reconciliation
Input:           check1_result : {verdict, session_id, failing_count, ...}
                 check2_result : {verdict, session_id, failing_count, ...}
                 check3_result : {verdict, session_id, failing_count, ...}
                 listener_timing_signal : {
                   result        : enum{READY, BLOCKED},
                   session_id    : uuid,
                   t_ae_complete : timestamp,
                   error         : varchar | NULL
                 }
                 — signal received from AE Completion Listener (Component 3)
                   on BOTH READY and BLOCKED paths
                 — provides t_ae_complete for dynamic deadline computation
                 — all three check results AND listener signal must be
                   received (or timed out) before Aggregator emits
Tracked state:   t_dispatch     : timestamp
                   — set when run_signal is received (Aggregator start)
                   — used as the floor for the dynamic deadline
                 t_ae_complete  : timestamp | NULL
                   — set when listener_timing_signal is received
                   — NULL if AE signal never arrives (AE timeout path)
                   — used to compute: deadline = max(t_dispatch + 5 min,
                                                     t_ae_complete + 5 min)
                 (W-2 FIX — L1 Diagnostic Run 2 · 2026-03-27:
                  listener_timing_signal added as formal Input field.
                  t_dispatch and t_ae_complete declared as tracked state fields.
                  Previously Fix 3 described this mechanism in Transformation prose
                  only — no formal Input or tracked field declarations existed.
                  Implementers follow Input and tracked state blocks, not prose notes.)
Transformation:  IF all three results received
                   → assemble three-row result set:
                     Row 1: check_name = 'Capacity vs Usage'
                            verdict    = check1_result.verdict
                            session_id = session_id
                            failing_count = check1_result.failing_count
                            detail     = serialized failing_records | NULL
                     Row 2: check_name = 'Usage vs Tenant Mapping'
                            verdict    = check2_result.verdict
                            session_id = session_id
                            failing_count = check2_result.failing_count
                            detail     = serialized unresolved_pairs | NULL
                                         (each entry: {tenant_id, billing_period})
                     Row 3: check_name = 'Computed vs Billed vs Posted'
                            verdict    = check3_result.verdict
                            session_id = session_id
                            failing_count = check3_result.failing_count
                            detail     = serialized failing_records | NULL
                   → aggregation_result = SUCCESS
                 IF any check result has not yet arrived → wait
                 WAIT TIMEOUT: IF all three check results have not arrived within
                   the RE effective timeout window
                   (max(5 min from dispatch, AE completion time + 5 min)):
                   → treat any non-arrived result as FAIL
                   → aggregation_result = FATAL
                   · error = "Check result not received within RE timeout window:
                               [check name(s) that did not arrive]"
                   This prevents an indefinite hang when Check 3 signal is lost
                   (e.g. Allocation Engine Completion Listener times out or the
                   signal is dropped). The named missing check surfaces a precise
                   failure for operator diagnosis — not a generic engine timeout.
                   (L2 P1 #20 — 2026-03-27)
                 IF any check result arrived as fatal error
                   → aggregation_result = FATAL
                   · error = named fatal error from failing check
                 Timeout tracking mechanism (FIX — L1 Diagnostic 2026-03-27):
                 The RE effective timeout = max(5 min from dispatch, AE + 5 min).
                 The Aggregator cannot know AE completion time directly. The
                 coordination mechanism is:
                   Step 1: At start (run_signal received), Aggregator records
                           t_dispatch = current timestamp.
                   Step 2: When Allocation Engine Completion Listener sends its
                           READY or BLOCKED signal to Check 3 Executor, it ALSO
                           sends a copy of that signal (with its timestamp) to
                           the Aggregator — so Aggregator records t_ae_complete.
                   Step 3: Aggregator computes its wait deadline as:
                             max(t_dispatch + 5 min, t_ae_complete + 5 min)
                           If t_ae_complete was never received (AE timed out at
                           State Machine level), Aggregator treats t_ae_complete
                           as undefined and applies t_dispatch + configured_max
                           (deployment-documented upper bound).
                 This makes the timeout dynamic and correct at any AE duration.
                 Impact: Allocation Engine Completion Listener must send a timing
                 signal to both Check 3 Executor AND the Aggregator on AE result.
                 Aggregator component block must declare t_dispatch and t_ae_complete
                 as tracked fields. No changes to RE's external interface.
Output:          aggregated_results : {
                   result : enum{SUCCESS, FATAL},
                   rows   : [{check_name, verdict, session_id,
                               failing_count, detail}] | NULL,
                   error  : varchar | NULL
                 }
Feeds:           Reconciliation Result Writer (if SUCCESS)
                 Reconciliation Engine Completion Emitter (if FATAL)
Failure path:    IF aggregation_result = FATAL
                   → do not write to reconciliation_results
                   → emit fatal error to Completion Emitter
                   → State Machine surfaces error · [Analyze] returns ACTIVE
```

---

### Component 6: Reconciliation Result Writer

```
Component:       Reconciliation Result Writer
Layer:           Reconciliation
Input:           aggregated_results : {result = SUCCESS, rows, session_id}
Transformation:  IF aggregated_results.result = SUCCESS
                   → write three rows atomically to reconciliation_results
                     (all three written or none — no partial writes)
                   → write_result = SUCCESS
                 ELSE → do not write
Output:          write_result : {
                   result     : enum{SUCCESS, FAIL},
                   session_id : uuid,
                   error      : varchar | NULL
                 }
Feeds:           Reconciliation Engine Completion Emitter
Failure path:    IF write fails
                   → write_result = FAIL
                   · error = "reconciliation_results write failed: [system error]"
                   → surface fatal error to Completion Emitter
                   → State Machine holds at UPLOADED · [Analyze] returns ACTIVE
```

---

### Component 7: Reconciliation Engine Completion Emitter

```
Component:       Reconciliation Engine Completion Emitter
Layer:           Reconciliation
Input:           write_result : {result, session_id, error}
                 OR aggregated_results : {result = FATAL, error}
Transformation:  IF write_result = SUCCESS
                   → emit reconciliation_engine_result:
                     {result = SUCCESS, session_id}
                 IF write_result = FAIL OR aggregated_results = FATAL
                   → emit reconciliation_engine_result:
                     {result = FAIL, session_id,
                      error  = named error from source component}
Output:          reconciliation_engine_result : {
                   result     : enum{SUCCESS, FAIL},
                   session_id : uuid,
                   error      : varchar | NULL
                 }
Feeds:           Engine Completion Collector (State Machine)
Failure path:    IF emit fails
                   → Engine Completion Collector 5-minute timeout fires
                   → State Machine surfaces timeout · [Analyze] returns ACTIVE
```

---

## STEP 4 — Problem-to-Design Analysis

```
Problem:          Identity failures, capacity boundary violations, and
                  revenue reconciliation gaps are all silent in the current
                  system. Nothing raises an alarm before the margin number
                  reaches the CFO. The Reconciliation Engine is the last
                  structural checkpoint before approval.

Required output:  Three PASS/FAIL verdicts written before the CFO sees
                  results. Each verdict tests a specific system boundary.
                  FAIL is exact — it identifies which boundary broke and
                  how many records are affected. Zone 3 shows verdict only.
                  The CFO decides what to do with it.

Design produces:  8 components. (I-3 FIX — L1 Run 4 · 2026-03-27: updated from 7 to 8.
                  RE Run Receiver is Component 0 — was consistently undercounted.)
                  Check 1 tests the physical boundary
                  (consumption vs capacity at grain). Check 2 tests the
                  identity boundary (every telemetry tenant_id vs IAM).
                  The Listener gates Check 3 on Allocation Engine success —
                  Check 3 cannot run on a failed or partial grain table.
                  Check 3 tests the financial boundary (computed revenue vs
                  billed vs posted) per tenant per billing_period with
                  FAIL-1/FAIL-2 distinction. Aggregator waits for all
                  three. Writer is atomic. Emitter signals State Machine.

Gap or match:     MATCH. Gap identified in STEP 4 (billing_period absent
                  from allocation_grain) closed by S2 — billing_period
                  added as an explicit named field in allocation_grain,
                  written by the Allocation Engine at grain construction
                  time. Check 3 joins on the explicit field.

Cross-module note: Allocation Engine design must add billing_period
                   to allocation_grain schema. This is a hard dependency
                   for Check 3 correctness.
```

---

## Component Summary

| # | Component | Layer | Runs when | Feeds |
|---|-----------|-------|-----------|-------|
| 0 | Reconciliation Engine Run Receiver | Reconciliation | On run_signal from Analysis Dispatcher | Check 1 Executor · Check 2 Executor |
| 1 | Check 1 Executor | Reconciliation | After Component 0 (parallel with Allocation Engine) | Result Aggregator |
| 2 | Check 2 Executor | Reconciliation | After Component 0 (parallel with Allocation Engine) | Result Aggregator |
| 3 | Allocation Engine Completion Listener | Reconciliation | On Allocation Engine signal | Check 3 Executor (if READY) · Reconciliation Result Aggregator (BOTH paths) |
| | | | (W-2 FIX — L1 Diagnostic Run 3 · 2026-03-27: Aggregator added as fan-out |
| | | | target on READY path. W-1 fix in Run 2 updated Component 3 block but |
| | | | did not update this summary row. BOTH paths now declared: READY path |
| | | | sends t_ae_complete timing signal to Aggregator; BLOCKED path sends |
| | | | forced FAIL signal to Aggregator. Now corrected.) |
| 4 | Check 3 Executor | Reconciliation | After Allocation Engine SUCCESS | Result Aggregator |
| 5 | Reconciliation Result Aggregator | Reconciliation | After all 3 checks complete | Result Writer |
| 6 | Reconciliation Result Writer | Reconciliation | After Aggregator SUCCESS | Completion Emitter |
| 7 | Reconciliation Engine Completion Emitter | Reconciliation | After write result | Engine Completion Collector |
