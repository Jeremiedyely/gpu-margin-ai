---
role: machine-readable-specification
reads-from: business.md
feeds-into: software-system-design.md
session-context: authoritative — load on every build session
---

# Requirements — GPU Gross Margin Visibility Application
**Created:** 2026-03-25
**Purpose:** Machine-readable specification. Claude reads this as authoritative context for all build sessions.

> See: business.md — WHY layer · CFO problem definition · market research · application purpose
---

## 1. PROBLEM

**One sentence:**
GPU cloud producers cannot see gross margin at the grain level because costs and revenue live in separate systems, making idle cost invisible, identity failures undetectable, and revenue unreconciled before CFO approval.

**Structural breakdown:**

```
WHO        GPU cloud producers
           — reserve GPU capacity from infrastructure providers
           — sell GPU-hours to AI model-building companies (tenants)

WHAT       Gross margin is invisible at the operational level because:
           Cost source:     FinOps / Cost Management  (reserved capacity cost)
           Revenue source:  IAM / contracted rates     (per-tenant billing rate)
           These systems do not talk to each other.

CONSEQUENCES
  1. Idle cost is blended into COGS — CFO cannot separate
     the cost of serving customers from the cost of unused capacity.

  2. Identity failures are silent — when a GPU job runs but the
     tenant cannot be resolved in IAM, the cost disappears into
     an untracked bucket. Revenue is lost. No signal is raised.

  3. Revenue cannot be reconciled — the number the engine computes
     may not match what Billing invoiced or what ERP posted.
     Three systems, three numbers, no cross-check before approval.

  4. No approval gate — no structural point where the CFO can
     review, confirm, and authorize the margin output before
     it leaves the system.
```

---

## 2. GRAIN

**Definition:**
```
Region × GPU Pool × Day × Allocation Target
```

**Why this grain:**
```
Region           — where the capacity lives
GPU Pool         — which cluster produced the cost
Day              — when the cost and consumption occurred
Allocation Target — WHO received the value:
                    tenant_id (customer) OR "unallocated" (idle/broken)
```

**Two record types at grain:**
```
Type A — Customer record
  allocation_target = tenant_id
  unallocated_type  = NULL
  revenue           = gpu_hours × contracted_rate
  cogs              = gpu_hours × cost_per_gpu_hour
  gross_margin      = revenue − cogs

Type B — Unallocated record
  allocation_target = "unallocated"
  unallocated_type  = "capacity_idle"    (reserved · no job ran)
                   OR "identity_broken"  (job ran · no IAM match)
  revenue           = 0
  gross_margin      = −cogs              (never 0 — always a cost)
```

**Closure rule:**
```
SUM(gpu_hours per pool per day) = reserved_gpu_hours
Idle cannot be absent. If consumption < reserved, a Type B row is forced.
This makes COGS separation structural — not derived, not estimated.
```

**Why this rule is forced (not derived):**
```
If idle were computed at the aggregate level — as a remainder after customer
rows are summed — it could be hidden by blending. A single unallocated dollar
has no named record. It cannot be filtered, trended, reconciled, or exported.

By forcing a Type B row at the grain level before any aggregation runs,
idle has a named record with its own gpu_hours, cogs, and gross_margin = −cogs.
It exists as a first-class row — not a subtraction.

This is the structural guarantee that makes blending architecturally impossible.
SUM(Type A cogs) + SUM(Type B cogs) = SUM(ALL reserved capacity cost).
No dollar can be absent. No cost can be hidden.
```

---

## 3. DOES THE GRAIN SOLVE THE OUTPUT AND PROBLEM?

```
PROBLEM 1 — Idle cost blended into COGS
  Grain solves it:  Type A and Type B are mutually exclusive record populations.
                    GPU COGS KPI reads Type A only.
                    Idle GPU Cost KPI reads Type B only.
                    Blending is architecturally impossible.
  Verdict:          SOLVED AT DATA MODEL LEVEL

PROBLEM 2 — Identity failures silent
  Grain solves it:  When tenant_id cannot be resolved in IAM,
                    the record is written as Type B / identity_broken.
                    It carries a cost. It is visible. It is named.
                    Check 2 (Usage vs Tenant Mapping) flags it before approval.
  Verdict:          SOLVED AT DATA MODEL LEVEL

PROBLEM 3 — Revenue unreconciled
  Grain solves it:  allocation_grain produces computed revenue per tenant.
                    Check 3 compares this to Billing (invoiced) and ERP (posted).
                    Three-way reconciliation closes before CFO approves.
  Verdict:          SOLVED BY CHECK 3 (above-grain aggregation · grain unchanged)

PROBLEM 4 — No approval gate
  Grain solves it:  final.allocation_result is immutable.
                    It is written only on APPROVED state transition.
                    Export is locked until APPROVED is server-confirmed.
                    The grain-level table IS the approval artifact.
  Verdict:          SOLVED BY STATE MACHINE (grain is the payload · state gates it)
```

**Summary:** The grain is the anchor for every output, every KPI, every check, and every export. All four problems are solved by — or directly depend on — the grain definition.

---

## 4. UI OUTPUTS (CFO)

**Screen 1 — Import Screen (View 1)**
```
Five file upload slots:
  Slot 1  Telemetry & Metering
  Slot 2  Cost Management / FinOps
  Slot 3  IAM / Tenant Management
  Slot 4  Billing System
  Slot 5  ERP / General Ledger

```

**Screen 2 — Analysis Screen (View 2)**

