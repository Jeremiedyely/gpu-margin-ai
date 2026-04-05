/**
 * Zone 2R Customer Renderer — Component 9/14.
 *
 * 4-tier GM% bar: red (<0%) · orange (0–29%) · yellow (30–37%) · green (≥38%).
 * Risk flag: FLAG (red) | CLEAR (no indicator).
 * Ranked by GM% descending, NULL last.
 */

import type { CustomerRecord, GmColor } from "@/types/api";

interface Zone2RProps {
  data: CustomerRecord[] | undefined;
  isLoading: boolean;
}

const GM_BAR_CLASSES: Record<GmColor, string> = {
  red: "gm-bar-red",
  orange: "gm-bar-orange",
  yellow: "gm-bar-yellow",
  green: "gm-bar-green",
};

function GMBar({ gmPct, gmColor }: { gmPct: string | null; gmColor: GmColor | null }) {
  if (gmPct === null || gmColor === null) {
    return (
      <div className="flex items-center gap-2">
        <div className="w-24 h-2.5 bg-slate-100 rounded-full" />
        <span className="text-slate-400 text-xs">—</span>
      </div>
    );
  }

  const pct = parseFloat(gmPct);
  const barWidth = Math.max(5, Math.min(100, Math.abs(pct)));

  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-2.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${GM_BAR_CLASSES[gmColor]}`}
          style={{ width: `${barWidth}%` }}
          data-testid="gm-bar"
          data-color={gmColor}
        />
      </div>
      <span className="text-xs font-medium text-slate-600">{pct.toFixed(2)}%</span>
    </div>
  );
}

export function Zone2RCustomerRenderer({ data, isLoading }: Zone2RProps) {
  if (isLoading) {
    return (
      <div className="bg-white rounded-2xl shadow-md border border-slate-100 p-6" data-testid="zone2r">
        <p className="sr-only">Loading customers...</p>
        <div className="h-5 bg-slate-200 rounded w-52 mb-5 animate-pulse" />
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
      <div className="bg-white rounded-2xl shadow-md border border-slate-100 p-6" data-testid="zone2r">
        <h3 className="text-base font-bold text-slate-800 mb-4">
          Gross Margin by Customer
        </h3>
        <p className="text-sm text-slate-400">No customer data available</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-md border border-slate-100 p-6" data-testid="zone2r">
      <h3 className="text-base font-bold text-slate-800 mb-4">
        Gross Margin by Customer
      </h3>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100 text-left">
              <th className="pb-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">Customer</th>
              <th className="pb-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">GM%</th>
              <th className="pb-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">Revenue</th>
              <th className="pb-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">Risk</th>
            </tr>
          </thead>
          <tbody>
            {data.map((c) => (
              <tr
                key={c.allocation_target}
                className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors"
                data-testid={`customer-row-${c.allocation_target}`}
              >
                <td className="py-3 font-medium text-slate-700">{c.allocation_target}</td>
                <td className="py-3">
                  <GMBar gmPct={c.gm_pct} gmColor={c.gm_color} />
                </td>
                <td className="py-3 text-slate-700 font-medium">
                  ${parseFloat(c.revenue).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                </td>
                <td className="py-3">
                  {c.risk_flag === "FLAG" ? (
                    <span
                      className="inline-flex items-center gap-1 px-2.5 py-1 bg-red-50 text-red-600 border border-red-200 rounded-full text-xs font-semibold"
                      data-testid="risk-flag"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" fill="none" viewBox="0 0 24 24" strokeWidth="2.5" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M3 3v1.5M3 21v-6m0 0 2.77-.693a9 9 0 0 1 6.208.682l.108.054a9 9 0 0 0 6.086.71l3.114-.732a48.524 48.524 0 0 1-.005-10.499l-3.11.732a9 9 0 0 1-6.085-.711l-.108-.054a9 9 0 0 0-6.208-.682L3 4.5M3 15V4.5" />
                      </svg>
                      FLAG
                    </span>
                  ) : (
                    <span className="text-xs text-emerald-500 font-medium">CLEAR</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
