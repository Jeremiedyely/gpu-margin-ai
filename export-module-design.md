---
role: module-design
module: Export
layer: Export
reads-from: requirements.md · software-system-design.md
session-context: Export Module design — 9 components — backward from file delivery to analyst
confirmed: 2026-03-27
suggestion-applied: S1 — Format-aware source_files verification in Output Verifier
---

# Export Module Design — GPU Gross Margin Visibility Application

> See: business.md — WHY layer · CFO problem definition
> See: requirements.md — WHAT layer · state machine · export formats · approval gate
> See: software-system-design.md — HOW layer · APPROVED State Gate · Output Verification sequence

---

## Scope

**Active scope:** Export Module | Layer: Export
**Output expected:** Three export files (CSV, Excel .xlsx, Power BI flat CSV) read from `final.allocation_result`. APPROVED State Gate confirms server-side state before any file is generated. `session_id` and `source_files` appended as the last two columns in all three formats. Output Verification runs after each file is produced. File is not delivered if verification fails.
**Consumed by:** CFO / analyst (downloads file) → Board presentation · GL · BI platform
**Failure behavior:** If export is not gated on server-confirmed state, a file could be generated from a pre-approval run or partial dataset. If session metadata is not appended at the record level, no downstream consumer can trace an exported row back to the ingestion run that produced it.

---

## Naming Note

Two distinct verification mechanisms exist in this system:

```
APPROVED State Gate  — confirms application lifecycle state = APPROVED
                       before Export Source Reader executes.
                       Fires first.

Output Verifier      — confirms file quality and grain integrity
                       after a generator produces the file.
                       Fires second.

These are sequential, not interchangeable.
```

---

## Backward Dependency Chain

```
Analyst receives file via computer:// link
              ↑
  File Delivery Handler
              ↑
  Output Verifier  (6 checks: existence · row count · grain · subtypes · readability · metadata format)
              ↑
  CSV Generator  |  Excel Generator  |  Power BI Generator
  (Bash write)   |  (xlsx skill)     |  (Bash write)
              ↑
  Format Router  (dispatches to exactly one generator per request)
              ↑
  Session Metadata Appender  (session_id + source_files → last two columns)
              ↑
  Export Source Reader  (reads final.allocation_result — immutable · approved)
              ↑
  APPROVED State Gate  (server-side state = APPROVED confirmed before any read)
              ↑
  Export request triggered by analyst click ([CSV] | [Excel] | [Power BI])
```

---

## Export Source Schema

```
final.allocation_result — fields read at export time:
  region             : varchar
  gpu_pool_id        : varchar
  date               : date
  billing_period     : varchar   (YYYY-MM — copied from allocation_grain)
  allocation_target  : varchar   (tenant_id | 'unallocated')
  unallocated_type   : varchar | NULL  ('capacity_idle' | 'identity_broken' | NULL)
  failed_tenant_id   : varchar | NULL  (original tenant_id for identity_broken rows
                                         · NULL for all other record types)
  gpu_hours          : decimal
  cost_per_gpu_hour  : decimal
  contracted_rate    : decimal | NULL
  revenue            : decimal
  cogs               : decimal
  gross_margin       : decimal
  [appended at export time — last two columns in all formats:]
  session_id         : uuid
  source_files       : varchar  (JSON array for CSV/Excel · pipe-delimited for Power BI)
```

---

## Component Blocks — 9 Components

---

### Component 1: APPROVED State Gate

