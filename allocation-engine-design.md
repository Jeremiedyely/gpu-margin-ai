---
role: module-design
module: Allocation Engine
layer: Allocation
reads-from: requirements.md · software-system-design.md
session-context: Allocation Engine design — 11 components — backward from allocation_grain write
confirmed: 2026-03-27
suggestion-applied: S1 — billing_period YYYY-MM format asserted in IAM File Validator (ingestion-module-design.md updated)
cross-module-output: billing_period field written to allocation_grain (required by Reconciliation Engine Check 3)
cross-module-signal: Allocation Engine Completion Emitter → Engine Completion Collector (State Machine) + Allocation Engine Completion Listener (Reconciliation Engine)
---

# Allocation Engine Design — GPU Gross Margin Visibility Application

> See: business.md — WHY layer · idle cost as first-class record · identity failure distinction
> See: requirements.md — WHAT layer · grain definition · Type A / Type B · closure rule · computation contract
> See: software-system-design.md — HOW layer · interaction protocol · anti-drift rules
> See: reconciliation-engine-design.md — billing_period dependency (S2) · Check 3 join key

---

## Scope

**Active scope:** Allocation Engine | Layer: Allocation
**Output expected:** `allocation_grain` populated with one row per Region × GPU Pool × Day × Allocation Target — Type A and Type B records classified, cost and revenue computed, closure rule enforced, `billing_period` field present — ready for UI aggregation and Reconciliation Engine Check 3.
**Consumed by:** UI Data Aggregators (KPI · Region · Customer) · Reconciliation Engine Check 3 · Export Source Reader · Approved Result Writer
**Failure behavior:** If blending is permitted at this layer — if idle is a remainder rather than a named record — the corruption propagates to every downstream consumer. The CFO receives a number that cannot be separated by root cause.

---

## allocation_grain Schema

```
allocation_grain (written atomically by Allocation Grain Writer):
  region             : varchar
  gpu_pool_id        : varchar
  date               : date
  billing_period     : varchar   (YYYY-MM — required by Reconciliation Check 3 · S2)
  allocation_target  : varchar   (tenant_id | 'unallocated')
  unallocated_type   : varchar | NULL  ('capacity_idle' | 'identity_broken' | NULL)
  failed_tenant_id   : varchar | NULL  (original tenant_id from telemetry for
                                         identity_broken rows · NULL for all others)
  gpu_hours          : decimal
  cost_per_gpu_hour  : decimal
  contracted_rate    : decimal | NULL  (NULL for Type B)
  revenue            : decimal         (0 for Type B · always)
  cogs               : decimal
  gross_margin       : decimal         (revenue − cogs for Type A · −cogs for Type B)
  session_id         : uuid

Closure guarantee:
  SUM(gpu_hours per gpu_pool_id per date) = reserved_gpu_hours
  for every Region × GPU Pool × Day in raw.cost_management.
  No gpu-hour can be absent. No cost can be hidden.
  This guarantee is enforced structurally — not derived.
```

---

## Billing Period Contract (S1)

```
System-wide constraint: billing_period = YYYY-MM (calendar month)
Enforced at:            IAM File Validator     (Ingestion Module, Component 3) — S1
                        Billing File Validator (Ingestion Module, Component 4)
                        ERP File Validator     (Ingestion Module, Component 5)
                        — all three checks confirmed 2026-03-27
Relied on by:           IAM Resolver (Allocation Engine, Component 4)
                        Check 3 Executor (Reconciliation Engine, Component 4)
If violated:            IAM, Billing, or ERP upload FAILS at validation
                        — file cannot enter raw.iam / raw.billing / raw.erp
                        — engine cannot run on non-conforming billing_period data
                        — prevents false Check 3 FAIL due to format mismatch
```

---

## Backward Dependency Chain

