---
role: deep-reference
reads-from: software-system-design.md
session-context: load only when implementing or debugging AskUserQuestion or TodoWrite tool calls — not required for design sessions
---

# Tool-Call Specification — AskUserQuestion & TodoWrite
**Parent:** software-system-design.md
**Purpose:** Full JSON schemas, execution flow diagrams, constraint mapping, task list templates, and gate compliance checks for AskUserQuestion and TodoWrite tool calls. Load this file when implementing or auditing tool-call behavior. Do not load during standard design sessions — the summary table in software-system-design.md is sufficient.

---

## FIRING POINT 1 — STEP 1: Scope Confirmation

### When it fires
Immediately after STEP 0 confirms this is a NEW INSTRUCTION.
Before any design work begins. Before stating expected output.

### What the file requires
→ Do NOT assume what is being designed
→ Ask a precision multiple-choice question
→ Wait for selection
→ Confirm in one sentence: "Designing [X]. Output expected: [Y]."

### Tool call

```json
{
  "questions": [
    {
      "question": "What are we designing today?",
      "header": "Design scope",
      "multiSelect": false,
      "options": [
        {
          "label": "Ingestion Module",
          "description": "CSV intake, validation, field typing, and source parsing for all 5 upstream files — Telemetry, Cost Management, IAM, Billing, ERP."
        },
        {
          "label": "Allocation Engine",
          "description": "Tenant-level GPU cost allocation logic — maps gpu_hours_consumed to allocation_target per Region × GPU Pool × Day grain."
        },
        {
          "label": "Reconciliation Engine",
          "description": "Three-check reconciliation — Capacity vs Usage (Check 1), Usage vs Tenant Mapping (Check 2), and Computed vs Billed vs Posted (Check 3). Surfaces capacity_idle and identity_broken failure modes. Check 3 added S3 confirmed 2026-03-25."
        },
        {
          "label": "State Machine, UI Screen, or Export",
          "description": "Application state management (EMPTY → UPLOADED → ANALYZED → APPROVED), the analyst-facing screen (one screen, two views, three zones), or the export layer (CSV, Excel, Power BI flat CSV)."
        }
      ]
    }
  ]
}
```

### After user responds

If Ingestion, Allocation, or Reconciliation selected:
→ Claude confirms in one sentence before proceeding to STEP 2:
  "Designing [selected scope]. Output expected: [named output from Application Context]."
→ Proceed to STEP 2 — do not skip.

If "State Machine, UI Screen, or Export" selected:
→ Do NOT proceed to STEP 2 yet.
→ Fire a second AskUserQuestion to resolve the exact scope within that bundle:

```json
{
  "questions": [
    {
      "question": "Which of these are we designing?",
      "header": "Narrow scope",
      "multiSelect": false,
      "options": [
        {
          "label": "State Machine",
          "description": "Application lifecycle management — EMPTY → UPLOADED → ANALYZED → APPROVED state transitions, APPROVED State Gate, and state-driven access control for Export."
        },
        {
          "label": "UI Screen",
          "description": "The analyst-facing screen — one screen, two views, three zones. What the analyst sees and interacts with."
        },
        {
          "label": "Export Module",
          "description": "The output layer — CSV, Excel (xlsx skill), Power BI flat CSV, and PDF summary (pdf skill). Active only in APPROVED state."
        }
      ]
    }
  ]
}
```

→ After user selects one:
  Claude confirms in one sentence: "Designing [selected module]. Output expected: [named output from Application Context]."
→ Proceed to STEP 2 — do not skip.

### If user selects "Other" (auto-provided by tool)
The tool automatically appends an "Other" option to every question — do not add it manually.
When selected, the user provides free text describing their scope.
Claude confirms the described scope in one sentence before proceeding.
Do not assume — restate what was described and ask: "Is this the scope?"
If confirmed → proceed to STEP 2.

---

## FIRING POINT 2 — STEP 2: Output Confirmation

### When it fires
After STEP 1 scope is confirmed.
After Claude has stated:
→ Expected output (what the system produces at this layer)
→ Consumed by (downstream component or analyst)
→ Failure behavior (what breaks downstream if output fails)

Claude states all three first. Then fires AskUserQuestion.

