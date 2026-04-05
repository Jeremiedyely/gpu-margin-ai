---
title: GPU Gross Margin Visibility — Full API Surface
interfaces: 14
modules: 6
categories: 4
adrs: 5
constraints: 11
session-key: session_id GUID · K1 · required on all contracts
governing-doc: solution-software-architect-api.md · software-system-design.md · software-architect-api.md
produced-by: solution-software-architect-api.md (solution layer) · software-architect-api.md Phase 3–4 (interface contracts) · Round 16 repair loop (ADR Register · Constraint Registry · Module Map · Category dimension)
---

# Full API Surface — GPU Gross Margin Visibility Application

> See: software-system-design.md — authoritative grain · module definitions · state machine
> See: architecture-diagram.mermaid — module topology · cross-module contracts K1–K5
> See: db-schema-design.md — field names · types · constraints

---

## Problem Statement

```
GPU cloud provider cannot see gross margin per tenant per GPU pool per day.
Revenue is computed separately from COGS with no reconciliation layer.
Identity mismatches (identity_broken tenants) and idle capacity are
invisible to the CFO — no mechanism exists to attribute, quantify,
or approve unallocated cost before export.
```

---

## Terminal Output Contract

```
TERMINAL OUTPUT:  CFO export — gross margin per grain cell
                  Region × GPU Pool × Day × Allocation Target
                  State = APPROVED · write_result = SUCCESS · immutable

CONDITIONS THAT MUST HOLD:
  1. All 14 interfaces executed without FAIL
  2. Closure Rule satisfied: SUM(gpu_hours per pool per day) = reserved_gpu_hours
  3. C9 sole-writer produced verbatim grain copy into final.allocation_result
  4. Export Gate returned OPEN (state = APPROVED AND write_result = SUCCESS · K5)
  5. K7 column set preserved: 13 grain columns · infrastructure columns excluded
  6. THROW 51000 active: final.allocation_result UPDATE + DELETE permanently blocked

WHAT GUARANTEES IT:
  ADR-01 — SM sole lifecycle controller prevents unauthorized state transitions
  ADR-02 — C9 sole-writer rule ensures only approved data enters final table
  ADR-03 — Dual-condition Export Gate prevents export from corrupt final table
  ADR-05 — Grain INSERT-only rule prevents silent downstream invalidation
```

---

## Module Responsibility Map

```
INGESTION
  Owns:        raw.telemetry · raw.cost_management · raw.iam · raw.billing · raw.erp · ingestion_log
  Produces:    session_id K1 · EMPTY_TO_UPLOADED signal
  Consumes:    5 source files from UI
  Boundaries:  ① Interface 1  → Ingestion (file intake · CAT 3)
               ② Interface 2  Ingestion → SM (UPLOADED signal · CAT 1)

ALLOCATION ENGINE
  Owns:        dbo.allocation_grain · dbo.kpi_cache · dbo.identity_broken_tenants
  Produces:    grain rows (Type A · CI · IB) · kpi_cache 1 row · IBT rows · AE_COMPLETE signal
  Consumes:    ANALYSIS_DISPATCHED from SM · raw tables from Ingestion
  Boundaries:  ③ Interface 3  SM → AE (dispatch · CAT 2)
               ⑤ Interface 5  AE → allocation_grain (write · CAT 3)
               ⑥ Interface 6  AE → kpi_cache (write · CAT 3)
               ⑦ Interface 7  AE → identity_broken_tenants (write · CAT 3)
               ⑧ Interface 8  AE → SM + RE (completion fan-out · CAT 2)

RECONCILIATION ENGINE
  Owns:        dbo.reconciliation_results
  Produces:    3 reconciliation verdicts (Check 1 · Check 2 · Check 3) · RE_COMPLETE signal
  Consumes:    ANALYSIS_DISPATCHED from SM · AE_COMPLETE from AE (gates Check 3) · raw tables · K2
  Boundaries:  ④ Interface 4  SM → RE (dispatch · CAT 2)
               ⑧ Interface 8  AE fan-out → RE ACL (completion gate · CAT 2)
               ⑨ Interface 9  RE → reconciliation_results (write · CAT 3)
               ⑩ Interface 10 RE → SM (completion signal · CAT 2)

STATE MACHINE
  Owns:        State Store (application_state · write_result K5) · state_history ·
               final.allocation_result (sole-writer via C9 · ADR-02 · THROW 51000)
  Produces:    lifecycle transitions · ANALYSIS_DISPATCHED signals · APPROVED state · Export Gate verdict
  Consumes:    EMPTY_TO_UPLOADED from Ingestion · AE_COMPLETE + RE_COMPLETE from engines ·
               ANALYZED_TO_APPROVED from UI
  Boundaries:  ② Interface 2  Ingestion → SM (Transition Request Receiver · CAT 1)
               ③④ Interfaces 3+4  SM → AE + RE (Analysis Dispatcher · CAT 2)
               ⑧⑩ Interfaces 8+10 Engine completions → SM Collector (CAT 2)
               ⑪ Interface 11 UI → SM (APPROVED signal · CAT 1)
               ⑫ Interface 12 SM → final.allocation_result (C9 write · CAT 3)
               ⑬ Interface 13 Export → SM Export Gate (gate query · CAT 4)

UI SCREEN
  Owns:        no data stores
  Produces:    5 source files · ANALYZED_TO_APPROVED approval signal
  Consumes:    kpi_cache (Zone 1 KPIs) · allocation_grain (Zone 2L/2R) ·
               reconciliation_results (Zone 3) · session state
  Boundaries:  ① Interface 1  UI → Ingestion (file upload · CAT 3)
               ⑪ Interface 11 UI → SM (APPROVED signal · CAT 1)

EXPORT
  Owns:        no data stores
  Produces:    CFO export file (CSV · Excel · Power BI) · immutable per session
  Consumes:    Export Gate verdict from SM · final.allocation_result (post-gate)
  Boundaries:  ⑬ Interface 13 Export → SM Export Gate (CAT 4)
               ⑭ Interface 14 Export → final.allocation_result (read · CAT 3)
```

---

## Index

| # | Interface | Category | Type | K-contracts | ADR | Section |
|---|-----------|----------|------|-------------|-----|---------|
| 1 | UI → Ingestion (file upload) | CAT 3 — Data Production | T3 — Data Write | K1 | — | §TYPE-3-01 |
| 2 | Ingestion → State Machine (UPLOADED) | CAT 1 — Lifecycle Control | T1 — State Transition | K1 | ADR-01 | §TYPE-1-01 |
| 3 | State Machine → AE (run signal) | CAT 2 — Engine Orchestration | T2 — Engine Run | K1 | ADR-01 | §TYPE-2-01 |
| 4 | State Machine → RE (run signal) | CAT 2 — Engine Orchestration | T2 — Engine Run | K1 | ADR-01 | §TYPE-2-02 |
| 5 | AE → allocation_grain (write) | CAT 3 — Data Production | T3 — Data Write | K1 K2 K3 K4 | ADR-05 | §TYPE-3-02 |
| 6 | AE → kpi_cache (write at ANALYZED) | CAT 3 — Data Production | T3 — Data Write | K1 | ADR-05 | §TYPE-3-03 |
| 7 | AE → identity_broken_tenants (write) | CAT 3 — Data Production | T3 — Data Write | K1 K3 | ADR-05 | §TYPE-3-04 |
| 8 | AE → SM + RE (completion fan-out) | CAT 2 — Engine Orchestration | T2 — Engine Run | K1 | ADR-04 | §TYPE-2-03 |
| 9 | RE → reconciliation_results (write) | CAT 3 — Data Production | T3 — Data Write | K1 K2 | — | §TYPE-3-05 |
| 10 | RE → State Machine (completion signal) | CAT 2 — Engine Orchestration | T2 — Engine Run | K1 | ADR-01 | §TYPE-2-04 |
| 11 | UI → State Machine (APPROVED signal) | CAT 1 — Lifecycle Control | T1 — State Transition | K1 | ADR-01 | §TYPE-1-02 |
| 12 | SM → final.allocation_result (write C9) | CAT 3 — Data Production | T3 — Data Write | K1 K5 | ADR-02 | §TYPE-3-06 |
| 13 | Export → SM Export Gate (query) | CAT 4 — Gate Enforcement | T4 — Gate Query | K1 K5 | ADR-03 | §TYPE-4-01 |
| 14 | Export → final.allocation_result (read) | CAT 3 — Data Production | T3 — Data Read | K1 | ADR-02 ADR-03 | §TYPE-3-07 |