```
ZONE 1 — Four KPI Cards
  GPU Revenue        
  GPU COGS             
  Idle GPU Cost        
  Cost Allocation Rate 

ZONE 2 LEFT — Gross Margin by Region
  Columns: Region · GM% · Idle% · Revenue · Status
  Status:  HOLDING (idle% ≤ 30%) · AT RISK (idle% > 30%)
  Pills below table:
    identity_broken  (red)
    capacity_idle    (orange)

ZONE 2 RIGHT — Gross Margin by Customer
  Columns: Customer · GM% bar · Revenue · Risk
  GM% bar: green ≥ 38% · yellow 30–38% · orange < 30%
  Risk:    FLAG if GM% < 0 OR identity failure on tenant · CLEAR otherwise

ZONE 3 — Reconciliation Verdicts (integrity signal before approval)
  Two columns: Check · Status
  Three rows:
    Capacity vs Usage            PASS / FAIL
    Usage vs Tenant Mapping      PASS / FAIL
    Computed vs Billed vs Posted PASS / FAIL
  No drill-down · no variance · no root cause · no correction

FOOTER CONTROLS (state-gated)
  [Approve]    active in ANALYZED state
  [CSV]        locked until APPROVED
  [Excel]      locked until APPROVED
  [Power BI]   locked until APPROVED
```

**Export (three formats — APPROVED state only)**
```
Source:  Same source table (immutable · approved)

Format 1: CSV
Format 2: Excel .xlsx
Format 3: Power BI flat CSV
```

---

## 5. COMPUTATION CONTRACT

**Purpose:** Defines the exact formula for every computed value in the UI. All formulas derive from the grain. No formula introduces a new field not already defined in Section 2.

```
GPU Revenue
  Formula:   SUM(gpu_hours × contracted_rate)
             WHERE allocation_target ≠ "unallocated"
  Source:    Type A records only
  Grain:     aggregated across Region × GPU Pool × Day × tenant_id

GPU COGS
  Formula:   SUM(gpu_hours × cost_per_gpu_hour)
             WHERE allocation_target ≠ "unallocated"
  Source:    Type A records only
  Grain:     aggregated across Region × GPU Pool × Day × tenant_id

Idle GPU Cost
  Formula:   SUM(gpu_hours × cost_per_gpu_hour)
             WHERE allocation_target = "unallocated"
  Source:    Type B records only
  Grain:     aggregated across Region × GPU Pool × Day × "unallocated"
  Display:   dollar value + percentage of total COGS
             Idle GPU Cost % = Idle GPU Cost / (GPU COGS + Idle GPU Cost) × 100

Cost Allocation Rate
  Formula:   SUM(Type A cogs) / (SUM(Type A cogs) + SUM(Type B cogs)) × 100
  Meaning:   share of total GPU cost successfully anchored to a paying customer
  Complement: 100% − Cost Allocation Rate = idle drag rate

GM% (by Region and by Customer)
  Formula:   (SUM(revenue) − SUM(cogs)) / SUM(revenue) × 100
  Source:    Type A records only — grouped by Region or by tenant_id
  Color thresholds:
    green    GM% ≥ 38%   — healthy margin
    yellow   GM% 30–38%  — compressed, above floor
    orange   GM% < 30%   — at or approaching breakeven risk

Idle% (by Region)
  Formula:   SUM(Type B cogs per region) / SUM(ALL cogs per region) × 100
  Status threshold:
    HOLDING  idle% ≤ 30%
    AT RISK  idle% > 30%

Gross Margin (unit — Type A record)
  Formula:   revenue − cogs
             = (gpu_hours × contracted_rate) − (gpu_hours × cost_per_gpu_hour)

Gross Margin (unit — Type B record)
  Formula:   −cogs
             = −(gpu_hours × cost_per_gpu_hour)
  Revenue:   always 0 — never positive, never NULL
```

---

## 6. STATE MACHINE

**Purpose:** Defines the four application states, their transition conditions, and which UI controls are active at each state. The approval gate is enforced by state — not by UI logic alone.

```
States — four only:

  EMPTY      No files uploaded. Import screen (View 1) is active.
             Analysis controls are locked. No computation is possible.

  UPLOADED   All five files received and validation passed.
             Analysis has not yet run.
             Import screen remains active. [Analyze] becomes available.

  ANALYZED   Allocation engine and reconciliation engine have completed.
             Analysis screen (View 2) is active.
             KPI cards, Region table, Customer table, and reconciliation
             verdicts are visible and populated.
             [Approve] button is active.
             Export buttons (CSV, Excel, Power BI) are locked.

  APPROVED   CFO has reviewed and explicitly approved the ANALYZED output.
             final.allocation_result written to immutable table with
             timestamp and unique session_id.
             Export buttons unlock. All three formats read from the
             approved immutable table only.
             [Approve] button deactivates.
             No further state transitions are possible for this session.

Transition rules:
  EMPTY    → UPLOADED   all five files pass validation
  UPLOADED → ANALYZED   allocation and reconciliation engines complete
                        without fatal error
  ANALYZED → APPROVED   CFO explicit approval confirmed server-side
  APPROVED → (terminal) no further transitions. Export reads from
                        immutable table only. Session is closed.

State gate enforcement:
  Export is locked at the server level until state = APPROVED.
  UI lock alone is not sufficient — the APPROVED State Gate confirms
  server-side state before any export file is generated.
  (APPROVED State Gate is distinct from Output Verification.
   State Gate fires first. Output Verification fires after file is produced.)
```

