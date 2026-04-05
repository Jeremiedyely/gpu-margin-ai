---
name: problem-tracking
description: >
  Diagnostic and debugging framework for the GPU Gross Margin Visibility Application
  and any distributed system with layered architecture. Use this document as the
  operational reference when encountering failures, wiring mismatches, silent
  degradation, or architectural drift during build, test, or runtime. Triggers when
  investigating test failures, runtime errors, state machine stalls, pipeline crashes,
  or any gap between expected and observed system behavior.
  Does NOT replace the specification — use the relevant module design file for that.
  Does NOT govern architectural decisions — use solution-software-architect-api.md.
role: diagnostic-reference
reads-from: >
  gpu-margin-engineer.prompt.md · solution-software-architect-api.md ·
  cowork.prompt.md · prompt-writer.md · software-system-design.md
feeds-into: >
  debugging sessions · post-incident analysis · build regression triage ·
  implementation review
created: 2026-04-05
---

# Problem Tracking — Diagnostic & Debugging Framework

> See: gpu-margin-engineer.prompt.md — build protocol · anti-drift rules · failure modes
> See: solution-software-architect-api.md — ADRs · interface categories · constraint registry
> See: cowork.prompt.md — Eight Laws · diagnostic framework · severity labels
> See: prompt-writer.md — cognitive flow · structural construction

---

## Purpose

This document is the operational brain for debugging distributed systems. It encodes
the diagnostic thinking, pattern recognition, and decomposition discipline extracted
from building the GPU Gross Margin Visibility Application — but its principles apply
to any layered system with state machines, pipelines, and cross-module contracts.

The framework is designed around a core truth: **the symptom is never the problem**.
The symptom is the surface. The problem is structural — a missing layer, a broken
contract, a silent rollback, a wiring mismatch. This document teaches you to find the
structure beneath the surface.

---

## Part I — The Diagnostic Protocol

Every debugging session follows this sequence. Do not skip steps. Do not jump to fixes.

```
STEP 1 — OBSERVE
  What is the exact symptom?
  What is the exact error message (or absence of one)?
  Where in the pipeline did the symptom surface?
  Is the failure loud (error thrown) or silent (wrong output, no output)?

STEP 2 — LOCATE
  Which layer owns the symptom?
    → Frontend (React, TypeScript, component state, rendering)
    → API (FastAPI, routing, request/response, serialization)
    → State Machine (transitions, guards, receivers, executors)
    → Pipeline (Celery tasks, engine orchestration, wiring)
    → Database (schema, constraints, FK violations, migrations)
    → Infrastructure (Docker, networking, env vars, service health)
  A symptom in Layer N is often caused by a defect in Layer N-1.

STEP 3 — DECOMPOSE
  Break the failure into its smallest testable unit.
  Can the failing component be called in isolation?
  Does it pass alone but fail in the full suite?
  What changed between "last known good" and now?

STEP 4 — DIAGNOSE
  Apply the root cause framework (see Part II).
  Name the structural mechanism that produced the failure.
  Do not stop at "it doesn't work." Name WHY it doesn't work.

STEP 5 — RECOMMEND
  Propose the fix with:
    → What changes
    → What contract or invariant it restores
    → What downstream effect the fix has
  Present to the user. Wait for approval.

STEP 6 — FIX
  Apply the approved fix only. No scope expansion.
  No "while I'm here" improvements.

STEP 7 — VERIFY
  Run the regression. Confirm the fix. Confirm no new failures.
  If new failures appear → return to STEP 1 with the new symptom.
```

---

## Part II — Root Cause Framework

Every defect has a structural cause. These are the ten root cause categories,
ordered by frequency in layered distributed systems.

### RC-1 — Transaction Boundary Violation

The write happened but was never committed, or the commit scope was wrong.

**Signature:** Data appears to be written (no error thrown) but is not visible to
subsequent reads. State doesn't advance. Silent success with no effect.

