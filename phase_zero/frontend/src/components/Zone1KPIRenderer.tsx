/**
 * Zone 1 KPI Renderer — Component 7/14.
 *
 * Renders four KPI cards from pre-computed cache.
 * If data unavailable → cards show "Unavailable" (not zero).
 */

import type { KPIResponse } from "@/types/api";

interface Zone1Props {
  data: KPIResponse | undefined;
  isLoading: boolean;
  isError: boolean;
}

interface KPICardProps {
  label: string;
  value: string | null;
  format: "dollar" | "percent";
}

function formatDollar(val: string): string {
  const num = parseFloat(val);
  return `$${num.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatPercent(val: string): string {
  return `${parseFloat(val).toFixed(2)}%`;
}

function KPICard({ label, value, format }: KPICardProps) {
  const display =
    value === null
      ? "Unavailable"
      : format === "dollar"
        ? formatDollar(value)
        : formatPercent(value);

  return (
    <div
      className="bg-white rounded-lg shadow p-6"
      data-testid={`kpi-card-${label.toLowerCase().replace(/\s+/g, "-")}`}
    >
      <p className="text-sm text-gray-500 mb-1">{label}</p>
      <p
        className={`text-2xl font-bold ${
          value === null ? "text-red-400" : "text-gray-800"
        }`}
        data-testid="kpi-value"
      >
        {display}
      </p>
    </div>
  );
}

export function Zone1KPIRenderer({ data, isLoading, isError }: Zone1Props) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-4 gap-4" data-testid="zone1">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="bg-white rounded-lg shadow p-6 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-2/3 mb-2" />
            <div className="h-8 bg-gray-200 rounded w-1/2" />
          </div>
        ))}
      </div>
    );
  }

  const isUnavailable = isError || !data;

  return (
    <div className="grid grid-cols-4 gap-4" data-testid="zone1">
      <KPICard
        label="GPU Revenue"
        value={isUnavailable ? null : data.gpu_revenue}
        format="dollar"
      />
      <KPICard
        label="GPU COGS"
        value={isUnavailable ? null : data.gpu_cogs}
        format="dollar"
      />
      <KPICard
        label="Idle GPU Cost"
        value={isUnavailable ? null : data.idle_gpu_cost}
        format="dollar"
      />
      <KPICard
        label="Cost Allocation Rate"
        value={isUnavailable ? null : data.cost_allocation_rate}
        format="percent"
      />
    </div>
  );
}