---

## TYPE 1 — State Transition Signals  ·  CATEGORY 1: Lifecycle Control

Pattern: fire-and-confirm
Solution layer: one module signals the State Machine to advance the session lifecycle.
Required fields on all TYPE 1: session_id · requested_transition · source_component
Response fields on all TYPE 1: transition_result (ACCEPTED | REJECTED) · new_state · rejection_reason (if REJECTED)
Governing ADR: ADR-01 — State Machine as sole lifecycle controller

---

### §TYPE-1-01 · Interface 2 — Ingestion → State Machine

```
═══════════════════════════════════════════════════════════════════
CONTRACT: Ingestion (State Transition Emitter) → State Machine (Transition Request Receiver)
TYPE: 1 — State Transition Signal
SESSION KEY: session_id GUID — required · K1
═══════════════════════════════════════════════════════════════════

REQUEST
  Method:               internal call · fired by Ingestion Commit on SUCCESS
  Required:
    session_id          GUID          K1 · generated by Ingestion Orchestrator
    requested_transition  NVARCHAR50  "EMPTY_TO_UPLOADED"
    source_component    NVARCHAR50    "INGESTION_COMMIT"

───────────────────────────────────────────────────────────────────
RESPONSE — SUCCESS
  transition_result     ACCEPTED
  new_state             UPLOADED
  session_id            GUID

───────────────────────────────────────────────────────────────────
RESPONSE — FAILURE
  INVALID_TRANSITION
    detected by:  Transition Validator
    handled by:   Transition Request Receiver
    retryable:    NO — session is not in EMPTY state · operator investigation required
    structure:    { error_code, error_message, session_id, source_component, current_state }
    recovery:     Ingestion logs failure · session dropped · new upload required

  SESSION_NOT_FOUND
    detected by:  Transition Request Receiver
    handled by:   Ingestion (State Transition Emitter)
    retryable:    NO — session_id was not committed to ingestion_log before signal fired
    structure:    { error_code, error_message, session_id, source_component }
    recovery:     Ingestion re-checks ingestion_log write · escalate if log entry missing

  DUPLICATE_SIGNAL
    detected by:  Transition Validator
    handled by:   Transition Request Receiver
    retryable:    NO — UPLOADED already set · second signal is structural error in Ingestion
    structure:    { error_code, error_message, session_id, current_state }
    recovery:     Ingestion Commit has a defect — deduplicate at emitter before re-signaling

───────────────────────────────────────────────────────────────────
GUARANTEES
  Idempotency:  NO — duplicate signal returns DUPLICATE_SIGNAL · second call is not safe
  Atomicity:    YES — UPLOADED state write and state_history entry written in same transaction
  Ordering:     ENFORCED — Transition Validator enforces EMPTY → UPLOADED · out-of-order rejected

═══════════════════════════════════════════════════════════════════
```

---

### §TYPE-1-02 · Interface 11 — UI → State Machine (APPROVED signal)

```
═══════════════════════════════════════════════════════════════════
CONTRACT: UI (Approve Confirmation Dialog) → State Machine (Transition Request Receiver)
TYPE: 1 — State Transition Signal
SESSION KEY: session_id GUID — required · K1
NOTE: This is the CFO gate. Triggers SM → final.allocation_result write (Interface 12) atomically.
═══════════════════════════════════════════════════════════════════

REQUEST
  Method:               internal call · HTTP POST · fired by [Confirm Approval] click only
  Required:
    session_id          GUID          K1
    requested_transition  NVARCHAR50  "ANALYZED_TO_APPROVED"
    source_component    NVARCHAR50    "APPROVAL_DIALOG"
  Note: SM rejects this signal from any source_component other than "APPROVAL_DIALOG"

───────────────────────────────────────────────────────────────────
RESPONSE — SUCCESS
  transition_result     ACCEPTED
  new_state             APPROVED
  session_id            GUID
  Note: SM Approved Result Writer C9 fires immediately after ACCEPTED (Interface 12)

───────────────────────────────────────────────────────────────────
RESPONSE — FAILURE
  INVALID_TRANSITION
    detected by:  Transition Validator
    handled by:   Transition Request Receiver
    retryable:    NO — session not in ANALYZED state · UI must re-read current state
    structure:    { error_code, error_message, session_id, current_state }
    recovery:     UI refreshes state display · [Approve] button re-evaluates active status

  SESSION_TERMINAL
    detected by:  Transition Validator
    handled by:   Transition Request Receiver
    retryable:    NO — APPROVED is terminal · no further transitions permitted
    structure:    { error_code, error_message, session_id, current_state: "APPROVED" }
    recovery:     UI deactivates [Approve] button · export controls remain ACTIVE

  SESSION_NOT_FOUND
    detected by:  Transition Request Receiver
    handled by:   UI (Approve Confirmation Dialog)
    retryable:    NO
    structure:    { error_code, error_message, session_id }
    recovery:     UI displays error · CFO must reload session

  UNAUTHORIZED_SOURCE
    detected by:  Transition Validator
    handled by:   Transition Request Receiver
    retryable:    NO — source_component not "APPROVAL_DIALOG" · structural defect in caller
    structure:    { error_code, error_message, session_id, source_component }
    recovery:     Escalate — only APPROVAL_DIALOG may trigger APPROVED transition

───────────────────────────────────────────────────────────────────
GUARANTEES
  Idempotency:  NO — if APPROVED already, returns SESSION_TERMINAL · not a safe retry
  Atomicity:    YES — APPROVED state write is atomic with Interface 12 (C9 grain copy) · K5
  Ordering:     ENFORCED — session must be in ANALYZED state · SM rejects any other state

═══════════════════════════════════════════════════════════════════
```

---

## TYPE 2 — Engine Run Signals  ·  CATEGORY 2: Engine Orchestration

Pattern: dispatch-and-acknowledge · completion separate
Solution layer: State Machine dispatches signals to engines and collects completion reports.
Completion reported separately via Completion Emitter — NOT in the acknowledgment response.
Required fields on all TYPE 2: session_id · run_signal | completion_result · timestamp
Governing ADR: ADR-01 (dispatch authority) · ADR-04 (fan-out non-atomicity)

---

### §TYPE-2-01 · Interface 3 — State Machine → Allocation Engine

