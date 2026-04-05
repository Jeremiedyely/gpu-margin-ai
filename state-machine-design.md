---
role: module-design
module: State Machine
layer: State
reads-from: requirements.md · software-system-design.md
session-context: State Machine design — 12 components — backward from confirmed state + closed session
confirmed: 2026-03-27
suggestion-applied: S1 — Fixed timeout (5 min) + ANALYZING sub-status in State Store
---

# State Machine Design — GPU Gross Margin Visibility Application

> See: business.md — WHY layer · CFO problem definition · approval gate purpose
> See: requirements.md — WHAT layer · four states · transition rules · state gate enforcement
> See: software-system-design.md — HOW layer · interaction protocol · anti-drift rules

---

## Scope

**Active scope:** State Machine | Layer: State
**Output expected:** Server-side state management across four states with valid transition enforcement, export gate responses, and terminal session close on APPROVED. Named failure path at every transition.
**Consumed by:** UI (Screen Router · Footer Control Managers) · Export Module (APPROVED State Gate) · all transition-emitting modules (Ingestion · UI [Analyze] · Approve Confirmation Dialog)
**Failure behavior:** Without server-side state enforcement, export can be triggered from a pre-approval or incomplete state. Without a terminal APPROVED session, re-analysis after CFO approval is possible — invalidating the approved artifact.

---

## State Store Schema

```
state_store (server-side · persisted):
  application_state  : enum{EMPTY, UPLOADED, ANALYZED, APPROVED}
  analysis_status    : enum{IDLE, ANALYZING} | NULL
                       — NULL when state ∈ {EMPTY, APPROVED}
                       — IDLE when no engine run is active
                       — ANALYZING when engines are running (display signal only)
                       — does NOT create a fifth state · no transition rules
  session_id         : uuid | NULL      (set at EMPTY → UPLOADED)
  session_status     : enum{ACTIVE, TERMINAL}
  write_result       : enum{SUCCESS, FAIL} | NULL
                       — NULL until ANALYZED → APPROVED transition fires
                       — set to SUCCESS or FAIL by Approved Result Writer
                         at the moment final.allocation_result is written
                       — read by Export Gate Enforcer at export gate query time
                       — persisted server-side: survives State Machine restarts
                       — required by Export Gate Enforcer alongside
                         application_state = APPROVED before gate returns OPEN
  retry_count        : integer
                       — per-session counter · incremented by Engine Completion
                         Collector each time an ANALYZED transition fails
                       — reset to 0 on successful UPLOADED → ANALYZED transition
                       — read by Engine Completion Collector to enforce
                         ANALYSIS_MAX_RETRIES = 3 limit
                       — when retry_count ≥ ANALYSIS_MAX_RETRIES:
                           [Analyze] rendered LOCKED · session flagged for operator
                       (C-2 FIX — L1 Diagnostic Run 2 · 2026-03-27:
                        field added to schema block; previously prescribed in
                        Component 6 but absent from schema definition.)
  state_history      : [{
                          from_state  : varchar,
                          to_state    : varchar,
                          timestamp   : timestamp,
                          trigger     : varchar
                        }]
```

---

## Valid Transition Table

```
  From       To          Trigger source                    Condition
  ─────────────────────────────────────────────────────────────────────
  EMPTY    → UPLOADED    Ingestion State Emitter           all 5 files validated + written
  UPLOADED → ANALYZED    Engine Completion Collector       both engines SUCCESS (≤5 min)
  ANALYZED → APPROVED    Approve Confirmation Dialog FIRE  CFO explicit confirmation
  APPROVED → (none)      —                                 terminal · no transitions
```

---

## Backward Dependency Chain

```
Current state exposed to all consumers + session closed after APPROVED
                      ↑
          APPROVED Session Closer  ←── marks session_status = TERMINAL
                      ↑
          Export Gate Enforcer     ←── responds OPEN/BLOCKED to APPROVED State Gate
                      ↑
          Approved Result Writer   ←── writes final.allocation_result (immutable · once only)
                      ↑
  ┌──────────────────────────────────────────────────────────────────┐
  │  Three Transition Executors                                       │
  │  EMPTY→UPLOADED · UPLOADED→ANALYZED · ANALYZED→APPROVED          │
  └──────────────────────────────────────────────────────────────────┘
         ↑                     ↑                      ↑
  from Ingestion        from Engine              from Approve
  State Emitter         Completion               Confirmation
                        Collector                Dialog (FIRE)
                              ↑
                  Engine Completion Collector (5 min timeout · analysis_status → IDLE)
                              ↑
                  Analysis Dispatcher (sets analysis_status = ANALYZING)
                              ↑
                      Transition Validator
                      (three-rule table · routes INVALID to rejection handler)
                              ↑
                      Transition Request Receiver
                      (single entry point for all signals)
                              ↑
                          State Store
                      (persists state · exposes to consumers · rejects unauthorized writes)
```

---

## Component Blocks — 12 Components

---

### Component 1: State Store

