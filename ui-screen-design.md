---
role: module-design
module: UI Screen
layer: UI
reads-from: requirements.md · software-system-design.md
session-context: UI Screen module design — 14 components — backward from CFO output
confirmed: 2026-03-27
---

# UI Screen Module Design — GPU Gross Margin Visibility Application

> See: business.md — WHY layer · CFO problem definition
> See: requirements.md — WHAT layer · grain · computation contract · state machine
> See: software-system-design.md — HOW layer · interaction protocol · anti-drift rules

---

## Scope

**Active scope:** UI Screen Module | Layer: UI
**Output expected:** Two-view, three-zone screen with state-gated footer controls
**Consumed by:** CFO (analyst)
**Failure behavior:** If the screen fails to enforce state gates, export can fire without approval. If zone data does not render correctly, the CFO sees corrupted or blended margin data and cannot make a defensible approval decision.

---

## Backward Dependency Chain

```
CFO sees rendered screen
        ↑
Screen Router — selects active view based on application_state
        ↑
View 1 Renderer                   Analysis View Container
        ↑                                   ↑
View 1 Footer Control Manager     Zone 1–3 Renderers
                                  View 2 Footer Control Manager
                                  Approve Confirmation Dialog
                                            ↑
                                  KPI Data Aggregator
                                  Region Data Aggregator
                                  Customer Data Aggregator
                                  Reconciliation Result Reader
                                            ↑
                                  allocation_grain table
                                  reconciliation_results table
```

---

## Component Blocks — 13 Components

---

### Component 1: Screen Router

```
Component:       Screen Router
Layer:           UI
Input:           application_state : enum{EMPTY, UPLOADED, ANALYZED, APPROVED}
                 — sourced from State Machine
Transformation:  IF application_state ∈ {EMPTY, UPLOADED}
                   → active_view = VIEW_1
                 IF application_state ∈ {ANALYZED, APPROVED}
                   → active_view = VIEW_2
                 ELSE
                   → active_view = ERROR
Output:          active_view : enum{VIEW_1, VIEW_2, ERROR}
Feeds:           View 1 Renderer (if VIEW_1)
                 Analysis View Container (if VIEW_2)
                 Error Boundary (if ERROR)
Failure path:    IF application_state is null or unrecognized
                   → active_view = ERROR
                   → render error boundary
                   → surface "Application state unresolvable.
                              Contact your data team with Session ID: [session_id]"
                   Note (L2 P2 #33 — 2026-03-27): session_id must be resolved from
                   State Store even in the ERROR path, so the analyst can reference
                   it for operator escalation. If session_id is also unresolvable,
                   surface "Application state unresolvable. Contact your data team."
                   → all controls locked
                   → no view rendered
```

---

### Component 2: View 1 Footer Control Manager

```
Component:       View 1 Footer Control Manager
Layer:           UI
Input:           application_state : enum{EMPTY, UPLOADED}
                 analysis_status   : enum{IDLE, ANALYZING} | NULL
                                     — sourced from State Machine State Store
                                     — NULL when application_state ∈ {EMPTY, APPROVED}
                                     — read on every render alongside application_state
                 (C-1/W-3 FIX — L1 Diagnostic Run 3 · 2026-03-27:
                  analysis_status added as formal Input. Previously Component 2 read
                  application_state only. During analysis, application_state remains
                  UPLOADED — analysis_status = ANALYZING is the only signal that the
                  engine run is in flight. Without it as an input, [Analyze] stays ACTIVE
                  and the analyst can trigger a second dispatch while the first is running.)
Transformation:  IF application_state = EMPTY
                   → analyze_control = LOCKED
                 IF application_state = UPLOADED AND analysis_status = IDLE
                   → analyze_control = ACTIVE
                 IF application_state = UPLOADED AND analysis_status = ANALYZING
                   → analyze_control = ANALYZING
                   (View 1 Renderer renders [Analyze] LOCKED with
                    "Analysis in progress..." label — analyst cannot re-click)
                 ELSE
                   → analyze_control = LOCKED
Output:          view1_footer_state : {analyze_control : enum{ACTIVE, LOCKED, ANALYZING}}
                 — ACTIVE:    [Analyze] clickable
                 — LOCKED:    [Analyze] not clickable (EMPTY state or error)
                 — ANALYZING: [Analyze] not clickable · progress label surfaced
                               to confirm action was received and engine run is in flight
Feeds:           View 1 Renderer
Failure path:    IF application_state unresolvable
                   → analyze_control = LOCKED
                   → surface "Control state error" in footer
```

