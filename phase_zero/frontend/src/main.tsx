/**
 * App entry point.
 *
 * QueryClientProvider → ScreenRouter.
 * Single QueryClient instance — shared cache for all TanStack Query hooks.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ScreenRouter } from "./components/ScreenRouter";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-gray-50 p-6">
        <header className="max-w-7xl mx-auto mb-8">
          <h1 className="text-2xl font-bold text-gray-800">
            GPU Gross Margin Visibility
          </h1>
        </header>
        <main className="max-w-7xl mx-auto">
          <ScreenRouter />
        </main>
      </div>
    </QueryClientProvider>
  </StrictMode>
);
