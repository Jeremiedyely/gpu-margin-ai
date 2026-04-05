/**
 * View 2 Footer Control Manager — Component 13/14.
 *
 * Approve button gated on state = ANALYZED.
 * Export buttons gated on state = APPROVED.
 * Server-state render invariant — all states from server, never local.
 */

import { useState } from "react";
import type { ApproveControl, ExportControl, View2FooterState } from "@/types/api";
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

export function View2FooterControlManager({
  applicationState,
  sessionId,
}: View2FooterProps) {
  const [showDialog, setShowDialog] = useState(false);
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

  return (
    <>
      <div
        className="border-t pt-6 flex gap-4 items-center"
        data-testid="view2-footer"
      >
        {/* Approve button */}
        <button
          className={`px-6 py-3 rounded-lg font-semibold text-white ${
            footer.approve_control === "ACTIVE"
              ? "bg-blue-600 hover:bg-blue-700 cursor-pointer"
              : "bg-gray-300 cursor-not-allowed"
          }`}
          disabled={footer.approve_control !== "ACTIVE"}
          onClick={handleApproveClick}
          data-testid="approve-button"
          data-control={footer.approve_control}
        >
          {footer.approve_control === "DEACTIVATED" ? "Approved" : "Approve"}
        </button>

        <div className="border-l h-8 mx-2" />

        {/* Export buttons */}
        {(["csv_control", "excel_control", "power_bi_control"] as const).map(
          (key) => {
            const label = key === "csv_control" ? "CSV" : key === "excel_control" ? "Excel" : "Power BI";
            const isActive = footer[key] === "ACTIVE";
            return (
              <button
                key={key}
                className={`px-4 py-2 rounded-lg text-sm font-medium ${
                  isActive
                    ? "bg-green-600 text-white hover:bg-green-700 cursor-pointer"
                    : "bg-gray-200 text-gray-400 cursor-not-allowed"
                }`}
                disabled={!isActive}
                data-testid={`export-${label.toLowerCase().replace(" ", "-")}`}
                data-control={footer[key]}
              >
                Export {label}
              </button>
            );
          }
        )}
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
