/**
 * Zone 2L Region Renderer — Component 8/14.
 *
 * Ranked table by GM% descending, NULL last.
 * Status: HOLDING (neutral) | AT RISK (red).
 * Subtype pills: identity_broken (red) | capacity_idle (orange).
 */

import type { RegionRecord } from "@/types/api";

interface Zone2LProps {
  data: RegionRecord[] | undefined;
  isLoading: boolean;
}

function gmBarClass(gmPct: string | null): string {
  if (gmPct === null) return "bg-slate-200";
  const pct = parseFloat(gmPct);
  if (pct < 0) return "gm-bar-red";
  if (pct < 30) return "gm-bar-orange";
  if (pct < 38) return "gm-bar-yellow";
  return "gm-bar-green";
}

export function Zone2LRegionRenderer({ data, isLoading }: Zone2LProps) {
  if (isLoading) {
    return (
      <div className="bg-white rounded-2xl shadow-md border border-slate-100 p-6" data-testid="zone2l">
        <p className="sr-only">Loading regions...</p>
        <div className="h-5 bg-slate-200 rounded w-48 mb-5 animate-pulse" />
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-10 bg-slate-100 rounded-xl animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="bg-white rounded-2xl shadow-md border border-slate-100 p-6" data-testid="zone2l">
        <h3 className="text-base font-bold text-slate-800 mb-4">
          Gross Margin by Region
        </h3>
        <p className="text-sm text-slate-400">No region data available</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-md border border-slate-100 p-6" data-testid="zone2l">
      <h3 className="text-base font-bold text-slate-800 mb-4">
        Gross Margin by Region
      </h3>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100 text-left">
              <th className="pb-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">Region</th>
              <th className="pb-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">GM%</th>
              <th className="pb-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">Idle%</th>
              <th className="pb-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">Revenue</th>
              <th className="pb-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">Status</th>
            </tr>
          </thead>
          <tbody>
            {data.map((r) => {
              const pct = r.gm_pct !== null ? parseFloat(r.gm_pct) : null;
              const barWidth = pct !== null ? Math.max(5, Math.min(100, Math.abs(pct))) : 0;

              return (
                <tr
                  key={r.region}
                  className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors"
                  data-testid={`region-row-${r.region}`}
                >
                  <td className="py-3 font-medium text-slate-700">{r.region}</td>
                  <td className="py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-20 h-2.5 bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${gmBarClass(r.gm_pct)}`}
                          style={{ width: `${barWidth}%` }}
                        />
                      </div>
                      <span className="text-xs font-medium text-slate-600">
                        {r.gm_pct !== null ? `${parseFloat(r.gm_pct).toFixed(1)}%` : "—"}
                      </span>
                    </div>
                  </td>
                  <td className="py-3 text-slate-500">{r.idle_pct}%</td>
                  <td className="py-3 text-slate-700 font-medium">
                    ${parseFloat(r.revenue).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                  </td>
                  <td className="py-3">
                    <span
                      className={`px-2.5 py-1 rounded-full text-xs font-semibold ${
                        r.status === "AT RISK"
                          ? "bg-red-50 text-red-600 border border-red-200"
                          : "bg-slate-100 text-slate-500 border border-slate-200"
                      }`}
                      data-testid="region-status"
                    >
                      {r.status}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Subtype pills */}
      <div className="mt-4 flex gap-2 flex-wrap">
        {data.some((r) => r.identity_broken_count > 0) && (
          <span
            className="px-3 py-1.5 bg-red-50 text-red-600 border border-red-200 rounded-full text-xs font-semibold flex items-center gap-1.5"
            data-testid="pill-identity-broken"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126Z" />
            </svg>
            Identity Broken
          </span>
        )}
        {data.some((r) => r.capacity_idle_count > 0) && (
          <span
            className="px-3 py-1.5 bg-orange-50 text-orange-600 border border-orange-200 rounded-full text-xs font-semibold flex items-center gap-1.5"
            data-testid="pill-capacity-idle"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
            Capacity Idle
          </span>
        )}
      </div>
    </div>
  );
}