```
Component:       State Store
Layer:           State
Input:           state_write_request : {
                   new_state       : enum{EMPTY, UPLOADED, ANALYZED, APPROVED},
                   analysis_status : enum{IDLE, ANALYZING} | NULL,
                   trigger         : varchar,
                   session_id      : uuid | NULL
                 }
                 — written by Transition Executors and Analysis Dispatcher only
Transformation:  IF state_write_request is received from an authorized source
                   → persist new_state + analysis_status to server-side store
                   → append to state_history:
                     {from_state, to_state, timestamp = now(), trigger}
                   → expose updated application_state + analysis_status
                     to all consumers
                   → store_write_result = SUCCESS
                 IF write request comes from unauthorized source
                   → reject · store_write_result = FAIL
                   · error = "Unauthorized state write attempt"
State history log completeness (P2 #24 FIX — 2026-03-27):
                 trigger is a required field in every state_history entry.
                 Completeness contract:
                   trigger must be populated from the enumerated set below —
                   never NULL, never an empty string, never freeform text.
                   Enumerated trigger values (all callers must use exactly these):
                     "ingestion_complete"        (EMPTY → UPLOADED · Ingestion State Emitter)
                     "analyze_dispatched"        (UPLOADED → ANALYZED start · Analysis Dispatcher)
                     "engine_completion_success" (UPLOADED → ANALYZED · UPLOADED→ANALYZED Executor)
                     "engine_completion_fail"    (UPLOADED stays · Engine Completion Collector FAIL)
                     "cfo_approval_fire"         (ANALYZED → APPROVED · ANALYZED→APPROVED Executor)
                     "session_closed"            (APPROVED · APPROVED Session Closer)
                     "analysis_status_update"    (analysis_status only writes — no state change)
                   IF trigger is NULL or not in the enumerated set:
                     → state_write_request = FAIL
                     · error = "state_history write rejected — trigger not in
                                enumerated set: [received value]"
                     → do not persist new_state · do not append to state_history
                   state_history write MUST be atomic with the new_state persist.
                   A state_history entry missing for a persisted transition is an
                   audit gap — the session cannot be fully reconstructed from log.
                   No partial writes: state persisted + history appended, or neither.
state_history retention policy (L2 P2 — 2026-03-27):
                 state_history grows with every state transition across all sessions.
                 Without a retention boundary it grows unbounded and becomes a
                 query-time liability for any component reading historical state.
                 Policy:
                   Retain: all entries for the last MAX_HISTORY_SESSIONS sessions
                           OR all entries within the last HISTORY_RETENTION_DAYS days
                           — whichever boundary is reached last (keep more, not less)
                   Archive: entries outside the retention window are moved to an
                            archive store — not deleted. Audit trail is preserved.
                   Defaults (document in deployment config and tune per environment):
                     MAX_HISTORY_SESSIONS    = 90 sessions
                     HISTORY_RETENTION_DAYS  = 180 days
                   Enforcement: archival job runs at session close (APPROVED state)
                   — not on every write. Bounded operation per session, not per row.
                 Impact: State Store query performance remains stable at production
                 session volume. Approved sessions remain auditable via archive store.
                 No change to state_history write behavior or schema.
Output:          application_state  : enum{EMPTY, UPLOADED, ANALYZED, APPROVED}
                 analysis_status    : enum{IDLE, ANALYZING} | NULL
                 — continuously exposed to UI · Export Gate Enforcer
                 store_write_result : enum{SUCCESS, FAIL}
Feeds:           All consumers of application_state
Failure path:    IF persist fails (I/O error)
                   → store_write_result = FAIL
                   · error = "State persist failed — state may be inconsistent"
                   → surface "Application state error — do not proceed"
                   → do not expose new_state until persist confirmed
```

---

### Component 2: Transition Request Receiver

```
Component:       Transition Request Receiver
Layer:           State
Input:           transition_signal : {
                   requested_transition : varchar,
                   source               : enum{INGESTION, UI_ANALYZE, APPROVAL_DIALOG},
                   session_id           : uuid | NULL
                 }
                 — receives from:
                   Ingestion State Transition Emitter  (EMPTY → UPLOADED)
                   UI [Analyze] button click           (UPLOADED → ANALYZED)
                   Approve Confirmation Dialog FIRE    (ANALYZED → APPROVED)
Transformation:  IF transition_signal received from recognized source
                   → read current_state from State Store
                   → pass to Transition Validator
                 IF signal source is unrecognized
                   → reject · error = "Unrecognized transition source: [source]"
Idempotency contract (P3 #28 FIX — 2026-03-27):
                 The Transition Request Receiver MUST be idempotent on duplicate
                 signals for the same session_id. Duplicate signals can arrive
                 from:
                   — ACK re-delivery (Analysis Dispatcher or Completion Emitter
                     re-emits on no-ACK, but the original signal was also processed)
                   — UI re-submit (analyst clicks [Analyze] or [Approve] twice
                     before the first signal reaches the server)
                   — Network retry (client timeout causes a second HTTP request
                     while the first is still processing)
                 Idempotency rule: IF a transition_signal is received and the
                 current_state ALREADY equals the target state of that transition:
                   requested = "EMPTY→UPLOADED"  AND current_state = UPLOADED
                   requested = "UPLOADED→ANALYZED" AND current_state = ANALYZED
                   requested = "ANALYZED→APPROVED" AND current_state = APPROVED
                 → do NOT forward to Transition Validator
                 → return idempotent_response:
                   {result = ALREADY_COMPLETE,
                    current_state = [current_state],
                    message = "Transition [requested] already completed for
                               session [session_id]. No action taken."}
                 This is NOT an error — it is a safe no-op. The UI receives
                 ALREADY_COMPLETE and treats it identically to SUCCESS (the state
                 it expected is already confirmed server-side).
                 If the state is in-progress (e.g. transition is currently being
                 executed): the Receiver passes to the Transition Validator as
                 normal — the Validator will return INVALID if the state has
                 advanced or not yet reached the required from_state.
Output:          transition_request : {
                   current_state        : enum{EMPTY, UPLOADED, ANALYZED, APPROVED},
                   requested_transition : varchar,
                   source               : varchar,
                   session_id           : uuid | NULL
                 }
                 OR idempotent_response : {
                   result        : 'ALREADY_COMPLETE',
                   current_state : varchar,
                   message       : varchar
                 }
Feeds:           Transition Validator (on new transition only)
                 UI directly (on ALREADY_COMPLETE — does not forward to Validator)
Failure path:    IF current_state cannot be read from State Store
                   → reject transition_signal
                   · error = "Cannot process transition — state unreadable"
                   → surface error to UI · do not pass to Transition Validator
```