```
Component:       APPROVED State Gate
Layer:           Export
Input:           export_request : {
                   format       : enum{CSV, EXCEL, POWER_BI},
                   requested_by : varchar
                 }
                 — triggered by analyst click on export button
                 — session_id is not required: the Export Gate Enforcer resolves
                   session_id from State Store internally
Transformation:  Send state_query : {requester = 'APPROVED_STATE_GATE'}
                 to State Machine Export Gate Enforcer.
                 Await gate_response : {result      : enum{OPEN, BLOCKED},
                                        reason_code : enum{GATE_OPEN,
                                                           GATE_BLOCKED_NOT_APPROVED,
                                                           GATE_BLOCKED_WRITE_NULL,
                                                           GATE_BLOCKED_WRITE_FAILED,
                                                           GATE_BLOCKED_STATE_UNREADABLE} | NULL,
                                        reason      : varchar | NULL}
                 (W-3 FIX — L1 Run 4 · 2026-03-27: reason_code added to declared Input.
                  Previously this component only declared {result, reason} — reason_code
                  was added to the Enforcer's Output by P2 #27 FIX but was never declared
                  here. Transformation now branches on reason_code programmatically instead
                  of inspecting reason string text.)

                 IF gate_response.result = OPEN
                   → gate_result = OPEN
                 IF gate_response.result = BLOCKED
                   → gate_result = BLOCKED
                   · reason = gate_response.reason
                 IF Export Gate Enforcer does not respond
                   → gate_result = BLOCKED
                   · reason = "State gate check failed — no response from State Machine"

                 Note: Export Gate Enforcer evaluates both application_state = APPROVED
                 AND Approved Result Writer write_result = SUCCESS before returning OPEN.
                 This gate accepts the Enforcer's verdict — it does not replicate that logic.

                 BLOCKED reason surface rules (W-3 FIX — L1 Run 4 · 2026-03-27:
                 Branching now uses reason_code enum — not text inspection of reason string.
                 Previously "IF gate_response.reason indicates write_result = NULL" was
                 fragile text parsing — any change to the reason string in the Enforcer
                 would silently break message routing here. reason_code is stable and
                 programmatically branchable. L2 P2 #42 BLOCKED rule also applied.):
                   IF gate_response.reason_code = GATE_BLOCKED_WRITE_NULL
                     → surface "Export blocked — approval record incomplete.
                                Contact your admin with Session ID: [session_id]"
                   IF gate_response.reason_code = GATE_BLOCKED_WRITE_FAILED
                     → surface "Export blocked — result write not confirmed.
                                Contact your admin with Session ID: [session_id]"
                   IF gate_response.reason_code = GATE_BLOCKED_NOT_APPROVED
                     → surface "Export unavailable — data has not been approved"
                   IF gate_response.reason_code = GATE_BLOCKED_STATE_UNREADABLE
                     → surface "System state unavailable — try again or contact support"
                   These messages are distinct per reason_code. Do not collapse them.
                   reason (text) is preserved for operator logs — use reason_code for routing.
Output:          gate_result : {
                   result  : enum{OPEN, BLOCKED},
                   format  : enum{CSV, EXCEL, POWER_BI},
                   reason  : varchar | NULL
                 }
Feeds:           Export Source Reader (if OPEN) | UI Error Surface (if BLOCKED)
Failure path:    IF Export Gate Enforcer does not respond
                   → gate_result = BLOCKED
                   → surface "Export unavailable — state gate unreachable"
                   → no file is generated
                   → no read of final.allocation_result occurs
```

---

### Component 2: Export Source Reader

```
Component:       Export Source Reader
Layer:           Export
Input:           gate_result : {result = OPEN, format}
Transformation:  IF gate_result = OPEN
                   → read ALL rows from final.allocation_result
                   → read session_id from final.allocation_result
                     (present in every row — read once from any row)
                   → IF table is empty
                     → read_result = FAIL · error = "Approved table contains no rows"
                   → IF read succeeds
                     → read_result = SUCCESS · row_count = n
                 ELSE → do not read
Output:          export_dataset : {
                   result     : enum{SUCCESS, FAIL},
                   format     : enum{CSV, EXCEL, POWER_BI},
                   session_id : uuid,
                   records    : [{region, gpu_pool_id, date, billing_period,
                                  allocation_target, unallocated_type,
                                  failed_tenant_id, gpu_hours,
                                  cost_per_gpu_hour, contracted_rate, revenue,
                                  cogs, gross_margin}],
                   row_count  : integer,
                   error      : varchar | NULL
                 }
                 Note: session_id is read from final.allocation_result and
                 carried forward so Session Metadata Appender can query
                 raw.ingestion_log by session_id to retrieve source_files.
Feeds:           Session Metadata Appender
Failure path:    IF final.allocation_result is unreadable or empty
                   → read_result = FAIL
                   → surface named error to UI
                   → block all export formats
                   → do not pass dataset downstream
```

---

### Component 3: Session Metadata Appender

```
Component:       Session Metadata Appender
Layer:           Export
Input:           export_dataset : {result = SUCCESS, records, format, row_count,
                                   session_id : uuid}
                 — session_id carried forward from Export Source Reader
                   (read from final.allocation_result)
Transformation:  Using export_dataset.session_id as the lookup key:
                   Query raw.ingestion_log WHERE session_id = export_dataset.session_id
                   Resolve: source_files : varchar  (raw JSON array from log)
                 IF source_files cannot be resolved for that session_id
                   → appender_result = FAIL
                   · error = "Session metadata unresolvable — ingestion log missing
                               for session [session_id]"
                 IF resolved
                   → append session_id as second-to-last column to every row
                   → append source_files as last column to every row
                     (raw value — format transformation handled by generators)
                   → appender_result = SUCCESS
Output:          enriched_dataset : {
                   result       : enum{SUCCESS, FAIL},
                   format       : enum{CSV, EXCEL, POWER_BI},
                   records      : [{...all grain fields, session_id, source_files}],
                   row_count    : integer,
                   session_id   : uuid,
                   error        : varchar | NULL
                 }
Feeds:           Format Router
Failure path:    IF appender_result = FAIL
                   → do not pass enriched_dataset downstream
                   → surface "Export blocked — session metadata could not be appended"
                   → no file is generated
```

