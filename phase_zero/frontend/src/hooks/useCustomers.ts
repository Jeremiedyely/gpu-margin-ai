import { useQuery } from "@tanstack/react-query";
import type { CustomerResponse } from "@/types/api";

async function fetchCustomers(sessionId: string): Promise<CustomerResponse> {
  const res = await fetch(`/api/customers/${sessionId}`);
  if (!res.ok) throw new Error(`Customer fetch failed: ${res.status}`);
  return res.json();
}

export function useCustomers(sessionId: string | null) {
  return useQuery<CustomerResponse>({
    queryKey: ["customers", sessionId],
    queryFn: () => fetchCustomers(sessionId!),
    enabled: !!sessionId,
  });
}