---

### Component 3: Transition Validator

```
Component:       Transition Validator
Layer:           State
Input:           transition_request : {current_state, requested_transition,
                                       source, session_id}
Transformation:  Apply three-rule valid transition table:
                   EMPTY    + "EMPTY→UPLOADED"    + source=INGESTION
                              → validation_result = VALID
                   UPLOADED + "UPLOADED→ANALYZED"  + source=UI_ANALYZE
                              → validation_result = VALID
                   ANALYZED + "ANALYZED→APPROVED"  + source=APPROVAL_DIALOG
                              → validation_result = VALID
                   APPROVED + any requested_transition
                              → validation_result = INVALID
                              · reason = "Session is terminal — no further transitions"
                   ANY other combination
                              → validation_result = INVALID
                              · reason = "Transition [requested] not valid
                                          from state [current_state]"
Output:          validation_result : {
                   result               : enum{VALID, INVALID},
                   requested_transition : varchar,
                   current_state        : varchar,
                   session_id           : uuid | NULL,
                   reason               : varchar | NULL
                 }
Feeds:           EMPTY→UPLOADED Executor       (if VALID + EMPTY→UPLOADED)
                 Analysis Dispatcher           (if VALID + UPLOADED→ANALYZED)
                 ANALYZED→APPROVED Executor    (if VALID + ANALYZED→APPROVED)
                 Invalid Transition Rejection Handler (if INVALID)
Failure path:    IF transition table cannot be evaluated
                   → validation_result = INVALID
                   · reason = "Transition validation failed — treating as invalid"
                   → route to Invalid Transition Rejection Handler
```

---

### Component 4: EMPTY → UPLOADED Executor

```
Component:       EMPTY → UPLOADED Executor
Layer:           State
Input:           validation_result : {result = VALID,
                                      requested_transition = "EMPTY→UPLOADED",
                                      session_id}
Transformation:  IF validation_result = VALID
                   → write to State Store:
                     new_state       = UPLOADED
                     analysis_status = IDLE
                     trigger         = "ingestion_complete"
                     session_id      = session_id
                   → IF store_write_result = SUCCESS → transition_result = SUCCESS
                   → IF store_write_result = FAIL    → transition_result = FAIL
Output:          transition_result : {
                   result     : enum{SUCCESS, FAIL},
                   new_state  : 'UPLOADED',
                   session_id : uuid,
                   error      : varchar | NULL
                 }
Feeds:           State Store (write) · UI (via updated application_state)
Failure path:    IF State Store write fails
                   → transition_result = FAIL
                   · error = "EMPTY→UPLOADED transition failed — state not persisted"
                   → state remains EMPTY
                   → surface "File upload could not be confirmed — retry upload"
```

---

### Component 5: Analysis Dispatcher

