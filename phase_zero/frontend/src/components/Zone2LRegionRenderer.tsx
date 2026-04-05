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

export function Zone2LRegionRenderer({ data, isLoading }: Zone2LProps) {
  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-6" data-testid="zone2l">
        <p className="text-gray-400">Loading regions...</p>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6" data-testid="zone2l">
        <h3 className="text-lg font-semibold text-gray-700 mb-4">
          Gross Margin by Region
        </h3>
        <p className="text-gray-400">No region data available</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow p-6" data-testid="zone2l">
      <h3 className="text-lg font-semibold text-gray-700 mb-4">
        Gross Margin by Region
      </h3>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-gray-500">
            <th className="pb-2">Region</th>
            <th className="pb-2">GM%</th>
            <th className="pb-2">Idle%</th>
            <th className="pb-2">Revenue</th>
            <th className="pb-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {data.map((r) => (
            <tr key={r.region} className="border-b" data-testid={`region-row-${r.region}`}>
              <td className="py-2 font-medium">{r.region}</td>
              <td className="py-2">{r.gm_pct !== null ? `${r.gm_pct}%` : "—"}</td>
              <td className="py-2">{r.idle_pct}%</td>
              <td className="py-2">
                ${parseFloat(r.revenue).toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </td>
              <td className="py-2">
                <span
                  className={`px-2 py-1 rounded text-xs font-semibold ${
                    r.status === "AT RISK"
                      ? "bg-red-100 text-red-700"
                      : "bg-gray-100 text-gray-600"
                  }`}
                  data-testid="region-status"
                >
                  {r.status}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Subtype pills */}
      <div className="mt-4 flex gap-2">
        {data.some((r) => r.identity_broken_count > 0) && (
          <span
            className="px-3 py-1 bg-red-100 text-red-700 rounded-full text-xs font-semibold"
            data-testid="pill-identity-broken"
          >
            Identity Broken
          </span>
        )}
        {data.some((r) => r.capacity_idle_count > 0) && (
          <span
            className="px-3 py-1 bg-orange-100 text-orange-700 rounded-full text-xs font-semibold"
            data-testid="pill-capacity-idle"
          >
            Capacity Idle
          </span>
        )}
      </div>
    </div>
  );
}