```
═══════════════════════════════════════════════════════════════════
CONTRACT: State Machine (Analysis Dispatcher) → Allocation Engine (Run Receiver)
TYPE: 2 — Engine Run Signal · dispatch-and-acknowledge
SESSION KEY: session_id GUID — required · K1
NOTE: Dispatched simultaneously with Interface 4 (SM → RE). AE and RE run in parallel.
═══════════════════════════════════════════════════════════════════

REQUEST
  Method:               internal call · fired by Analysis Dispatcher on UPLOADED state
  Required:
    run_signal          NVARCHAR50    "ANALYSIS_DISPATCHED"
    session_id          GUID          K1
    dispatch_timestamp  DATETIME2     SM dispatch time · AE uses for 5-min timeout calculation

───────────────────────────────────────────────────────────────────
RESPONSE — ACKNOWLEDGMENT ONLY (not completion)
  acknowledgment_result   RECEIVED
  session_id              GUID
  Note: AE completion is reported via Interface 8 (Completion Emitter) — not here

───────────────────────────────────────────────────────────────────
RESPONSE — FAILURE
  DUPLICATE_RUN
    detected by:  AE Run Receiver
    handled by:   AE Run Receiver
    retryable:    NO — AE already processing this session_id · structural error in Dispatcher
    structure:    { error_code, error_message, session_id }
    recovery:     SM Dispatcher deduplicates by session_id · does not re-dispatch

  SESSION_INVALID
    detected by:  AE Run Receiver
    handled by:   AE Run Receiver
    retryable:    NO — session_id not in UPLOADED state at time of dispatch
    structure:    { error_code, error_message, session_id, current_state }
    recovery:     SM re-checks state before re-dispatching · only valid from UPLOADED

  AE_UNAVAILABLE
    detected by:  SM Analysis Dispatcher (timeout on acknowledgment)
    handled by:   SM Analysis Dispatcher
    retryable:    CONDITIONAL — retry up to SM-defined limit · SM transitions to FAIL after limit
    structure:    { error_code, error_message, session_id }
    recovery:     SM marks analysis FAIL · session remains in UPLOADED · operator recovery required

───────────────────────────────────────────────────────────────────
GUARANTEES
  Idempotency:  NO — duplicate dispatch raises DUPLICATE_RUN · AE does not run twice
  Atomicity:    N/A — signal only · no write at acknowledgment
  Ordering:     ENFORCED — SM dispatches only when state = UPLOADED and analysis_status = IDLE

═══════════════════════════════════════════════════════════════════
```

---

### §TYPE-2-02 · Interface 4 — State Machine → Reconciliation Engine

```
═══════════════════════════════════════════════════════════════════
CONTRACT: State Machine (Analysis Dispatcher) → Reconciliation Engine (Run Receiver)
TYPE: 2 — Engine Run Signal · dispatch-and-acknowledge
SESSION KEY: session_id GUID — required · K1
NOTE: Dispatched simultaneously with Interface 3 (SM → AE). RE and AE run in parallel.
      Check 1 and Check 2 begin immediately. Check 3 is gated on AE completion (Interface 8).
═══════════════════════════════════════════════════════════════════

REQUEST
  Method:               internal call · fired by Analysis Dispatcher simultaneously with Interface 3
  Required:
    run_signal          NVARCHAR50    "ANALYSIS_DISPATCHED"
    session_id          GUID          K1
    dispatch_timestamp  DATETIME2     SM dispatch time · RE uses for timeout calculation

───────────────────────────────────────────────────────────────────
RESPONSE — ACKNOWLEDGMENT ONLY
  acknowledgment_result   RECEIVED
  session_id              GUID
  Note: RE completion is reported via Interface 10 (Completion Emitter) — not here
        Check 3 does not start until AE sends completion signal (Interface 8 → RE_ACL)

───────────────────────────────────────────────────────────────────
RESPONSE — FAILURE
  DUPLICATE_RUN
    detected by:  RE Run Receiver
    handled by:   RE Run Receiver
    retryable:    NO — same as Interface 3
    structure:    { error_code, error_message, session_id }
    recovery:     SM deduplicates · does not re-dispatch

  SESSION_INVALID
    detected by:  RE Run Receiver
    handled by:   RE Run Receiver
    retryable:    NO
    structure:    { error_code, error_message, session_id, current_state }
    recovery:     SM re-checks state

  RE_UNAVAILABLE
    detected by:  SM Analysis Dispatcher (timeout on acknowledgment)
    handled by:   SM Analysis Dispatcher
    retryable:    CONDITIONAL — retry up to SM-defined limit
    structure:    { error_code, error_message, session_id }
    recovery:     SM marks analysis FAIL · operator recovery required

───────────────────────────────────────────────────────────────────
GUARANTEES
  Idempotency:  NO — duplicate dispatch raises DUPLICATE_RUN
  Atomicity:    N/A — signal only
  Ordering:     ENFORCED — Check 3 internally gated on AE completion · RE handles this independently

═══════════════════════════════════════════════════════════════════
```

---

### §TYPE-2-03 · Interface 8 — AE → SM + RE (Completion Signal Fan-Out)

```
═══════════════════════════════════════════════════════════════════
CONTRACT: AE (Completion Emitter) → SM (Engine Completion Collector) + RE (AE Completion Listener)
TYPE: 2 — Engine Run Signal · fan-out · two recipients
SESSION KEY: session_id GUID — required · K1
NOTE: Fan-out — single signal sent to two consumers simultaneously.
      Partial delivery is possible. Each recipient handles independently.
      SM requires BOTH AE and RE completion before ANALYZED gate opens.
      RE_ACL requires this signal to ungate Check 3.
═══════════════════════════════════════════════════════════════════

REQUEST
  Method:               internal call · fan-out to two recipients
  Required:
    run_signal          NVARCHAR50    "AE_COMPLETE"
    session_id          GUID          K1
    completion_result   NVARCHAR10    SUCCESS | FAIL
    completion_timestamp  DATETIME2   AE completion time
    fail_reason         NVARCHAR255   NULL on SUCCESS · describes failure on FAIL
  Recipients:
    → SM Engine Completion Collector
    → RE AE Completion Listener (gates Check 3)

───────────────────────────────────────────────────────────────────
RESPONSE — ACKNOWLEDGMENT (per recipient)
  acknowledgment_result   RECEIVED
  session_id              GUID
  recipient               SM_COLLECTOR | RE_LISTENER

───────────────────────────────────────────────────────────────────
RESPONSE — FAILURE
  SM_COLLECTOR_UNREACHABLE
    detected by:  AE Completion Emitter (no ACK within timeout)
    handled by:   AE Completion Emitter
    retryable:    CONDITIONAL — retry up to 5-min SM timeout from dispatch · then FAIL
    structure:    { error_code, error_message, session_id, recipient: "SM_COLLECTOR" }
    recovery:     SM times out · marks AE FAIL · session remains UPLOADED · operator required

  RE_LISTENER_UNREACHABLE
    detected by:  AE Completion Emitter (no ACK within timeout)
    handled by:   AE Completion Emitter
    retryable:    CONDITIONAL — retry up to RE timeout ceiling
    structure:    { error_code, error_message, session_id, recipient: "RE_LISTENER" }
    recovery:     RE Check 3 cannot proceed · RE times out · RE emits FAIL to SM Collector

  PARTIAL_DELIVERY
    detected by:  AE Completion Emitter
    handled by:   AE Completion Emitter
    retryable:    CONDITIONAL — retry unACKed recipient only · do not re-send to ACKed recipient
    structure:    { error_code, error_message, session_id, unacked_recipient }
    recovery:     Retry unACKed recipient · log partial delivery · escalate if retry exhausted

───────────────────────────────────────────────────────────────────
GUARANTEES
  Idempotency:  NO — deduplicate by session_id + signal type at each recipient
  Atomicity:    NO — fan-out is not atomic · each recipient handles independently
  Ordering:     ENFORCED — Grain Write (Interface 5) + Cache Writes (6,7) must complete before this fires

═══════════════════════════════════════════════════════════════════
```

---

### §TYPE-2-04 · Interface 10 — RE → State Machine (Completion Signal)