```
Component:       Analysis Dispatcher
Layer:           State
Input:           validation_result : {result = VALID,
                                      requested_transition = "UPLOADED→ANALYZED",
                                      session_id : uuid | NULL}
                 Note: session_id in the incoming signal may be NULL for the
                 UPLOADED→ANALYZED transition — the UI [Analyze] click does not
                 carry session_id. The Analysis Dispatcher resolves session_id
                 from State Store (set at EMPTY→UPLOADED). The signal's
                 session_id field is not used for this transition.
Transformation:  IF validation_result = VALID
                   → resolve session_id from State Store (current active session)
                   → IF State Store session_id is NULL or unresolvable
                     → write to State Store: analysis_status = IDLE
                     → dispatch_result = FAIL
                     · error = "Session ID not found in State Store — cannot dispatch engines"
                     → surface error to UI · [Analyze] returns ACTIVE
                     → STOP — do not write ANALYZING · do not emit run_signals
                   → read current analysis_status from State Store
                     IF analysis_status = ANALYZING
                       → dispatch_result = FAIL
                       · error = "Analysis already in progress for this session —
                                  wait for the current run to complete or time out.
                                  Session ID: [session_id]"
                       → do NOT write analysis_status = ANALYZING
                       → do NOT emit run_signals to either engine
                       → surface error to UI · [Analyze] remains in ANALYZING state
                       → STOP
                       Note: this is a server-side guard. View 1 Footer Control Manager
                       also locks [Analyze] when analysis_status = ANALYZING (UI-side
                       guard). Both guards are required — the server-side guard protects
                       against race conditions, direct API calls, or UI state loss.
                       (C-1/W-3 FIX — L1 Diagnostic Run 3 · 2026-03-27:
                        Pre-dispatch guard added. Previously the Dispatcher wrote
                        analysis_status = ANALYZING without first checking whether
                        it was already ANALYZING — allowing a second dispatch to proceed
                        while the first engine run was still in flight.)
                   → write to State Store: analysis_status = ANALYZING
                     (View 1 Footer Control Manager reads this and locks [Analyze]
                      with "Analysis in progress..." label — declared consumer of
                      analysis_status at the UI layer per C-1/W-3 fix)
                   → emit run_signal to Allocation Engine:
                     {trigger = "ANALYZE", session_id}  ← from State Store
                   → emit run_signal to Reconciliation Engine:
                     {trigger = "ANALYZE", session_id}  ← from State Store
                   → both engines run in parallel
                 Dispatch ACK contract:
                   Each engine must acknowledge receipt of its run_signal
                   within DISPATCH_ACK_TIMEOUT (deployment-configured ·
                   recommended default: 10 seconds).
                   IF Allocation Engine does not ACK within the window
                     → re-dispatch run_signal to Allocation Engine only
                     · do NOT re-dispatch to Reconciliation Engine
                   IF Reconciliation Engine does not ACK within the window
                     → re-dispatch run_signal to Reconciliation Engine only
                     · do NOT re-dispatch to Allocation Engine
                   If re-dispatch ACK also fails after DISPATCH_MAX_RETRIES attempts:
                     → write to State Store: analysis_status = IDLE
                     → dispatch_result = FAIL
                     · error = "Analysis dispatch failed — [engine name] unreachable.
                                Contact your operator. Session ID: [session_id]"
                   DISPATCH_MAX_RETRIES (deployment-configured · recommended default: 3)
                   Must be documented in deployment config and tuned per environment.
                   Same parameter governs re-dispatch retry count for both AE and RE.
                   (W-5 FIX — L1 Run 4 · 2026-03-27: "[N] attempts" replaced with named
                    parameter DISPATCH_MAX_RETRIES. Previously the retry count was an
                    anonymous placeholder — untunable per environment and absent from
                    the deployment config register. Named parameter added here and in
                    AE Completion Emitter Delivery contract. Register updated.)
                   This dispatch FAIL is a distinct signal — it means the engine
                   never received its signal. It is NOT the same as an engine
                   timeout (which means the engine received the signal but ran too
                   long). Operators must treat these as different failure modes.
                   (L2 P1 #29 — 2026-03-27)
                   → dispatch_result = DISPATCHED
                 IF either engine is unavailable at dispatch time
                   → write to State Store: analysis_status = IDLE
                   → dispatch_result = FAIL
                   · error = "Engine unavailable: [engine name]"
Output:          dispatch_result : {
                   result     : enum{DISPATCHED, FAIL},
                   session_id : uuid | NULL,
                   error      : varchar | NULL
                 }
Feeds:           Engine Completion Collector (via engine result signals)
Failure path:    IF dispatch_result = FAIL
                   → analysis_status written back to IDLE
                   → state remains UPLOADED
                   → surface "Analysis could not start — [engine] unavailable"
                   → [Analyze] button returns to ACTIVE in UI
```

---

### Component 6: Engine Completion Collector

