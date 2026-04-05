/**
 * View 1 Renderer — Component 3/14 (Import View).
 *
 * Renders five upload slots + [Analyze] control.
 * Includes View 1 Footer Control Manager logic (Component 2/14).
 *
 * Footer control logic:
 *   EMPTY                              → LOCKED
 *   UPLOADED + analysis_status = IDLE  → ACTIVE
 *   UPLOADED + analysis_status = ANALYZING → ANALYZING (locked + label)
 *   else                               → LOCKED
 */

import type { AnalysisStatus, AnalyzeControl } from "@/types/api";

interface View1Props {
  applicationState: "EMPTY" | "UPLOADED";
  analysisStatus: AnalysisStatus;
}

const SLOT_LABELS = [
  "Telemetry & Metering",
  "Cost Management / FinOps",
  "IAM / Tenant Management",
  "Billing System",
  "ERP / General Ledger",
] as const;

function deriveAnalyzeControl(
  appState: "EMPTY" | "UPLOADED",
  analysisStatus: AnalysisStatus
): AnalyzeControl {
  if (appState === "EMPTY") return "LOCKED";
  if (appState === "UPLOADED" && analysisStatus === "IDLE") return "ACTIVE";
  if (appState === "UPLOADED" && analysisStatus === "ANALYZING")
    return "ANALYZING";
  return "LOCKED";
}

export function View1Renderer({
  applicationState,
  analysisStatus,
}: View1Props) {
  const analyzeControl = deriveAnalyzeControl(applicationState, analysisStatus);
  const isFilled = applicationState === "UPLOADED";

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <h1 className="text-2xl font-bold text-gray-800 mb-8">
        GPU Gross Margin Visibility
      </h1>

      {/* Upload Slots */}
      <div className="space-y-4 mb-8">
        {SLOT_LABELS.map((label, i) => (
          <div
            key={label}
            className={`flex items-center p-4 rounded-lg border ${
              isFilled
                ? "border-green-300 bg-green-50"
                : "border-gray-300 bg-white"
            }`}
            data-testid={`upload-slot-${i + 1}`}
          >
            <span className="text-gray-600 w-8">{i + 1}.</span>
            <span className="font-medium text-gray-700">{label}</span>
            {isFilled && (
              <span
                className="ml-auto text-green-600"
                data-testid={`slot-check-${i + 1}`}
              >
                ✓
              </span>
            )}
          </div>
        ))}
      </div>

      {/* Footer — Analyze Button */}
      <div className="border-t pt-6" data-testid="view1-footer">
        <button
          className={`px-6 py-3 rounded-lg font-semibold text-white ${
            analyzeControl === "ACTIVE"
              ? "bg-blue-600 hover:bg-blue-700 cursor-pointer"
              : "bg-gray-400 cursor-not-allowed"
          }`}
          disabled={analyzeControl !== "ACTIVE"}
          data-testid="analyze-button"
          data-control={analyzeControl}
        >
          {analyzeControl === "ANALYZING"
            ? "Analysis in progress..."
            : "Analyze"}
        </button>
      </div>
    </div>
  );
}

// Export for testing
export { deriveAnalyzeControl, SLOT_LABELS };
