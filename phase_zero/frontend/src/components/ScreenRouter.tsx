/**
 * Screen Router — Component 1/14.
 *
 * Routes to View 1 (EMPTY/UPLOADED) or View 2 (ANALYZED/APPROVED).
 * If application_state is null or unrecognized → ERROR view.
 *
 * Reads state from server on every render (server-state render invariant).
 */

import { useAppState } from "@/hooks/useAppState";
import type { ActiveView, ApplicationState } from "@/types/api";
import { View1Renderer } from "./View1Renderer";
import { AnalysisViewContainer } from "./AnalysisViewContainer";

function resolveView(state: ApplicationState | null): ActiveView {
  if (state === "EMPTY" || state === "UPLOADED") return "VIEW_1";
  if (state === "ANALYZED" || state === "APPROVED") return "VIEW_2";
  return "ERROR";
}

export function ScreenRouter() {
  const { data, isLoading, error } = useAppState();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-gray-500">Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <p className="text-red-600 font-semibold">
            Application state unresolvable.
          </p>
          <p className="text-gray-500 mt-2">
            Contact your data team.
          </p>
        </div>
      </div>
    );
  }

  const appState = data?.application_state ?? null;
  const sessionId = data?.session_id ?? null;
  const analysisStatus = data?.analysis_status ?? null;
  const activeView = resolveView(appState);

  if (activeView === "VIEW_1") {
    return (
      <View1Renderer
        applicationState={appState as "EMPTY" | "UPLOADED"}
        analysisStatus={analysisStatus}
      />
    );
  }

  if (activeView === "VIEW_2") {
    return (
      <AnalysisViewContainer
        applicationState={appState as "ANALYZED" | "APPROVED"}
        sessionId={sessionId!}
      />
    );
  }

  // ERROR view
  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-center">
        <p className="text-red-600 font-semibold">
          Application state unresolvable.
        </p>
        <p className="text-gray-500 mt-2">
          Contact your data team
          {sessionId ? ` with Session ID: ${sessionId}` : ""}.
        </p>
      </div>
    </div>
  );
}

// Export for testing
export { resolveView };