---

### Component 4: Format Router

```
Component:       Format Router
Layer:           Export
Input:           enriched_dataset : {result = SUCCESS, format, records, session_id}
Transformation:  IF enriched_dataset.result = SUCCESS
                   → route based on format:
                     format = CSV       → dispatch to CSV Generator
                                          source_files format: JSON array
                     format = EXCEL     → dispatch to Excel Generator
                                          source_files format: JSON array
                     format = POWER_BI  → dispatch to Power BI Generator
                                          source_files format: pipe-delimited string
                   → format declaration is passed with routed_dataset so each
                     generator and Output Verifier Check 6 can validate without
                     re-inspecting the format field independently
                     (L2 P2 #40 — 2026-03-27)
                   → exactly one generator receives the dataset per export request
                 IF enriched_dataset.result = FAIL → do not route
Output:          routed_dataset : {format, records, session_id, row_count}
                 — delivered to exactly one generator
Feeds:           CSV Generator (if CSV) | Excel Generator (if EXCEL)
                 | Power BI Generator (if POWER_BI)
Failure path:    IF format is unrecognized or null
                   → route_result = FAIL
                   · error = "Unrecognized export format: [format]"
                   → surface error to UI · no file generated
```

---

### Component 5: CSV Generator

```
Component:       CSV Generator
Layer:           Export
Input:           routed_dataset : {format = CSV, records, session_id, row_count}
Transformation:  IF records is non-empty
                   → write all records to file using Bash write
                   → filename: gpu-margin-export-[session_id].csv
                   → column order: per EXPORT_COLUMN_ORDER shared constant
                     (see module-level definition — do not duplicate inline)
                   → source_files: JSON array format
                     e.g. ["file1.csv","file2.csv","file3.csv","file4.csv","file5.csv"]
                   → delimiter: comma · header row included · UTF-8 encoding
                   → file written to workspace folder
                   → generation_result = SUCCESS
                 IF records is empty → generation_result = FAIL
Output:          csv_file : {
                   result    : enum{SUCCESS, FAIL},
                   filename  : varchar,
                   filepath  : varchar,
                   format    : 'CSV',
                   row_count : integer,
                   error     : varchar | NULL
                 }
Feeds:           Output Verifier
Failure path:    IF Bash write fails
                   → generation_result = FAIL
                   · error = "CSV write failed: [system error]"
                   → do not deliver file · surface error to UI
```

---

### Component 6: Excel Generator

```
Component:       Excel Generator
Layer:           Export
Input:           routed_dataset : {format = EXCEL, records, session_id, row_count}
Transformation:  IF records is non-empty
                   → invoke xlsx skill with generation timeout
                     XLSX_GENERATION_TIMEOUT = configurable (deployment config)
                     recommended default: 120 seconds
                     (L2 P2 #38 — 2026-03-27)
                   → filename: gpu-margin-export-[session_id].xlsx
                   → sheet name: "GPU Margin Allocation"
                   → column order: per EXPORT_COLUMN_ORDER shared constant
                     (see module-level definition — same as CSV Generator)
                   → source_files: JSON array format (same as CSV)
                   → header row: bold · freeze top row
                   → file written to workspace folder
                   → generation_result = SUCCESS
                 IF records is empty → generation_result = FAIL
Output:          excel_file : {
                   result    : enum{SUCCESS, FAIL},
                   filename  : varchar,
                   filepath  : varchar,
                   format    : 'EXCEL',
                   row_count : integer,
                   error     : varchar | NULL
                 }
Feeds:           Output Verifier
Failure path:    IF xlsx skill fails
                   → generation_result = FAIL
                   · error = "Excel generation failed: [skill error]"
                   → do not deliver file · surface error to UI
                 IF xlsx skill does not complete within XLSX_GENERATION_TIMEOUT
                   → generation_result = FAIL
                   · error = "Excel generation timed out.
                              Try CSV export for large datasets."
                   → do not deliver file · surface error to UI
```

---

### Component 7: Power BI Flat CSV Generator

