/**
 * View1Renderer — Tests (V1-01 → V1-10)
 *
 * Tests deriveAnalyzeControl logic + render states.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { View1Renderer, deriveAnalyzeControl } from "../components/View1Renderer";

/** Wrap component with QueryClientProvider for tests that render. */
function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe("deriveAnalyzeControl", () => {
  // V1-01: EMPTY → LOCKED
  it("V1-01 EMPTY state → LOCKED", () => {
    expect(deriveAnalyzeControl("EMPTY", null)).toBe("LOCKED");
  });

  // V1-02: UPLOADED + IDLE → ACTIVE
  it("V1-02 UPLOADED + IDLE → ACTIVE", () => {
    expect(deriveAnalyzeControl("UPLOADED", "IDLE")).toBe("ACTIVE");
  });

  // V1-03: UPLOADED + ANALYZING → ANALYZING
  it("V1-03 UPLOADED + ANALYZING → ANALYZING", () => {
    expect(deriveAnalyzeControl("UPLOADED", "ANALYZING")).toBe("ANALYZING");
  });

  // V1-04: UPLOADED + null → LOCKED
  it("V1-04 UPLOADED + null → LOCKED", () => {
    expect(deriveAnalyzeControl("UPLOADED", null)).toBe("LOCKED");
  });
});

describe("View1Renderer", () => {
  // V1-05: renders 5 upload slots
  it("V1-05 renders 5 upload slots", () => {
    renderWithClient(<View1Renderer applicationState="EMPTY" analysisStatus={null} sessionId={null} />);
    for (let i = 1; i <= 5; i++) {
      expect(screen.getByTestId(`upload-slot-${i}`)).toBeInTheDocument();
    }
  });

  // V1-06: EMPTY shows no checkmarks
  it("V1-06 EMPTY shows no checkmarks", () => {
    renderWithClient(<View1Renderer applicationState="EMPTY" analysisStatus={null} sessionId={null} />);
    expect(screen.queryByTestId("slot-check-1")).not.toBeInTheDocument();
  });

  // V1-07: UPLOADED shows checkmarks
  it("V1-07 UPLOADED shows checkmarks on all slots", () => {
    renderWithClient(<View1Renderer applicationState="UPLOADED" analysisStatus="IDLE" sessionId="test-session-1" />);
    for (let i = 1; i <= 5; i++) {
      expect(screen.getByTestId(`slot-check-${i}`)).toBeInTheDocument();
    }
  });

  // V1-08: Analyze button disabled when LOCKED
  it("V1-08 Analyze button disabled when LOCKED", () => {
    renderWithClient(<View1Renderer applicationState="EMPTY" analysisStatus={null} sessionId={null} />);
    const btn = screen.getByTestId("analyze-button");
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("data-control", "LOCKED");
  });

  // V1-09: Analyze button enabled when ACTIVE
  it("V1-09 Analyze button enabled when ACTIVE", () => {
    renderWithClient(<View1Renderer applicationState="UPLOADED" analysisStatus="IDLE" sessionId="test-session-1" />);
    const btn = screen.getByTestId("analyze-button");
    expect(btn).not.toBeDisabled();
    expect(btn).toHaveAttribute("data-control", "ACTIVE");
  });

  // V1-10: ANALYZING shows progress label
  it("V1-10 ANALYZING shows progress label", () => {
    renderWithClient(<View1Renderer applicationState="UPLOADED" analysisStatus="ANALYZING" sessionId="test-session-1" />);
    const btn = screen.getByTestId("analyze-button");
    expect(btn).toHaveTextContent("Analysis in progress...");
    expect(btn).toBeDisabled();
  });
});