```
allocation_grain written + completion signal emitted
              ↑
  Allocation Engine Completion Emitter
  (signals: Engine Completion Collector + Allocation Engine Completion Listener)
              ↑
  Allocation Grain Writer  (atomic write · session_id appended)
              ↑
  Cost & Revenue Calculator  (revenue · cogs · gross_margin per record)
              ↑
  Closure Rule Enforcer  (forces capacity_idle if idle > 0 · FAILs if idle < 0)
    ↑                ↑
  Type A          Identity Broken
  Record Builder  Record Builder
    ↑                ↑
        IAM Resolver  (LEFT JOIN allocation_target + billing_period to raw.iam)
              ↑
  Billing Period Deriver  (YYYY-MM from date — all telemetry records)
              ↑
  Telemetry Aggregator  (SUM gpu_hours per tenant + region + pool + date)

  Cost Rate Reader  (runs in parallel — raw.cost_management → cost rates)
  — feeds: Type A Record Builder · Identity Broken Record Builder
           · Closure Rule Enforcer

  Allocation Engine Run Receiver  (entry point — receives run_signal from
  — provides session_id to:         State Machine Analysis Dispatcher)
    Telemetry Aggregator · Cost Rate Reader
```

---

## Component Blocks — 11 Components

---

### Component 0: Allocation Engine Run Receiver (Entry Point)

```
Component:       Allocation Engine Run Receiver
Layer:           Allocation
Input:           run_signal : {trigger : varchar, session_id : uuid}
                 — received from State Machine Analysis Dispatcher
                   when UPLOADED → ANALYZED transition is requested
Transformation:  IF run_signal.trigger = 'ANALYZE' AND session_id is valid uuid
                   → receiver_result = READY
                   → session_id extracted for use by all downstream components
                 IF trigger is unrecognized OR session_id is absent or invalid
                   → receiver_result = FAIL
                   · error = "Invalid run signal received — Allocation Engine cannot start"
Output:          engine_ready : {
                   result     : enum{READY, FAIL},
                   session_id : uuid,
                   error      : varchar | NULL
                 }
Feeds:           Telemetry Aggregator · Cost Rate Reader
                 (both receive session_id from this component)
Failure path:    IF receiver_result = FAIL
                   → surface fatal error to Allocation Engine Completion Emitter
                   → engine does not proceed
                   → Emitter signals FAIL to both State Machine and Reconciliation Engine
```

---

### Component 1: Telemetry Aggregator

```
Component:       Telemetry Aggregator
Layer:           Allocation
Input:           raw.telemetry : {tenant_id, region, gpu_pool_id,
                                  date, gpu_hours_consumed}
                 session_id : uuid
Transformation:  Filter: WHERE session_id = current session_id
                   (defense in depth — Ingestion Commit replacement semantics
                    guarantee only one session's rows are active, but this
                    filter ensures correctness even if replacement fails)
                 Group by tenant_id + region + gpu_pool_id + date
                 Compute: gpu_hours = SUM(gpu_hours_consumed)
                 IF raw.telemetry filtered by session_id contains no rows
                   → aggregator_result = FAIL
                   · error = "raw.telemetry contains no rows for session [session_id]"
                 IF aggregation succeeds → aggregator_result = SUCCESS
Scale note:      The GROUP BY aggregation at this grain (tenant × region × pool × date)
                 is a full-table scan over all session rows. At 10M+ rows, a single
                 unbounded scan may consume the majority of the AE_TIMEOUT window.
                 THRESHOLD: When session row count in raw.telemetry exceeds [T] rows,
                 process in date-range chunks (e.g. one week per chunk) rather than as
                 a single scan. Merge chunk results before feeding Billing Period Deriver.
                 The threshold [T] must be documented in deployment config and tuned to
                 keep chunk processing well within AE_TIMEOUT at peak volume.
                 (L2 P2 #9 — 2026-03-27)
Deployment req:  raw.telemetry reads in this component run concurrently with
                 Check 1 and Check 2 in the Reconciliation Engine — three readers
                 on the same table in the same analysis window.
                 All three reads MUST use snapshot isolation or a read replica.
                 Concurrent reads must not block each other and must not see
                 partial ingestion state (e.g. if Ingestion Commit STEP 2 is
                 still in progress for another session).
                 This is a deployment prerequisite — not optional.
                 (L2 P1 #17 — 2026-03-27)
Output:          telemetry_aggregated : {
                   result  : enum{SUCCESS, FAIL},
                   records : [{tenant_id, region, gpu_pool_id,
                               date, gpu_hours : decimal}],
                   error   : varchar | NULL
                 }
Feeds:           Billing Period Deriver
Failure path:    IF raw.telemetry unreadable or empty
                   → aggregator_result = FAIL
                   → surface fatal error to Allocation Engine Completion Emitter
                   → state remains UPLOADED · [Analyze] returns ACTIVE
```

