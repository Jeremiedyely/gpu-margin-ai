---
role: why-layer
feeds-into: requirements.md
session-context: load first — establishes the problem, market validation, CFO impact, and application purpose
---

# CFO & Companies — Problem, Impact, and Application Purpose

**Created:** 2026-03-25 13:12 CDT

> See: requirements.md — WHAT layer · grain definition · computation contract · state machine · UI outputs

---

## What problem the web application is solving? — One sentence

GPU gross margin is being corrupted silently — upstream systems each look clean in isolation, but when their outputs are combined across system boundaries, inconsistencies flow directly into the gross margin calculation with no alarm and no traceable root cause.

---

## Is the problem real? Research as of 2026-03-25

**Conclusion:** The problem is real, well-documented, and active right now.

### The market exists and is large

GPU cloud producers serving AI model builders are a confirmed and growing segment. CoreWeave serves OpenAI, Mistral AI, and IBM directly. Microsoft Azure signed a $2B+ contract with CoreWeave specifically to serve OpenAI's compute demand. Lambda Labs serves AI developers and researchers. CoreWeave's annualized revenue is projected to exceed $5 billion by FY2026. GPU clouds are growing 1,000% year-over-year by some estimates.

### The idle GPU problem is confirmed at scale

Over 75% of organizations report GPU utilization below 70% at peak load. Utilization rates across cloud deployments consistently run 30–50%. When OpenAI trained GPT-4 across roughly 25,000 A100 GPUs, average utilization hovered between 32–36% — meaning most of those chips sat idle while still accruing full reservation cost. Teams waste 30–50% of their GPU budget on provisioned-but-inactive capacity.

### The cost visibility and margin problem is confirmed

84% of enterprises report significant gross margin erosion tied to unoptimized AI workloads. The Flexera 2025 State of the Cloud Report found organizations exceeding cloud budgets by an average of 17%, with 32% of that spend identified as pure waste. Most AI costs sit in "shared infrastructure" and cannot be cleanly allocated to specific customers or features — which is precisely the cost allocation failure the application is built to surface.

### The cost attribution gap is confirmed at the producer level

GPU providers with older fleets face depreciation schedules that may understate true economic cost. AWS updated EC2 Capacity Blocks pricing on January 4, 2026 with significant rate increases, compressing margins for producers with fixed-rate customer contracts. The gap between reserved capacity cost (fixed) and actual customer consumption (variable) is the structural margin exposure the application diagnoses.

The problem the application solves — GPU gross margin corrupted silently by idle cost blending and identity failures — is not theoretical. It is happening at the exact companies the application targets, confirmed by current industry data.

### Sources
- The AI Cost Crisis: AI Cost Sprawl Explained — cloudzero.com
- GPU Clouds Growing 1,000% YoY — Sacra
- CoreWeave — The Essential Cloud for AI — coreweave.com
- Solving GPU Overprovisioning Cost Waste in 2026 — lyceum.technology
- You're Probably Underutilizing Your GPUs — Stack Overflow Blog
- Blackwell GPUs and the New Economics of Cloud AI Pricing — Medium
- Cloud Infrastructure Suffers AI Growing Pains — TechTarget
- Cloud GPU Providers Compared 2026 — gpu.fm

---

## How this problem impacts the CFO

The CFO of a GPU cloud producer serving AI companies faces this problem across four distinct pressure points.

### 1. Gross margin is wrong and the CFO cannot prove it or fix it

89% of CFOs report rising cloud costs have negatively impacted gross margins over the past 12 months. When idle GPU cost blends into COGS as an undifferentiated number, the CFO sees a gross margin figure that is structurally lower than true unit margin — but cannot separate the performance signal (how profitable is each customer?) from the waste signal (how much capacity went unabsorbed?). The board sees a margin. The CFO cannot explain what is causing it or whether it will improve.

### 2. Forecast variance is indefensible

85% of companies miss AI infrastructure forecasts by more than 10%. 74% of CFOs report monthly cloud forecast variance of 5–10% or higher. For a GPU cloud producer, the structural reason is that cost is fixed at reservation and revenue is variable at consumption. When idle cost is not separated into its own line, the CFO is forecasting a blended number that moves for two completely different reasons — utilization and identity failures — with no way to distinguish them. The forecast is built on a structurally corrupted input.

### 3. Pricing and contract decisions are made against the wrong floor

The cost per GPU-hour sets the pricing floor. If that cost is blended with idle cost rather than derived from actual reserved capacity at the unit level, the CFO and sales team are negotiating customer rates against a number that overstates true COGS. They compress margin unnecessarily on some contracts and underestimate exposure on others. Leaders are making pricing, packaging, and investment decisions in the dark.

