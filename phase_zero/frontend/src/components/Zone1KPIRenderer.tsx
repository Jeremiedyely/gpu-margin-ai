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
  accent: "blue" | "red" | "amber" | "green";
  icon: React.ReactNode;
}

function formatDollar(val: string): string {
  const num = parseFloat(val);
  return `$${num.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatPercent(val: string): string {
  return `${parseFloat(val).toFixed(2)}%`;
}

const ACCENT_CLASSES: Record<string, string> = {
  blue: "kpi-accent-blue",
  red: "kpi-accent-red",
  amber: "kpi-accent-amber",
  green: "kpi-accent-green",
};

const ICON_BG_CLASSES: Record<string, string> = {
  blue: "bg-blue-50 text-blue-500",
  red: "bg-red-50 text-red-500",
  amber: "bg-amber-50 text-amber-500",
  green: "bg-emerald-50 text-emerald-500",
};

function KPICard({ label, value, format, accent, icon }: KPICardProps) {
  const display =
    value === null
      ? "Unavailable"
      : format === "dollar"
        ? formatDollar(value)
        : formatPercent(value);

  return (
    <div
      className={`bg-white rounded-2xl shadow-md border border-slate-100 p-5 ${ACCENT_CLASSES[accent]}`}
      data-testid={`kpi-card-${label.toLowerCase().replace(/\s+/g, "-")}`}
    >
      <div className="flex items-start justify-between mb-3">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
          {label}
        </p>
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${ICON_BG_CLASSES[accent]}`}>
          {icon}
        </div>
      </div>
      <p
        className={`text-2xl font-bold tracking-tight ${
          value === null ? "text-red-400" : "text-slate-800"
        }`}
        data-testid="kpi-value"
      >
        {display}
      </p>
    </div>
  );
}

/* SVG Icons */
const RevenueIcon = (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18 9 11.25l4.306 4.306a11.95 11.95 0 0 1 5.814-5.518l2.74-1.22m0 0-5.94-2.281m5.94 2.28-2.28 5.941" />
  </svg>
);

const COGSIcon = (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 6 9 12.75l4.286-4.286a11.948 11.948 0 0 1 4.306 6.43l.776 2.898m0 0 3.182-5.511m-3.182 5.51-5.511-3.181" />
  </svg>
);

const IdleIcon = (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126Z" />
  </svg>
);

const AllocationIcon = (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 6a7.5 7.5 0 1 0 7.5 7.5h-7.5V6Z" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 10.5H21A7.5 7.5 0 0 0 13.5 3v7.5Z" />
  </svg>
);

export function Zone1KPIRenderer({ data, isLoading, isError }: Zone1Props) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" data-testid="zone1">
        {[
          { accent: "blue", label: "GPU Revenue" },
          { accent: "red", label: "GPU COGS" },
          { accent: "amber", label: "Idle GPU Cost" },
          { accent: "green", label: "Cost Allocation Rate" },
        ].map((card) => (
          <div
            key={card.label}
            className={`bg-white rounded-2xl shadow-md border border-slate-100 p-5 animate-pulse ${ACCENT_CLASSES[card.accent]}`}
          >
            <div className="flex items-start justify-between mb-3">
              <div className="h-3 bg-slate-200 rounded w-20" />
              <div className="w-8 h-8 bg-slate-100 rounded-lg" />
            </div>
            <div className="h-8 bg-slate-200 rounded w-28" />
          </div>
        ))}
      </div>
    );
  }

  const isUnavailable = isError || !data;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" data-testid="zone1">
      <KPICard
        label="GPU Revenue"
        value={isUnavailable ? null : data.gpu_revenue}
        format="dollar"
        accent="blue"
        icon={RevenueIcon}
      />
      <KPICard
        label="GPU COGS"
        value={isUnavailable ? null : data.gpu_cogs}
        format="dollar"
        accent="red"
        icon={COGSIcon}
      />
      <KPICard
        label="Idle GPU Cost"
        value={isUnavailable ? null : data.idle_gpu_cost}
        format="dollar"
        accent="amber"
        icon={IdleIcon}
      />
      <KPICard
        label="Cost Allocation Rate"
        value={isUnavailable ? null : data.cost_allocation_rate}
        format="percent"
        accent="green"
        icon={AllocationIcon}
      />
    </div>
  );
}
