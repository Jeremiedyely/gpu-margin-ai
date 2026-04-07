# GPU Gross Margin Visibility Platform

A full-stack financial intelligence system that ingests raw GPU infrastructure data, computes gross margin at multiple grain levels, reconciles results against billing and ERP records, and produces a locked, auditable, exportable financial view.

---

## The Problem

In GPU cloud infrastructure businesses, finance teams are flying blind. They know total cloud cost. They know total revenue. But they cannot answer:

- Which customer is actually unprofitable at the unit level?
- Is that loss from idle capacity, or a contracted rate that's too low?
- Does what we billed match what we computed — and does what we computed match what we posted to the GL?

Without a system like this, those questions get answered in Excel — manually, monthly, inconsistently, after the fact. By the time a customer with negative gross margin is discovered, they've been underwater for three months.

---

## What It Does

Answers one structural question: **for every GPU-hour consumed, are we making or losing money — and why?**

Five source files feed in. The system validates, ingests, allocates, reconciles, and surfaces results as a locked approvable view with export controls.

```
Upload → Analyze → Approve → Export
```

---

## The Three Reconciliation Checks

These are the core of the value.

| Check | What It Catches |
|---|---|
| **Capacity vs Usage** | Unutilized GPU capacity written off as invisible cost leakage |
| **Usage vs Tenant Mapping** | GPU hours consumed by tenants with no IAM match — you cannot bill them |
| **Computed vs Billed vs Posted** | Mismatches between calculated revenue, invoiced amounts, and GL entries |

---

## Architecture

### State Machine

Every session transitions through a locked, append-only state machine:

```
EMPTY → UPLOADED → ANALYZED → APPROVED → TERMINAL
```

No state can be skipped. No state can be reversed. Results are locked on approval. A new session is required for any subsequent analysis run.

### Data Pipeline

```
Telemetry (GPU usage)
Cost Management (cloud rates)       ┐
IAM (tenant ownership)              ├─► Allocation Engine ─► Reconciliation Engine ─► KPI Cache
Billing (what was invoiced)         │                                                      │
ERP (what was GL posted)           ┘                                                      ▼
                                                                                   Approve / Export
```

### Schema (16 Flyway Migrations)

| Schema | Tables |
|---|---|
| `raw` | ingestion_log, telemetry, cost_management, iam, billing, erp |
| `dbo` | allocation_grain, reconciliation_results, state_store, state_history, kpi_cache, identity_broken_tenants |
| `final` | allocation_result |

---

## Tech Stack

### Backend
- **FastAPI** — REST API
- **Celery + Redis** — async allocation and reconciliation workers
- **SQLAlchemy 2.0** — database layer
- **SQL Server 2022** — primary store (snapshot isolation)
- **Flyway** — versioned schema migrations
- **Python 3.12**, **openpyxl**, **pyodbc**

### Frontend
- **React 18** + **TypeScript 5**
- **Vite** — build tooling
- **TanStack Query** — server state management
- **Tailwind CSS** — design system
- **Nginx** — static file serving

### Infrastructure
- **Docker Compose** — full local stack (one command boot)
- **GitHub Actions CI** — full regression on every push

---

## What Gets Surfaced

**KPI Cards**
- GPU Revenue
- GPU COGS
- Idle GPU Cost
- Cost Allocation Rate

**Gross Margin by Region**
- GM% gradient bar (4-tier: green / yellow / orange / red)
- AT RISK status flag
- Identity Broken and Capacity Idle subtype pills

**Gross Margin by Customer**
- GM% gradient bar per tenant
- Risk FLAG badge
- Revenue

**Reconciliation Panel**
- PASS / FAIL verdict per check
- Escalation alert with session ID on any FAIL

---

## Export Formats

Unlocked on CFO approval:

| Format | Use Case |
|---|---|
| **CSV** | Raw data handoff |
| **Excel (.xlsx)** | Finance team analysis |
| **Power BI** | Dashboard ingestion |

---

## Running Locally

**Prerequisites:** Docker, Docker Compose

```bash
git clone https://github.com/Jeremiedyely/gpu-margin.git
cd gpu-margin/phase_zero
docker compose up
```

The stack boots in order: SQL Server → db_init (creates database) → Flyway (runs 16 migrations) → FastAPI + Celery workers → React frontend.

Frontend: `http://localhost:5173`
API: `http://localhost:8000`

---

## Test Suite

```bash
# Backend — pytest against real SQL Server (transactional rollback per test)
cd phase_zero
python -m pytest tests/ -v

# Frontend — vitest + React Testing Library
cd phase_zero/frontend
npx vitest run

# TypeScript
npx tsc --noEmit
```

CI runs on every push via GitHub Actions with a live SQL Server 2022 service container.

---

## Project Structure

```
phase_zero/
├── app/
│   ├── allocation/          # Allocation engine (GPU-hour → revenue/COGS)
│   ├── reconciliation/      # Three-check reconciliation engine
│   ├── ingestion/           # CSV parsers, validators, writers
│   ├── state_machine/       # State transitions, session lifecycle
│   ├── export/              # CSV / Excel / Power BI generators
│   ├── ui/                  # KPI, region, customer, reconciliation aggregators
│   └── api/                 # FastAPI routes
├── db/
│   ├── migrations/          # 16 Flyway SQL migrations
│   └── init/                # Database creation before Flyway
├── frontend/
│   └── src/
│       ├── components/      # 14 React components
│       ├── hooks/           # Data-fetch hooks (useKPI, useRegions, etc.)
│       └── types/           # TypeScript API contracts
├── tests/                   # pytest suites (allocation, reconciliation, ingestion, state machine, export, ui)
├── test_data/               # Sample CSVs (7 tenants, 3 regions, 4 dates)
└── docker-compose.yml
```

---

## Design Principle

Built as a **stewardship system** — not a reporting layer, but a control mechanism. It does not just show what the numbers are. It validates that the numbers are *true* before anyone approves them, locks the result once approved, and forces a new session for any subsequent analysis.

---

## Author

Jeremie — [Jeremiedyely@gmail.com](mailto:Jeremiedyely@gmail.com)
