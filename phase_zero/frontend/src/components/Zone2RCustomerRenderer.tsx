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

const GM_BAR_COLORS: Record<GmColor, string> = {
  red: "bg-red-500",
  orange: "bg-orange-400",
  yellow: "bg-yellow-400",
  green: "bg-green-500",
};

function GMBar({ gmPct, gmColor }: { gmPct: string | null; gmColor: GmColor | null }) {
  if (gmPct === null || gmColor === null) {
    return (
      <div className="flex items-center gap-2">
        <div className="w-24 h-3 bg-gray-200 rounded" />
        <span className="text-gray-400 text-xs">—</span>
      </div>
    );
  }

  const pct = parseFloat(gmPct);
  // Clamp bar width between 5% and 100% for visibility
  const barWidth = Math.max(5, Math.min(100, Math.abs(pct)));

  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-3 bg-gray-100 rounded overflow-hidden">
        <div
          className={`h-full rounded ${GM_BAR_COLORS[gmColor]}`}
          style={{ width: `${barWidth}%` }}
          data-testid="gm-bar"
          data-color={gmColor}
        />
      </div>
      <span className="text-xs text-gray-600">{pct.toFixed(2)}%</span>
    </div>
  );
}

export function Zone2RCustomerRenderer({ data, isLoading }: Zone2RProps) {
  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-6" data-testid="zone2r">
        <p className="text-gray-400">Loading customers...</p>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6" data-testid="zone2r">
        <h3 className="text-lg font-semibold text-gray-700 mb-4">
          Gross Margin by Customer
        </h3>
        <p className="text-gray-400">No customer data available</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow p-6" data-testid="zone2r">
      <h3 className="text-lg font-semibold text-gray-700 mb-4">
        Gross Margin by Customer
      </h3>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-gray-500">
            <th className="pb-2">Customer</th>
            <th className="pb-2">GM%</th>
            <th className="pb-2">Revenue</th>
            <th className="pb-2">Risk</th>
          </tr>
        </thead>
        <tbody>
          {data.map((c) => (
            <tr
              key={c.allocation_target}
              className="border-b"
              data-testid={`customer-row-${c.allocation_target}`}
            >
              <td className="py-2 font-medium">{c.allocation_target}</td>
              <td className="py-2">
                <GMBar gmPct={c.gm_pct} gmColor={c.gm_color} />
              </td>
              <td className="py-2">
                ${parseFloat(c.revenue).toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </td>
              <td className="py-2">
                {c.risk_flag === "FLAG" ? (
                  <span
                    className="px-2 py-1 bg-red-100 text-red-700 rounded text-xs font-semibold"
                    data-testid="risk-flag"
                  >
                    FLAG
                  </span>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