### 4. Identity failures produce false demand signals that reach the CFO as real data

When a tenant ID fails to anchor in telemetry, real consumption appears as idle cost. The cost allocation rate drops. The income statement reports underutilization. The CFO escalates a demand problem to the board. The actual root cause is an identity integrity failure in the ingestion layer — but nothing in the financial reporting surface can distinguish the two. The CFO is responding to a signal that was corrupted three layers upstream.

**The core CFO exposure:** the financial statements close cleanly, the audit passes, and the margin number is structurally wrong. There is no alarm. The problem is invisible by construction until it is separated at the grain level — which is precisely what the application is built to do.

### Sources
- Why Your Gross Margin Is Wrong — Cloud Capital
- 2025 State of AI Cost Management — 85% Miss Forecasts by >10% — prnewswire.com
- The AI Investment Decision: How CFOs Are Balancing Growth and Margin Risk — Cloud Capital
- Signal vs. Noise: Why Your Gross Margins Are Hemorrhaging in 2026 — valere.io
- Budgeting for Cloud Costs in 2025 — CFO Playbook — Cloud Capital
- GPU Cost Forecasting, AI Unit Economics — Ridgeway Financial Services
- Unit Economics for AI SaaS — CFO Survival Guide — drivetrain.ai

---

## The purpose of this web application — from the business and CFO problem

The purpose of the application is to make the CFO's gross margin number trustworthy.

Right now a GPU cloud producer's income statement closes cleanly — revenue is recognized, COGS is posted, gross margin is computed — and the number is structurally wrong. Not because of a calculation error. Because idle GPU cost blends silently into COGS with no named record, and identity failures make real customer consumption appear as unabsorbed waste. The financial statements cannot distinguish between the two. The CFO cannot separate true unit margin from utilization drag. Pricing decisions, contract negotiations, and board reporting are all built on a corrupted input.

The application exists to break that blended number apart — at the grain level, before any aggregation runs — so the CFO can see three things that are currently invisible:

First, exactly how much of COGS is real customer-allocated cost versus idle capacity cost sitting with no revenue offset. Second, which customers are profitable and which are compressing margin, at the account level. Third, whether the margin signal the business is reading is real — or whether it is being distorted by an identity integrity failure upstream that makes consumed GPU-hours look like idle capacity.

The application does not fix anything. It does not advise. It does not correct upstream records. It receives five source files, maps every GPU-hour to either a customer or an explicit unallocated record, runs two system boundary checks, and surfaces exactly where the inconsistencies are and which layer produced them.

The output is not a dashboard. It is a defensible number — one the CFO can approve, export, and bring to the board with confidence that what it shows is structurally accurate, not an artifact of blended, uncontrolled cost allocation.

---

## What outputs the web application provides

All four outputs come from the same source — the approved allocation grain table.

### 1. Four KPI cards (Zone 1 — header)

The health of the system in four numbers:

- **GPU Revenue** — total revenue recognized from customer-allocated GPU consumption
- **GPU COGS** — total cost of customer-allocated GPU hours only
- **Idle GPU Cost** — cost of GPU capacity with no customer anchor, in dollars and as a percentage of total COGS
- **Cost Allocation Rate** — share of total GPU cost successfully anchored to a paying customer

These are the inputs to every decision below them. They tell the CFO whether the margin number is being compressed by real demand gaps or by system failures upstream.

### 2. Gross Margin by Region (Zone 2 — left)

A ranked table showing where margin is holding and where it is leaking, by geographic region. Columns: GM%, Idle%, Revenue, and a status flag (HOLDING / AT RISK when idle exceeds 30%). Below the table, idle breakdown pills distinguish `identity_broken` (red) from `capacity_idle` (orange) — so the CFO can see not just that a region is at risk, but why.

### 3. Gross Margin by Customer (Zone 2 — right)

A ranked table showing which customers are profitable and which are compressing margin, by account. GM% is displayed as a color-coded bar (green ≥38% / yellow 30–38% / orange <30%). A risk flag fires when GM% is negative or when that customer's tenant ID has an identity failure — meaning their consumption may be partially misclassified as idle cost.

### 4. Reconciliation verdicts (Zone 3 — bottom)

Three rows. Three checks. PASS or FAIL only.

- **Capacity vs Usage** — does consumed GPU ever exceed reserved capacity? A FAIL means telemetry is over-reporting or capacity is under-reported.
- **Usage vs Tenant Mapping** — does every tenant ID in telemetry resolve to a valid IAM record? A FAIL means identity-broken unallocated records exist — real consumption with no customer anchor.
- **Computed vs Billed vs Posted** — does revenue computed from the allocation grain match the Billing system and the ERP/GL posted amount per tenant? A FAIL has two subtypes: FAIL-1 (computed ≠ billed) and FAIL-2 (billed ≠ posted). Both evaluated independently per tenant per billing period. *(Added — S3 confirmed 2026-03-25)*