### What the file requires
Ask: "Is this the correct expected output?"
Wait for confirmation or correction.
If corrected → return to correction point only. Do not restart STEP 1.

### Tool call

```json
{
  "questions": [
    {
      "question": "Is this the correct expected output?",
      "header": "Output check",
      "multiSelect": false,
      "options": [
        {
          "label": "Confirmed — proceed to design",
          "description": "The expected output, consumer, and failure behavior are correct as stated. Proceed to STEP 3 backward design."
        },
        {
          "label": "Correction needed",
          "description": "Something in the expected output, consumer, or failure behavior is wrong. Describe the correction — Claude will return to that point only without restarting."
        }
      ]
    }
  ]
}
```

### After user responds

If Confirmed:
→ Proceed to STEP 3 — backward design

If Correction needed:
→ User selects "Correction needed" — or selects "Other" (auto-provided by tool) to describe the correction in free text
→ Return to the specific correction point only
→ Do NOT restart STEP 1
→ Do NOT restart from the top
→ Restate the corrected output block
→ Fire AskUserQuestion again: "Is this now correct?"
→ Repeat until confirmed

---

## FIRING POINT 3 — STEP 5: Suggestion Selection

### When it fires
After STEP 4 analysis is complete.
Only if the design has a gap, a risk, or an alternative that meaningfully changes output quality.
If no gap → STEP 5 does not fire AskUserQuestion — proceed to STEP 7 (save) then STEP 6.

### What the file requires
Present as bounded options: S1, S2, S3 — each with a one-sentence summary.
Ask: "Which direction do you want to take, or should we proceed as designed?"
User decides. Claude executes.

### Tool call (template — populated after STEP 4 gap analysis)

```json
{
  "questions": [
    {
      "question": "Which direction do you want to take, or should we proceed as designed?",
      "header": "Direction",
      "multiSelect": false,
      "options": [
        {
          "label": "S1 — [Suggestion title]",
          "description": "[What it changes] — [Why it matters] — [Trade-off if adopted]."
        },
        {
          "label": "S2 — [Suggestion title]",
          "description": "[What it changes] — [Why it matters] — [Trade-off if adopted]."
        },
        {
          "label": "S3 — [Suggestion title]",
          "description": "[What it changes] — [Why it matters] — [Trade-off if adopted]."
        },
        {
          "label": "Proceed as designed",
          "description": "The current design is sufficient. No suggestion is adopted. Move to STEP 7 (save and link) then STEP 6 to wait for next instruction."
        }
      ]
    }
  ]
}
```

### After user responds

If S1, S2, or S3 selected:
→ Execute the selected suggestion
→ Do not execute suggestions not selected
→ Do not expand scope
→ Proceed to STEP 7 (save) then STEP 6

If Proceed as designed:
→ No changes
→ Proceed to STEP 7 (save) then STEP 6

If fewer than 3 suggestions exist:
→ Remove unused S slots from the options array
→ Minimum: 1 suggestion option + "Proceed as designed" = 2 options total
→ Do not fabricate suggestions to fill slots

---

## STEP 0 — Why AskUserQuestion Does NOT Fire Here

STEP 0 is a scope check Claude resolves from context — not a user decision.

Continuation = follow-up clarification, minor adjustment, delta change, confirmation request.
New instruction = new component, new layer, different part of the system, scope shift.

Claude reads the incoming instruction and determines the path.
If the determination is ambiguous → Claude defaults to NEW INSTRUCTION and proceeds to STEP 1.
AskUserQuestion in STEP 1 then resolves the ambiguity naturally.

---

## AskUserQuestion — Execution Flow

```
Receive instruction
        ↓
STEP 0 — Claude determines: continuation or new?
        │
        ├── CONTINUATION
        │       → Restate active scope (one line)
        │       → Delta output
        │       → STEP 4 analysis
        │       → STEP 5: AskUserQuestion fires IF gap exists
        │       → STEP 7: conditional save IF delta affects file artifact
        │       → STEP 6: wait (mark complete on delivery)
        │
        └── NEW INSTRUCTION
                → STEP 1: AskUserQuestion fires ← user selects module/layer
                → Confirm selection in one sentence
                → STEP 2: Claude states output block
                → AskUserQuestion fires ← user confirms or corrects
                → STEP 3: backward design + internal anti-drift gate (no AskUserQuestion — Claude executes and verifies internally as one task)
                → STEP 4: analysis (no AskUserQuestion — Claude analyzes)
                → STEP 5: AskUserQuestion fires IF gap exists ← user picks direction
                → STEP 7: save design output — link via computer:// (no AskUserQuestion — Claude executes)
                → STEP 6: wait (no AskUserQuestion — scope locked)
```