**Diagnostic questions:**
- Does the connection have an explicit `begin()` / `commit()` boundary?
- Is the write inside a savepoint (`begin_nested`) without an outer transaction?
- Does the ORM auto-commit, or does it require explicit commit?
- Is the connection closed before commit (dependency injection teardown)?

**Example from this project:** The `/api/analyze` endpoint used a FastAPI
dependency-injected connection with no auto-commit. The `dispatch_analysis` function
wrote `analysis_status = ANALYZING` inside a savepoint, but the outer implicit
transaction never committed. When the connection closed, the write was silently
rolled back. The Celery task fired, but the UI never saw ANALYZING.

**Fix pattern:** Replace dependency-injected connections with explicit
`engine.connect()` + `conn.begin()` for any endpoint that writes state.


### RC-2 — Wiring Mismatch (Attribute / Argument Name)

The caller uses a different name than the callee defines.

**Signature:** `AttributeError: 'X' object has no attribute 'payload'` or
`TypeError: unexpected keyword argument`. The individual components are correct
in isolation — the error is in the glue code that connects them.

**Diagnostic questions:**
- What attribute name does the result class actually define?
- What argument names does the function signature actually accept?
- Was the wiring code written from memory or by reading the actual class definitions?
- Are there intermediate steps in the pipeline that were skipped?

**Example from this project:** `tasks.py` referenced `.payload` on every result
class, but the actual attributes were `.records`, `.capacity_idle`, etc.
`calculate_cost_revenue` was called with one combined list, but the function
takes three separate keyword arguments. `enforce_closure_rule` was called with
`type_a_records=` but the parameter is `type_a=`.

**Fix pattern:** Read every result class and function signature before writing
orchestration code. Never wire from memory. The specification is in the code, not
in your head.


### RC-3 — Missing Pipeline Step

A required intermediate transformation was omitted from the orchestration.

**Signature:** Type mismatch between producer and consumer. Function receives
records that are missing a required field. The pipeline jumps from Step N to
Step N+2.

**Diagnostic questions:**
- What type does the consumer expect?
- What type does the producer emit?
- Is there an intermediate component in the design that transforms between them?
- Does the component numbering reveal a gap? (e.g., jumping from Component 1 to
  Component 3 without Component 2)

**Example from this project:** `resolve_iam` expects `TelemetryEnrichedRecord`
(with `billing_period` field), but `tasks.py` passed `TelemetryAggregatedRecord`
directly from the telemetry aggregator. The missing step was
`derive_billing_periods` (Component 2/10 in the Allocation Engine), which enriches
records with `billing_period = YYYY-MM`.

**Fix pattern:** Map the full pipeline by component number. Verify every step is
present. Verify the output type of Step N matches the input type of Step N+1.


### RC-4 — State Assumption Violation

Code assumes a state that doesn't exist yet, or assumes state survives a
context boundary that destroys it.

**Signature:** `null` or `undefined` where a value is expected. 422 validation
errors. Component works after a fresh action but fails after a page refresh,
container restart, or component remount.

**Diagnostic questions:**
- Is this state stored in the server (database) or the client (React state)?
- Does a page refresh or component remount destroy this state?
- Does a container restart or redeployment destroy this state?
- Is there a server-side source of truth that can replace the client state?

**Example from this project:** `View1Renderer` stored `sessionId` in React
`useState`. After a Docker rebuild, the old UPLOADED session persisted in the
database, but the frontend had no memory of the session_id. Clicking Analyze
sent `session_id: null` → FastAPI returned 422 Unprocessable Entity.

**Fix pattern:** For any state that must survive restarts, store it server-side
and poll or pass it as a prop. Client state is ephemeral. Server state is durable.
Prefer durable.


### RC-5 — Implicit State Machine Gap

The state machine has a valid state that no code path handles, or a code path
assumes a state that the machine never produces.

**Signature:** Unresolvable state errors. White screens. Buttons that never
activate. Transitions that silently fail.

