/**
 * useAppState — fetches application_state from the server on every render.
 *
 * Server-state render invariant (L2 P1 #34):
 *   Button states MUST be derived from application_state received from the
 *   State Machine on every render. They must NEVER be read from UI local state.
 */

import { useQuery } from "@tanstack/react-query";
import type { StateResponse } from "@/types/api";

async function fetchState(): Promise<StateResponse> {
  const res = await fetch("/api/state");
  if (!res.ok) throw new Error(`State fetch failed: ${res.status}`);
  return res.json();
}

export function useAppState() {
  return useQuery<StateResponse>({
    queryKey: ["appState"],
    queryFn: fetchState,
    refetchInterval: 3000, // poll every 3s during analysis
    staleTime: 1000,
  });
}