```
═══════════════════════════════════════════════════════════════════
CONTRACT: RE (Completion Emitter) → State Machine (Engine Completion Collector)
TYPE: 2 — Engine Run Signal · completion report
SESSION KEY: session_id GUID — required · K1
NOTE: SM Engine Completion Collector requires BOTH this signal AND AE completion signal
      (Interface 8 → SM) before opening ANALYZED gate.
      RE timeout: max(5 min from dispatch · AE completion time + 5 min).
═══════════════════════════════════════════════════════════════════

REQUEST
  Method:               internal call · fired by RE Completion Emitter after Result Writer
  Required:
    run_signal          NVARCHAR50    "RE_COMPLETE"
    session_id          GUID          K1
    completion_result   NVARCHAR10    SUCCESS | FAIL
    completion_timestamp  DATETIME2   RE completion time
    fail_reason         NVARCHAR255   NULL on SUCCESS · describes failure on FAIL

───────────────────────────────────────────────────────────────────
RESPONSE — ACKNOWLEDGMENT
  acknowledgment_result   RECEIVED
  session_id              GUID

───────────────────────────────────────────────────────────────────
RESPONSE — FAILURE
  SM_COLLECTOR_UNREACHABLE
    detected by:  RE Completion Emitter (no ACK within RE timeout)
    handled by:   RE Completion Emitter
    retryable:    CONDITIONAL — retry up to RE timeout ceiling
    structure:    { error_code, error_message, session_id }
    recovery:     SM times out on RE · marks RE FAIL · ANALYZED gate does not open

  DUPLICATE_COMPLETION
    detected by:  SM Engine Completion Collector
    handled by:   SM Engine Completion Collector
    retryable:    NO — deduplicate by session_id + signal type
    structure:    { error_code, error_message, session_id }
    recovery:     SM ignores duplicate · uses first received completion result

───────────────────────────────────────────────────────────────────
GUARANTEES
  Idempotency:  NO — SM Collector deduplicates by session_id + signal type
  Atomicity:    N/A — signal only
  Ordering:     ENFORCED — RE Result Writer (Interface 9) must complete before this signal fires

═══════════════════════════════════════════════════════════════════
```

---

## TYPE 3 — Data Read / Write  ·  CATEGORY 3: Data Production

Pattern: write-and-confirm | query-and-return
Solution layer: a module produces data into a table it exclusively owns (writes) or reads from it (reads).
Required fields: session_id K1 · result (SUCCESS | FAIL) · rows_written | rows_read
Governing ADR: ADR-02 (C9 sole-writer · Interface 12) · ADR-05 (grain INSERT-only · Interface 5)

---

### §TYPE-3-01 · Interface 1 — UI → Ingestion (File Upload)

```
═══════════════════════════════════════════════════════════════════
CONTRACT: UI (5 Upload Slots) → Ingestion (Ingestion Orchestrator)
TYPE: 3 — Data Write · file intake
SESSION KEY: session_id — NOT yet assigned · generated by Ingestion Orchestrator on receipt
NOTE: session_id is the OUTPUT of this interface, not the input.
      All 5 files must be present for the call to be accepted.
═══════════════════════════════════════════════════════════════════

REQUEST
  Method:               HTTP POST · multipart/form-data
  Required:
    files               FILE[5]       exactly 5 · one per source type
      telemetry         FILE          raw.telemetry source · CSV
      cost_management   FILE          raw.cost_management source · CSV
      iam               FILE          raw.iam source · CSV
      billing           FILE          raw.billing source · CSV
      erp               FILE          raw.erp source · CSV
  Note: No session_id in request — Ingestion Orchestrator generates it

───────────────────────────────────────────────────────────────────
RESPONSE — SUCCESS
  result                RECEIVED
  session_id            GUID          K1 · generated by Ingestion Orchestrator
  files_received        INT           5
  status                PROCESSING    validators and parsers executing

───────────────────────────────────────────────────────────────────
RESPONSE — FAILURE
  FILE_COUNT_MISMATCH
    detected by:  Ingestion Orchestrator
    handled by:   Ingestion Orchestrator
    retryable:    YES — re-upload with all 5 files
    structure:    { error_code, error_message, files_received, files_required: 5 }
    recovery:     UI shows missing file slots · CFO re-uploads complete set

  FILE_TYPE_INVALID
    detected by:  Validator × 5
    handled by:   Ingestion Orchestrator (FAIL path — drops session)
    retryable:    YES — re-upload corrected file
    structure:    { error_code, error_message, filename, validation_failure_reason }
    recovery:     UI highlights failing slot · CFO corrects and re-uploads

  UPLOAD_INTERRUPTED
    detected by:  Raw Table Writer × 5
    handled by:   Ingestion Commit (FAIL → drop entire session · no partial data)
    retryable:    YES — re-upload all 5 files
    structure:    { error_code, error_message, session_id }
    recovery:     Ingestion Commit drops partial session · UI resets to EMPTY state

───────────────────────────────────────────────────────────────────
GUARANTEES
  Idempotency:  NO — each call generates a new session_id · duplicate uploads = new session
  Atomicity:    YES — Ingestion Commit: all 5 files promoted or none · no partial session
  Ordering:     NO — files may arrive in any order within the batch · Orchestrator assembles

═══════════════════════════════════════════════════════════════════
```

---

### §TYPE-3-02 · Interface 5 — AE → allocation_grain (Write)

```
═══════════════════════════════════════════════════════════════════
CONTRACT: AE (Allocation Grain Writer) → dbo.allocation_grain
TYPE: 3 — Data Write · INSERT-only · atomic per session
SESSION KEY: session_id GUID — required · K1
NOTE: INSTEAD OF UPDATE trigger active: THROW 51003 (TR_allocation_grain_prevent_update · R14-W-1)
      DELETE permitted for Ingestion Commit session replacement only.
      Three record types per grain: Type A · capacity_idle · identity_broken.
      Closure Rule enforced before write: SUM(gpu_hours per pool per day) = reserved_gpu_hours.
═══════════════════════════════════════════════════════════════════

REQUEST
  Method:               SQL INSERT · batched · single transaction per session
  Required (per row):
    session_id          GUID          K1
    region              NVARCHAR(100) grain dimension 1
    gpu_pool_id         NVARCHAR(100) grain dimension 2
    date                DATE          grain dimension 3 · ISO 8601 YYYY-MM-DD
    billing_period      NVARCHAR(7)   dim 4a · LEFT(date,7) · K2
    allocation_target   NVARCHAR(255) dim 4b · tenant_id (TypeA) | 'unallocated' (TypeB)
    unallocated_type    NVARCHAR(20)  NULL (TypeA) | 'capacity_idle' | 'identity_broken' · K4
    failed_tenant_id    NVARCHAR(255) NULL (TypeA + CI) · original tenant_id (IB only) · K3
    gpu_hours           DECIMAL(18,6) gt 0
    cost_per_gpu_hour   DECIMAL(18,6) gt 0 · from raw.cost_management · same for all rows in pool-day
    contracted_rate     DECIMAL(18,6) NULL (TypeB) · from raw.iam (TypeA only)
    revenue             DECIMAL(18,2) TypeA: gpu_hours × contracted_rate · TypeB: 0 exactly
    cogs                DECIMAL(18,2) gt 0 · gpu_hours × cost_per_gpu_hour · all types
    gross_margin        DECIMAL(18,2) TypeA: revenue − cogs · TypeB: −cogs (always lt 0, never 0)

───────────────────────────────────────────────────────────────────
RESPONSE — SUCCESS
  result                SUCCESS
  session_id            GUID
  rows_written          INT           total rows across all three types

───────────────────────────────────────────────────────────────────
RESPONSE — FAILURE
  CONSTRAINT_VIOLATION
    detected by:  SQL engine (CHK constraint · 13 total)
    handled by:   AE Allocation Grain Writer (ROLLBACK on failure)
    retryable:    NO — formula or range violation indicates AE calculation defect
    structure:    { error_code, error_message, session_id, violated_constraint, row_detail }
    recovery:     AE emits FAIL to SM Collector and RE_ACL · session remains UPLOADED

  DUPLICATE_GRAIN_KEY
    detected by:  SQL engine (filtered UNIQUE index · C-3 · 3 indexes)
    handled by:   AE Allocation Grain Writer (ROLLBACK)
    retryable:    NO — AE produced duplicate grain cell · deduplication defect in AE
    structure:    { error_code, error_message, session_id, index_name, natural_key_values }
    recovery:     AE emits FAIL · operator investigates Closure Rule Enforcer and AE dedup logic

  TRIGGER_BLOCKED
    detected by:  SQL engine (INSTEAD OF UPDATE · THROW 51003)
    handled by:   AE Allocation Grain Writer
    retryable:    NO — UPDATE path does not exist in correct AE code · structural defect
    structure:    { error_code: 51003, error_message, session_id }
    recovery:     Escalate — AE has an UPDATE statement where only INSERT is permitted

───────────────────────────────────────────────────────────────────
GUARANTEES
  Idempotency:  NO — duplicate INSERT raises DUPLICATE_GRAIN_KEY
  Atomicity:    YES — all rows for session in one transaction · ROLLBACK on any failure
  Ordering:     ENFORCED — Closure Rule Enforcer must complete before write ·
                            all three record types included before transaction commits

═══════════════════════════════════════════════════════════════════
```