---

### Component 3: View 1 Renderer (Import View)

```
Component:       View 1 Renderer (Import View)
Layer:           UI
Input:           active_view = VIEW_1,
                 application_state : enum{EMPTY, UPLOADED},
                 view1_footer_state : {analyze_control}
Transformation:  Render five upload slots:
                 IF application_state = EMPTY
                   → all five slots: empty state, no filename, no checkmark
                   → [Analyze] rendered per view1_footer_state (LOCKED)
                 IF application_state = UPLOADED AND analyze_control = ACTIVE
                   → all five slots: filled state, filename displayed
                   → [Analyze] rendered ACTIVE
                 IF application_state = UPLOADED AND analyze_control = ANALYZING
                   → all five slots: filled state, filename displayed
                   → [Analyze] rendered LOCKED
                   → button label: "Analysis in progress..."
                   → analyst cannot re-click · click event ignored while ANALYZING
                   (C-1/W-3 FIX — L1 Diagnostic Run 3 · 2026-03-27:
                    ANALYZING branch added. Previously the UPLOADED condition rendered
                    [Analyze] ACTIVE regardless of analysis_status — the button stayed
                    clickable during the entire 5-minute engine run window. An impatient
                    analyst could dispatch a second engine run while the first was in
                    flight, corrupting allocation_grain. This branch closes that window
                    at the UI layer. Analysis Dispatcher also guards server-side — see
                    state-machine-design.md Component 5.)
                 ELSE → render slots in unknown state — surface slot error

                 Slot labels (fixed):
                   Slot 1: Telemetry & Metering
                   Slot 2: Cost Management / FinOps
                   Slot 3: IAM / Tenant Management
                   Slot 4: Billing System
                   Slot 5: ERP / General Ledger

Output:          rendered View 1 — five upload slots + [Analyze] control
Feeds:           Screen Router (as VIEW_1 output)
Failure path:    IF active_view ≠ VIEW_1
                   → do not render — return control to Screen Router
                 IF slot state cannot be determined
                   → render slot as empty
                   → do not render filled state without confirmed file presence
```

---

### Component 4: KPI Data Aggregator