---

## AskUserQuestion — Constraint Mapping

| File rule | Tool behavior | Match |
|---|---|---|
| "Do NOT assume what is being designed" | Tool blocks execution until user responds | ✅ Enforced structurally |
| "Do NOT produce a design before scope is confirmed" | STEP 1 AskUserQuestion must complete before STEP 3 | ✅ Enforced by sequence |
| "Use multiple-choice questions" | Tool renders options as selectable choices | ✅ Native behavior |
| "I select one. You confirm." | Tool returns selection → Claude confirms in one sentence | ✅ Matches protocol |
| "If corrected → return to correction point only. Do not restart." | STEP 2 correction loops within STEP 2 only | ✅ No restart of STEP 1 |
| "I decide. You execute." | Tool gives user the decision. Claude acts on response. | ✅ Native behavior |
| "Do not offer suggestions until design is produced" | STEP 5 tool call cannot fire before STEP 4 is complete | ✅ Enforced by sequence |
| Maximum 4 options per question (schema: maxItems 4) | 6 modules → 4 named options + "Other" auto-provided by tool = full coverage | ✅ Covered |

---

## TodoWrite Tool — Task Protocol

### Task Layers — Summary

The file contains two execution paths and three structural layers.
TodoWrite must reflect all three.

| Layer | What It Contains | TodoWrite Role |
|---|---|---|
| Interaction Protocol | STEP 0–7 (+ STEP 1b) — the execution sequence | Task items |
| Anti-Drift Rules | 10 enforcement gates — fire inline during steps | Verification sub-tasks inside STEP 3 GATE |
| Governing Principles | 6 invariants — govern all steps, never listed as tasks | Implicit — not task items |

Note: "STEP 3 GATE" is the anti-drift verification that runs within STEP 3 — it is NOT a separate TodoWrite task.
STEP 3 stays in_progress while the gate check runs. STEP 3 is only marked completed after the gate passes.
Only one task may be in_progress at a time. STEP 3 GATE is an internal sub-check, not a concurrent task item.

### Two Execution Paths Found

STEP 0 is the branch point. Every session starts here.

```
STEP 0
   ├── IF CONTINUATION → STEP 4 → STEP 5 → STEP 7 (conditional) → STEP 6
   └── IF NEW INSTRUCTION → STEP 1 → STEP 2 → STEP 3 → STEP 4 → STEP 5 → STEP 7 → STEP 6
```

---

### PATH A — NEW INSTRUCTION
#### TodoWrite Task List

```json
[
  {
    "content": "STEP 0 — Scope check: new instruction confirmed, run full sequence",
    "activeForm": "Running scope check — new instruction path activated",
    "status": "completed"
  },
  {
    "content": "STEP 1 — Ask precision multiple-choice question: what are we designing?",
    "activeForm": "Asking scope confirmation — waiting for selection",
    "status": "in_progress"
  },
  {
    "content": "STEP 1b — Confirm selection: 'Designing [X]. Output expected: [Y]'",
    "activeForm": "Confirming selected scope and named output",
    "status": "pending"
  },
  {
    "content": "STEP 2 — State expected output, downstream consumer, and failure behavior",
    "activeForm": "Stating expected output, consumer, and failure behavior — awaiting confirmation",
    "status": "pending"
  },
  {
    "content": "STEP 3 — Build backward design and run STEP 3 GATE verification before marking complete",
    "activeForm": "Building backward design — output → transformation → input → source → prerequisite — then running internal gate check before marking complete",
    "status": "pending"
  },
  {
    "content": "STEP 4 — Analyze: Problem → Required output → Design produces → Gap or match",
    "activeForm": "Analyzing design against problem statement — checking for gap or match",
    "status": "pending"
  },
  {
    "content": "STEP 5 — Suggestion check: offer S1/S2/S3 if gap or risk exists, ask for direction",
    "activeForm": "Checking for gaps — offering bounded suggestions if needed",
    "status": "pending"
  },
  {
    "content": "STEP 7 — Save design output as [module-name]-design.md — link via computer://",
    "activeForm": "Saving design output to workspace folder and linking for analyst access",
    "status": "pending"
  },
  {
    "content": "STEP 6 — Deliver wait message: scope locked, no expansion, no preview — mark complete on delivery",
    "activeForm": "Delivering wait message — marking complete on delivery",
    "status": "pending"
  }
]
```