```
Component:       Engine Completion Collector
Layer:           State
Input:           allocation_engine_result    : {result : enum{SUCCESS, FAIL},
                                                session_id, error : varchar | NULL}
                 reconciliation_engine_result : {result : enum{SUCCESS, FAIL},
                                                 session_id, error : varchar | NULL}
                 — both signals must arrive before collector emits
Timeout:         Allocation Engine: AE_TIMEOUT (configurable parameter — not hardcoded).
                 Derivation basis: AE_TIMEOUT = 2 × P95 AE completion time at peak
                 data volume. Must be re-derived and reconfigured at each
                 order-of-magnitude data volume increase. The derivation basis and
                 current configured value must be documented in deployment config.
                 Default seed value: 5 minutes (for pre-production baseline only).
                 Reconciliation Engine: the Reconciliation Engine runs Checks 1+2
                   in parallel with the Allocation Engine, then runs Check 3
                   sequentially after Allocation Engine SUCCESS. Its effective
                   timeout is therefore:
                     max(5 minutes from dispatch,
                         Allocation Engine completion time + 5 minutes)
                   This prevents a false timeout when the Allocation Engine
                   completes late and Check 3 has insufficient remaining window.
                 IF Allocation Engine has not returned within AE_TIMEOUT
                   → collection_result = FAIL
                   · error = "Engine timeout after [AE_TIMEOUT]: Allocation Engine"
                 IF Reconciliation Engine has not returned within its effective
                   timeout window (defined above)
                   → collection_result = FAIL
                   · error = "Engine timeout: Reconciliation Engine"
                 (L2 P1 #23 — 2026-03-27)
Transformation:  IF both results received within their respective timeouts
                   AND both = SUCCESS
                   → write to State Store: analysis_status = IDLE
                   → collection_result = SUCCESS
                 IF either result = FAIL (within timeout)
                   → write to State Store: analysis_status = IDLE
                   → collection_result = FAIL
                   · errors = [all named engine errors]
                 IF timeout fires before both results received
                   → write to State Store: analysis_status = IDLE
                   → collection_result = FAIL
                   · error = "Engine timeout: [engine name]"
Partial-arrival handling (P2 #25 FIX — 2026-03-27):
                 Four distinct arrival scenarios must be handled and distinguished:
                   1. Both arrive — both SUCCESS → collection_result = SUCCESS
                   2. Both arrive — either FAIL  → collection_result = FAIL
                                    · errors = named engine errors from failing engine(s)
                   3. One arrives, one times out (engine ran but did not complete
                      in time — engine received the signal but exceeded timeout):
                      → collection_result = FAIL
                      · error = "Engine timeout after [AE_TIMEOUT|RE_timeout]:
                                 [engine name] — received signal, did not complete"
                      · the arrived engine's result is preserved in errors list
                        for operator diagnosis
                   4. One arrives, one never signals (signal was dispatched but
                      engine never ACKed and ACK timeout also expired — signal loss):
                      → collection_result = FAIL
                      · error = "Engine signal not received: [engine name] —
                                 dispatch sent, no ACK within DISPATCH_ACK_TIMEOUT.
                                 Treat as infrastructure failure, not engine failure."
                      · operators must investigate signal delivery, not engine logic
                 The distinction between scenario 3 (engine ran, timed out) and
                 scenario 4 (signal never delivered) is diagnostically critical:
                 Scenario 3 → investigate engine performance or data volume.
                 Scenario 4 → investigate message broker, network, or dispatcher.
                 Both surface to the analyst as "Analysis failed — retry" but the
                 operator error message must use the correct scenario label.
                 Determination: Dispatcher ACK contract (P1 #29) tracks whether
                 the engine ACKed the run_signal. If the engine ACKed (scenario 3)
                 vs never ACKed (scenario 4), the Dispatcher can tag
                 collection_source_hint in the dispatch result.
                 Engine Completion Collector reads this hint to assign the
                 correct failure label. If hint is unavailable, default to
                 scenario 3 label (conservative — avoids misattributing
                 infrastructure failure to engine performance).
Output:          collection_result : {
                   result     : enum{SUCCESS, FAIL},
                   session_id : uuid,
                   errors     : [varchar] | NULL
                 }
Feeds:           UPLOADED→ANALYZED Executor        (if SUCCESS)
                 Invalid Transition Rejection Handler (if FAIL — surfaces engine errors)
Failure path:    IF collection_result = FAIL
                   → analysis_status = IDLE (cleared before surfacing error)
                   → state remains UPLOADED
                   → surface all named errors to UI
                   → [Analyze] button returns to ACTIVE — analyst may retry
Max retry policy (L2 P2 — 2026-03-27):
                 Without a retry limit, a persistent infrastructure failure
                 (e.g. engine crash loop, exhausted resources, network partition)
                 allows the analyst to trigger analysis indefinitely — masking the
                 root cause and consuming resources on each attempt.
                 Policy:
                   ANALYSIS_MAX_RETRIES = 3 (configurable · document in deployment config)
                   Counter: retry_count tracked in State Store per session_id,
                            incremented each time collection_result = FAIL for
                            this session.
                   IF retry_count < ANALYSIS_MAX_RETRIES
                     → [Analyze] returns ACTIVE as normal · analyst may retry
                   IF retry_count ≥ ANALYSIS_MAX_RETRIES
                     → [Analyze] rendered LOCKED
                     → surface: "Analysis has failed [n] times for this session.
                                  Contact your operator with Session ID: [session_id]
                                  before retrying."
                     → state remains UPLOADED · session is not terminal
                     → operator must investigate and confirm clearance before
                       retry_count is reset (manual operator action required)
                   Successful ANALYZED transition resets retry_count = 0 for
                   the session — partial retry history does not carry forward
                   to future analysis attempts within the same session.
                 Impact: retry_count field added to State Store schema.
                 Transition Executors and Invalid Transition Rejection Handler
                 must read retry_count before returning [Analyze] to ACTIVE.
                 No change to transition rules or valid transition table.
```

---

### Component 7: UPLOADED → ANALYZED Executor

```
Component:       UPLOADED → ANALYZED Executor
Layer:           State
Input:           collection_result : {result = SUCCESS, session_id}
Transformation:  IF collection_result = SUCCESS
                   → write to State Store:
                     new_state       = ANALYZED
                     analysis_status = NULL
                     trigger         = "engine_completion_success"
                     session_id      = session_id
                   → IF store_write_result = SUCCESS → transition_result = SUCCESS
                   → IF store_write_result = FAIL    → transition_result = FAIL
Output:          transition_result : {
                   result    : enum{SUCCESS, FAIL},
                   new_state : 'ANALYZED',
                   error     : varchar | NULL
                 }
Feeds:           State Store (write) · UI (via updated state — [Approve] activates)
Failure path:    IF State Store write fails
                   → transition_result = FAIL
                   · error = "UPLOADED→ANALYZED transition failed — state not persisted"
                   → state remains UPLOADED
                   → surface "Analysis completed but state could not be confirmed — retry"
```

---

### Component 8: ANALYZED → APPROVED Executor

```
Component:       ANALYZED → APPROVED Executor
Layer:           State
Input:           validation_result : {result = VALID,
                                      requested_transition = "ANALYZED→APPROVED",
                                      session_id}
                 — triggered by Approve Confirmation Dialog FIRE signal
Transformation:  IF validation_result = VALID
                   → transition_result = SUCCESS
                   → pass to Approved Result Writer (Component 9):
                       trigger         = "cfo_approval_fire"
                       session_id      = session_id
                   — Component 8 does NOT write application_state = APPROVED
                     to the State Store directly.
                   — Component 9 (Approved Result Writer) is the SOLE writer
                     of application_state = APPROVED and write_result in ONE
                     atomic State Store transaction.
                   — This component's role: validate the transition and trigger
                     Component 9. Not to write APPROVED independently.
                   (C-3 FIX — L1 Diagnostic Run 2 · 2026-03-27:
                    direct State Store write removed from this component.
                    Previously this block wrote new_state = APPROVED to State Store
                    separately from Component 9's write_result write — creating a
                    crash window. Single atomic write now owned exclusively by
                    Component 9. Feeds updated: State Store removed as direct target.)
Output:          transition_result : {
                   result     : enum{SUCCESS, FAIL},
                   new_state  : 'APPROVED',
                   session_id : uuid,
                   trigger    : varchar,
                   error      : varchar | NULL
                 }
Feeds:           Approved Result Writer (if SUCCESS — carries trigger + session_id)
Failure path:    IF validation_result is absent or malformed
                   → transition_result = FAIL
                   · error = "ANALYZED→APPROVED transition validation failed"
                   → state remains ANALYZED
                   → [Approve] returns to ACTIVE — CFO may retry
                   → do not trigger Approved Result Writer
```

