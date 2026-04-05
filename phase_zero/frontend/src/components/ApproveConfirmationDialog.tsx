/**
 * Approve Confirmation Dialog — Component 14/14.
 *
 * Modal confirmation before ANALYZED → APPROVED transition.
 * Includes session_id in the dialog (P3 #35).
 * On confirm → sends transition request to backend.
 */

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
      className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50"
      data-testid="approve-dialog-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl p-7 max-w-md w-full mx-4 border border-slate-100"
        data-testid="approve-dialog"
      >
        {/* Icon */}
        <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center mb-4">
          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="#3b82f6">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
          </svg>
        </div>

        <h2 className="text-xl font-bold text-slate-800 mb-2">
          Approve Gross Margin Results
        </h2>
        <p className="text-sm text-slate-500 mb-2 leading-relaxed">
          This action is final. Once approved, results are locked and cannot be
          changed. Export options will become available.
        </p>
        <p
          className="text-xs text-slate-400 mb-6 font-mono bg-slate-50 px-3 py-1.5 rounded-lg inline-block"
          data-testid="dialog-session-id"
        >
          Session: {sessionId}
        </p>

        <div className="flex gap-3 justify-end">
          <button
            className="px-5 py-2.5 border border-slate-200 rounded-xl text-slate-600 hover:bg-slate-50 text-sm font-medium transition-colors"
            onClick={onCancel}
            data-testid="cancel-button"
          >
            Cancel
          </button>
          <button
            className="px-5 py-2.5 bg-blue-500 text-white rounded-xl hover:bg-blue-600 hover:-translate-y-0.5 shadow-md font-semibold text-sm transition-all"
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
