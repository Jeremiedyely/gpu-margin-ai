/**
 * Zone 3 Reconciliation Renderer — Component 11/14.
 *
 * PASS/FAIL verdicts only — no drill-down.
 * If any FAIL → escalation note with session_id.
 */

import type { VerdictRecord } from "@/types/api";

interface Zone3Props {
  data: VerdictRecord[] | undefined;
  sessionId: string | null;
  isLoading: boolean;
  isError: boolean;
}

export function Zone3ReconciliationRenderer({
  data,
  sessionId,
  isLoading,
  isError,
}: Zone3Props) {
  if (isLoading) {
    return (
      <div className="bg-white rounded-2xl shadow-md border border-slate-100 p-6" data-testid="zone3">
        <div className="h-5 bg-slate-200 rounded w-40 mb-5 animate-pulse" />
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-10 bg-slate-100 rounded-xl animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  const isUnavailable = isError || !data || data.length < 3;
  const hasFail = data?.some((r) => r.verdict === "FAIL") ?? false;
  const allPass = data?.every((r) => r.verdict === "PASS") ?? false;

  return (
    <div className="bg-white rounded-2xl shadow-md border border-slate-100 p-6" data-testid="zone3">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-bold text-slate-800">
          Reconciliation
        </h3>
        {!isUnavailable && (
          <span
            className={`px-3 py-1 rounded-full text-xs font-semibold ${
              allPass
                ? "bg-emerald-50 text-emerald-600 border border-emerald-200"
                : "bg-red-50 text-red-600 border border-red-200"
            }`}
          >
            {allPass ? "All Checks Passed" : "Issues Detected"}
          </span>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100 text-left">
              <th className="pb-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">Check</th>
              <th className="pb-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">Status</th>
            </tr>
          </thead>
          <tbody>
            {isUnavailable ? (
              <>
                {["Capacity vs Usage", "Usage vs Tenant Mapping", "Computed vs Billed vs Posted"].map(
                  (name) => (
                    <tr key={name} className="border-b border-slate-50">
                      <td className="py-3 text-slate-600">{name}</td>
                      <td className="py-3 text-slate-400 text-xs" data-testid="verdict-unavailable">
                        Data unavailable
                      </td>
                    </tr>
                  )
                )}
              </>
            ) : (
              data.map((r) => (
                <tr
                  key={r.check}
                  className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors"
                  data-testid={`recon-row-${r.check}`}
                >
                  <td className="py-3 text-slate-700 font-medium">{r.check}</td>
                  <td className="py-3">
                    <span
                      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${
                        r.verdict === "PASS"
                          ? "bg-emerald-50 text-emerald-600 border border-emerald-200"
                          : "bg-red-50 text-red-600 border border-red-200"
                      }`}
                      data-testid="verdict-badge"
                      data-verdict={r.verdict}
                    >
                      {r.verdict === "PASS" ? (
                        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="none" viewBox="0 0 24 24" strokeWidth="2.5" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                        </svg>
                      ) : (
                        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="none" viewBox="0 0 24 24" strokeWidth="2.5" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                        </svg>
                      )}
                      {r.verdict}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Escalation alert for FAIL */}
      {hasFail && (
        <div
          className="mt-4 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700 flex items-start gap-3"
          data-testid="escalation-note"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor" className="flex-shrink-0 mt-0.5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126Z" />
          </svg>
          <div>
            <strong>Reconciliation Failed</strong>
            <p className="mt-1 text-red-600">
              One or more reconciliation checks failed. Contact your data team
              {sessionId ? ` with Session ID: ${sessionId}` : ""} to investigate the
              root cause.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
