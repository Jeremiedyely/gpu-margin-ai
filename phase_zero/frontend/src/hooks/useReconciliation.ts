import { useQuery } from "@tanstack/react-query";
import type { ReconciliationResponse } from "@/types/api";

async function fetchReconciliation(
  sessionId: string
): Promise<ReconciliationResponse> {
  const res = await fetch(`/api/reconciliation/${sessionId}`);
  if (!res.ok)
    throw new Error(`Reconciliation fetch failed: ${res.status}`);
  return res.json();
}

export function useReconciliation(sessionId: string | null) {
  return useQuery<ReconciliationResponse>({
    queryKey: ["reconciliation", sessionId],
    queryFn: () => fetchReconciliation(sessionId!),
    enabled: !!sessionId,
  });
}