---

### Component 2: Billing Period Deriver

```
Component:       Billing Period Deriver
Layer:           Allocation
Input:           telemetry_aggregated : {result = SUCCESS, records}
Transformation:  For every record:
                   billing_period = LEFT(date, 7)
                   (YYYY-MM truncation: 2026-03-15 → "2026-03")
                 Contract note (L2 P2 #12): This derivation assumes raw.telemetry.date
                 is in ISO 8601 YYYY-MM-DD format. Any change to the date format in
                 raw.telemetry (e.g. MM/DD/YYYY, Unix timestamp, or other ISO variant)
                 requires a simultaneous update to this component. Downstream consumers
                 of billing_period — IAM Resolver (join key) and Check 3 Executor
                 (join key) — depend on the derivation being correct. A wrong
                 billing_period propagates silently into both joins with no error.
                 (L2 P2 #12 — 2026-03-27)
                 IF any date is not ISO 8601 format
                   → deriver_result = FAIL
                   · error = "Cannot derive billing_period — invalid date: [value]"
                 IF all dates parse correctly → deriver_result = SUCCESS
Output:          telemetry_enriched : {
                   result  : enum{SUCCESS, FAIL},
                   records : [{tenant_id, region, gpu_pool_id,
                               date, billing_period, gpu_hours}],
                   error   : varchar | NULL
                 }
Feeds:           IAM Resolver
Failure path:    IF deriver_result = FAIL
                   → surface fatal error to Completion Emitter
                   → engine does not proceed
```

---

### Component 3: Cost Rate Reader

```
Component:       Cost Rate Reader
Layer:           Allocation
Input:           raw.cost_management : {region, gpu_pool_id, date,
                                        reserved_gpu_hours, cost_per_gpu_hour}
                 session_id : uuid
                 — runs in parallel with Telemetry Aggregator chain
Transformation:  Read all rows from raw.cost_management
                   WHERE session_id = current session_id
                   (defense in depth — scopes read to current session only)
                 Index by region + gpu_pool_id + date for lookup
                 IF raw.cost_management filtered by session_id is empty or unreadable
                   → reader_result = FAIL
                   · error = "raw.cost_management unavailable for session [session_id]"
                 IF read succeeds → reader_result = SUCCESS
Output:          cost_rates : {
                   result  : enum{SUCCESS, FAIL},
                   records : [{region, gpu_pool_id, date,
                               reserved_gpu_hours, cost_per_gpu_hour}],
                   error   : varchar | NULL
                 }
Feeds:           Type A Record Builder · Identity Broken Record Builder
                 · Closure Rule Enforcer
Failure path:    IF reader_result = FAIL
                   → surface fatal error to Completion Emitter
                   → engine does not proceed
```

---

### Component 4: IAM Resolver

