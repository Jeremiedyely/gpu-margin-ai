/**
 * View 2 Footer Control Manager — Component 13/14.
 *
 * Approve button gated on state = ANALYZED.
 * Export buttons gated on state = APPROVED.
 * Server-state render invariant — all states from server, never local.
 */

import { useState } from "react";
import type { View2FooterState } from "@/types/api";
import { ApproveConfirmationDialog } from "./ApproveConfirmationDialog";

interface View2FooterProps {
  applicationState: "ANALYZED" | "APPROVED";
  sessionId: string;
}

function deriveFooterState(appState: "ANALYZED" | "APPROVED"): View2FooterState {
  if (appState === "ANALYZED") {
    return {
      approve_control: "ACTIVE",
      csv_control: "LOCKED",
      excel_control: "LOCKED",
      power_bi_control: "LOCKED",
    };
  }
  // APPROVED
  return {
    approve_control: "DEACTIVATED",
    csv_control: "ACTIVE",
    excel_control: "ACTIVE",
    power_bi_control: "ACTIVE",
  };
}

const ExportIcon = (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
  </svg>
);

export function View2FooterControlManager({
  applicationState,
  sessionId,
}: View2FooterProps) {
  const [showDialog, setShowDialog] = useState(false);
  const [exporting, setExporting] = useState<string | null>(null);
  const [closing, setClosing] = useState(false);
  const footer = deriveFooterState(applicationState);

  const handleApproveClick = () => {
    if (footer.approve_control === "ACTIVE") {
      setShowDialog(true);
    }
  };

  const handleConfirm = async () => {
    try {
      // Fire ANALYZED → APPROVED transition
      await fetch("/api/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          requested_transition: "ANALYZED→APPROVED",
        }),
      });
    } finally {
      setShowDialog(false);
    }
  };

  const handleExport = async (format: "csv" | "excel" | "power_bi") => {
    setExporting(format);
    try {
      const res = await fetch(`/api/export/${sessionId}/${format}`);
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        const detail = body?.detail;
        const message = typeof detail === "string" ? detail : JSON.stringify(detail) || `Export failed: ${res.status}`;
        alert(message);
        return;
      }
      // Trigger browser download
      const blob = await res.blob();
      const disposition = res.headers.get("Content-Disposition") || "";
      const filenameMatch = disposition.match(/filename="?([^"]+)"?/);
      const filename = filenameMatch?.[1] || `gpu_margin_export.${format === "excel" ? "xlsx" : format === "power_bi" ? "txt" : "csv"}`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(`Export error: ${err}`);
    } finally {
      setExporting(null);
    }
  };

  return (
    <>
      <div
        className="bg-white rounded-2xl shadow-md border border-slate-100 p-5"
        data-testid="view2-footer"
      >
        <div className="flex gap-3 items-center flex-wrap">
          {/* Approve button */}
          <button
            className={`px-6 py-2.5 rounded-xl font-semibold text-sm text-white transition-all ${
              footer.approve_control === "ACTIVE"
                ? "bg-blue-500 hover:bg-blue-600 hover:-translate-y-0.5 shadow-md cursor-pointer"
                : footer.approve_control === "DEACTIVATED"
                  ? "bg-emerald-500 cursor-default"
                  : "bg-slate-300 cursor-not-allowed"
            }`}
            disabled={footer.approve_control !== "ACTIVE"}
            onClick={handleApproveClick}
            data-testid="approve-button"
            data-control={footer.approve_control}
          >
            {footer.approve_control === "DEACTIVATED" ? (
              <span className="flex items-center gap-1.5">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth="2.5" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                </svg>
                Approved
              </span>
            ) : "Approve"}
          </button>

          <div className="w-px h-8 bg-slate-200 mx-1" />

          {/* New Session button — only when APPROVED */}
          {applicationState === "APPROVED" && (
            <>
              <button
                className={`px-5 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                  closing
                    ? "bg-slate-200 text-slate-400 cursor-not-allowed"
                    : "bg-indigo-500 text-white hover:bg-indigo-600 hover:-translate-y-0.5 shadow-md cursor-pointer"
                }`}
                disabled={closing}
                onClick={async () => {
                  setClosing(true);
                  try {
                    await fetch("/api/session/close", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ session_id: sessionId }),
                    });
                  } catch (err) {
                    alert(`Close failed: ${err}`);
                  } finally {
                    setClosing(false);
                  }
                }}
                data-testid="new-session-button"
              >
                {closing ? "Closing..." : (
                  <span className="flex items-center gap-1.5">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                    </svg>
                    New Session
                  </span>
                )}
              </button>
              <div className="w-px h-8 bg-slate-200 mx-1" />
            </>
          )}

          {/* Export buttons */}
          {(["csv_control", "excel_control", "power_bi_control"] as const).map(
            (key) => {
              const label = key === "csv_control" ? "CSV" : key === "excel_control" ? "Excel" : "Power BI";
              const format = key === "csv_control" ? "csv" : key === "excel_control" ? "excel" : "power_bi";
              const isActive = footer[key] === "ACTIVE";
              const isExporting = exporting === format;
              return (
                <button
                  key={key}
                  className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                    isActive && !isExporting
                      ? "bg-emerald-500 text-white hover:bg-emerald-600 hover:-translate-y-0.5 shadow-md cursor-pointer"
                      : "bg-slate-200 text-slate-400 cursor-not-allowed"
                  }`}
                  disabled={!isActive || isExporting}
                  onClick={() => handleExport(format as "csv" | "excel" | "power_bi")}
                  data-testid={`export-${label.toLowerCase().replace(" ", "-")}`}
                  data-control={footer[key]}
                >
                  {isExporting ? "Exporting..." : (
                    <span className="flex items-center gap-1.5">
                      {ExportIcon}
                      {label}
                    </span>
                  )}
                </button>
              );
            }
          )}
        </div>
      </div>

      {showDialog && (
        <ApproveConfirmationDialog
          sessionId={sessionId}
          onConfirm={handleConfirm}
          onCancel={() => setShowDialog(false)}
        />
      )}
    </>
  );
}

// Export for testing
export { deriveFooterState };