**Diagnostic questions:**
- What are all possible values of the state variable (including null)?
- Does every code path (switch/if-else) handle every possible value?
- Does the initial state (no row exists) have a code path?
- Does the transition receiver handle "no prior state" for the first transition?

**Example from this project:** The `receive_transition_signal` function required
a `state_store` row to exist before processing any transition. But EMPTY→UPLOADED
is the first transition — no row exists yet. The receiver returned REJECTED, the
upload endpoint silently swallowed the rejection, and the state never advanced.

**Fix pattern:** Enumerate every possible state value including null/absent.
Trace every code path against that enumeration. The first transition in any
state machine always requires special handling for "no prior state."


### RC-6 — Cross-Module Resource Contamination

Multiple independent resources (connections, engines, pools) accumulate across
modules during a full test run, causing intermittent failures.

**Signature:** Tests pass individually or in small groups but fail in the full
suite. Failures are non-deterministic. Database timeouts or integrity errors
appear only under full load.

**Diagnostic questions:**
- How many database engines/connections exist simultaneously?
- Does each test module create its own engine? Do they accumulate?
- Are connections pooled (QueuePool) or fresh per use (NullPool)?
- Do pooled connections survive across test modules?

**Example from this project:** Seven separate `conftest.py` files each created
an independent SQLAlchemy engine with `scope="session"`. Three used QueuePool,
holding zombie connections. When all modules ran together, 6+ engines competed
for MSSQL resources, causing 34 intermittent failures in state_machine tests.

**Fix pattern:** One shared engine at root conftest level. Use NullPool for test
isolation. Every sub-conftest inherits the shared engine.


### RC-7 — Silent Error Swallowing

An error occurs but the calling code doesn't check the result, doesn't surface
the error, or catches it and returns success anyway.

**Signature:** Operation "succeeds" (200 response, no error) but produces no
observable effect. The user sees "nothing happened."

**Diagnostic questions:**
- Does the calling code check the result status of every sub-operation?
- Are there `if result == "FORWARD"` checks that skip the else case?
- Does the catch block set an error state visible to the user?
- Does the error display handle nested objects (not just strings)?

**Example from this project:** The upload endpoint's state transition block
only checked `if receiver.result == "FORWARD"` with no else clause. When the
receiver returned REJECTED, the code silently fell through and returned
`200 SUCCESS`. The frontend also displayed `[object Object]` because the
error handler didn't unwrap FastAPI's nested `detail` structure.

**Fix pattern:** Every sub-operation result must be explicitly checked. Every
non-success path must either raise an error or return a structured failure.
Error display code must handle strings, objects, and arrays.


### RC-8 — Infrastructure Configuration Drift

The runtime environment doesn't match what the code expects.

**Signature:** Services fail to start. Migration tools exit with error codes.
Connection strings resolve to wrong hosts. Environment variables are missing
or point to wrong services.

**Diagnostic questions:**
- Does the DATABASE_URL inside the container resolve to the correct hostname?
- Did Flyway migrations run successfully? (check `docker logs gpu_margin_flyway`)
- Are all required tables, schemas, and constraints present?
- Do environment variables in `.env` match what docker-compose.yml references?

**Fix pattern:** Always check infrastructure health before debugging application
code. `docker logs [service]` is the first command, not the last.


### RC-9 — Serialization / Type Boundary Crossing

Data changes shape when crossing a serialization boundary (JSON, FormData,
Pydantic, database row).

**Signature:** 422 Unprocessable Entity. Fields missing after deserialization.
UUID becomes string becomes null. Decimal becomes float.

**Diagnostic questions:**
- What type does the sender serialize?
- What type does the receiver expect to deserialize?
- Does the serialization format preserve the type? (JSON has no UUID, no Decimal)
- Does the Pydantic model accept the serialized form?

**Fix pattern:** Trace the data type across every boundary. If a UUID is stored
as a string in JSON, the receiver must parse it back. If Decimal is needed,
don't rely on float serialization.