```
Component:       IAM Resolver
Layer:           Allocation
Input:           telemetry_enriched : {result = SUCCESS, records}
                 raw.iam : {tenant_id, contracted_rate, billing_period}
Transformation:  For every record in telemetry_enriched.records:
                   LEFT JOIN raw.iam ON
                     telemetry.tenant_id     = iam.tenant_id
                     AND telemetry.billing_period = iam.billing_period
                   IF match found
                     → classification = TYPE_A
                     · contracted_rate = iam.contracted_rate
                   IF no match found
                     → classification = IDENTITY_BROKEN
                     · contracted_rate = NULL
                   (billing_period format guaranteed YYYY-MM by IAM Validator —
                    join is exact — no approximation logic required)
Coupling contract (L2 P2 #22 — 2026-03-27):
                 This component derives billing_period using LEFT(date, 7) in the
                 Billing Period Deriver (upstream). Check 2 in the Reconciliation
                 Engine uses the same derivation. If this derivation ever changes
                 (e.g. fiscal year alignment), Check 2 must change simultaneously.
                 The two components are coupled on billing_period derivation.
                 A change to one without the other produces disagreement on which
                 tenants are "resolved" — Check 2 and IAM Resolver report
                 inconsistent identity_broken populations. Also see: Check 3
                 coupling (same constraint, different downstream).
                 IF raw.iam is unreadable
                   → resolver_result = FAIL
                   · error = "raw.iam unavailable"
Output:          resolved_records : {
                   result           : enum{SUCCESS, FAIL},
                   type_a           : [{tenant_id, region, gpu_pool_id, date,
                                        billing_period, gpu_hours, contracted_rate}],
                   identity_broken  : [{tenant_id, region, gpu_pool_id, date,
                                        billing_period, gpu_hours}],
                   error            : varchar | NULL
                 }
Feeds:           Type A Record Builder (type_a list)
                 Identity Broken Record Builder (identity_broken list)
Failure path:    IF resolver_result = FAIL
                   → surface fatal error to Completion Emitter
                   → engine does not proceed
Deployment req:  raw.iam MUST have a composite index on (tenant_id, billing_period)
                 before this component executes. Without this index, the LEFT JOIN
                 is a full table scan per run. At production scale (e.g. 10M+ IAM rows),
                 an unindexed join turns a sub-minute resolution into a multi-minute
                 bottleneck that may push AE past its 5-minute timeout.
                 This index is a deployment prerequisite — not optional.
                 (L2 P1 #8 — 2026-03-27)
```

---

### Component 5: Type A Record Builder

```
Component:       Type A Record Builder
Layer:           Allocation
Grain:           Region × GPU Pool × Day × tenant_id (Type A)
Input:           resolved_records.type_a : [{tenant_id, region, gpu_pool_id,
                                             date, billing_period,
                                             gpu_hours, contracted_rate}]
                 cost_rates : [{region, gpu_pool_id, date,
                                reserved_gpu_hours, cost_per_gpu_hour}]
Transformation:  For each Type A record:
                   Look up cost_per_gpu_hour from cost_rates
                   WHERE region + gpu_pool_id + date match
                   IF no cost_rates row found
                     → builder_result = FAIL
                     · error = "No cost rate for [region + pool + date]"
                   IF found → assemble Type A grain record:
                     allocation_target = tenant_id
                     unallocated_type  = NULL
                     failed_tenant_id  = NULL
                     cost_per_gpu_hour = from cost_rates lookup
                     contracted_rate   = from type_a record
                     (revenue · cogs · gross_margin computed downstream)
Output:          type_a_records : {
                   result  : enum{SUCCESS, FAIL},
                   records : [{region, gpu_pool_id, date, billing_period,
                               allocation_target, unallocated_type = NULL,
                               failed_tenant_id = NULL,
                               gpu_hours, cost_per_gpu_hour, contracted_rate}],
                   error   : varchar | NULL
                 }
Feeds:           Closure Rule Enforcer
                 (I-4 FIX — L1 Run 4 · 2026-03-27: "(via Cost & Revenue Calculator)"
                  removed — it was incorrect. Type A Record Builder feeds directly
                  into Closure Rule Enforcer. Cost & Revenue Calculator is downstream
                  of Closure Rule Enforcer, not an intermediary here.
                  Summary table correctly said "Closure Rule Enforcer" without the
                  misleading parenthetical — component block now aligned.)
Failure path:    IF any Type A record has no matching cost_rates row
                   → builder_result = FAIL
                   · error = "Cost rate missing for [region + pool + date]"
                   → surface fatal error · engine does not proceed
```

---

### Component 6: Identity Broken Record Builder