---

### Component 9: Approved Result Writer

```
Component:       Approved Result Writer
Layer:           State
Input:           transition_result : {result = SUCCESS,
                                      new_state = 'APPROVED', session_id}
Transformation:  IF transition_result = SUCCESS AND new_state = APPROVED
                   → write final.allocation_result as immutable table:
                     source:  allocation_grain (current session)
                     columns: region · gpu_pool_id · date · billing_period
                              · allocation_target · unallocated_type
                              · failed_tenant_id
                              · gpu_hours · cost_per_gpu_hour · contracted_rate
                              · revenue · cogs · gross_margin
                              · row_id      : uuid (unique per row)
                              · approved_at : timestamp (server time at write)
                              · session_id  : uuid
                   → table is written once — no updates · no deletes permitted
                   → IF table write succeeds:
                       write_result = SUCCESS
                       → persist write_result = SUCCESS to State Store
                         (State Store field: write_result — set for current session_id)
                   → IF table write fails:
                       write_result = FAIL
                       → persist write_result = FAIL to State Store
Atomic write invariant: The State Store write that sets write_result MUST be
                 performed in the same atomic transaction as any State Store write
                 that confirms application_state = APPROVED for this session.
                 These two fields must never be written to the State Store in
                 separate transactions. A crash between two separate writes leaves
                 application_state = APPROVED but write_result = NULL — the Export
                 Gate Enforcer reads NULL and returns BLOCKED permanently after any
                 State Machine restart. Single-transaction write is mandatory.
                 (L2 P1 #26 — 2026-03-27)
                 Coordination mechanism (FIX — L1 Diagnostic 2026-03-27):
                 Component 8 (ANALYZED→APPROVED Executor) must NOT write
                 application_state = APPROVED to State Store independently.
                 Instead, Component 8 passes transition_result = SUCCESS to
                 Component 9 (Approved Result Writer), which performs ONE atomic
                 State Store transaction containing BOTH:
                   (a) application_state = APPROVED
                   (b) write_result = SUCCESS (or FAIL if table write fails)
                 Component 8's role is to validate the transition and trigger
                 Component 9 — not to write APPROVED directly. This collapses
                 two separate writes into one atomic transaction at a single
                 component boundary.
                 Impact: ANALYZED→APPROVED Executor component block must be
                 updated to remove its direct State Store write of new_state=APPROVED
                 and instead pass trigger to Approved Result Writer only.
                 Approved Result Writer becomes the sole writer for the APPROVED
                 state transition, eliminating the crash window between the two writes.
                 ELSE → do not write
Output:          write_result : {
                   result      : enum{SUCCESS, FAIL},
                   session_id  : uuid,
                   approved_at : timestamp,
                   row_count   : integer,
                   error       : varchar | NULL
                 }
Feeds:           APPROVED Session Closer (write_result signal — unchanged)
                 State Store (write_result field — persisted for Export Gate Enforcer)
                 Note: both consumers receive write_result from this component.
                 Session Closer receives the direct signal.
                 State Store receives the persisted field write.
                 Export Gate Enforcer reads write_result from State Store — not directly
                 from this component.
Failure path:    IF table write fails
                   → write_result = FAIL
                   → persist write_result = FAIL to State Store
                   · error = "Approved result table write failed"
                   → surface "Approval recorded but result table could not be written
                               — contact support"
                   → state remains APPROVED (transition already persisted)
                   → export remains locked (Export Gate Enforcer reads
                     write_result = FAIL from State Store · gate returns BLOCKED)
```

---

### Component 10: Invalid Transition Rejection Handler

```
Component:       Invalid Transition Rejection Handler
Layer:           State
Input:           validation_result : {result = INVALID, reason, current_state}
                 OR collection_result : {result = FAIL, errors}
Transformation:  IF source = Transition Validator (INVALID)
                   → rejection_type = INVALID_TRANSITION
                   · message = "Transition not permitted: [reason]"
                   → do not modify State Store
                   → do not advance state
                 IF source = Engine Completion Collector (FAIL)
                   → rejection_type = ENGINE_FAILURE
                   · message = all named engine errors (including timeout if applicable)
                   → state remains UPLOADED
                   → [Analyze] returns to ACTIVE
Output:          rejection_response : {
                   type    : enum{INVALID_TRANSITION, ENGINE_FAILURE},
                   message : varchar,
                   state   : varchar  (current state — unchanged)
                 }
Feeds:           UI (surfaces rejection message to analyst)
Failure path:    IF rejection cannot be communicated to UI
                   → log rejection server-side
                   · error = "Rejection handler failed to surface message"
                   → state remains unchanged regardless
```

---

### Component 11: Export Gate Enforcer