### RC-10 — Coupling Contract Violation

A shared contract (billing_period derivation, column order, snapshot isolation)
is implemented differently in different components.

**Signature:** Silent wrong results. Check 2 disagrees with IAM Resolver.
Export formats diverge. Reconciliation produces false verdicts.

**Diagnostic questions:**
- Is the shared logic imported from a single source, or copied?
- Did a change to one component update all coupled components?
- Are there tests that verify cross-component consistency?

**Fix pattern:** Shared constants imported, never copied. Coupling contracts
documented. Changes to coupled components require simultaneous review of all
components in the contract.

---

## Part III — The Debugging Checklist

Use this checklist sequentially. Each section gates the next.

### A — Infrastructure Health

```
[ ] Docker containers all running?  (docker ps)
[ ] Flyway migrations succeeded?    (docker logs gpu_margin_flyway)
[ ] Database accessible?             (docker logs gpu_margin_web — check for connection errors)
[ ] Redis healthy?                   (docker logs gpu_margin_redis)
[ ] Celery worker connected?         (docker logs gpu_margin_celery_worker)
[ ] Celery beat scheduling?          (docker logs gpu_margin_celery_beat)
[ ] Environment variables correct?   (.env file matches docker-compose.yml references)
[ ] Vite proxy configured?           (vite.config.ts → /api → http://localhost:8000)
```

### B — API Layer Health

```
[ ] /health endpoint returns 200?
[ ] /api/state returns valid JSON?
[ ] POST endpoints receive correct Content-Type?
    (multipart/form-data for upload, application/json for analyze/approve)
[ ] Pydantic models match frontend payload shape?
[ ] Error responses are structured (not [object Object])?
```

### C — State Machine Health

```
[ ] state_store has a row for the active session?
[ ] application_state matches expected value?
[ ] analysis_status matches expected value?
[ ] Transition receiver handles "no row" case (EMPTY→UPLOADED)?
[ ] All transitions commit within explicit transaction boundaries?
[ ] Double-dispatch guards are active?
```

### D — Pipeline Health

```
[ ] Celery task received by worker?  (docker logs gpu_margin_celery_worker)
[ ] Task completed or raised error?
[ ] Every pipeline step present?     (check component numbering for gaps)
[ ] Result attributes match wiring?  (.records vs .payload vs .capacity_idle)
[ ] Function argument names match?   (type_a= vs type_a_records=)
[ ] Intermediate transformations present? (billing_period deriver, etc.)
```

### E — Frontend Health

```
[ ] Browser console shows errors?    (F12 → Console tab)
[ ] Network tab shows request/response? (F12 → Network tab)
[ ] State polling returns expected values? (/api/state every 3s)
[ ] Component props include server-sourced session_id?
[ ] Error display unwraps nested objects?
[ ] Button disabled state matches expected logic?
```

---

## Part IV — System Decomposition Thinking

### Layer Model

Every distributed system has layers. Debugging requires knowing which layer
you're in and which layer caused the problem.

```
LAYER 6 — USER INTERFACE
  What the user sees. Symptoms surface here.
  Rendering, component state, props, event handlers.

LAYER 5 — API GATEWAY
  Request routing, serialization, authentication.
  FastAPI endpoints, Pydantic validation, CORS, proxy.

LAYER 4 — STATE MACHINE
  Lifecycle control. Transitions, guards, executors.
  The brain of the system. If state doesn't advance, nothing downstream works.

LAYER 3 — PIPELINE ORCHESTRATION
  Task wiring. Celery tasks, engine sequencing.
  The glue code. Most wiring mismatches live here.

LAYER 2 — DOMAIN ENGINES
  Business logic. Allocation, reconciliation, computation.
  Individual components are usually correct — the errors are in how they connect.

LAYER 1 — DATA PERSISTENCE
  Database schema, constraints, triggers, migrations.
  FK violations, CHECK constraint failures, missing tables.

LAYER 0 — INFRASTRUCTURE
  Docker, networking, environment, service health.
  If this layer is broken, nothing above it can work.
```