```
Component:       Identity Broken Record Builder
Layer:           Allocation
Grain:           Region × GPU Pool × Day × 'unallocated' / identity_broken
Input:           resolved_records.identity_broken : [{tenant_id, region,
                                                      gpu_pool_id, date,
                                                      billing_period, gpu_hours}]
                 cost_rates : [{region, gpu_pool_id, date,
                                reserved_gpu_hours, cost_per_gpu_hour}]
Transformation:  For each identity_broken record:
                   Look up cost_per_gpu_hour from cost_rates
                   WHERE region + gpu_pool_id + date match
                   Assemble Type B grain record:
                     allocation_target = 'unallocated'
                     unallocated_type  = 'identity_broken'
                     failed_tenant_id  = tenant_id  (carried from IAM Resolver output)
                     contracted_rate   = NULL
                     revenue           = 0
                   Note: failed_tenant_id preserves the original tenant_id that
                   failed IAM resolution. This is a descriptive field only — it
                   does not change allocation_target. The grain cell belongs to
                   'unallocated'. failed_tenant_id enables Customer Data Aggregator
                   to satisfy the Risk flag requirement: FLAG if GM% < 0 OR
                   identity failure on tenant.
                   IF no cost_rates row found
                     → builder_result = FAIL
                     · error = "No cost rate for [region + pool + date]"
                   IF resolved_records.identity_broken is empty
                     → output empty list (valid — no identity failures this session)
Output:          identity_broken_records : {
                   result  : enum{SUCCESS, FAIL},
                   records : [{region, gpu_pool_id, date, billing_period,
                               allocation_target = 'unallocated',
                               unallocated_type  = 'identity_broken',
                               failed_tenant_id  = tenant_id,
                               gpu_hours, cost_per_gpu_hour,
                               contracted_rate = NULL, revenue = 0}],
                   error   : varchar | NULL
                 }
Feeds:           Closure Rule Enforcer
Failure path:    IF any record has no cost_rates row
                   → builder_result = FAIL · surface fatal error
```

---

### Component 7: Closure Rule Enforcer

```
Component:       Closure Rule Enforcer
Layer:           Allocation
Grain:           Region × GPU Pool × Day (evaluated per pool per day)
Input:           type_a_records.records
                 identity_broken_records.records
                 cost_rates : [{region, gpu_pool_id, date,
                                reserved_gpu_hours, cost_per_gpu_hour}]
Transformation:  For each Region × GPU Pool × Day in cost_rates:
                   consumed = SUM(gpu_hours) across type_a_records
                              + SUM(gpu_hours) across identity_broken_records
                              WHERE region + gpu_pool_id + date match
                   reserved = cost_rates.reserved_gpu_hours
                   idle     = reserved − consumed

                   IF idle > 0
                     → force one Type B / capacity_idle record:
                       allocation_target = 'unallocated'
                       unallocated_type  = 'capacity_idle'
                       failed_tenant_id  = NULL
                       gpu_hours         = idle
                       cost_per_gpu_hour = cost_rates.cost_per_gpu_hour
                       contracted_rate   = NULL
                       revenue           = 0
                       billing_period    = YYYY-MM from date
                   IF idle = 0
                     → no capacity_idle row — pool fully consumed
                   IF idle < 0
                     → enforcement_result = FAIL
                     · error = "[Allocation Engine — Closure Rule Enforcer]
                                Consumed exceeds reserved:
                                region=[region] · pool=[gpu_pool_id] · date=[date]
                                consumed=[n] · reserved=[m]"
                     Source label is required (L2 P2 #13): Check 1 in the
                     Reconciliation Engine also detects consumed > reserved and
                     surfaces a FAIL — but from a different component. Without a
                     source label in the error message, the analyst cannot determine
                     whether the failure originated in Allocation (Closure Rule) or
                     Reconciliation (Check 1), which are diagnostically different
                     failure paths requiring different root cause analysis.
                     (consistent with Reconciliation Engine Check 1 FAIL)
                     (L2 P2 #13 — 2026-03-27)

                 Closure guarantee after this component:
                   SUM(all gpu_hours per pool per day) = reserved_gpu_hours
                   No cost is hidden. No idle is a remainder.
Output:          capacity_idle_records : {
                   result  : enum{SUCCESS, FAIL},
                   records : [{region, gpu_pool_id, date, billing_period,
                               allocation_target = 'unallocated',
                               unallocated_type  = 'capacity_idle',
                               failed_tenant_id  = NULL,
                               gpu_hours, cost_per_gpu_hour,
                               contracted_rate = NULL, revenue = 0}],
                   error   : varchar | NULL
                 }
Feeds:           Cost & Revenue Calculator
Failure path:    IF idle < 0 for any pool-day
                   → enforcement_result = FAIL
                   · surface fatal error · engine does not proceed
                   (Reconciliation Engine Check 1 will also FAIL — consistent)
```

---

### Component 8: Cost & Revenue Calculator

