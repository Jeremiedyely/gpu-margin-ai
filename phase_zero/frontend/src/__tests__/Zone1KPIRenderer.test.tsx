/**
 * Zone1KPIRenderer — Tests (KPI-01 → KPI-08)
 *
 * Tests KPI card rendering, formatting, and unavailable state.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Zone1KPIRenderer } from "../components/Zone1KPIRenderer";
import type { KPIResponse } from "../types/api";

const MOCK_KPI: KPIResponse = {
  gpu_revenue: "150000.00",
  gpu_cogs: "90000.00",
  idle_gpu_cost: "12000.00",
  idle_gpu_cost_pct: "13.33",
  cost_allocation_rate: "86.67",
};

describe("Zone1KPIRenderer", () => {
  // KPI-01: loading state shows skeleton
  it("KPI-01 loading state renders skeleton", () => {
    render(<Zone1KPIRenderer data={undefined} isLoading={true} isError={false} />);
    const zone = screen.getByTestId("zone1");
    expect(zone).toBeInTheDocument();
    // Skeleton has no kpi-value elements
    expect(screen.queryAllByTestId("kpi-value")).toHaveLength(0);
  });

  // KPI-02: renders 4 KPI cards with data
  it("KPI-02 renders 4 KPI cards with data", () => {
    render(<Zone1KPIRenderer data={MOCK_KPI} isLoading={false} isError={false} />);
    const values = screen.getAllByTestId("kpi-value");
    expect(values).toHaveLength(4);
  });

  // KPI-03: GPU Revenue formatted as dollar
  it("KPI-03 GPU Revenue formatted as dollar", () => {
    render(<Zone1KPIRenderer data={MOCK_KPI} isLoading={false} isError={false} />);
    const card = screen.getByTestId("kpi-card-gpu-revenue");
    expect(card).toHaveTextContent("$150,000.00");
  });

  // KPI-04: Cost Allocation Rate formatted as percent
  it("KPI-04 Cost Allocation Rate formatted as percent", () => {
    render(<Zone1KPIRenderer data={MOCK_KPI} isLoading={false} isError={false} />);
    const card = screen.getByTestId("kpi-card-cost-allocation-rate");
    expect(card).toHaveTextContent("86.67%");
  });

  // KPI-05: error state shows Unavailable
  it("KPI-05 error state shows Unavailable on all cards", () => {
    render(<Zone1KPIRenderer data={undefined} isLoading={false} isError={true} />);
    const values = screen.getAllByTestId("kpi-value");
    values.forEach((v) => expect(v).toHaveTextContent("Unavailable"));
  });

  // KPI-06: no data shows Unavailable
  it("KPI-06 no data shows Unavailable", () => {
    render(<Zone1KPIRenderer data={undefined} isLoading={false} isError={false} />);
    const values = screen.getAllByTestId("kpi-value");
    values.forEach((v) => expect(v).toHaveTextContent("Unavailable"));
  });

  // KPI-07: Idle GPU Cost card present
  it("KPI-07 Idle GPU Cost card present", () => {
    render(<Zone1KPIRenderer data={MOCK_KPI} isLoading={false} isError={false} />);
    expect(screen.getByTestId("kpi-card-idle-gpu-cost")).toBeInTheDocument();
  });

  // KPI-08: GPU COGS formatted correctly
  it("KPI-08 GPU COGS formatted correctly", () => {
    render(<Zone1KPIRenderer data={MOCK_KPI} isLoading={false} isError={false} />);
    const card = screen.getByTestId("kpi-card-gpu-cogs");
    expect(card).toHaveTextContent("$90,000.00");
  });
});