```
Component:       Power BI Flat CSV Generator
Layer:           Export
Input:           routed_dataset : {format = POWER_BI, records, session_id, row_count}
Transformation:  IF records is non-empty
                   → write all records to file using Bash write
                   → filename: gpu-margin-powerbi-[session_id].csv
                   → flat structure: no nested fields · no JSON in any column
                   → source_files column: transform JSON array → pipe-delimited string
                     e.g. file1.csv|file2.csv|file3.csv|file4.csv|file5.csv
                     (no brackets · no quotes · pipes only)
                   → column order: per EXPORT_COLUMN_ORDER shared constant
                     (see module-level definition — source_files last, pipe-delimited)
                   → delimiter: comma · header row included · UTF-8 encoding
                   → file written to workspace folder
                   → generation_result = SUCCESS
                 IF records is empty → generation_result = FAIL
Output:          power_bi_file : {
                   result    : enum{SUCCESS, FAIL},
                   filename  : varchar,
                   filepath  : varchar,
                   format    : 'POWER_BI',
                   row_count : integer,
                   error     : varchar | NULL
                 }
Feeds:           Output Verifier
Failure path:    IF Bash write fails
                   → generation_result = FAIL
                   · error = "Power BI CSV write failed: [system error]"
                   → do not deliver file · surface error to UI
```

---

### Component 8: Output Verifier

```
Component:       Output Verifier
Layer:           Export
Input:           file_output : {result = SUCCESS, filename, filepath,
                                row_count, format}
                 — received from whichever generator produced the file
Transformation:  Run 6 verification checks in sequence:

                 Check 1: File exists in workspace folder at filepath
                          FAIL → "File not found at [filepath]"

                 Check 2: Row count in file matches row_count from
                          Export Source Reader
                          FAIL → "Row count mismatch: expected [n] · found [m]"

                 Check 3: Grain structure confirmed — all columns in
                          EXPORT_COLUMN_ORDER are present in file in the
                          declared order. (See module-level constant.)
                          Minimum grain dimensions required:
                            region · gpu_pool_id · date · allocation_target
                          FAIL → "Column missing or out of order: [name]"
                          (Validates against EXPORT_COLUMN_ORDER — not a
                           hardcoded inline list)

                 Check 4: Failure mode subtypes valid and distinguishable —
                          unallocated_type column present AND all non-null values
                          must be exactly one of: 'capacity_idle' · 'identity_broken'
                          Any non-null value outside this enumeration is invalid.
                          FAIL → "unallocated_type column absent or unpopulated"
                                 OR "Invalid unallocated_type value found: [value]
                                     at row [index]"
                          Note: NULL is a valid value (Type A records).
                          A column that is all-NULL still passes Check 4 as long
                          as the column is present. What fails is a non-null value
                          that is not 'capacity_idle' or 'identity_broken'.
                          This closes the gap between presence validation and
                          contract validation — an upstream regression that writes
                          a new unallocated_type string is caught here before
                          the file reaches the CFO.
                          (L2 P1 #43 — 2026-03-27)

                 Check 5: File is readable — open and parse without error
                          FAIL → "File failed to open or parse: [error]"

                 Check 6: session_id and source_files are last two columns ·
                          values are non-null in all rows · AND format check:
                          IF format = CSV or EXCEL
                            → source_files must be valid JSON array
                              FAIL → "source_files: expected JSON array for [format]"
                          IF format = POWER_BI
                            → source_files must be pipe-delimited string
                              (no brackets · no quotes)
                              FAIL → "source_files: expected pipe-delimited string for Power BI"

                 IF all 6 checks pass → verification_status = PASS
                 IF any check fails   → verification_status = FAIL
                                      · failed_check = [check number + description]

Output:          verification_result : {
                   status        : enum{PASS, FAIL},
                   file          : varchar,
                   format        : varchar,
                   grain         : enum{CONFIRMED, DEVIATION},
                   failure_modes : enum{VISIBLE, GAP_FOUND},
                   export_state  : enum{APPROVED_CONFIRMED, BLOCKED},
                   failed_check  : varchar | NULL
                 }
Feeds:           File Delivery Handler (if PASS) | Generator (if FAIL — re-run)
Failure path:    IF verification_status = FAIL
                   → do not deliver file
                   → surface failed_check to UI
                   → return to generator that produced the file
                   → re-run generator · re-run verification
                   → do not advance to delivery until status = PASS

                 Max re-run limit (L2 P2 #37 — 2026-03-27):
                   MAX_EXPORT_RERUNS = 3 (total attempts including initial)
                   configurable in deployment config
                   IF attempt count reaches MAX_EXPORT_RERUNS without PASS
                     → halt · do not re-run further
                     → surface "Export generation failed after [n] attempts.
                                Contact data team with Session ID: [session_id]
                                and format: [format]."
                     → export is terminal FAIL for this request
```

