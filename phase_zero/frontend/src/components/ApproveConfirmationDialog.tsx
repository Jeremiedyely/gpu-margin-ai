/**
 * Approve Confirmation Dialog — Component 14/14.
 *
 * Modal confirmation before ANALYZED → APPROVED transition.
 * Includes session_id in the dialog (P3 #35).
 * On confirm → sends transition request to backend.
 */

import { useState } from "react";

interface ApproveDialogProps {
  sessionId: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ApproveConfirmationDialog({
  sessionId,
  onConfirm,
  onCancel,
}: ApproveDialogProps) {
  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      data-testid="approve-dialog-overlay"
    >
      <div
        className="bg-white rounded-lg shadow-xl p-6 max-w-md w-full mx-4"
        data-testid="approve-dialog"
      >
        <h2 className="text-xl font-bold text-gray-800 mb-4">
          Approve Gross Margin Results
        </h2>
        <p className="text-gray-600 mb-2">
          This action is final. Once approved, results are locked and cannot be
          changed.
        </p>
        <p className="text-sm text-gray-400 mb-6" data-testid="dialog-session-id">
          Session ID: {sessionId}
        </p>
        <div className="flex gap-3 justify-end">
          <button
            className="px-4 py-2 border border-gray-300 rounded-lg text-gray-600 hover:bg-gray-50"
            onClick={onCancel}
            data-testid="cancel-button"
          >
            Cancel
          </button>
          <button
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-semibold"
            onClick={onConfirm}
            data-testid="confirm-approve-button"
          >
            Confirm Approval
          </button>
        </div>
      </div>
    </div>
  );
}