```
Component:       Export Gate Enforcer
Layer:           State
Input:           state_query : {requester = "APPROVED_STATE_GATE"}
                 — queried by Export Module APPROVED State Gate
                 — no session_id required in query: the Enforcer resolves
                   session_id from State Store (current active session)
Transformation:  Read application_state from State Store
                 Read session_id from State Store (current active session)
                 Read write_result from State Store (field: write_result — persisted
                   by Approved Result Writer at final.allocation_result write time)
                 Note: write_result is NOT read from Approved Result Writer directly.
                 It is read from the State Store where it was persisted at write time.
                 This ensures write_result survives State Machine restarts and is
                 available at any future export gate query — not only immediately
                 after the Approved Result Writer completes.
                 IF application_state = APPROVED
                    AND write_result = SUCCESS
                   → gate_response = OPEN
                 IF application_state ≠ APPROVED
                   → gate_response = BLOCKED
                   · reason = "State is [current_state] — export requires APPROVED"
                 IF application_state = APPROVED AND write_result = NULL
                   → gate_response = BLOCKED
                   · reason = "Approved result table write not yet confirmed —
                               export blocked (write_result not yet set)"
                 IF application_state = APPROVED AND write_result ≠ SUCCESS
                                                 AND write_result IS NOT NULL
                   → gate_response = BLOCKED
                   · reason = "Approved result table not confirmed — export blocked"
                 (P1 #27 FIX — L2 Run 3 · 2026-03-27:
                  NULL condition moved before ≠ SUCCESS condition.
                  Previously: condition 3 was 'write_result ≠ SUCCESS' — which
                  evaluates TRUE when write_result IS NULL (NULL ≠ SUCCESS = TRUE
                  in SQL and most evaluation contexts). Condition 4 (IS NULL) was
                  therefore dead code — the NULL case was always caught by condition 3
                  and returned "Approved result table not confirmed" reason, masking
                  the correct operator diagnosis of "write not yet set."
                  Fix: Evaluate NULL first (condition 3). Then evaluate explicit
                  FAIL — write_result ≠ SUCCESS AND write_result IS NOT NULL —
                  as condition 4. Three conditions are now non-overlapping and
                  exhaustive: OPEN / NULL / explicit-FAIL. Operators receive
                  the correct reason in all three cases.)
Output:          gate_response : {
                   result      : enum{OPEN, BLOCKED},
                   reason_code : enum{GATE_OPEN,
                                      GATE_BLOCKED_NOT_APPROVED,
                                      GATE_BLOCKED_WRITE_NULL,
                                      GATE_BLOCKED_WRITE_FAILED,
                                      GATE_BLOCKED_STATE_UNREADABLE} | NULL,
                   reason      : varchar | NULL
                 }
                 (P2 #27 FIX — 2026-03-27:
                  reason_code added as a structured enum field alongside the
                  human-readable reason string. Previously only a text reason
                  was returned — the Export APPROVED State Gate and any
                  operator tooling had to parse text to distinguish block causes.
                  reason_code allows programmatic branching without string parsing:
                    GATE_OPEN                    → result = OPEN
                    GATE_BLOCKED_NOT_APPROVED    → state ≠ APPROVED
                    GATE_BLOCKED_WRITE_NULL      → write_result IS NULL (not yet set)
                    GATE_BLOCKED_WRITE_FAILED    → write_result ≠ SUCCESS AND NOT NULL
                    GATE_BLOCKED_STATE_UNREADABLE → State Store read failure
                  reason (text) is preserved for human-readable operator messages.
                  Both fields are always returned together.
                  Export Module APPROVED State Gate must consume reason_code
                  and surface the correct distinct BLOCKED message per code:
                    GATE_BLOCKED_NOT_APPROVED    → "Export requires approval first"
                    GATE_BLOCKED_WRITE_NULL      → "Approval record incomplete —
                                                    contact your admin"
                    GATE_BLOCKED_WRITE_FAILED    → "Export blocked — result write
                                                    not confirmed"
                    GATE_BLOCKED_STATE_UNREADABLE → "System state unavailable —
                                                     try again or contact support")
Feeds:           Export Module APPROVED State Gate
Failure path:    IF State Store is unreadable at query time
                   → gate_response = BLOCKED
                   · reason_code = GATE_BLOCKED_STATE_UNREADABLE
                   · reason = "State unreadable — export blocked"
                   → do not open gate on read failure
```

---

### Component 12: APPROVED Session Closer

