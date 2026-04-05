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
      <div className="bg-white rounded-lg shadow p-6" data-testid="zone3">
        <p className="text-gray-400">Loading reconciliation...</p>
      </div>
    );
  }

  const isUnavailable = isError || !data || data.length < 3;
  const hasFail = data?.some((r) => r.verdict === "FAIL") ?? false;

  return (
    <div className="bg-white rounded-lg shadow p-6" data-testid="zone3">
      <h3 className="text-lg font-semibold text-gray-700 mb-4">
        Reconciliation
      </h3>

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-gray-500">
            <th className="pb-2">Check</th>
            <th className="pb-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {isUnavailable ? (
            <>
              {["Capacity vs Usage", "Usage vs Tenant Mapping", "Computed vs Billed vs Posted"].map(
                (name) => (
                  <tr key={name} className="border-b">
                    <td className="py-2">{name}</td>
                    <td className="py-2 text-gray-400" data-testid="verdict-unavailable">
                      Data unavailable
                    </td>
                  </tr>
                )
              )}
            </>
          ) : (
            data.map((r) => (
              <tr key={r.check} className="border-b" data-testid={`recon-row-${r.check}`}>
                <td className="py-2">{r.check}</td>
                <td className="py-2">
                  <span
                    className={`px-2 py-1 rounded text-xs font-semibold ${
                      r.verdict === "PASS"
                        ? "bg-green-100 text-green-700"
                        : "bg-red-100 text-red-700"
                    }`}
                    data-testid="verdict-badge"
                    data-verdict={r.verdict}
                  >
                    {r.verdict}
                  </span>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      {/* Escalation note for FAIL */}
      {hasFail && (
        <div
          className="mt-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700"
          data-testid="escalation-note"
        >
          One or more reconciliation checks failed. Contact your data team
          {sessionId ? ` with Session ID: ${sessionId}` : ""} to investigate the
          root cause.
        </div>
      )}
    </div>
  );
}