```
Component:       Cost & Revenue Calculator
Layer:           Allocation
Grain:           All grain records (Type A + identity_broken + capacity_idle)
Input:           type_a_records.records
                 identity_broken_records.records
                 capacity_idle_records.records
Transformation:  For each Type A record:
                   revenue      = gpu_hours × contracted_rate
                   cogs         = gpu_hours × cost_per_gpu_hour
                   gross_margin = revenue − cogs

                 For each Type B record (identity_broken or capacity_idle):
                   revenue      = 0   (set by record builders)
                   cogs         = gpu_hours × cost_per_gpu_hour
                   gross_margin = −cogs
                   (gross_margin is never 0 — always negative — always a cost)

                 IF any required field is null or zero where not permitted:
                   Type A: gpu_hours · cost_per_gpu_hour · contracted_rate
                   Type B: gpu_hours · cost_per_gpu_hour
                   → calculation_result = FAIL
                   · error = "Null or zero in required field: [field · record]"
                 IF all calculations succeed → calculation_result = SUCCESS
Output:          computed_records : {
                   result  : enum{SUCCESS, FAIL},
                   records : [{region, gpu_pool_id, date, billing_period,
                               allocation_target, unallocated_type,
                               failed_tenant_id,
                               gpu_hours, cost_per_gpu_hour, contracted_rate,
                               revenue, cogs, gross_margin}],
                   error   : varchar | NULL
                 }
                 Pass-through invariant (L2 P2 #14 — 2026-03-27):
                 failed_tenant_id is a PASS-THROUGH field in this component.
                 It must NOT be evaluated, modified, nullified, or conditionally
                 assigned by any revenue or cost calculation logic here.
                 It is set once — by Identity Broken Record Builder (= tenant_id)
                 or as NULL by Type A Record Builder and Closure Rule Enforcer —
                 and must arrive at the Allocation Grain Writer unchanged.
                 Any future change to revenue modeling logic in this component
                 must explicitly preserve this invariant. If conditional logic is
                 added for a new GPU tier or pricing model, failed_tenant_id must
                 pass through regardless of the condition branch.
                 Note: failed_tenant_id is set explicitly by each record builder —
                 NULL in Type A Record Builder · NULL in Closure Rule Enforcer ·
                 tenant_id in Identity Broken Record Builder.
                 The Calculator carries the value unchanged. No defaulting required.
Feeds:           Allocation Grain Writer
Failure path:    IF calculation_result = FAIL
                   → surface fatal error · engine does not proceed
```

---

### Component 9: Allocation Grain Writer

```
Component:       Allocation Grain Writer
Layer:           Allocation
Input:           computed_records : {result = SUCCESS, records},
                 session_id : uuid
Transformation:  IF computed_records.result = SUCCESS
                   → append session_id to every record
                   → write all records atomically to allocation_grain
                     (all written or none — no partial writes)
                     WRITE TIMEOUT: The atomic write transaction must have an
                     explicit timeout (e.g. 60 seconds). If the timeout fires,
                     rollback all rows for this session_id and surface:
                     write_result = FAIL · error = "Grain write timed out — session [id]"
                     An unbounded lock on allocation_grain blocks Check 3 (which reads
                     it post-AE) and any UI render query during that window.
                     (L2 P2 #10 — 2026-03-27)
                   → write_result = SUCCESS · row_count = n
                 ELSE → do not write
Output:          write_result : {
                   result     : enum{SUCCESS, FAIL},
                   session_id : uuid,
                   row_count  : integer,
                   error      : varchar | NULL
                 }
Feeds:           Allocation Engine Completion Emitter
Failure path:    IF write fails mid-execution
                   → rollback MUST use DB transaction ROLLBACK — not DELETE.
                     A DELETE-based rollback that itself fails mid-execution
                     leaves partial rows in allocation_grain tagged with this
                     session_id. Check 3 Executor then reads a partial grain
                     and produces spurious FAIL-1 verdicts for every
                     allocation_target + billing_period that is missing from
                     the incomplete write — no system error is raised, the
                     wrong verdict propagates silently to Zone 3 and the CFO.
                     Implementation contract:
                       The atomic write (all records or none) MUST be wrapped
                       in a single DB transaction. On any write failure, the
                       transaction ROLLBACK is issued by the DB engine — it is
                       not a manual DELETE loop. If the ROLLBACK itself fails
                       (rare), the operator must be alerted immediately:
                       "CRITICAL: allocation_grain rollback failed for session
                        [session_id] — manual cleanup required before next
                        analysis run. Check 3 will produce wrong verdicts until
                        orphaned rows are removed."
                   · write_result = FAIL
                   · error = "allocation_grain write failed — transaction rolled back:
                               [system error] · session_id: [session_id]"
                   → surface fatal error · engine does not proceed
                   (P1 #12 FIX — L2 Run 3 · 2026-03-27:
                    Rollback mechanism explicitly prescribed as DB transaction
                    ROLLBACK. Previously the failure path said "rollback all rows"
                    without specifying the mechanism — a developer reading this
                    could implement DELETE-based cleanup. If DELETE fails mid-loop,
                    partial rows persist in allocation_grain; Check 3 reads the
                    partial grain and produces wrong FAIL-1 verdicts with no error.
                    DB transaction ROLLBACK is now the mandatory mechanism.)
```