#### Notes on PATH A

→ STEP 1 stays `in_progress` until user selects from multiple-choice.
→ STEP 1b marks complete only after one-sentence confirmation is delivered.
→ STEP 2 stays `in_progress` until user confirms the output statement.
  If corrected → return to STEP 2 correction point only. Do not restart STEP 1.
→ STEP 3 includes STEP 3 GATE as an internal sub-check — STEP 3 is not marked complete until the gate passes.
  Only one task is in_progress at a time. STEP 3 GATE does not become its own task item.
→ STEP 5 is conditional: only produces suggestions if STEP 4 found a gap or risk.
  If no gap → STEP 5 = "No suggestions — design closes the problem" → mark complete.
→ STEP 7 fires after STEP 5 completes — save is unconditional after every STEP 3 execution.
→ STEP 6: mark as `completed` immediately after the wait message is delivered.
  The wait state is enforced by Claude not acting — not by keeping a task permanently open.
  A permanently pending task conflicts with Cowork's TodoWrite model (tasks complete on delivery).

---

### PATH B — CONTINUATION
#### TodoWrite Task List

```json
[
  {
    "content": "STEP 0 — Scope check: continuation confirmed, restate active scope in one line",
    "activeForm": "Confirming continuation — restating active scope",
    "status": "completed"
  },
  {
    "content": "Build delta output only — what changed and why within active scope",
    "activeForm": "Building delta output for active scope",
    "status": "in_progress"
  },
  {
    "content": "STEP 4 — Analyze delta: does the change close the gap or introduce new risk?",
    "activeForm": "Analyzing delta against problem and design",
    "status": "pending"
  },
  {
    "content": "STEP 5 — Suggestion check on delta: offer bounded options if gap persists",
    "activeForm": "Checking delta for remaining gaps — offering suggestions if needed",
    "status": "pending"
  },
  {
    "content": "STEP 7 (conditional) — If delta affects a file artifact: save updated design output and link via computer://",
    "activeForm": "Saving updated design artifact to workspace folder and linking for analyst access",
    "status": "pending"
  },
  {
    "content": "STEP 6 — Deliver wait message: scope locked, no expansion, no preview — mark complete on delivery",
    "activeForm": "Delivering wait message — marking complete on delivery",
    "status": "pending"
  }
]
```

#### Notes on PATH B

→ Active scope line must be restated before delta output is built.
  Format: "Active scope: [component] | Layer: [layer] | Output: [named output]"
→ Delta means: only what changed. Nothing outside the active scope.
→ STEP 1 and STEP 2 are intentionally absent — scope is already confirmed.
→ STEP 3 is absent — no new full design. Delta only.
→ STEP 4 still runs — even a delta must be analyzed for gap or match.
→ STEP 7 (conditional): if the delta corrects a component that produces or modifies a file artifact
  → add STEP 7 task: save the updated design output as [module-name]-design.md → link via computer://
  → if the delta is design text or structural correction only (no file artifact affected) → STEP 7 is omitted.
→ STEP 6: mark complete on delivery — wait enforcement is behavioral, not a permanently open task.

---

### Anti-Drift Rules — Gate Mapping

These rules do not become separate task items.
They are enforcement checks that fire inside STEP 3 GATE (PATH A) or inside the delta task (PATH B).