No drill-down. No variance. No suggested action. The check name and the verdict. The CFO sees exactly which system boundary broke and makes the call.

### After approval — three export formats

CSV, Excel (.xlsx), and Power BI flat CSV. All three read from the same approved, immutable table. No consumer receives a different number than any other. Every export includes `session_id` and `source_files` as the last two columns — populated from `raw.ingestion_log` at the moment of CFO approval, linking every exported row to the exact ingestion run and source files that produced it. *(Added — S2 confirmed 2026-03-25)*

---

## Do the application outputs solve the business and CFO problems?

Yes. Each output maps directly to a specific problem.

**Problem: Gross margin is wrong and the CFO cannot prove it or fix it.**
Output that solves it: Zone 1 KPI cards + Zone 2 Region and Customer tables. The KPI cards separate what was previously one blended COGS number into three distinct components — customer-allocated cost, idle cost, and the allocation rate. For the first time the CFO sees true unit margin separated from idle drag. The Region and Customer tables show exactly where the compression is coming from and which accounts are profitable. The margin number is no longer a blended approximation — it is a structured, grain-level computation with a named record for every dollar.

**Problem: Forecast variance is indefensible — the CFO cannot explain what is moving margin month to month.**
Output that solves it: Idle GPU Cost KPI + unallocated subtype distinction (capacity_idle vs. identity_broken). These two outputs separate the two root causes that were previously indistinguishable. Idle cost from genuine underutilization (capacity_idle) is a demand and reservation planning problem. Idle cost from identity failures (identity_broken) is a system integrity problem. With the subtype visible, the CFO can forecast margin movement by cause — not just observe that it moved.

**Problem: Pricing and contract decisions are made against the wrong cost floor.**
Output that solves it: GPU COGS KPI + Gross Margin by Customer table. GPU COGS in Zone 1 is the cost of actually serving customers — not blended with idle. This is the true cost floor for pricing decisions. The Customer table shows the GM% per account against that floor. The CFO can see which contracts are priced above cost, which are inverted, and which are approaching the breakeven threshold.

**Problem: Identity failures produce false demand signals that reach the CFO as real data.**
Output that solves it: Reconciliation Check 2 (Usage vs Tenant Mapping) + identity_broken unallocated rows + Customer Risk flag. Check 2 fires a FAIL the moment any tenant ID in telemetry has no IAM match. The identity_broken pill in Zone 2 shows which region it is coming from. The Customer Risk flag flags the affected account. The CFO no longer receives a false underutilization signal as a clean margin number.

**Problem: The financial statements close cleanly but the margin is structurally wrong with no alarm.**
Output that solves it: The approval gate + export controls. The application does not allow export until the CFO reviews and approves the results. The approved output is written to an immutable table. All three export formats read from the same approved record. The number that enters the board presentation, the GL, and the BI platform is the same number the CFO reviewed and approved at the grain level.

**One-line answer:** Every output the application produces exists to give the CFO one thing that currently does not exist — a gross margin number that is structurally accurate, traceable to its source, and separable by root cause before it reaches the income statement.

---

## Do the application outputs solve the cloud and AI infrastructure companies' problems?

Yes. Here is the direct mapping between what the industry is experiencing and what each output addresses.

**Industry problem: 85% of companies miss AI infrastructure forecasts by more than 10%.**
The root cause is that idle cost and identity failures blend into COGS as one undifferentiated number. The application's KPI cards split that number into three components — allocated cost, idle cost, and allocation rate — so the forecast is built on a structured input, not a blended approximation. The variance becomes explainable because the cause is visible.

**Industry problem: 84% of companies report gross margin erosion from AI infrastructure costs they cannot control or trace.**
Erosion that cannot be traced cannot be managed. The Region and Customer margin tables give cloud and AI infrastructure companies the first grain-level view of where margin is holding and where it is leaking — by geography, by account, by day. The erosion is no longer a directional signal on the income statement. It is a named record with a dollar value and a source.

**Industry problem: GPU utilization runs 30–50% across cloud deployments — but companies cannot distinguish idle capacity from identity failures.**
This is the exact problem the two unallocated subtypes solve. `capacity_idle` means GPUs were reserved and no job was submitted — a utilization and reservation planning problem. `identity_broken` means a job ran and GPU-hours were consumed but the customer anchor failed — a system integrity problem. Both look identical on the income statement. The application makes them distinguishable at the record level before any aggregation runs.

