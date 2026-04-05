import { useQuery } from "@tanstack/react-query";
import type { KPIResponse } from "@/types/api";

async function fetchKPI(sessionId: string): Promise<KPIResponse> {
  const res = await fetch(`/api/kpi/${sessionId}`);
  if (!res.ok) throw new Error(`KPI fetch failed: ${res.status}`);
  return res.json();
}

export function useKPI(sessionId: string | null) {
  return useQuery<KPIResponse>({
    queryKey: ["kpi", sessionId],
    queryFn: () => fetchKPI(sessionId!),
    enabled: !!sessionId,
  });
}