```
Component:       KPI Data Aggregator
Layer:           UI
Grain:           All Region × GPU Pool × Day × Allocation Target (full table)
Input:           allocation_grain : {
                   gpu_hours          : decimal,
                   cost_per_gpu_hour  : decimal,
                   contracted_rate    : decimal,
                   allocation_target  : varchar,
                   unallocated_type   : varchar | NULL
                 }
Transformation:  GPU Revenue
                   = SUM(gpu_hours × contracted_rate)
                     WHERE allocation_target ≠ 'unallocated'
                 GPU COGS
                   = SUM(gpu_hours × cost_per_gpu_hour)
                     WHERE allocation_target ≠ 'unallocated'
                 Idle GPU Cost
                   = SUM(gpu_hours × cost_per_gpu_hour)
                     WHERE allocation_target = 'unallocated'
                 Idle GPU Cost %
                   = Idle GPU Cost / (GPU COGS + Idle GPU Cost) × 100
                 Cost Allocation Rate
                   = GPU COGS / (GPU COGS + Idle GPU Cost) × 100
                 IF allocation_grain is empty or null
                   → kpi_payload = NULL → failure path fires
Cache requirement (L2 P2 #30 — 2026-03-27):
                 KPI aggregations (GPU Revenue · GPU COGS · Idle GPU Cost · etc.)
                 must be pre-computed at analysis completion time — when
                 allocation_grain is written and the session transitions to ANALYZED
                 — and cached as a session-level summary artifact. UI renders read
                 from the summary artifact, not from allocation_grain directly.
                 At production grain sizes (e.g. 500K rows), a full-table SUM on
                 every page load is a throughput risk under concurrent access.
                 Cache is invalidated only on new session (new session_id).
                 Cache key: session_id. The artifact is immutable once written.
Output:          kpi_payload : {
                   gpu_revenue          : decimal,
                   gpu_cogs             : decimal,
                   idle_gpu_cost        : decimal,
                   idle_gpu_cost_pct    : decimal,
                   cost_allocation_rate : decimal
                 }
Feeds:           Zone 1 Renderer
Failure path:    IF allocation_grain is null or empty
                   → kpi_payload = NULL
                   → Zone 1 renders all four cards in error state
                   → label preserved, value replaced with "Unavailable"
                   → do not render zero as a real value
```

---

### Component 5: Zone 1 Renderer (KPI Cards)

```
Component:       Zone 1 Renderer (KPI Cards)
Layer:           UI
Input:           kpi_payload : {gpu_revenue, gpu_cogs,
                                idle_gpu_cost, idle_gpu_cost_pct,
                                cost_allocation_rate}
Transformation:  IF kpi_payload is complete (no null fields)
                   → render four cards:
                     Card 1: GPU Revenue          — dollar value
                     Card 2: GPU COGS             — dollar value
                     Card 3: Idle GPU Cost        — dollar value + idle_gpu_cost_pct
                     Card 4: Cost Allocation Rate — percentage
                 IF kpi_payload = NULL
                   → render four cards in error state
                   → label preserved, value = "Unavailable"
                   → do not suppress or collapse any card
Output:          rendered Zone 1 — four KPI cards
Feeds:           Analysis View Container
Failure path:    IF kpi_payload is NULL
                   → render error state per card
                   → do not block Analysis View Container from rendering
```

---

### Component 6: Region Data Aggregator

```
Component:       Region Data Aggregator
Layer:           UI
Grain:           Region — preserving Type A / Type B separation within each region
Input:           allocation_grain : {
                   region             : varchar,
                   gpu_hours          : decimal,
                   cost_per_gpu_hour  : decimal,
                   contracted_rate    : decimal,
                   allocation_target  : varchar,
                   unallocated_type   : varchar | NULL
                 }
Transformation:  Per region:
                   Revenue  = SUM(gpu_hours × contracted_rate)
                              WHERE allocation_target ≠ 'unallocated'
                   COGS_A   = SUM(gpu_hours × cost_per_gpu_hour)
                              WHERE allocation_target ≠ 'unallocated'
                   COGS_B   = SUM(gpu_hours × cost_per_gpu_hour)
                              WHERE allocation_target = 'unallocated'
                   IF Revenue = 0 → GM% = NULL
                   ELSE GM%      = (Revenue − COGS_A) / Revenue × 100
                   Idle%    = COGS_B / (COGS_A + COGS_B) × 100
                   Status:  IF Idle% ≤ 30% → HOLDING
                            IF Idle% > 30% → AT RISK
                   Subtype pill counts:
                     identity_broken_count = COUNT rows WHERE unallocated_type = 'identity_broken'
                     capacity_idle_count   = COUNT rows WHERE unallocated_type = 'capacity_idle'
                 IF no data for a region → row omitted (not zero-filled)
                 IF allocation_grain null → region_payload = []
Output:          region_payload : [{
                   region                  : varchar,
                   gm_pct                  : decimal | NULL,
                   idle_pct                : decimal,
                   revenue                 : decimal,
                   status                  : enum{HOLDING, AT RISK},
                   identity_broken_count   : integer,
                   capacity_idle_count     : integer
                 }]
Feeds:           Zone 2L Renderer
Failure path:    IF allocation_grain is null
                   → region_payload = []
                   → Zone 2L renders "No region data available"
```

