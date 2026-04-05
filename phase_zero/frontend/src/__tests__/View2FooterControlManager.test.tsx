/**
 * View2FooterControlManager — Tests (FTR-01 → FTR-08)
 *
 * Tests deriveFooterState logic + button states.
 */

import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import {
  View2FooterControlManager,
  deriveFooterState,
} from "../components/View2FooterControlManager";

describe("deriveFooterState", () => {
  // FTR-01: ANALYZED → approve ACTIVE, exports LOCKED
  it("FTR-01 ANALYZED → approve ACTIVE, exports LOCKED", () => {
    const state = deriveFooterState("ANALYZED");
    expect(state.approve_control).toBe("ACTIVE");
    expect(state.csv_control).toBe("LOCKED");
    expect(state.excel_control).toBe("LOCKED");
    expect(state.power_bi_control).toBe("LOCKED");
  });

  // FTR-02: APPROVED → approve DEACTIVATED, exports ACTIVE
  it("FTR-02 APPROVED → approve DEACTIVATED, exports ACTIVE", () => {
    const state = deriveFooterState("APPROVED");
    expect(state.approve_control).toBe("DEACTIVATED");
    expect(state.csv_control).toBe("ACTIVE");
    expect(state.excel_control).toBe("ACTIVE");
    expect(state.power_bi_control).toBe("ACTIVE");
  });
});

describe("View2FooterControlManager render", () => {
  // FTR-03: ANALYZED renders enabled approve button
  it("FTR-03 ANALYZED renders enabled approve button", () => {
    render(
      <View2FooterControlManager applicationState="ANALYZED" sessionId="sess-1" />
    );
    const btn = screen.getByTestId("approve-button");
    expect(btn).not.toBeDisabled();
    expect(btn).toHaveAttribute("data-control", "ACTIVE");
  });

  // FTR-04: ANALYZED renders disabled export buttons
  it("FTR-04 ANALYZED renders disabled export buttons", () => {
    render(
      <View2FooterControlManager applicationState="ANALYZED" sessionId="sess-1" />
    );
    expect(screen.getByTestId("export-csv")).toBeDisabled();
    expect(screen.getByTestId("export-excel")).toBeDisabled();
    expect(screen.getByTestId("export-power-bi")).toBeDisabled();
  });

  // FTR-05: APPROVED renders disabled approve button with "Approved" label
  it("FTR-05 APPROVED renders disabled approve with Approved label", () => {
    render(
      <View2FooterControlManager applicationState="APPROVED" sessionId="sess-1" />
    );
    const btn = screen.getByTestId("approve-button");
    expect(btn).toBeDisabled();
    expect(btn).toHaveTextContent("Approved");
  });

  // FTR-06: APPROVED renders enabled export buttons
  it("FTR-06 APPROVED renders enabled export buttons", () => {
    render(
      <View2FooterControlManager applicationState="APPROVED" sessionId="sess-1" />
    );
    expect(screen.getByTestId("export-csv")).not.toBeDisabled();
    expect(screen.getByTestId("export-excel")).not.toBeDisabled();
    expect(screen.getByTestId("export-power-bi")).not.toBeDisabled();
  });

  // FTR-07: clicking approve opens dialog
  it("FTR-07 clicking approve opens confirmation dialog", () => {
    render(
      <View2FooterControlManager applicationState="ANALYZED" sessionId="sess-1" />
    );
    expect(screen.queryByTestId("approve-dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("approve-button"));
    expect(screen.getByTestId("approve-dialog")).toBeInTheDocument();
  });

  // FTR-08: dialog shows session_id
  it("FTR-08 dialog shows session_id", () => {
    render(
      <View2FooterControlManager applicationState="ANALYZED" sessionId="sess-42" />
    );
    fireEvent.click(screen.getByTestId("approve-button"));
    expect(screen.getByTestId("dialog-session-id")).toHaveTextContent("sess-42");
  });
});
