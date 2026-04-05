/**
 * View1Renderer — Tests (V1-01 → V1-10)
 *
 * Tests deriveAnalyzeControl logic + render states.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { View1Renderer, deriveAnalyzeControl } from "../components/View1Renderer";

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
    render(<View1Renderer applicationState="EMPTY" analysisStatus={null} />);
    for (let i = 1; i <= 5; i++) {
      expect(screen.getByTestId(`upload-slot-${i}`)).toBeInTheDocument();
    }
  });

  // V1-06: EMPTY shows no checkmarks
  it("V1-06 EMPTY shows no checkmarks", () => {
    render(<View1Renderer applicationState="EMPTY" analysisStatus={null} />);
    expect(screen.queryByTestId("slot-check-1")).not.toBeInTheDocument();
  });

  // V1-07: UPLOADED shows checkmarks
  it("V1-07 UPLOADED shows checkmarks on all slots", () => {
    render(<View1Renderer applicationState="UPLOADED" analysisStatus="IDLE" />);
    for (let i = 1; i <= 5; i++) {
      expect(screen.getByTestId(`slot-check-${i}`)).toBeInTheDocument();
    }
  });

  // V1-08: Analyze button disabled when LOCKED
  it("V1-08 Analyze button disabled when LOCKED", () => {
    render(<View1Renderer applicationState="EMPTY" analysisStatus={null} />);
    const btn = screen.getByTestId("analyze-button");
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("data-control", "LOCKED");
  });

  // V1-09: Analyze button enabled when ACTIVE
  it("V1-09 Analyze button enabled when ACTIVE", () => {
    render(<View1Renderer applicationState="UPLOADED" analysisStatus="IDLE" />);
    const btn = screen.getByTestId("analyze-button");
    expect(btn).not.toBeDisabled();
    expect(btn).toHaveAttribute("data-control", "ACTIVE");
  });

  // V1-10: ANALYZING shows progress label
  it("V1-10 ANALYZING shows progress label", () => {
    render(<View1Renderer applicationState="UPLOADED" analysisStatus="ANALYZING" />);
    const btn = screen.getByTestId("analyze-button");
    expect(btn).toHaveTextContent("Analysis in progress...");
    expect(btn).toBeDisabled();
  });
});