---

### Component 7: Zone 2L Renderer (Gross Margin by Region)

```
Component:       Zone 2L Renderer (Gross Margin by Region)
Layer:           UI
Input:           region_payload : [{region, gm_pct : decimal | NULL, idle_pct,
                                    revenue, status,
                                    identity_broken_count, capacity_idle_count}]
Transformation:  IF region_payload is non-empty
                   → render ranked table (by GM% descending · NULL last)
                   → columns: Region | GM% | Idle% | Revenue | Status
                   → IF gm_pct = NULL → render "—" in GM% column for that row
                   → Status flag: HOLDING (neutral) | AT RISK (red)
                   → below table: render subtype pills
                     identity_broken pill (red)   — if identity_broken_count > 0
                     capacity_idle pill (orange)  — if capacity_idle_count > 0
                     no pills rendered if both counts = 0
                 IF region_payload = []
                   → render "No region data available" — zone maintained in layout
Output:          rendered Zone 2L — ranked region table + subtype pills
Feeds:           Analysis View Container
Failure path:    IF region_payload = []
                   → render empty state in zone
                   → do not collapse zone
                   → maintain layout position
```

---

### Component 8: Customer Data Aggregator

```
Component:       Customer Data Aggregator
Layer:           UI
Grain:           allocation_target — Type A records only
                 (WHERE allocation_target ≠ 'unallocated')
Input:           allocation_grain : {
                   allocation_target  : varchar,
                   gpu_hours          : decimal,
                   cost_per_gpu_hour  : decimal,
                   contracted_rate    : decimal,
                   unallocated_type   : varchar | NULL,
                   failed_tenant_id   : varchar | NULL
                 }
                 Note: allocation_target holds the tenant_id value for Type A records.
                 failed_tenant_id is populated only on identity_broken rows and
                 carries the original tenant_id that failed IAM resolution.
Transformation:  Build identity_broken set:
                   identity_broken_tenants =
                     SET of failed_tenant_id values
                     WHERE unallocated_type = 'identity_broken'
                     AND failed_tenant_id IS NOT NULL

                 Per allocation_target WHERE allocation_target ≠ 'unallocated':
                   Revenue = SUM(gpu_hours × contracted_rate)
                   COGS    = SUM(gpu_hours × cost_per_gpu_hour)
                   IF Revenue = 0 → GM% = NULL · gm_color = NULL
                   ELSE
                     GM%     = (Revenue − COGS) / Revenue × 100
                     GM color (L2 P2 #36 — 2026-03-27):
                               red    IF GM% < 0%   (negative margin — Risk flag threshold)
                               orange IF GM% 0–29%
                               yellow IF GM% 30–37%
                               green  IF GM% ≥ 38%
                     Note: red is added to align visual encoding with the Risk flag
                     threshold. Previously orange covered both 0–29% and negative
                     margin — a CFO scanning the table could not visually distinguish
                     "low margin" (e.g. 15%) from "negative margin" (e.g. -5%).
                     Red pre-attentively encodes negative margin before the Risk flag
                     is read. The gm_color enum must be updated to include 'red'.
                   Risk flag:
                     FLAG  IF (GM% IS NOT NULL AND GM% < 0)
                              OR (allocation_target ∈ identity_broken_tenants)
                     CLEAR otherwise (including when GM% = NULL
                                      and not in identity_broken_tenants)
                 IF no Type A records → customer_payload = []
SET artifact requirement (L2 P2 #31 — 2026-03-27):
                 identity_broken_tenants SET must be pre-built at analysis completion
                 time and stored as a session-level artifact. Customer Zone renders
                 read from the artifact — not by re-scanning allocation_grain on every
                 render. At large grain sizes, SET reconstruction on every render
                 delays Risk flag display — which is the CFO's primary signal for
                 tenant-level integrity. Same cache key as KPI cache: session_id.
                 Artifact is immutable once written at ANALYZED state.
Integration test requirement:
                 The Risk flag depends on correct failed_tenant_id propagation
                 from 4 upstream components across 2 modules. A NULL regression
                 in any of these components causes the Risk flag to silently
                 under-fire — the CFO sees a clean result for a tenant that has
                 an identity integrity failure.
                 REQUIRED TEST: Before any deployment of the Allocation Engine
                 or the UI module, an end-to-end integration test must verify:
                   1. A known identity_broken tenant is present in raw.iam input
                   2. IAM Resolver classifies it as IDENTITY_BROKEN
                   3. Identity Broken Record Builder sets failed_tenant_id = tenant_id
                   4. Cost & Revenue Calculator carries failed_tenant_id unchanged
                   5. allocation_grain contains a row with failed_tenant_id = that tenant
                   6. Customer Data Aggregator includes that tenant_id in
                      identity_broken_tenants SET
                   7. The matching allocation_target row renders Risk = FLAG
                 This test covers the entire failed_tenant_id propagation chain.
                 A break at any step produces a Risk flag gap with no system error.
                 (L2 P1 #32 — 2026-03-27)
Output:          customer_payload : [{
                   allocation_target : varchar,
                   gm_pct            : decimal | NULL,
                   gm_color          : enum{red, orange, yellow, green} | NULL,
                   revenue           : decimal,
                   risk_flag         : enum{FLAG, CLEAR}
                 }]
                 Note (FIX — L1 Diagnostic 2026-03-27): enum updated from 3-tier
                 {green, yellow, orange} to 4-tier {red, orange, yellow, green}
                 to match transformation (L2 P2 #36) and Zone 2R Renderer contract.
                 Impact: Zone 2R Renderer receives 'red' values without type
                 contract violation. Export Verifier Check 4 is unaffected (checks
                 unallocated_type, not gm_color). No grain schema change required.
Feeds:           Zone 2R Renderer
Failure path:    IF no Type A records in allocation_grain
                   → customer_payload = []
                   → Zone 2R renders empty state
```

