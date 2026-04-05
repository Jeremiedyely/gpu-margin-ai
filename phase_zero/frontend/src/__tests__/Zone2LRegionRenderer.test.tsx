/**
 * Zone2LRegionRenderer — Tests (RGN-01 → RGN-08)
 *
 * Tests region table rendering, status badges, and pills.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Zone2LRegionRenderer } from "../components/Zone2LRegionRenderer";
import type { RegionRecord } from "../types/api";

const MOCK_REGIONS: RegionRecord[] = [
  {
    region: "us-east-1",
    gm_pct: "42.50",
    idle_pct: "15.00",
    revenue: "80000.00",
    status: "HOLDING",
    identity_broken_count: 1,
    capacity_idle_count: 2,
  },
  {
    region: "eu-west-1",
    gm_pct: "28.00",
    idle_pct: "35.00",
    revenue: "50000.00",
    status: "AT RISK",
    identity_broken_count: 0,
    capacity_idle_count: 1,
  },
];

describe("Zone2LRegionRenderer", () => {
  // RGN-01: loading state
  it("RGN-01 loading state shows loading message", () => {
    render(<Zone2LRegionRenderer data={undefined} isLoading={true} />);
    expect(screen.getByTestId("zone2l")).toHaveTextContent("Loading regions...");
  });

  // RGN-02: empty data
  it("RGN-02 empty data shows no data message", () => {
    render(<Zone2LRegionRenderer data={[]} isLoading={false} />);
    expect(screen.getByTestId("zone2l")).toHaveTextContent("No region data available");
  });

  // RGN-03: renders region rows
  it("RGN-03 renders region rows", () => {
    render(<Zone2LRegionRenderer data={MOCK_REGIONS} isLoading={false} />);
    expect(screen.getByTestId("region-row-us-east-1")).toBeInTheDocument();
    expect(screen.getByTestId("region-row-eu-west-1")).toBeInTheDocument();
  });

  // RGN-04: HOLDING status badge
  it("RGN-04 HOLDING status badge rendered", () => {
    render(<Zone2LRegionRenderer data={MOCK_REGIONS} isLoading={false} />);
    const badges = screen.getAllByTestId("region-status");
    expect(badges[0]).toHaveTextContent("HOLDING");
  });

  // RGN-05: AT RISK status badge
  it("RGN-05 AT RISK status badge rendered", () => {
    render(<Zone2LRegionRenderer data={MOCK_REGIONS} isLoading={false} />);
    const badges = screen.getAllByTestId("region-status");
    expect(badges[1]).toHaveTextContent("AT RISK");
  });

  // RGN-06: identity broken pill shown
  it("RGN-06 identity broken pill shown when count > 0", () => {
    render(<Zone2LRegionRenderer data={MOCK_REGIONS} isLoading={false} />);
    expect(screen.getByTestId("pill-identity-broken")).toBeInTheDocument();
  });

  // RGN-07: capacity idle pill shown
  it("RGN-07 capacity idle pill shown when count > 0", () => {
    render(<Zone2LRegionRenderer data={MOCK_REGIONS} isLoading={false} />);
    expect(screen.getByTestId("pill-capacity-idle")).toBeInTheDocument();
  });

  // RGN-08: no pills when counts are zero
  it("RGN-08 no pills when all counts are zero", () => {
    const noIssues: RegionRecord[] = [
      { ...MOCK_REGIONS[0], identity_broken_count: 0, capacity_idle_count: 0 },
    ];
    render(<Zone2LRegionRenderer data={noIssues} isLoading={false} />);
    expect(screen.queryByTestId("pill-identity-broken")).not.toBeInTheDocument();
    expect(screen.queryByTestId("pill-capacity-idle")).not.toBeInTheDocument();
  });
});
