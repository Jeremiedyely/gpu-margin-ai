/**
 * ScreenRouter — Tests (SR-01 → SR-06)
 *
 * Tests the resolveView pure function and basic render paths.
 * Hooks are mocked — we only test view routing logic here.
 */

import { describe, it, expect } from "vitest";
import { resolveView } from "../components/ScreenRouter";

describe("resolveView", () => {
  // SR-01: EMPTY → VIEW_1
  it("SR-01 routes EMPTY to VIEW_1", () => {
    expect(resolveView("EMPTY")).toBe("VIEW_1");
  });

  // SR-02: UPLOADED → VIEW_1
  it("SR-02 routes UPLOADED to VIEW_1", () => {
    expect(resolveView("UPLOADED")).toBe("VIEW_1");
  });

  // SR-03: ANALYZED → VIEW_2
  it("SR-03 routes ANALYZED to VIEW_2", () => {
    expect(resolveView("ANALYZED")).toBe("VIEW_2");
  });

  // SR-04: APPROVED → VIEW_2
  it("SR-04 routes APPROVED to VIEW_2", () => {
    expect(resolveView("APPROVED")).toBe("VIEW_2");
  });

  // SR-05: null → ERROR
  it("SR-05 routes null to ERROR", () => {
    expect(resolveView(null)).toBe("ERROR");
  });

  // SR-06: unrecognized string → ERROR
  it("SR-06 routes unrecognized state to ERROR", () => {
    expect(resolveView("GARBAGE" as any)).toBe("ERROR");
  });
});