---

### Component 10: Allocation Engine Completion Emitter

```
Component:       Allocation Engine Completion Emitter
Layer:           Allocation
Input:           write_result : {result, session_id, error}
                 — or any upstream fatal error collected
Transformation:  IF write_result = SUCCESS
                   → emit allocation_engine_result:
                     {result = SUCCESS, session_id}
                   → signal delivered to TWO consumers:
                     1. Engine Completion Collector (State Machine)
                        — contributes to UPLOADED → ANALYZED transition
                     2. Allocation Engine Completion Listener
                        (Reconciliation Engine)
                        — gates Check 3 execution
                 IF write_result = FAIL (or any upstream fatal error)
                   → emit allocation_engine_result:
                     {result = FAIL, session_id,
                      error  = named error from source component}
                   → both consumers receive FAIL signal
Output:          allocation_engine_result : {
                   result     : enum{SUCCESS, FAIL},
                   session_id : uuid,
                   error      : varchar | NULL
                 }
Feeds:           Engine Completion Collector (State Machine)
                 Allocation Engine Completion Listener (Reconciliation Engine)
Delivery contract: Each consumer must acknowledge receipt within ACK_TIMEOUT
                 (deployment-configured · recommended default: 10 seconds).
                 IF Engine Completion Collector (State Machine) does not ACK:
                   → re-emit allocation_engine_result to State Machine only
                 IF Allocation Engine Completion Listener (Reconciliation) does not ACK:
                   → re-emit allocation_engine_result to Reconciliation Engine only
                 Re-emission targets the non-acknowledging consumer only —
                 a consumer that already ACKed does not receive a duplicate.
                 Consumers must be idempotent: a re-emitted signal with the same
                 session_id must produce the same result as the original.
                 If re-emit also produces no ACK after DISPATCH_MAX_RETRIES attempts:
                   → surface "Completion signal delivery failed: [consumer name]"
                   → treat as engine FAIL for that consumer's timeout path
                 DISPATCH_MAX_RETRIES (deployment-configured · recommended default: 3)
                 Same parameter as Analysis Dispatcher ACK retry — documented in
                 deployment config. Governs both dispatch re-sends and completion
                 signal re-emits for consistency.
                 (W-5 FIX — L1 Run 4 · 2026-03-27: "[N] attempts" replaced with named
                  parameter DISPATCH_MAX_RETRIES. Previously the retry count was an
                  anonymous placeholder — untunable and absent from deployment config.
                  Named parameter now shared with SM Analysis Dispatcher retry contract.)
                 This ACK contract provides at-least-once delivery to both consumers.
                 (L2 P1 #15 — 2026-03-27)
Failure path:    IF emit fails to reach either consumer
                   → Engine Completion Collector 5-minute timeout fires
                   → State Machine surfaces timeout · [Analyze] returns ACTIVE
```

---

## STEP 4 — Problem-to-Design Analysis

