/**
 * API response types — mirrors FastAPI Pydantic models.
 *
 * These types are the contract between the Python backend and the React frontend.
 * Any change to api_routes.py response models must be reflected here.
 */

// ── State ──────────────────────────────────────────────────────────

export type ApplicationState = "EMPTY" | "UPLOADED" | "ANALYZED" | "APPROVED";
export type AnalysisStatus = "IDLE" | "ANALYZING" | null;

export interface StateResponse {
  session_id: string | null;
  application_state: ApplicationState | null;
  analysis_status: AnalysisStatus;
}

// ── View routing ───────────────────────────────────────────────────

export type ActiveView = "VIEW_1" | "VIEW_2" | "ERROR";

// ── KPI (Zone 1) ──────────────────────────────────────────────────

export interface KPIResponse {
  gpu_revenue: string;
  gpu_cogs: string;
  idle_gpu_cost: string;
  idle_gpu_cost_pct: string;
  cost_allocation_rate: string;
}

// ── Customers (Zone 2R) ────────────────────────────────────────────

export type GmColor = "red" | "orange" | "yellow" | "green";
export type RiskFlag = "FLAG" | "CLEAR";

export interface CustomerRecord {
  allocation_target: string;
  gm_pct: string | null;
  gm_color: GmColor | null;
  revenue: string;
  risk_flag: RiskFlag;
}

export interface CustomerResponse {
  payload: CustomerRecord[];
  identity_broken_tenants: string[];
}

// ── Regions (Zone 2L) ──────────────────────────────────────────────

export type RegionStatus = "HOLDING" | "AT RISK";

export interface RegionRecord {
  region: string;
  gm_pct: string | null;
  idle_pct: string;
  revenue: string;
  status: RegionStatus;
  identity_broken_count: number;
  capacity_idle_count: number;
}

export interface RegionResponse {
  payload: RegionRecord[];
}

// ── Reconciliation (Zone 3) ────────────────────────────────────────

export type Verdict = "PASS" | "FAIL";

export interface VerdictRecord {
  check: string;
  verdict: Verdict;
}

export interface ReconciliationResponse {
  payload: VerdictRecord[];
  session_id: string;
}

// ── Footer controls ────────────────────────────────────────────────

export type AnalyzeControl = "ACTIVE" | "LOCKED" | "ANALYZING";
export type ApproveControl = "ACTIVE" | "DEACTIVATED";
export type ExportControl = "ACTIVE" | "LOCKED";

export interface View1FooterState {
  analyze_control: AnalyzeControl;
}

export interface View2FooterState {
  approve_control: ApproveControl;
  csv_control: ExportControl;
  excel_control: ExportControl;
  power_bi_control: ExportControl;
}
