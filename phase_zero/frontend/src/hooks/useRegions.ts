import { useQuery } from "@tanstack/react-query";
import type { RegionResponse } from "@/types/api";

async function fetchRegions(sessionId: string): Promise<RegionResponse> {
  const res = await fetch(`/api/regions/${sessionId}`);
  if (!res.ok) throw new Error(`Region fetch failed: ${res.status}`);
  return res.json();
}

export function useRegions(sessionId: string | null) {
  return useQuery<RegionResponse>({
    queryKey: ["regions", sessionId],
    queryFn: () => fetchRegions(sessionId!),
    enabled: !!sessionId,
  });
}