```
Component:       APPROVED Session Closer
Layer:           State
Input:           write_result : {result = SUCCESS, session_id}
                 — received from Approved Result Writer
Transformation:  IF write_result = SUCCESS
                   → write to State Store:
                     session_status = TERMINAL
                     terminal_at    = now() (recorded in state_history)
                   → configure Transition Request Receiver to block all future
                     transition_signals for this session_id:
                     any incoming signal → routed immediately to
                     Invalid Transition Rejection Handler
                     · reason = "Session [session_id] is terminal — no transitions permitted"
                   → closer_result = SUCCESS
Output:          closer_result : {
                   result      : enum{SUCCESS, FAIL},
                   session_id  : uuid,
                   terminal_at : timestamp
                 }
Feeds:           State Store (session_status write)
Failure path:    IF session_status write fails
                   → closer_result = FAIL
                   · error = "Session close failed — session may accept further transitions"
                   → surface "Session close error — contact support"
                   → export remains available (state = APPROVED · result written)
                   Scheduled retry (P1 #25 FIX — L2 Run 3 · 2026-03-27):
                   Previously the failure path said "retry on next incoming request
                   for this session_id." After APPROVED, NO further requests arrive
                   for that session_id — the retry never fires. A failed session close
                   leaves session_status ≠ TERMINAL indefinitely. The Transition
                   Request Receiver does not block signals for non-TERMINAL sessions
                   — the terminal gate remains open.
                   Fix: On closer_result = FAIL, the Session Closer MUST register
                   a background scheduled retry:
                     Retry interval : CLOSER_RETRY_INTERVAL (deployment-configured ·
                                       recommended default: 60 seconds)
                     Max attempts   : CLOSER_MAX_RETRIES (deployment-configured ·
                                       recommended default: 5 attempts)
                     Retry behavior : On each scheduled attempt, re-read session_id
                                       from State Store and re-issue the
                                       session_status = TERMINAL write.
                                       IF write succeeds → closer_result = SUCCESS ·
                                         cancel remaining scheduled retries.
                                       IF write fails again → decrement remaining
                                         attempts · schedule next retry.
                     After CLOSER_MAX_RETRIES exhausted without success:
                       → surface operator alert:
                         "CRITICAL: Session [session_id] could not be marked
                          TERMINAL after [n] attempts. Transition gate is open.
                          Manual session close required."
                       → operator must manually write session_status = TERMINAL
                         to State Store for this session_id before next session.
                   Deployment config: CLOSER_RETRY_INTERVAL and CLOSER_MAX_RETRIES
                   must be documented and tuned per environment. Both values must be
                   set before production deployment.
```

---

## STEP 4 — Problem-to-Design Analysis

```
Problem:          Without a server-side state gate, export can be triggered
                  from a pre-approval or incomplete state. Without a terminal
                  APPROVED session, re-analysis after CFO approval is
                  possible — invalidating the approved artifact. Without an
                  engine timeout and progress signal, a stalled engine leaves
                  the application in an ambiguous, indefinite state.

Required output:  A server-side state machine that enforces exactly three
                  valid transitions, rejects all others with a named reason,
                  requires both engines to succeed before ANALYZED fires,
                  writes final.allocation_result as an immutable table only
                  on APPROVED, responds OPEN to export gate queries only
                  when state = APPROVED AND result table write confirmed,
                  and marks the session terminal after APPROVED.

Design produces:  12 components. State Store persists state server-side and
                  rejects unauthorized writes. Transition Request Receiver
                  is the single entry point — no transition bypasses it.
                  Transition Validator enforces the three-rule table.
                  Analysis Dispatcher triggers both engines in parallel and
                  sets analysis_status = ANALYZING for UI progress signaling.
                  Engine Completion Collector requires both engines within
                  5 minutes — timeout fires FAIL and clears ANALYZING.
                  ANALYZED → APPROVED Executor triggers Approved Result
                  Writer — immutable write, once only. Export Gate Enforcer
                  gates on state = APPROVED AND confirmed result write —
                  not state alone. APPROVED Session Closer marks session
                  terminal and blocks all further signals for that session_id.

Gap or match:     MATCH. Gap identified in STEP 4 (undefined engine timeout
                  and no progress signal) closed by S1 — 5-minute fixed
                  timeout in Engine Completion Collector and ANALYZING
                  sub-status in State Store for UI progress display.
```

---

## Component Summary

| # | Component | Layer | Feeds |
|---|-----------|-------|-------|
| 1 | State Store | State | All consumers of application_state |
| 2 | Transition Request Receiver | State | Transition Validator (on new transition) · UI directly (on ALREADY_COMPLETE — P3 #28 FIX) |
| | | | (W-4 FIX — L1 Run 4 · 2026-03-27: UI direct feed added. P3 #28 FIX added idempotency |
| | | | contract — on ALREADY_COMPLETE the Receiver returns directly to UI without forwarding |
| | | | to Transition Validator. Summary row only listed Transition Validator. Now corrected.) |
| 3 | Transition Validator | State | Executors / Analysis Dispatcher / Rejection Handler |
| 4 | EMPTY → UPLOADED Executor | State | State Store · UI |
| 5 | Analysis Dispatcher | State | Engine Completion Collector (via engines) |
| 6 | Engine Completion Collector | State | UPLOADED→ANALYZED Executor / Rejection Handler |
| 7 | UPLOADED → ANALYZED Executor | State | State Store · UI |
| 8 | ANALYZED → APPROVED Executor | State | Approved Result Writer |
| | | | (W-1 FIX — L1 Diagnostic Run 3 · 2026-03-27: '· State Store' removed. |
| | | | C-3 fix in Run 2 made Component 9 the sole APPROVED writer — Component 8 |
| | | | no longer writes to State Store directly. Summary table was not updated |
| | | | at that time. Now corrected.) |
| 9 | Approved Result Writer | State | APPROVED Session Closer · State Store (write_result field — persisted for Export Gate Enforcer) |
| | | | (W-4 FIX — L1 Run 4 · 2026-03-27: State Store added as explicit feed. P1 #26 FIX made |
| | | | Component 9 the sole atomic writer of application_state = APPROVED + write_result in one |
| | | | transaction — State Store is a consumer of that write. Summary row only listed APPROVED |
| | | | Session Closer; State Store feed was omitted. Now corrected.) |
| 10 | Invalid Transition Rejection Handler | State | UI |
| 11 | Export Gate Enforcer | State | Export Module APPROVED State Gate |
| 12 | APPROVED Session Closer | State | State Store |