```
Problem:          Idle cost blends silently into COGS — no named record —
                  and identity failures make real consumption disappear.
                  The Allocation Engine is the only layer where every
                  GPU-hour is forced into a named record before any
                  aggregation runs. If blending is permitted here, the
                  corruption propagates to every downstream consumer.

Required output:  allocation_grain with one row per grain cell. Every
                  GPU-hour anchored to exactly one allocation_target.
                  Type A and Type B mutually exclusive. Idle cost a
                  first-class record — not a remainder. capacity_idle and
                  identity_broken distinguished at the record level.
                  billing_period present and correct. Closure guarantee
                  enforced structurally — not derived.

Design produces:  11 components. (I-2 FIX — L1 Run 4 · 2026-03-27: updated from 10 to 11.
                  AE Run Receiver is Component 0 — was consistently undercounted.)
                  Telemetry Aggregator groups consumption
                  by grain dimensions. Billing Period Deriver writes
                  YYYY-MM before the IAM join. Cost Rate Reader runs in
                  parallel. IAM Resolver LEFT JOINs on tenant_id +
                  billing_period — unresolved → identity_broken. Type A
                  and Identity Broken builders assemble classified records
                  with cost rates. Closure Rule Enforcer computes idle per
                  pool per day and forces a capacity_idle row when idle > 0
                  — blending architecturally impossible. It also FAILs if
                  consumed > reserved — consistent with Check 1. Cost &
                  Revenue Calculator applies the correct formula per type.
                  Grain Writer is atomic. Completion Emitter signals both
                  State Machine and Reconciliation Engine.

Gap or match:     MATCH. Gap identified in STEP 4 (IAM billing_period
                  alignment) closed by S1 — YYYY-MM format asserted in
                  IAM File Validator at ingestion. ingestion-module-design.md
                  updated. Join in IAM Resolver is exact — no approximation.
```

---

## Record Builder Required Field Checklist (L2 P1 #11 — 2026-03-27)

Any new record builder added to the Allocation Engine must explicitly declare all
three fields below before the component is accepted. This checklist exists because
`failed_tenant_id` propagation is the root of the Risk flag in the UI and is
carried silently if not explicitly set. An undeclared field defaults silently
to NULL — producing invisible Risk flag under-fires or grain schema violations.

```
Required declaration for every new record builder:

  1. failed_tenant_id  — explicit value required:
       identity_broken: failed_tenant_id = tenant_id (from IAM Resolver output)
       capacity_idle:   failed_tenant_id = NULL (explicit)
       Type A:          failed_tenant_id = NULL (explicit)
       Any new type:    must declare — NULL or tenant_id — no implicit defaulting

  2. unallocated_type  — explicit value required:
       capacity_idle:   unallocated_type = 'capacity_idle'
       identity_broken: unallocated_type = 'identity_broken'
       Type A:          unallocated_type = NULL (explicit)
       Any new type:    must declare a new named value or NULL explicitly

  3. allocation_target — explicit value required:
       Type A:          allocation_target = tenant_id
       Type B:          allocation_target = 'unallocated'
       Any new type:    must declare

A component submission that leaves any of the three fields undeclared is
incomplete. Undeclared ≠ NULL. It is a missing contract.
```

---

## Component Summary

| # | Component | Layer | Runs when | Feeds |
|---|-----------|-------|-----------|-------|
| 0 | Allocation Engine Run Receiver | Allocation | On run_signal from Analysis Dispatcher | Telemetry Aggregator · Cost Rate Reader |
| 1 | Telemetry Aggregator | Allocation | After Component 0 (READY) | Billing Period Deriver |
| 2 | Billing Period Deriver | Allocation | After Component 1 | IAM Resolver |
| 3 | Cost Rate Reader | Allocation | After Component 0 (parallel with 1-2) | Type A Builder · IB Builder · Closure Rule |
| 4 | IAM Resolver | Allocation | After Component 2 | Type A Builder · IB Builder |
| 5 | Type A Record Builder | Allocation | After 3+4 | Closure Rule Enforcer |
| 6 | Identity Broken Record Builder | Allocation | After 3+4 | Closure Rule Enforcer |
| 7 | Closure Rule Enforcer | Allocation | After 5+6+3 | Cost & Revenue Calculator |
| 8 | Cost & Revenue Calculator | Allocation | After Component 7 | Allocation Grain Writer |
| 9 | Allocation Grain Writer | Allocation | After Component 8 | Completion Emitter |
| 10 | Allocation Engine Completion Emitter | Allocation | After Component 9 | State Machine + Recon Engine |