---

### §TYPE-3-03 · Interface 6 — AE → kpi_cache (Write at ANALYZED)

```
═══════════════════════════════════════════════════════════════════
CONTRACT: AE (KPI Data Aggregator) → dbo.kpi_cache
TYPE: 3 — Data Write · INSERT-only · one row per session
SESSION KEY: session_id GUID — PK and K1
NOTE: INSTEAD OF UPDATE + DELETE trigger: THROW 51001 (TR_kpi_cache_prevent_mutation · R11-W-1)
      Written at ANALYZED time. Prerequisite: Interface 5 (grain write) must be complete.
      consumed_at (R15-REC-1): operator diagnostic timestamp — no downstream consumer declared.
═══════════════════════════════════════════════════════════════════

REQUEST
  Method:               SQL INSERT · single row per session
  Required:
    session_id          GUID          K1 · PK
    gpu_revenue         DECIMAL(18,2) gte 0 · SUM(TypeA revenue) · Zone 1 KPI
    gpu_cogs            DECIMAL(18,2) gte 0 · SUM(TypeA cogs) · Zone 1 KPI
    idle_gpu_cost       DECIMAL(18,2) gte 0 · SUM(TypeB cogs) · Zone 1 KPI
    idle_gpu_cost_pct   DECIMAL(5,2)  0–100 · idle_gpu_cost / (gpu_cogs + idle_gpu_cost) × 100
    cost_allocation_rate  DECIMAL(5,2) 0–100 · gpu_cogs / (gpu_cogs + idle_gpu_cost) × 100
    computed_at         DATETIME2     DEFAULT SYSUTCDATETIME · R15-REC-1 operator diagnostic

───────────────────────────────────────────────────────────────────
RESPONSE — SUCCESS
  result                SUCCESS
  session_id            GUID
  rows_written          1

───────────────────────────────────────────────────────────────────
RESPONSE — FAILURE
  GRAIN_NOT_FOUND
    detected by:  KPI Data Aggregator (before INSERT)
    handled by:   KPI Data Aggregator
    retryable:    CONDITIONAL — retry after confirming Interface 5 completed successfully
    structure:    { error_code, error_message, session_id }
    recovery:     AE checks grain write result · retries kpi_cache write once · then FAIL

  DUPLICATE_SESSION
    detected by:  SQL engine (PK violation)
    handled by:   KPI Data Aggregator
    retryable:    NO — one row per session is a hard constraint · structural defect in AE
    structure:    { error_code, error_message, session_id }
    recovery:     Escalate — KPI Aggregator fired twice for same session

  TRIGGER_BLOCKED
    detected by:  SQL engine (INSTEAD OF UPDATE / DELETE · THROW 51001)
    handled by:   KPI Data Aggregator
    retryable:    NO — UPDATE/DELETE path does not exist in correct AE code
    structure:    { error_code: 51001, error_message, session_id }
    recovery:     Escalate — structural defect in KPI Aggregator

  PCT_TOLERANCE_VIOLATION
    detected by:  KPI Data Aggregator (before write) · CHK constraint (at write)
    handled by:   KPI Data Aggregator
    retryable:    NO — idle_gpu_cost_pct + cost_allocation_rate must sum to 100 (tol 0.01)
    structure:    { error_code, error_message, session_id, pct_sum }
    recovery:     AE recalculates percentages · checks for floating-point rounding error

───────────────────────────────────────────────────────────────────
GUARANTEES
  Idempotency:  NO — duplicate INSERT raises DUPLICATE_SESSION
  Atomicity:    YES — single row INSERT · all or nothing
  Ordering:     ENFORCED — allocation_grain write (Interface 5) must complete first

═══════════════════════════════════════════════════════════════════
```

---

### §TYPE-3-04 · Interface 7 — AE → identity_broken_tenants (Write)

```
═══════════════════════════════════════════════════════════════════
CONTRACT: AE (SET Pre-Builder) → dbo.identity_broken_tenants
TYPE: 3 — Data Write · INSERT-only · composite PK · zero or more rows per session
SESSION KEY: session_id GUID — composite PK col 1 · K1
NOTE: INSTEAD OF UPDATE + DELETE trigger: THROW 51002 (TR_identity_broken_tenants_prevent_mutation · R11-W-2)
      Zero rows is valid — no IB grain rows means no IB tenants to record.
      K3: failed_tenant_id carries from IB grain rows through IBT into Zone 2R Risk flag.
═══════════════════════════════════════════════════════════════════

REQUEST
  Method:               SQL INSERT · batched · single transaction
  Required (per row):
    session_id          GUID          K1 · composite PK col 1
    failed_tenant_id    NVARCHAR(255) composite PK col 2 · K3 · original tenant_id of IB grain row
  Note: One row per unique failed_tenant_id across all IB grain rows for this session
        Zero rows valid if no identity_broken grain rows exist for session

───────────────────────────────────────────────────────────────────
RESPONSE — SUCCESS
  result                SUCCESS
  session_id            GUID
  rows_written          INT           0 if no IB rows · gt 0 if IB rows exist

───────────────────────────────────────────────────────────────────
RESPONSE — FAILURE
  GRAIN_NOT_FOUND
    detected by:  SET Pre-Builder (query before INSERT)
    handled by:   SET Pre-Builder
    retryable:    CONDITIONAL — retry after confirming Interface 5 completed
    structure:    { error_code, error_message, session_id }
    recovery:     AE checks grain write result · retries once · then FAIL

  DUPLICATE_IB_KEY
    detected by:  SQL engine (composite PK violation)
    handled by:   SET Pre-Builder
    retryable:    NO — structural defect · SET Pre-Builder produced duplicate failed_tenant_id
    structure:    { error_code, error_message, session_id, failed_tenant_id }
    recovery:     AE deduplicates failed_tenant_id SET before INSERT

  TRIGGER_BLOCKED
    detected by:  SQL engine (INSTEAD OF UPDATE / DELETE · THROW 51002)
    handled by:   SET Pre-Builder
    retryable:    NO
    structure:    { error_code: 51002, error_message, session_id }
    recovery:     Escalate — structural defect in SET Pre-Builder

───────────────────────────────────────────────────────────────────
GUARANTEES
  Idempotency:  NO — duplicate INSERT raises DUPLICATE_IB_KEY
  Atomicity:    YES — all rows in one transaction · ROLLBACK on failure
  Ordering:     ENFORCED — grain write (Interface 5) must complete first · IB rows must exist

═══════════════════════════════════════════════════════════════════
```

---

### §TYPE-3-05 · Interface 9 — RE → reconciliation_results (Write)

