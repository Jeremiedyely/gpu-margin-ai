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
import { AppHeader } from "./AppHeader";

function resolveView(state: ApplicationState | null): ActiveView {
  if (state === null || state === "EMPTY" || state === "UPLOADED") return "VIEW_1";
  if (state === "ANALYZED" || state === "APPROVED") return "VIEW_2";
  return "ERROR";
}

export function ScreenRouter() {
  const { data, isLoading, error } = useAppState();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-50">
        <AppHeader />
        <div className="flex items-center justify-center" style={{ minHeight: "calc(100vh - 72px)" }}>
          <div className="text-center">
            <div className="gpu-spinner mx-auto mb-4" />
            <p className="text-sm text-slate-400">Loading application state...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-slate-50">
        <AppHeader />
        <div className="flex items-center justify-center" style={{ minHeight: "calc(100vh - 72px)" }}>
          <div className="bg-white rounded-2xl shadow-md border border-red-100 p-8 max-w-md text-center">
            <div className="w-12 h-12 bg-red-50 rounded-xl flex items-center justify-center mx-auto mb-4">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="#ef4444">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126Z" />
              </svg>
            </div>
            <p className="text-lg font-semibold text-slate-800 mb-1">
              Application state unresolvable
            </p>
            <p className="text-sm text-slate-400">
              Contact your data team.
            </p>
          </div>
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
        sessionId={sessionId}
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
    <div className="min-h-screen bg-slate-50">
      <AppHeader sessionId={sessionId} />
      <div className="flex items-center justify-center" style={{ minHeight: "calc(100vh - 72px)" }}>
        <div className="bg-white rounded-2xl shadow-md border border-red-100 p-8 max-w-md text-center">
          <div className="w-12 h-12 bg-red-50 rounded-xl flex items-center justify-center mx-auto mb-4">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="#ef4444">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126Z" />
            </svg>
          </div>
          <p className="text-lg font-semibold text-slate-800 mb-1">
            Application state unresolvable
          </p>
          <p className="text-sm text-slate-400">
            Contact your data team
            {sessionId ? ` with Session ID: ${sessionId}` : ""}.
          </p>
        </div>
      </div>
    </div>
  );
}

// Export for testing
export { resolveView };