**The Layer Rule:** A symptom at Layer N is often caused by a defect at Layer N-1
or Layer N-2. Always check one layer below the symptom before debugging at the
symptom layer.


### Pattern Recognition — Five Archetypes

**Archetype 1 — The Silent Swallow**
Operation succeeds (200 OK) but produces no effect.
Look for: unchecked result codes, missing else branches, transaction rollbacks.

**Archetype 2 — The Phantom State**
State that exists in one context but not another.
Look for: client-only state, ephemeral storage, container restarts erasing state.

**Archetype 3 — The First-Time Failure**
Works on second attempt but not first.
Look for: missing initialization, "no row" edge cases, first-transition handling.

**Archetype 4 — The Suite Poisoner**
Tests pass alone, fail together.
Look for: shared mutable state, accumulated connections, global singletons.

**Archetype 5 — The Name Game**
Individual components are correct, orchestration crashes.
Look for: `.payload` vs `.records`, `type_a_records=` vs `type_a=`, missing steps.

---

## Part V — Architecture Fundamentals for Debugging

### The Four Questions

Before debugging any system, answer these:

1. **What is the grain?** — What is the atomic unit of data that flows through the
   system? In this project: Region × GPU Pool × Day × Allocation Target. Every
   query, computation, and export must operate at this grain or explicitly declare
   the aggregation rule.

2. **What are the state transitions?** — What are the valid lifecycle states, and
   what are the legal transitions between them? In this project:
   EMPTY → UPLOADED → ANALYZED → APPROVED (terminal). Each transition has a
   receiver, validator, and executor. Each must be tested.

3. **What are the atomicity boundaries?** — Which writes must succeed or fail as
   a unit? In this project: Ingestion Commit (5 tables), Grain Writer (all rows),
   Approved Result Writer (state + write_result). Break atomicity and you get
   partial data reaching downstream consumers.

4. **What are the coupling contracts?** — Which components share a constant, a
   derivation rule, or a timing assumption? In this project: five contracts (K1-K5).
   Change one side without the other and you get silent wrong results.


### The Distributed System Invariants

These hold true in any distributed system, not just this one:

- **Writes without commits are reads.** If you don't commit, you didn't write.
- **Client state is suggestion, server state is truth.** Never trust client-only
  state for critical decisions.
- **The first operation is always special.** The first row, the first transition,
  the first request — all require explicit handling for "nothing exists yet."
- **Glue code has the most bugs.** Individual components are usually correct.
  The orchestration that connects them is where mismatches hide.
- **Loud failures are gifts. Silent failures are debts.** An error you can see
  is an error you can fix. An error you can't see propagates to the end user.
- **Infrastructure is Layer 0.** If containers, migrations, or networking are
  broken, debugging application code is wasted effort. Check Layer 0 first.

---

## Part VI — Severity Classification

Use these labels consistently in all diagnostic output.

```
🔴 CRITICAL — System cannot function. Data integrity at risk.
              Must be fixed before any other work proceeds.
              Examples: FK violation, missing table, transaction not committing,
              state machine stuck, pipeline crash.

🟡 WARNING  — System functions but with degraded behavior.
              Should be fixed before production deployment.
              Examples: error display shows [object Object], test flakiness,
              unused dependencies, missing error messages.

🟢 PASS     — Component or behavior is correct.
              No action needed.

🔵 RECOMMENDATION — Not a defect, but an improvement opportunity.
              Address when capacity allows.
              Examples: better logging, consolidating imports, adding retry logic.
```

---

## Part VII — The Problem Register

Track every defect found during the build in this format. This is the living
record of what broke, why it broke, and what fixed it.