```
═══════════════════════════════════════════════════════════════════
CONTRACT: RE (Result Writer C7) → dbo.reconciliation_results
TYPE: 3 — Data Write · INSERT-only · exactly 3 rows per session · atomic
SESSION KEY: session_id GUID — required · K1
NOTE: Format of detail field owned by C7 (R10-W-1) — not surfaced to CFO.
      failing_count is operator diagnostic only — not surfaced to CFO.
      UQ(session_id, check_name) enforces exactly one verdict per check per session.
═══════════════════════════════════════════════════════════════════

REQUEST
  Method:               SQL INSERT · 3 rows · single transaction
  Required (per row · 3 rows always):
    session_id          GUID          K1
    check_name          NVARCHAR(50)  "Capacity vs Usage" |
                                      "Usage vs Tenant Mapping" |
                                      "Computed vs Billed vs Posted"
    verdict             NVARCHAR(4)   PASS | FAIL
    fail_subtype        NVARCHAR(6)   NULL (PASS) | NULL (Check 1+2 FAIL) |
                                      FAIL-1 | FAIL-2 (Check 3 FAIL only)
    failing_count       INT           NULL on PASS · gt 0 on FAIL · operator only
    detail              NVARCHAR(MAX) operator prose · format owned by C7 · not null on FAIL

───────────────────────────────────────────────────────────────────
RESPONSE — SUCCESS
  result                SUCCESS
  session_id            GUID
  rows_written          3

───────────────────────────────────────────────────────────────────
RESPONSE — FAILURE
  DUPLICATE_VERDICT
    detected by:  SQL engine (UQ(session_id, check_name))
    handled by:   RE Result Writer C7 (ROLLBACK)
    retryable:    NO — verdicts already written for this session · structural defect in RE
    structure:    { error_code, error_message, session_id, check_name }
    recovery:     Escalate — Result Writer C7 fired twice for same session

  CHECK_INCOMPLETE
    detected by:  RE Result Aggregator (before write)
    handled by:   RE Result Aggregator
    retryable:    CONDITIONAL — wait for remaining checks up to timeout · then FAIL
    structure:    { error_code, error_message, session_id, pending_checks[] }
    recovery:     RE Aggregator holds write until all 3 checks return · then writes atomically

  AE_NOT_COMPLETE
    detected by:  RE AE Completion Listener (before Check 3 starts)
    handled by:   RE AE Completion Listener
    retryable:    CONDITIONAL — wait for AE completion signal (Interface 8) up to RE timeout
    structure:    { error_code, error_message, session_id }
    recovery:     RE Check 3 blocked · if AE times out RE marks Check 3 FAIL · writes all 3 rows

  INVALID_FAIL_SUBTYPE
    detected by:  RE Result Writer C7 (before INSERT) · SQL engine CHK constraint (at INSERT)
    handled by:   RE Result Writer C7
    retryable:    NO — fail_subtype non-null on Check 1 or Check 2 is a schema violation
    structure:    { error_code, error_message, session_id, check_name, fail_subtype }
    recovery:     RE recalculates fail_subtype · null for non-Check-3 rows

───────────────────────────────────────────────────────────────────
GUARANTEES
  Idempotency:  NO — duplicate write raises DUPLICATE_VERDICT
  Atomicity:    YES — all 3 rows in one transaction · ROLLBACK on any failure · format C7 (R10-W-1)
  Ordering:     ENFORCED — Check 3 gated on AE completion (Interface 8) ·
                            Result Aggregator waits for all 3 checks before write

═══════════════════════════════════════════════════════════════════
```

---

### §TYPE-3-06 · Interface 12 — SM → final.allocation_result (Write C9)

```
═══════════════════════════════════════════════════════════════════
CONTRACT: SM (Approved Result Writer C9) → final.allocation_result
TYPE: 3 — Data Write · INSERT-only · verbatim grain copy at APPROVED · sole writer
SESSION KEY: session_id GUID — required · K1
NOTE: INSTEAD OF UPDATE + DELETE trigger: THROW 51000 (TR_final_allocation_result_prevent_mutation)
      Atomic with APPROVED state write (Interface 11 ACCEPTED → this write → write_result to State Store · K5)
      13 CHKs W-9 copy fidelity · 3 filtered UNIQUEs R7-W-1 mirroring grain indexes.
      C9 is the sole writer — no other component may INSERT into this table.
═══════════════════════════════════════════════════════════════════

REQUEST
  Method:               SQL INSERT · batched · single transaction · atomic with APPROVED state write
  Source:               dbo.allocation_grain WHERE session_id = X · verbatim copy
  Required (per row — verbatim grain columns):
    session_id          GUID          K1
    region              NVARCHAR(100)
    gpu_pool_id         NVARCHAR(100)
    date                DATE
    billing_period      NVARCHAR(7)   K2
    allocation_target   NVARCHAR(255)
    unallocated_type    NVARCHAR(20)  K4
    failed_tenant_id    NVARCHAR(255) NULL TypeA+CI · original tenant_id IB · K3
    gpu_hours           DECIMAL(18,6)
    cost_per_gpu_hour   DECIMAL(18,6)
    contracted_rate     DECIMAL(18,6) NULL TypeB
    revenue             DECIMAL(18,2)
    cogs                DECIMAL(18,2)
    gross_margin        DECIMAL(18,2)
  Generated at write (not from grain):
    row_id              GUID          NEWSEQUENTIALID · per-row export traceability
    approved_at         DATETIME2     DEFAULT SYSUTCDATETIME · DB write time · W-11

───────────────────────────────────────────────────────────────────
RESPONSE — SUCCESS
  result                SUCCESS
  session_id            GUID
  rows_written          INT
  write_result          SUCCESS       persisted to State Store · K5 · Export Gate reads this

───────────────────────────────────────────────────────────────────
RESPONSE — FAILURE
  GRAIN_NOT_FOUND
    detected by:  C9 (query before INSERT)
    handled by:   C9
    retryable:    NO — grain must exist before APPROVED is triggered · structural defect
    structure:    { error_code, error_message, session_id }
    recovery:     write_result = FAIL written to State Store · Export Gate returns BLOCKED

  CONSTRAINT_VIOLATION_W9
    detected by:  SQL engine (W-9 CHK constraint · 13 copy-fidelity checks)
    handled by:   C9 (ROLLBACK)
    retryable:    NO — W-9 violation means grain and final schema have diverged · schema defect
    structure:    { error_code, error_message, session_id, violated_constraint }
    recovery:     write_result = FAIL written to State Store · escalate schema defect

  UNIQUE_VIOLATION_R7
    detected by:  SQL engine (filtered UNIQUE index · R7-W-1 · 3 indexes)
    handled by:   C9 (ROLLBACK)
    retryable:    NO — natural key collision in final table · grain has duplicate after constraint bypass
    structure:    { error_code, error_message, session_id, index_name }
    recovery:     write_result = FAIL · escalate · grain integrity must be investigated

  TRIGGER_BLOCKED
    detected by:  SQL engine (INSTEAD OF UPDATE / DELETE · THROW 51000)
    handled by:   C9
    retryable:    NO — C9 must only INSERT · UPDATE/DELETE path is structural defect
    structure:    { error_code: 51000, error_message, session_id }
    recovery:     Escalate — C9 has a forbidden mutation statement

  WRITE_FAIL (generic)
    detected by:  C9 (any unclassified failure)
    handled by:   C9
    retryable:    CONDITIONAL — one retry · then FAIL
    structure:    { error_code, error_message, session_id, root_cause }
    recovery:     write_result = FAIL written to State Store · Export Gate returns BLOCKED ·
                  operator must re-trigger APPROVED flow after root cause resolved

───────────────────────────────────────────────────────────────────
GUARANTEES
  Idempotency:  NO — duplicate INSERT raises UNIQUE_VIOLATION_R7
  Atomicity:    YES — atomic with APPROVED state write and write_result State Store update ·
                      ROLLBACK rolls back all three ·
                      if C9 write fails: state reverts to pre-APPROVED · write_result = FAIL
  Ordering:     ENFORCED — C9 is sole writer · triggered only by CFO_APPROVAL signal ·
                            grain must be fully written (Interface 5) before C9 reads it

═══════════════════════════════════════════════════════════════════
```