---

### Component 9: File Delivery Handler

```
Component:       File Delivery Handler
Layer:           Export
Input:           verification_result : {status = PASS, file, filepath, format}
Transformation:  IF verification_result.status = PASS
                   → receive filepath directly from Output Verifier Check 1
                     (atomic filepath handoff — no intermediate move or rename
                      between Verifier Check 1 confirmation and delivery)
                     (L2 P2 #41 — 2026-03-27)
                   → confirm file is present in workspace folder at that filepath
                   → generate computer:// link for analyst access
                   → surface link to UI with label:
                     CSV:      "Download CSV Export"
                     Excel:    "Download Excel Export"
                     Power BI: "Download Power BI Export"
                   → delivery_result = SUCCESS
                 ELSE → do not deliver
Output:          delivery : {
                   result   : enum{SUCCESS, FAIL},
                   filename : varchar,
                   link     : computer:// URI
                 }
Feeds:           UI (analyst receives link)
Failure path:    IF file cannot be confirmed in workspace folder at delivery time
                   → delivery_result = FAIL
                   · error = "File not found in workspace at delivery time"
                   → surface error to UI · do not surface a broken link
```

---

## STEP 4 — Problem-to-Design Analysis

```
Problem:          The CFO approves a margin number — but if export is not
                  gated on server-confirmed state, a file could be generated
                  from a pre-approval run, a partial dataset, or an
                  unapproved table. Additionally, if session metadata is not
                  appended at the record level, no downstream consumer can
                  trace an exported row back to the ingestion run that
                  produced it.

Required output:  Three export files that are structurally identical in
                  content (same approved table, same grain, same row count),
                  format-differentiated in delivery, traceable to their
                  source via session_id and source_files at the record level,
                  and only reachable after server-confirmed APPROVED state
                  and a passing Output Verification.

Design produces:  9 components. APPROVED State Gate queries server-side
                  state before any read occurs. Export Source Reader reads
                  the immutable approved table only. Session Metadata
                  Appender resolves and appends session_id + source_files
                  to every row before any generator runs. Format Router
                  dispatches to exactly one generator per request. Each
                  generator uses the correct tool (xlsx skill for Excel,
                  Bash write for CSV and Power BI). Output Verifier runs
                  6 checks including format-aware source_files validation
                  (Check 6 — S1). File Delivery Handler only surfaces the
                  link after verification passes.

Gap or match:     MATCH. Gap identified in STEP 4 (source_files format
                  mismatch between Power BI and other formats) closed by
                  S1 (format-aware Check 6 in Output Verifier).
```

---

## EXPORT_COLUMN_ORDER — Shared Constant (L2 P1 #39 — 2026-03-27)

Column order for all three export generators and Output Verifier Check 3 is
defined here as a single shared constant. All generators read from this
constant — they do not maintain their own column lists. The Output Verifier
validates against the same constant. A new field addition to
final.allocation_result requires a change here only — not in four separate places.

```
EXPORT_COLUMN_ORDER = [
  region,
  gpu_pool_id,
  date,
  billing_period,
  allocation_target,
  unallocated_type,
  failed_tenant_id,
  gpu_hours,
  cost_per_gpu_hour,
  contracted_rate,
  revenue,
  cogs,
  gross_margin,
  session_id,       ← second-to-last (appended by Session Metadata Appender)
  source_files      ← last (appended by Session Metadata Appender)
]
```

Any generator that produces a file in a column order other than EXPORT_COLUMN_ORDER
is non-conformant. Output Verifier Check 3 validates column presence against this
constant. Check 6 separately validates the position of the last two columns.

---

## Component Summary

| # | Component | Layer | Tool | Feeds |
|---|-----------|-------|------|-------|
| 1 | APPROVED State Gate | Export | — | Export Source Reader / UI Error |
| 2 | Export Source Reader | Export | — | Session Metadata Appender |
| 3 | Session Metadata Appender | Export | — | Format Router |
| 4 | Format Router | Export | — | CSV / Excel / Power BI Generator |
| 5 | CSV Generator | Export | Bash write | Output Verifier |
| 6 | Excel Generator | Export | xlsx skill | Output Verifier |
| 7 | Power BI Flat CSV Generator | Export | Bash write | Output Verifier |
| 8 | Output Verifier | Export | — | File Delivery Handler / Generator |
| 9 | File Delivery Handler | Export | computer:// | UI (analyst) |