---

### Component 9: Zone 2R Renderer (Gross Margin by Customer)

```
Component:       Zone 2R Renderer (Gross Margin by Customer)
Layer:           UI
Input:           customer_payload : [{
                   allocation_target : varchar,
                   gm_pct            : decimal | NULL,
                   gm_color          : enum{red, orange, yellow, green} | NULL,
                   revenue           : decimal,
                   risk_flag         : enum{FLAG, CLEAR}
                 }]
                 Note (FIX — L1 Diagnostic Run 2 · 2026-03-27): gm_color enum updated
                 from 3-tier {green, yellow, orange} to 4-tier {red, orange, yellow, green}
                 to match Component 8 (Customer Data Aggregator) output schema.
                 C-1: receiver contract now matches sender contract at this boundary.
Transformation:  IF customer_payload is non-empty
                   → render ranked table (by GM% descending · NULL last)
                   → columns: Customer | GM% bar | Revenue | Risk
                   → IF gm_pct = NULL
                     → render "—" in GM% column for that row
                     → render gray bar (no color) in GM% bar column
                   → IF gm_pct IS NOT NULL
                     → GM% bar: color-coded per gm_color
                       (red < 0% / orange 0–29% / yellow 30–37% / green ≥ 38%
                        per L2 P2 #36 — updated from 3-tier to 4-tier)
                   → Risk: FLAG (red indicator) | CLEAR (no indicator)
                 IF customer_payload = []
                   → render "No customer data available" — zone maintained
Output:          rendered Zone 2R — ranked customer table
Feeds:           Analysis View Container
Failure path:    IF customer_payload = []
                   → render empty state in zone
                   → do not collapse zone
```