**Industry problem: Infrastructure costs are scaling faster than companies can track them, and leaders are making pricing and investment decisions in the dark.**
The Cost Allocation Rate KPI directly measures how much of the GPU cost base is anchored to a paying customer. If that rate drops, the application surfaces whether it dropped because customers consumed less or because the identity layer broke. Pricing decisions, capacity planning, and contract negotiations can now be made against a number that reflects structural reality.

**Industry problem: Shared infrastructure costs cannot be fairly attributed across customers, creating financial reporting friction.**
The grain — Region × GPU Pool × Day × Allocation Target — solves this at the data architecture level. Every GPU-hour has exactly one allocation target. Either a customer owns it or `unallocated` owns it. There is no third state. Attribution is not estimated or averaged. It is a structural property of the grain.

**One-line answer:** The application outputs solve the core problem that cloud and AI infrastructure companies face — not by optimizing spend or suggesting corrections, but by making the invisible visible at the grain level so that every financial decision downstream is built on a number that is structurally accurate and traceable to its source.

---

## What are the web application goals? What is unique about it?

### The goal

Make the GPU gross margin number trustworthy before it reaches the income statement. Not approximate. Not blended. Not inferred from aggregates. Structurally accurate — at the grain level, traceable to its source, separable by root cause, and approved by the CFO before it enters any downstream system.

Everything the application does serves that single goal. The grain forces every GPU-hour into a named record. The allocation engine computes cost and revenue at that record level. The reconciliation engine tests system boundary integrity before the number is approved. The approval gate locks the result before export. The export formats all read from the same approved table. Nothing in the flow allows a blended, estimated, or uncontrolled number to pass through.

### What is unique — five things no existing tool does together

**1. Unallocated is a first-class record, not an absence.**
Every existing FinOps tool — CloudHealth, Apptio, AWS Cost Explorer — treats idle as a remainder computed at the aggregate level. A number you subtract. A percentage you report. In this application, idle is a named row in the grain table with its own gpu_hours, cogs, and gross_margin = −cogs. It exists before any aggregation runs. It cannot be hidden by blending. It can be filtered, trended, exported, and reconciled the same as any customer row. No current tool stores idle as an explicit first-class allocation record at this grain.

**2. Two unallocated subtypes that require completely different interventions.**
`capacity_idle` — reserved capacity with no job submitted — is a utilization and reservation planning problem. `identity_broken` — a job ran, GPU-hours were consumed, but the customer anchor failed — is a system integrity problem. On the income statement they look identical: unabsorbed COGS with no revenue offset. In this application they are distinguished at the record level. The CFO does not receive a blended idle signal. They receive a classified one. No existing tool makes this distinction explicitly in the data model.

**3. Three reconciliation checks that test system boundary integrity — not just data completeness.**
Most tools validate that data arrived. These checks test whether the outputs of independent systems are structurally consistent with each other across defined boundaries. Check 1 tests whether consumed GPU-hours ever exceed reserved capacity — a boundary between Telemetry and Cost Management. Check 2 tests whether every tenant ID in Telemetry resolves to a valid IAM record — a boundary between the physical system and the identity layer. Check 3 tests whether revenue computed from the allocation grain matches what Billing invoiced and what ERP posted — a boundary between the financial systems. A FAIL is not a missing field. It is a structural inconsistency between two systems that corrupts the margin calculation silently. *(Check 3 added — S3 confirmed 2026-03-25)*

**4. The approval gate makes the margin number a deliberate act, not an automatic output.**
The application has four states. Export is locked until the CFO reviews the grain-level results and explicitly approves them. The approved output is written to an immutable table with a timestamp and a unique row identifier. All three export formats read from that same approved table. The number that enters the board presentation, the BI platform, and the GL is the number the CFO saw, reviewed, and approved — not a number produced automatically by a pipeline the CFO never touched.

**5. It is not a FinOps optimization tool. It is a margin integrity control.**
Every tool in this space — CloudHealth, Apptio, Cloudability, AWS Cost Explorer — is built to reduce spend. They optimize. They recommend. They suggest rightsizing, reserved instance coverage, and waste reduction. This application does none of that. It does not advise. It does not correct. It does not suggest. It receives five source files, maps every GPU-hour to a grain record, runs three integrity checks, surfaces exactly where the system is inconsistent and which source field produced it, and waits for the CFO to decide. The decision and correction authority belongs entirely to the user. That is not a limitation — it is the design principle. The application is a control, not an optimizer.

The combination of these five properties — explicit unallocated records, two classified subtypes, system boundary integrity checks, an approval gate, and a non-advisory posture — does not exist as a product in the current market. That is what makes it unique.
