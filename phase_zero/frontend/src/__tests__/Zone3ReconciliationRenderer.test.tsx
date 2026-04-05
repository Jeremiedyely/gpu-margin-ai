/**
 * Zone3ReconciliationRenderer — Tests (REC-01 → REC-08)
 *
 * Tests verdict rendering, escalation note, and unavailable state.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Zone3ReconciliationRenderer } from "../components/Zone3ReconciliationRenderer";
import type { VerdictRecord } from "../types/api";

const ALL_PASS: VerdictRecord[] = [
  { check: "Capacity vs Usage", verdict: "PASS" },
  { check: "Usage vs Tenant Mapping", verdict: "PASS" },
  { check: "Computed vs Billed vs Posted", verdict: "PASS" },
];

const ONE_FAIL: VerdictRecord[] = [
  { check: "Capacity vs Usage", verdict: "PASS" },
  { check: "Usage vs Tenant Mapping", verdict: "FAIL" },
  { check: "Computed vs Billed vs Posted", verdict: "PASS" },
];

describe("Zone3ReconciliationRenderer", () => {
  // REC-01: loading state
  it("REC-01 loading state shows loading message", () => {
    render(
      <Zone3ReconciliationRenderer
        data={undefined}
        sessionId="sess-1"
        isLoading={true}
        isError={false}
      />
    );
    expect(screen.getByTestId("zone3")).toHaveTextContent("Loading reconciliation...");
  });

  // REC-02: all PASS verdicts render
  it("REC-02 all PASS verdicts render with PASS badges", () => {
    render(
      <Zone3ReconciliationRenderer
        data={ALL_PASS}
        sessionId="sess-1"
        isLoading={false}
        isError={false}
      />
    );
    const badges = screen.getAllByTestId("verdict-badge");
    expect(badges).toHaveLength(3);
    badges.forEach((b) => expect(b).toHaveAttribute("data-verdict", "PASS"));
  });

  // REC-03: no escalation note on all PASS
  it("REC-03 no escalation note when all PASS", () => {
    render(
      <Zone3ReconciliationRenderer
        data={ALL_PASS}
        sessionId="sess-1"
        isLoading={false}
        isError={false}
      />
    );
    expect(screen.queryByTestId("escalation-note")).not.toBeInTheDocument();
  });

  // REC-04: FAIL verdict renders FAIL badge
  it("REC-04 FAIL verdict renders FAIL badge", () => {
    render(
      <Zone3ReconciliationRenderer
        data={ONE_FAIL}
        sessionId="sess-1"
        isLoading={false}
        isError={false}
      />
    );
    const badges = screen.getAllByTestId("verdict-badge");
    expect(badges[1]).toHaveAttribute("data-verdict", "FAIL");
  });

  // REC-05: escalation note on FAIL with session_id
  it("REC-05 escalation note shown with session_id on FAIL", () => {
    render(
      <Zone3ReconciliationRenderer
        data={ONE_FAIL}
        sessionId="sess-42"
        isLoading={false}
        isError={false}
      />
    );
    const note = screen.getByTestId("escalation-note");
    expect(note).toBeInTheDocument();
    expect(note).toHaveTextContent("sess-42");
  });

  // REC-06: error state shows unavailable
  it("REC-06 error state shows data unavailable", () => {
    render(
      <Zone3ReconciliationRenderer
        data={undefined}
        sessionId="sess-1"
        isLoading={false}
        isError={true}
      />
    );
    const unavailable = screen.getAllByTestId("verdict-unavailable");
    expect(unavailable).toHaveLength(3);
  });

  // REC-07: fewer than 3 checks shows unavailable
  it("REC-07 fewer than 3 checks shows unavailable", () => {
    render(
      <Zone3ReconciliationRenderer
        data={[ALL_PASS[0]]}
        sessionId="sess-1"
        isLoading={false}
        isError={false}
      />
    );
    const unavailable = screen.getAllByTestId("verdict-unavailable");
    expect(unavailable).toHaveLength(3);
  });

  // REC-08: null sessionId omits ID from escalation
  it("REC-08 null sessionId omits ID from escalation note", () => {
    render(
      <Zone3ReconciliationRenderer
        data={ONE_FAIL}
        sessionId={null}
        isLoading={false}
        isError={false}
      />
    );
    const note = screen.getByTestId("escalation-note");
    expect(note).not.toHaveTextContent("Session ID:");
  });
});
