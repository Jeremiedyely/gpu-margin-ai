/**
 * Analysis View Container — Component 12/14.
 *
 * View 2 assembly: Zone 1 (KPIs) + Zone 2L (Regions) + Zone 2R (Customers)
 * + Zone 3 (Reconciliation) + Footer (Approve / Export).
 *
 * Owns all data-fetch hooks; child renderers are pure projection.
 * Server-state render invariant — applicationState always from useAppState.
 */

import { useKPI } from "@/hooks/useKPI";
import { useCustomers } from "@/hooks/useCustomers";
import { useRegions } from "@/hooks/useRegions";
import { useReconciliation } from "@/hooks/useReconciliation";
import { Zone1KPIRenderer } from "./Zone1KPIRenderer";
import { Zone2LRegionRenderer } from "./Zone2LRegionRenderer";
import { Zone2RCustomerRenderer } from "./Zone2RCustomerRenderer";
import { Zone3ReconciliationRenderer } from "./Zone3ReconciliationRenderer";
import { View2FooterControlManager } from "./View2FooterControlManager";

interface AnalysisViewProps {
  sessionId: string;
  applicationState: "ANALYZED" | "APPROVED";
}

export function AnalysisViewContainer({
  sessionId,
  applicationState,
}: AnalysisViewProps) {
  const kpi = useKPI(sessionId);
  const customers = useCustomers(sessionId);
  const regions = useRegions(sessionId);
  const reconciliation = useReconciliation(sessionId);

  return (
    <div className="space-y-6" data-testid="analysis-view">
      {/* Zone 1 — KPI cards */}
      <Zone1KPIRenderer
        data={kpi.data}
        isLoading={kpi.isLoading}
        isError={kpi.isError}
      />

      {/* Zone 2 — Region (left) + Customer (right) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Zone2LRegionRenderer
          data={regions.data?.payload}
          isLoading={regions.isLoading}
        />
        <Zone2RCustomerRenderer
          data={customers.data?.payload}
          isLoading={customers.isLoading}
        />
      </div>

      {/* Zone 3 — Reconciliation verdicts */}
      <Zone3ReconciliationRenderer
        data={reconciliation.data?.payload}
        sessionId={sessionId}
        isLoading={reconciliation.isLoading}
        isError={reconciliation.isError}
      />

      {/* Footer — Approve + Export controls */}
      <View2FooterControlManager
        applicationState={applicationState}
        sessionId={sessionId}
      />
    </div>
  );
}