---

### Component 10: Reconciliation Result Reader

```
Component:       Reconciliation Result Reader
Layer:           UI
Input:           reconciliation_results : {
                   check_name : varchar,
                   verdict    : enum{PASS, FAIL}
                 }
                 — exactly three rows expected (one per check)
                 — FAIL-1 and FAIL-2 are internal Check 3 distinctions resolved
                   to FAIL before writing to reconciliation_results
Transformation:  Read three rows in fixed order:
                   Row 1: Capacity vs Usage            → PASS | FAIL
                   Row 2: Usage vs Tenant Mapping      → PASS | FAIL
                   Row 3: Computed vs Billed vs Posted → PASS | FAIL
                 IF result set has < 3 rows or is null
                   → result_payload = NULL → failure path fires
Output:          result_payload : [{
                   check   : varchar,
                   verdict : enum{PASS, FAIL}
                 }] — three rows exactly
Feeds:           Zone 3 Renderer
Failure path:    IF reconciliation_results null or < 3 rows
                   → result_payload = NULL
                   → Zone 3 renders all three rows as "Data unavailable"
                   → do not render PASS for rows with missing data
                   → do not suppress zone
```

---

### Component 11: Zone 3 Renderer (Reconciliation Verdicts)

```
Component:       Zone 3 Renderer (Reconciliation Verdicts)
Layer:           UI
Input:           result_payload : [{check, verdict}] — three rows
Transformation:  IF result_payload has three complete rows
                   → render two-column verdict table
                   → columns: Check | Status
                   → Row 1: Capacity vs Usage            | PASS (green) or FAIL (red)
                   → Row 2: Usage vs Tenant Mapping      | PASS (green) or FAIL (red)
                   → Row 3: Computed vs Billed vs Posted | PASS (green) or FAIL (red)
                   → no drill-down, no variance, no correction — verdict only
                 FAIL escalation path (L2 P2 #21 — 2026-03-27):
                   IF any row verdict = FAIL
                     → render the FAIL verdict row in red (as normal)
                     → below the verdict table, surface an escalation note:
                       "One or more reconciliation checks failed.
                        Contact your data team with Session ID: [session_id]
                        to investigate the root cause."
                     [session_id] is resolved from the reconciliation_results
                     table (session_id column). The analyst has no access to
                     internal reconciliation detail — this note gives them a
                     recovery action (escalate with session_id) rather than
                     just a verdict with no path forward.
                 IF result_payload = NULL
                   → render three rows as "Data unavailable"
                   → do not render PASS for missing data
Output:          rendered Zone 3 — three verdict rows
Feeds:           Analysis View Container
Failure path:    IF result_payload = NULL
                   → all three rows render "Data unavailable"
                   → zone maintained in layout — not collapsed
```

---

### Component 12: View 2 Footer Control Manager

```
Component:       View 2 Footer Control Manager
Layer:           UI
Input:           application_state : enum{ANALYZED, APPROVED}
Transformation:  IF application_state = ANALYZED
                   → approve_control  = ACTIVE
                   → csv_control      = LOCKED
                   → excel_control    = LOCKED
                   → power_bi_control = LOCKED
                 IF application_state = APPROVED
                   → approve_control  = DEACTIVATED
                   → csv_control      = ACTIVE
                   → excel_control    = ACTIVE
                   → power_bi_control = ACTIVE
                 ELSE → all controls = LOCKED
Render invariant: Button states MUST be derived from application_state received
                 from the State Machine on every render. They must NEVER be read
                 from UI local state, component memory, or any value set at a
                 prior render. If a page reload, navigation event, or session
                 restore clears local state, the button states must be
                 re-derived from the current application_state — not inferred
                 from any cached value. An APPROVED session whose local state
                 was cleared must still render approve_control = DEACTIVATED.
                 The State Machine will correctly reject a re-submit attempt via
                 INVALID TRANSITION — but the button must not present the
                 option to attempt it. Stateless render from server state is
                 the enforcement mechanism.
                 (L2 P1 #34 — 2026-03-27)
Output:          view2_footer_state : {
                   approve_control  : enum{ACTIVE, DEACTIVATED},
                   csv_control      : enum{ACTIVE, LOCKED},
                   excel_control    : enum{ACTIVE, LOCKED},
                   power_bi_control : enum{ACTIVE, LOCKED}
                 }
Feeds:           Analysis View Container
Failure path:    IF application_state unresolvable
                   → all controls = LOCKED
                   → surface "Control state error" in footer
                   → [Approve] does not activate
                   → exports do not unlock
```