---

### §TYPE-3-07 · Interface 14 — Export → final.allocation_result (Read)

```
═══════════════════════════════════════════════════════════════════
CONTRACT: Export (Export Source Reader) → final.allocation_result
TYPE: 3 — Data Read · SELECT-only · post-gate
SESSION KEY: session_id GUID — required · K1
NOTE: Gate query (Interface 13) MUST return OPEN before this read proceeds.
      K7: exactly 13 grain columns exported · infrastructure columns excluded (id · row_id · approved_at).
      Table is immutable (THROW 51000) — read result is deterministic across multiple calls.
═══════════════════════════════════════════════════════════════════

REQUEST
  Method:               SQL SELECT
  Required:
    session_id          GUID          K1 · WHERE clause
  Column set (K7 — 13 grain columns only):
    region · gpu_pool_id · date · billing_period · allocation_target
    unallocated_type · failed_tenant_id · gpu_hours · cost_per_gpu_hour
    contracted_rate · revenue · cogs · gross_margin
  Excluded (infrastructure):
    id · row_id · approved_at
  Appended downstream (by Session Metadata Appender — not from this table):
    session_id          GUID          second-to-last column in all export formats
    source_files        NVARCHAR(MAX) last column · from raw.ingestion_log by session_id

───────────────────────────────────────────────────────────────────
RESPONSE — SUCCESS
  result                SUCCESS
  session_id            GUID
  rows_read             INT           gt 0
  columns               13            K7 grain columns only

───────────────────────────────────────────────────────────────────
RESPONSE — FAILURE
  GATE_NOT_CHECKED
    detected by:  Export Source Reader (internal guard)
    handled by:   Export Source Reader
    retryable:    NO — caller must check gate (Interface 13) before reading · structural defect
    structure:    { error_code, error_message, session_id }
    recovery:     Export Source Reader enforces gate check as prerequisite · escalate defect

  SESSION_NOT_FOUND
    detected by:  Export Source Reader (zero rows returned)
    handled by:   Export Source Reader
    retryable:    NO — session_id not in final.allocation_result · write_result may be FAIL
    structure:    { error_code, error_message, session_id }
    recovery:     Export Source Reader returns FAIL · Output Verifier Check 2 also catches this

  ZERO_ROWS
    detected by:  Output Verifier (Check 2 — row count matches source)
    handled by:   Output Verifier
    retryable:    NO — final table exists but has zero rows · C9 write defect
    structure:    { error_code, error_message, session_id, rows_read: 0 }
    recovery:     Export stops · File Delivery Handler returns FAIL · operator investigates C9

  COLUMN_SET_VIOLATION
    detected by:  Output Verifier (Check 3 + Check 4)
    handled by:   Output Verifier
    retryable:    NO — K7 column set or unallocated_type column missing from result
    structure:    { error_code, error_message, session_id, missing_columns[] }
    recovery:     Export stops · escalate · SELECT statement in Export Source Reader has defect

───────────────────────────────────────────────────────────────────
GUARANTEES
  Idempotency:  YES — read-only · table is immutable (THROW 51000) · same rows on every call
  Atomicity:    N/A — read-only
  Ordering:     ENFORCED — gate query (Interface 13) must return OPEN before this read

═══════════════════════════════════════════════════════════════════
```

---

## TYPE 4 — Gate Query  ·  CATEGORY 4: Gate Enforcement

Pattern: query-and-verdict
Solution layer: a consumer asks a gate whether it may proceed before accessing protected data.
Required fields: session_id
Response: gate_result (OPEN | BLOCKED) · block_reason (if BLOCKED)
Note: BLOCKED is not an error — it is the expected response when conditions are not met.
Governing ADR: ADR-03 — Export Gate requires BOTH conditions (state = APPROVED AND write_result = SUCCESS)

---

### §TYPE-4-01 · Interface 13 — Export → SM Export Gate

```
═══════════════════════════════════════════════════════════════════
CONTRACT: Export (APPROVED State Gate) → State Machine (Export Gate Enforcer)
TYPE: 4 — Gate Query · read-only · prerequisite for Interface 14
SESSION KEY: session_id GUID — required · K1
NOTE: K5 — Export Gate reads write_result FROM State Store (not from memory · not from C9 directly).
      Both conditions required: state = APPROVED AND write_result = SUCCESS.
      Neither condition alone is sufficient to return OPEN.
      BLOCKED is a valid, expected response — not an error.
═══════════════════════════════════════════════════════════════════

REQUEST
  Method:               internal call · HTTP GET
  Required:
    session_id          GUID          K1

───────────────────────────────────────────────────────────────────
RESPONSE — OPEN (both conditions met)
  gate_result           OPEN
  session_id            GUID
  verified_state        APPROVED
  verified_write_result SUCCESS

───────────────────────────────────────────────────────────────────
RESPONSE — BLOCKED (one or both conditions not met)
  gate_result           BLOCKED
  session_id            GUID
  block_reason          STATE_NOT_APPROVED      application_state ≠ APPROVED
                      | WRITE_RESULT_FAIL       write_result = FAIL (C9 write failed)
                      | WRITE_RESULT_NULL       write_result = NULL (APPROVED not yet written)
                      | SESSION_NOT_FOUND       session_id unknown to State Store
  Note: Export module stops on BLOCKED · File Delivery Handler returns BLOCKED to UI

───────────────────────────────────────────────────────────────────
RESPONSE — FAILURE (gate itself unavailable)
  GATE_UNAVAILABLE
    detected by:  Export APPROVED State Gate (no response from SM within timeout)
    handled by:   Export APPROVED State Gate
    retryable:    CONDITIONAL — retry once · then treat as BLOCKED
    structure:    { error_code, error_message, session_id }
    recovery:     Export treats GATE_UNAVAILABLE as BLOCKED · does not proceed to Interface 14

───────────────────────────────────────────────────────────────────
GUARANTEES
  Idempotency:  YES — read-only · multiple calls return same result until state changes
  Atomicity:    N/A — read-only gate query
  Ordering:     ENFORCED — Export Gate reads write_result FROM State Store · K5 ·
                            prevents export if write_result was written as FAIL or not yet written

═══════════════════════════════════════════════════════════════════
```

---

## Architectural Constraint Registry