| Rule | Gate Point | TodoWrite Behavior |
|---|---|---|
| Rule 1 — No design before scope confirmed | Before STEP 3 starts | If STEP 1 not completed → mark STEP 3 blocked → return to STEP 1 |
| Rule 2 — No forward design | Inside STEP 3 | If design flows input→output → stop → reverse direction → restart STEP 3 |
| Rule 3 — No unnamed fields | STEP 3 GATE | All field names and types must be declared before gate passes |
| Rule 4 — No vague transformations | STEP 3 GATE | All transformations must use IF/THEN/ELSE before gate passes |
| Rule 5 — No missing failure paths | STEP 3 GATE | All components must have named failure path before gate passes |
| Rule 6 — No suggestions during design | Before STEP 5 | STEP 5 cannot start until STEP 4 is completed |
| Rule 7 — No scope expansion | Any step | If response addresses out-of-scope component → stop → lock back to active scope |
| Rule 8 — No output without grain | STEP 3 GATE | Grain (Region × GPU Pool × Day × Allocation Target) must be stated first |
| Rule 9 — One responsibility per component | STEP 3 GATE | Each component block must have exactly: one input · one rule · one output · one downstream |
| Rule 10 — No scope preview after STEP 6 | STEP 6 | STEP 6 closes with wait only — no "here is what we design next" content |

---

### Governing Principles — STEP 3 GATE Compliance Check

The 6 Governing Principles are not task items but they ARE verified inside STEP 3 GATE.
Before STEP 3 is marked completed, confirm each principle is satisfied in the component blocks just produced:

| Principle | Check |
|---|---|
| 1. Output first | Every component in the design traces to a named output. No orphan components. |
| 2. Backward design | Design was built output → transformation → input → source → prerequisite. Not forward. |
| 3. Confirmation before design | STEP 1 and STEP 2 were completed before STEP 3 began. |
| 4. Separation of concerns | No component carries more than one input, one transformation rule, one output, one downstream. |
| 5. Failure visibility | Every component has a named failure path. No implicit "it works" assumptions. |
| 6. Suggestion discipline | No suggestions were offered before STEP 4 was completed. |

If any principle is violated in the component blocks → stop → correct the violation → re-run the gate.
STEP 3 is only marked completed when all 10 Anti-Drift Rules and all 6 Governing Principles pass.

---

### State Machine Mapping

The file defines a 4-state application lifecycle.
These are not interaction protocol states — they are system states.
They should appear as context in STEP 2 (expected output), not as todo tasks.

```
EMPTY → UPLOADED → ANALYZED → APPROVED
```

Export is only active in APPROVED state.
If designing the Export module → STEP 2 must state:
  "Consumed by: analyst — only when APPROVED State Gate confirms state = APPROVED"
  "Failure behavior: export blocked if APPROVED State Gate returns state ≠ APPROVED"

---

### Two Failure Modes — TodoWrite Trigger Condition

These must be preserved at the grain record level through every design layer.
They surface in STEP 4 (analysis) as the primary test of whether the design closes the problem.

```
capacity_idle    → reserved GPU-hours with no matching consumption
                   gross_margin = −cogs on unallocated row

identity_broken  → consumed GPU-hours with no resolvable tenant_id in IAM
                   allocation_target = "unallocated" / unallocated_type = "identity_broken"
```

If STEP 4 analysis cannot confirm both failure modes are distinguishable at the grain record level
in the design just produced → Gap or match = GAP → STEP 5 must fire.

---

### Quick Reference — Which Path, Which Tasks

```
Receive instruction
        ↓
STEP 0 — Is it continuation or new?
        │
        ├── CONTINUATION
        │       → STEP 0 (restate scope) ✓
        │       → Delta output
        │       → STEP 4 (analyze delta)
        │       → STEP 5 (suggestions if gap)
        │       → STEP 7 (conditional save — only if delta affects file artifact)
        │       → STEP 6 (wait — mark complete on delivery)
        │
        └── NEW INSTRUCTION
                → STEP 0 (branch confirmed) ✓
                → STEP 1 (multiple-choice — wait)
                → STEP 1b (confirm selection)
                → STEP 2 (output statement — wait for confirmation)
                → STEP 3 (backward design + internal STEP 3 GATE — one task, gate runs inside, marks complete only after gate passes)
                → STEP 4 (analyze: problem vs design)
                → STEP 5 (suggestions if gap)
                → STEP 7 (save design output — link via computer://)
                → STEP 6 (wait — scope locked)
```