---

### Component 13: Approve Confirmation Dialog

```
Component:       Approve Confirmation Dialog
Layer:           UI
Input:           approve_control = ACTIVE (from View 2 Footer Control Manager),
                 cfo_click_event : {action = "approve_clicked"},
                 session_id : uuid — resolved from State Store (current active session)
Transformation:  IF approve_control = ACTIVE AND cfo_click_event fires
                   → render modal dialog:
                     Title:   "Approve Gross Margin Results"
                     Body:    "This action is final. Once approved, results
                               are locked and cannot be changed."
                     Actions: [Confirm Approval] | [Cancel]
                 IF CFO selects [Confirm Approval]
                   → emit state_transition_signal:
                     {signal               = 'FIRE',
                      requested_transition = 'ANALYZED→APPROVED',
                      source               = 'APPROVAL_DIALOG',
                      session_id           = session_id}
                   → forward to State Machine (Transition Request Receiver) only
                   → close dialog
                   → on successful APPROVED state transition, surface confirmation:
                     "Approved. Session ID: [session_id] — results locked for export."
                     (L2 P3 #35 — 2026-03-27)
                     This gives the CFO an audit reference without exposing internal
                     system architecture. The session_id can be cited in billing
                     disputes, ERP reconciliations, or audit requests.
                 IF CFO selects [Cancel]
                   → emit state_transition_signal:
                     {signal = 'CANCELLED', requested_transition = NULL,
                      source = NULL, session_id = NULL}
                   → forward to Analysis View Container only
                   → do NOT send to State Machine
                   → close dialog
                   → state remains ANALYZED
                   → [Approve] returns to ACTIVE — no state change
                 IF approve_control ≠ ACTIVE
                   → dialog does not render — click event ignored
                   → emit state_transition_signal:
                     {signal = 'BLOCKED', requested_transition = NULL,
                      source = NULL, session_id = NULL}
                   → forward to Analysis View Container only
                   → do NOT send to State Machine
Output:          state_transition_signal : {
                   signal               : enum{FIRE, CANCELLED, BLOCKED},
                   requested_transition : varchar | NULL,
                   source               : varchar | NULL,
                   session_id           : uuid | NULL
                 }
Feeds:           State Machine (FIRE only — full structured signal)
                 Analysis View Container (all signals — signal field only)
Failure path:    IF modal fails to render
                   → do not emit FIRE
                   → surface "Approval dialog failed to load"
                   → state remains ANALYZED
                   → [Approve] remains ACTIVE
```

---

### Component 14: Analysis View Container (View 2)