```
K1 — session_id GUID
  Enforced by:  Ingestion Orchestrator generates once on Interface 1 response ·
                SQL WHERE clause enforced on every read and write · carried through all 12 tables
  Protects:     Session isolation · prevents cross-session data contamination ·
                all grain, cache, and result rows scoped to one session
  Governs:      Interfaces 1–14 (all)

K2 — billing_period NVARCHAR(7) · YYYY-MM
  Enforced by:  AE Billing Period Deriver: LEFT(date, 7) ·
                CHECK constraint on dbo.allocation_grain ·
                join key: IAM Resolver LEFT JOIN · Check 2 · Check 3
  Protects:     IAM join accuracy · Check 2 (Usage vs Tenant Mapping) correctness ·
                Check 3 (Computed vs Billed vs Posted) correctness
  Governs:      Interfaces 5, 9

K3 — failed_tenant_id NVARCHAR(255)
  Enforced by:  AE IB Builder: SET from original tenant_id for identity_broken rows ·
                NULL on Type A and capacity_idle rows · composite PK in IBT (Interface 7)
  Protects:     Zone 2R Risk flag accuracy · full traceability of identity_broken tenants through export ·
                prevents silent loss of failed tenant attribution
  Governs:      Interfaces 5, 7

K4 — unallocated_type NVARCHAR(20)
  Enforced by:  AE Record Builders (capacity_idle | identity_broken · never blended) ·
                Output Verifier Check 4 (enforces column presence in all export formats)
  Protects:     Type separation integrity · prevents capacity_idle cost from blending with IB cost ·
                CFO visibility of distinct unallocated cost drivers
  Governs:      Interface 5

K5 — write_result · State Store persistence (not memory)
  Enforced by:  C9 writes write_result to State Store after INSERT (Interface 12) ·
                Export Gate Enforcer reads write_result FROM State Store — not from C9 directly ·
                survives process restarts because it is persisted
  Protects:     CFO export from corrupt or partial final.allocation_result ·
                guards against case where APPROVED state is written but C9 INSERT fails
  Governs:      Interfaces 12, 13

───────────────────────────────────────────────────────────────────
IMMUTABILITY CONSTRAINTS (THROW REGISTRY)

THROW 51000 — TR_final_allocation_result_prevent_mutation
  Enforced by:  INSTEAD OF UPDATE + DELETE trigger on final.allocation_result
  Protects:     CFO export integrity · approved result cannot be modified post-approval ·
                deterministic read result on Interface 14 across all export calls
  Governs:      Interfaces 12, 14

THROW 51001 — TR_kpi_cache_prevent_mutation
  Enforced by:  INSTEAD OF UPDATE + DELETE trigger on dbo.kpi_cache
  Protects:     Zone 1 KPI immutability after ANALYZED state ·
                UI cannot show a different KPI summary than what was computed at analysis time
  Governs:      Interface 6

THROW 51002 — TR_identity_broken_tenants_prevent_mutation
  Enforced by:  INSTEAD OF UPDATE + DELETE trigger on dbo.identity_broken_tenants
  Protects:     IBT SET integrity · Zone 2R Risk flag source data ·
                failed_tenant_id attribution cannot be silently corrected post-write
  Governs:      Interface 7

THROW 51003 — TR_allocation_grain_prevent_update
  Enforced by:  INSTEAD OF UPDATE trigger on dbo.allocation_grain ·
                DELETE permitted for Ingestion Commit session replacement only (ADR-05)
  Protects:     All downstream consumers of grain simultaneously:
                RE Check 3 · UI Zone 2L/2R · kpi_cache · IBT SET · final.allocation_result ·
                an UPDATE would silently invalidate all without any consumer knowing
  Governs:      Interface 5
  Next available THROW: 51004

───────────────────────────────────────────────────────────────────
SOLE-WRITER RULES

C9 — SM Approved Result Writer · final.allocation_result
  Enforced by:  Role-based DB access control (no other module has INSERT rights) ·
                INSTEAD OF UPDATE + DELETE (THROW 51000) blocks all mutation ·
                ADR-02 declares C9 as the exclusive writer at solution layer
  Protects:     CFO export integrity · immutability of the approved result ·
                prevents any engine or module from inserting unapproved or partial data
                into the export surface · read result in Interface 14 is deterministic
  Governs:      Interface 12 (sole write path) · Interface 14 (read of C9-produced data)

C7 — RE Result Writer · dbo.reconciliation_results  (R10-W-1)
  Enforced by:  Role-based DB access control (no other module has INSERT rights) ·
                UQ(session_id, check_name) constraint prevents duplicate verdict at DB layer ·
                format owned by C7 (R10-W-1): fail_subtype null-enforcement on Check 1+2 rows
  Note:         reconciliation_results has no THROW in the 51000–51003 registry.
                THROW 51002 belongs exclusively to dbo.identity_broken_tenants (AE-owned).
                C7 protection relies on role-based access control + UQ constraint, not a trigger.
  Protects:     Zone 3 reconciliation verdict integrity · UI display accuracy ·
                prevents a second writer from inserting a conflicting check result ·
                UQ(session_id, check_name) constraint catches any violation at DB layer
  Governs:      Interface 9 (sole write path) · reconciliation_results readable by UI Zone 3
```

---

## Architecture Decision Register

```
ADR-01  State Machine as sole lifecycle controller
  Decision:    All state transitions route through SM Transition Request Receiver.
               No module may advance the session lifecycle directly.
  Constraint:  source_component validated by SM Transition Validator on every signal ·
               UNAUTHORIZED_SOURCE returned if source_component is not the expected caller
  Rationale:   A single control point prevents split-brain lifecycle state ·
               prevents engines from self-promoting to ANALYZED or APPROVED
  Trade-off:   SM availability is critical path for all four phases ·
               SM failure blocks both analysis dispatch and approval
  References:  Interfaces 2, 3, 4, 10, 11 · CAT 1 + CAT 2 boundaries

ADR-02  C9 sole-writer rule for final.allocation_result
  Decision:    Only SM Approved Result Writer C9 may INSERT into final.allocation_result.
               No other module has write access.
  Constraint:  INSTEAD OF UPDATE + DELETE (THROW 51000) · role-based access control at DB layer ·
               Interface 12 is the only write path
  Rationale:   Immutability of the approved result is the core CFO export guarantee ·
               any other writer could produce an unapproved or partial result
  Trade-off:   If C9 fails, export is permanently blocked until operator recovery ·
               write_result = FAIL written to State Store · Export Gate returns BLOCKED
  References:  Interface 12 (C9 write) · Interface 14 (read) · K5 · THROW 51000 ·
               W-9 (13 copy-fidelity CHK constraints — verbatim grain copy enforcement) ·
               R7-W-1 (3 filtered UNIQUE indexes — mirror grain natural keys in final table)

ADR-03  Export Gate requires BOTH conditions (K5)
  Decision:    Export Gate returns OPEN only when state = APPROVED
               AND write_result = SUCCESS. Neither condition alone is sufficient.
  Constraint:  write_result read from State Store (not from memory · not from C9 directly) ·
               survives process restarts
  Rationale:   C9 write can fail after APPROVED state is written ·
               exporting from an empty or partial final table = corrupt CFO deliverable
  Trade-off:   If C9 fails, CFO cannot export until operator re-triggers APPROVED flow ·
               no self-healing path — operator intervention required
  References:  Interface 13 (Export Gate) · Interface 12 (C9 write) · K5

ADR-04  AE completion fan-out is not atomic
  Decision:    AE Completion Emitter delivers to SM Collector AND RE_ACL independently.
               Partial delivery is architecturally accepted.
  Constraint:  Each recipient deduplicates by session_id + signal type independently ·
               PARTIAL_DELIVERY error code surfaces unACKed recipients
  Rationale:   Atomic fan-out requires a coordinator — adding one creates a new single
               point of failure. Independent delivery with deduplication is the correct
               trade-off at the scale of this system.
  Trade-off:   Undetected partial delivery leaves RE_ACL blocked · RE times out · RE emits FAIL ·
               SM marks analysis FAIL · session remains UPLOADED
  References:  Interface 8 · RE timeout: max(5min · AE+5min)

ADR-05  Grain is INSERT-only · UPDATE blocked · DELETE for session replacement only
  Decision:    INSTEAD OF UPDATE (THROW 51003) prevents all UPDATE operations on allocation_grain.
               DELETE permitted exclusively for Ingestion Commit session replacement.
  Constraint:  TR_allocation_grain_prevent_update · role-based access control ·
               no correction path for grain errors post-write — re-ingest required
  Rationale:   Grain rows are the authoritative source for RE Check 3, UI, kpi_cache,
               IBT, and final.allocation_result. Any UPDATE silently invalidates all
               downstream consumers simultaneously with no notification mechanism.
  Trade-off:   No in-place correction path for grain errors · operator must re-ingest full session ·
               this is the correct trade-off to protect downstream immutability
  References:  THROW 51003 · K1 · Closure Rule · Interfaces 5 6 7
               (⑤ grain INSERT-only · ⑥ kpi_cache immutability · ⑦ IBT immutability —
               all three AE-owned tables share the same INSERT-only · immutable design principle)
```

---

> "Let all things be done decently and in order." — 1 Corinthians 14:40
