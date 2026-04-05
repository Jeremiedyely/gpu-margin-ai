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

import { useState, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { AnalysisStatus, AnalyzeControl } from "@/types/api";
import { AppHeader } from "./AppHeader";
import { ProgressStepper } from "./ProgressStepper";

interface View1Props {
  applicationState: "EMPTY" | "UPLOADED";
  analysisStatus: AnalysisStatus;
  sessionId: string | null;
}

const SLOT_LABELS = [
  "Telemetry & Metering",
  "Cost Management / FinOps",
  "IAM / Tenant Management",
  "Billing System",
  "ERP / General Ledger",
] as const;

const SLOT_KEYS = [
  "telemetry",
  "cost_management",
  "iam",
  "billing",
  "erp",
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
  sessionId: serverSessionId,
}: View1Props) {
  const queryClient = useQueryClient();
  const analyzeControl = deriveAnalyzeControl(applicationState, analysisStatus);
  const isFilled = applicationState === "UPLOADED";
  const isAnalyzing = analyzeControl === "ANALYZING";

  // File upload state
  const [files, setFiles] = useState<Record<string, File | null>>({
    telemetry: null,
    cost_management: null,
    iam: null,
    billing: null,
    erp: null,
  });
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [localSessionId, setLocalSessionId] = useState<string | null>(null);
  const sessionId = serverSessionId ?? localSessionId;
  const fileInputRefs = useRef<Record<string, HTMLInputElement | null>>({});

  const allFilesSelected = SLOT_KEYS.every((key) => files[key] !== null);

  const handleFileChange = (slot: string, file: File | null) => {
    setFiles((prev) => ({ ...prev, [slot]: file }));
    setUploadError(null);
  };

  const handleUpload = async () => {
    if (!allFilesSelected) return;
    setUploading(true);
    setUploadError(null);

    try {
      const formData = new FormData();
      for (const key of SLOT_KEYS) {
        formData.append(key, files[key]!);
      }

      const res = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        const detail = body?.detail;
        let message: string;
        if (typeof detail === "string") {
          message = detail;
        } else if (detail?.errors && Array.isArray(detail.errors)) {
          message = detail.errors.join("; ");
        } else if (detail) {
          message = JSON.stringify(detail);
        } else {
          message = `Upload failed: ${res.status}`;
        }
        throw new Error(message);
      }

      const data = await res.json();
      setLocalSessionId(data.session_id);
      queryClient.invalidateQueries({ queryKey: ["appState"] });
    } catch (err: any) {
      setUploadError(err.message || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleAnalyze = async () => {
    if (analyzeControl !== "ACTIVE") return;

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        const detail = body?.detail;
        let message: string;
        if (typeof detail === "string") {
          message = detail;
        } else if (detail?.errors && Array.isArray(detail.errors)) {
          message = detail.errors.join("; ");
        } else if (detail) {
          message = JSON.stringify(detail);
        } else {
          message = `Analyze failed: ${res.status}`;
        }
        throw new Error(message);
      }

      queryClient.invalidateQueries({ queryKey: ["appState"] });
    } catch (err: any) {
      setUploadError(err.message || "Analysis dispatch failed");
    }
  };

  const currentStep = isAnalyzing ? 2 : isFilled ? 2 : 1;

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader sessionId={isFilled ? sessionId : undefined} />

      <div className="max-w-5xl mx-auto px-10 py-7">
        <ProgressStepper currentStep={currentStep as 1 | 2} />

        {/* Analyzing state */}
        {isAnalyzing ? (
          <div className="bg-white rounded-2xl shadow-md border border-slate-100 max-w-xl mx-auto overflow-hidden">
            <div className="p-10 text-center">
              <div className="gpu-spinner mx-auto mb-5" />
              <div className="text-lg font-semibold text-slate-800 mb-1">
                Analysis in Progress
              </div>
              <div className="text-sm text-slate-400 mb-6">
                Running Allocation Engine &amp; Reconciliation Engine
              </div>
              <div>
                <span className="gpu-pulse-dot" />
                <span className="gpu-pulse-dot" />
                <span className="gpu-pulse-dot" />
              </div>
            </div>
          </div>
        ) : (
          /* Upload card */
          <div className="bg-white rounded-2xl shadow-md border border-slate-100 max-w-3xl mx-auto overflow-hidden">
            <div className="p-8">
              {/* Upload zone */}
              {!isFilled && (
                <div className="border-2 border-dashed border-slate-300 rounded-2xl p-10 text-center bg-slate-50/50 hover:border-blue-400 hover:bg-blue-50/40 transition-all cursor-pointer mb-6">
                  <div className="w-16 h-16 mx-auto mb-4 bg-blue-50 rounded-full flex items-center justify-center">
                    <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="#3b82f6">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5"/>
                    </svg>
                  </div>
                  <div className="text-lg font-semibold text-slate-800 mb-1">Upload Source Files</div>
                  <div className="text-sm text-slate-400">Select all 5 CSV files to begin analysis</div>
                </div>
              )}

              {/* File slots */}
              <div className="space-y-3 mb-6">
                {SLOT_LABELS.map((label, i) => (
                  <div
                    key={label}
                    className={`flex items-center px-4 py-3 rounded-xl border transition-all ${
                      isFilled || files[SLOT_KEYS[i]]
                        ? "border-emerald-200 bg-emerald-50/60"
                        : "border-slate-200 bg-white hover:border-slate-300"
                    }`}
                    data-testid={`upload-slot-${i + 1}`}
                  >
                    <span className="text-slate-400 w-7 text-sm font-medium">{i + 1}.</span>
                    <span className="font-medium text-slate-700 flex-1 text-sm">{label}</span>

                    {isFilled || files[SLOT_KEYS[i]] ? (
                      <div className="flex items-center gap-2">
                        {files[SLOT_KEYS[i]] && (
                          <span className="text-xs text-emerald-600 font-medium">
                            {files[SLOT_KEYS[i]]!.name}
                          </span>
                        )}
                        <span
                          className="w-6 h-6 bg-emerald-500 rounded-full flex items-center justify-center text-white text-xs"
                          data-testid={`slot-check-${i + 1}`}
                        >
                          ✓
                        </span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2">
                        <input
                          type="file"
                          accept=".csv"
                          className="hidden"
                          ref={(el) => { fileInputRefs.current[SLOT_KEYS[i]] = el; }}
                          onChange={(e) =>
                            handleFileChange(
                              SLOT_KEYS[i],
                              e.target.files?.[0] || null
                            )
                          }
                        />
                        <button
                          className="px-3 py-1.5 text-xs font-medium bg-blue-50 text-blue-600 rounded-lg border border-blue-200 hover:bg-blue-100 transition-colors"
                          onClick={() =>
                            fileInputRefs.current[SLOT_KEYS[i]]?.click()
                          }
                        >
                          Choose CSV
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* Error message */}
              {uploadError && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm flex items-start gap-2">
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor" className="flex-shrink-0 mt-0.5">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z"/>
                  </svg>
                  <span>{uploadError}</span>
                </div>
              )}

              {/* Action buttons */}
              <div className="border-t border-slate-100 pt-5 flex gap-3" data-testid="view1-footer">
                {!isFilled && (
                  <button
                    className={`px-6 py-2.5 rounded-xl font-semibold text-white text-sm transition-all ${
                      allFilesSelected && !uploading
                        ? "bg-emerald-500 hover:bg-emerald-600 hover:-translate-y-0.5 shadow-md"
                        : "bg-slate-300 cursor-not-allowed"
                    }`}
                    disabled={!allFilesSelected || uploading}
                    onClick={handleUpload}
                  >
                    {uploading ? "Uploading..." : "Upload All Files"}
                  </button>
                )}

                {isFilled && (
                  <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-700 text-sm flex items-center gap-2 mr-3">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5"/></svg>
                    <strong>5 files uploaded.</strong> Ready to analyze.
                  </div>
                )}

                <button
                  className={`px-6 py-2.5 rounded-xl font-semibold text-white text-sm transition-all ${
                    analyzeControl === "ACTIVE"
                      ? "bg-blue-500 hover:bg-blue-600 hover:-translate-y-0.5 shadow-md"
                      : "bg-slate-300 cursor-not-allowed"
                  }`}
                  disabled={analyzeControl !== "ACTIVE"}
                  onClick={handleAnalyze}
                  data-testid="analyze-button"
                  data-control={analyzeControl}
                >
                  Run Analysis
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Export for testing
export { deriveAnalyzeControl, SLOT_LABELS };