```
DEFECT-[NNN]
  Symptom:     [What the user or test reported]
  Layer:       [0-6 from the Layer Model]
  Root Cause:  [RC-1 through RC-10]
  Archetype:   [1-5 from Pattern Recognition]
  Mechanism:   [One sentence: what structural flaw caused the symptom]
  Fix:         [What was changed]
  Files:       [Which files were modified]
  Verified:    [How the fix was confirmed — test name, manual verification]
  Severity:    [🔴 🟡 🟢 🔵]
```

### Registered Defects — GPU Gross Margin Build

```
DEFECT-001
  Symptom:     ImportError: cannot import name 'emit_ingestion_signal'
  Layer:       5 — API Gateway
  Root Cause:  RC-2 — Wiring Mismatch
  Archetype:   5 — The Name Game
  Mechanism:   upload_routes.py imported a function that doesn't exist
               (emit_ingestion_signal vs emit_state_transition). Import was unused.
  Fix:         Removed the dead import line.
  Files:       app/api/upload_routes.py
  Verified:    pytest passed
  Severity:    🔴 CRITICAL

DEFECT-002
  Symptom:     RuntimeError: Form data requires "python-multipart"
  Layer:       5 — API Gateway
  Root Cause:  RC-8 — Infrastructure Configuration Drift
  Archetype:   3 — The First-Time Failure
  Mechanism:   FastAPI UploadFile requires python-multipart package, not declared
               in requirements.txt.
  Fix:         Added python-multipart>=0.0.6 to requirements.txt.
  Files:       requirements.txt
  Verified:    pip install + endpoint accepts FormData
  Severity:    🔴 CRITICAL

DEFECT-003
  Symptom:     34 state_machine tests fail in full suite, pass individually
  Layer:       1 — Data Persistence
  Root Cause:  RC-6 — Cross-Module Resource Contamination
  Archetype:   4 — The Suite Poisoner
  Mechanism:   7 separate conftest.py files created independent SQLAlchemy engines.
               Cumulative QueuePool connections exhausted MSSQL resources.
  Fix:         Single shared NullPool engine in root conftest. Removed engine
               fixtures from all 7 sub-conftest files.
  Files:       tests/conftest.py, tests/*/conftest.py (7 files)
  Verified:    598 passed in 27.07s — full green
  Severity:    🔴 CRITICAL

DEFECT-004
  Symptom:     White screen — "Application state unresolvable"
  Layer:       6 — User Interface
  Root Cause:  RC-5 — Implicit State Machine Gap
  Archetype:   3 — The First-Time Failure
  Mechanism:   ScreenRouter's resolveView(null) returned ERROR. When no session
               exists, API returns application_state: null — a valid initial state
               with no code path.
  Fix:         Added state === null check to resolveView, mapping to VIEW_1.
  Files:       frontend/src/components/ScreenRouter.tsx
  Verified:    Fresh browser load shows upload screen
  Severity:    🔴 CRITICAL

DEFECT-005
  Symptom:     Upload All Files button does nothing. Analyze stays locked.
  Layer:       4 — State Machine
  Root Cause:  RC-5 — Implicit State Machine Gap
  Archetype:   3 — The First-Time Failure
  Mechanism:   receive_transition_signal required a state_store row to exist before
               processing. EMPTY→UPLOADED is the first transition — no row exists.
               Receiver returned REJECTED. Upload endpoint silently swallowed it
               (RC-7) and returned 200 SUCCESS. State never advanced.
  Fix:         (a) Receiver treats missing row as current_state = "EMPTY".
               (b) Upload endpoint checks receiver/validator/executor results,
               raises HTTPException on failure.
  Files:       app/state_machine/transition_request_receiver.py,
               app/api/upload_routes.py,
               tests/state_machine/test_transition_request_receiver.py
  Verified:    Upload succeeds, state advances to UPLOADED, Analyze becomes active
  Severity:    🔴 CRITICAL

DEFECT-006
  Symptom:     Analyze button clickable but nothing happens. State stays UPLOADED.
  Layer:       5 — API Gateway
  Root Cause:  RC-1 — Transaction Boundary Violation
  Archetype:   1 — The Silent Swallow
  Mechanism:   Analyze endpoint used dependency-injected connection with no
               auto-commit. dispatch_analysis wrote ANALYZING inside a savepoint,
               but the outer transaction never committed. Write rolled back on
               connection close.
  Fix:         Replaced with explicit engine.connect() + conn.begin(). Celery task
               fires after commit.
  Files:       app/api/upload_routes.py
  Verified:    Analyze sets analysis_status = ANALYZING, button shows "in progress"
  Severity:    🔴 CRITICAL

DEFECT-007
  Symptom:     [object Object] displayed in error area. 422 on /api/analyze.
  Layer:       6 — User Interface + 4 — State Machine
  Root Cause:  RC-4 — State Assumption Violation + RC-9 — Serialization Boundary
  Archetype:   2 — The Phantom State
  Mechanism:   sessionId stored in React useState (ephemeral). After Docker rebuild,
               old session persisted in DB but frontend lost sessionId. Sent null
               to Pydantic UUID field → 422. Error display didn't unwrap nested
               FastAPI detail object → showed [object Object].
  Fix:         (a) Pass sessionId from server state via ScreenRouter prop.
               (b) Error display unwraps string/object/array detail structures.
  Files:       frontend/src/components/ScreenRouter.tsx,
               frontend/src/components/View1Renderer.tsx
  Verified:    Analyze sends correct session_id. Errors display as readable text.
  Severity:    🔴 CRITICAL

DEFECT-008
  Symptom:     Celery worker raises AttributeError: 'AggregatorResult' has no 'payload'
  Layer:       3 — Pipeline Orchestration
  Root Cause:  RC-2 — Wiring Mismatch + RC-3 — Missing Pipeline Step
  Archetype:   5 — The Name Game
  Mechanism:   tasks.py used .payload on all result classes (actual: .records,
               .capacity_idle). Called calculate_cost_revenue with 1 arg (needs 3).
               Used wrong kwarg names for enforce_closure_rule. Skipped
               billing_period_deriver (Component 2/10).
  Fix:         Corrected all attribute references. Added derive_billing_periods step.
               Fixed function call signatures.
  Files:       app/tasks.py
  Verified:    Pending — Flyway migration failure blocking full test
  Severity:    🔴 CRITICAL

DEFECT-009
  Symptom:     Flyway exits with code 1. Database tables not created.
  Layer:       0 — Infrastructure
  Root Cause:  RC-6 — Missing Lifecycle Step (database creation)
  Archetype:   3 — The First-Time Failure
  Mechanism:   docker-compose down -v destroys sqlserver_data volume. On next
               up, SQL Server starts fresh with only system databases (master,
               tempdb, msdb, model). Flyway JDBC URL targets databaseName=
               gpu_margin, which doesn't exist. Connection fails immediately.
               V1 migration (ALTER DATABASE gpu_margin) compounds the problem
               — even if Flyway connected to master, V1 assumes the database
               already exists. No CREATE DATABASE step anywhere in the chain.
  Fix:         Added db_init service (one-shot init container) to docker-compose.
               Runs after db health check, before Flyway. Uses sqlcmd to execute
               db/init/create_database.sql which does IF NOT EXISTS CREATE DATABASE.
               Flyway now depends_on db_init: service_completed_successfully.
               Startup chain: db (healthy) → db_init (creates database) → flyway
               (runs migrations) → web + celery_worker (start).
  Files:       docker-compose.yml, db/init/create_database.sql, db/init/init_db.sh
  Verified:    Pending — user needs to run docker-compose down -v && up --build
  Severity:    🔴 CRITICAL (BLOCKING — all downstream services depend on tables)
```

---

> "A false balance is an abomination to the LORD, but a just weight is his delight."
> — Proverbs 11:1

Every defect tracked honestly. Every root cause named precisely.
Every fix verified before the system moves forward.
This is measurement integrity applied to engineering.