```
Component:       Analysis View Container (View 2)
Layer:           UI
Input:           rendered_zone_1        : Zone 1 Renderer output,
                 rendered_zone_2L       : Zone 2L Renderer output,
                 rendered_zone_2R       : Zone 2R Renderer output,
                 rendered_zone_3        : Zone 3 Renderer output,
                 view2_footer_state     : View 2 Footer Control Manager output,
                 state_transition_signal : {signal : enum{FIRE, CANCELLED, BLOCKED}}
                                          — signal field only — from Approve
                                            Confirmation Dialog
Transformation:  Assemble View 2 layout:
                   Row 1: Zone 1 (full width — four KPI cards)
                   Row 2: Zone 2 (two columns — Zone 2L left, Zone 2R right)
                   Row 3: Zone 3 (full width — reconciliation verdicts)
                   Footer: [Approve] | [CSV] | [Excel] | [Power BI]
                           rendered per view2_footer_state

                 On state_transition_signal:
                   IF signal = CANCELLED
                     → close dialog · [Approve] returns to ACTIVE
                   IF signal = BLOCKED
                     → dialog did not render · no state change
                   IF signal = FIRE
                     → close dialog · screen transitions per state update
                       (Screen Router reflects APPROVED state via State Machine)

                 IF any individual zone is in error state
                   → maintain layout for all zones
                   → surface error within the affected zone only
                   → do not block other zones from rendering
                   → do not block [Approve] on zone error alone
                 IF all zones fail
                   → render View 2 shell with all zones in error state
                   → do not revert to View 1
Output:          rendered View 2 — complete analysis screen
Feeds:           Screen Router (as VIEW_2 output)
Failure path:    IF view2_footer_state is null
                   → render footer with all controls LOCKED
                   → surface "Footer state unavailable"
                   → do not infer control state from zone data
```

---

## STEP 4 — Problem-to-Design Analysis

```
Problem:          The CFO receives a margin figure that is blended and opaque —
                  idle cost is invisible, identity failures are silent, and no
                  gate exists before the number leaves the system.

Required output:  A screen that shows:
                  — four KPI cards separating allocated cost from idle cost
                  — region and customer margin tables with subtype distinction
                    (capacity_idle vs. identity_broken visually distinguishable)
                  — three reconciliation verdicts (PASS/FAIL only)
                  — footer controls state-gated (export locked until APPROVED,
                    [Approve] deactivated after use, confirmation dialog before
                    terminal state transition)

Design produces:  14 components that together enforce the above.
                  Screen Router enforces view transitions by state.
                  KPI Data Aggregator separates Type A and Type B before
                    any value reaches the screen.
                  Region and Customer aggregators preserve subtype distinction
                    at the record level before rendering.
                  Zone 2L renders capacity_idle (orange) and identity_broken
                    (red) as distinct pills — not blended.
                  Zone 3 renders three verdicts — no drill-down, no variance,
                    no correction.
                  View 2 Footer Control Manager locks export until APPROVED
                    and deactivates [Approve] after use.
                  Approve Confirmation Dialog adds a two-step friction point
                    before the terminal state transition fires.
                  Analysis View Container maintains layout on zone failure —
                    one zone error does not suppress the others.

Gap or match:     MATCH — all four CFO problems addressed at the UI layer.
                  Gap identified in STEP 4 (single-click irreversibility)
                  closed by S1 (Approve Confirmation Dialog — Component 13).
```

---

## Component Summary

| # | Component | Layer | Feeds |
|---|-----------|-------|-------|
| 1 | Screen Router | UI | View 1 Renderer / Analysis View Container / Error Boundary |
| 2 | View 1 Footer Control Manager | UI | View 1 Renderer |
| 3 | View 1 Renderer | UI | Screen Router |
| 4 | KPI Data Aggregator | UI | Zone 1 Renderer |
| 5 | Zone 1 Renderer | UI | Analysis View Container |
| 6 | Region Data Aggregator | UI | Zone 2L Renderer |
| 7 | Zone 2L Renderer | UI | Analysis View Container |
| 8 | Customer Data Aggregator | UI | Zone 2R Renderer |
| 9 | Zone 2R Renderer | UI | Analysis View Container |
| 10 | Reconciliation Result Reader | UI | Zone 3 Renderer |
| 11 | Zone 3 Renderer | UI | Analysis View Container |
| 12 | View 2 Footer Control Manager | UI | Analysis View Container |
| 13 | Approve Confirmation Dialog | UI | State Machine / Analysis View Container |
| 14 | Analysis View Container | UI | Screen Router |
