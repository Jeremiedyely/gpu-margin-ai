/**
 * Zone2RCustomerRenderer — Tests (CUST-01 → CUST-10)
 *
 * Tests customer table, GM% bar colors, and risk flag.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Zone2RCustomerRenderer } from "../components/Zone2RCustomerRenderer";
import type { CustomerRecord } from "../types/api";

const MOCK_CUSTOMERS: CustomerRecord[] = [
  {
    allocation_target: "tenant-A",
    gm_pct: "45.00",
    gm_color: "green",
    revenue: "60000.00",
    risk_flag: "CLEAR",
  },
  {
    allocation_target: "tenant-B",
    gm_pct: "-5.00",
    gm_color: "red",
    revenue: "20000.00",
    risk_flag: "FLAG",
  },
  {
    allocation_target: "tenant-C",
    gm_pct: "15.00",
    gm_color: "orange",
    revenue: "30000.00",
    risk_flag: "CLEAR",
  },
  {
    allocation_target: "tenant-D",
    gm_pct: "35.00",
    gm_color: "yellow",
    revenue: "40000.00",
    risk_flag: "CLEAR",
  },
];

describe("Zone2RCustomerRenderer", () => {
  // CUST-01: loading state
  it("CUST-01 loading state shows loading message", () => {
    render(<Zone2RCustomerRenderer data={undefined} isLoading={true} />);
    expect(screen.getByTestId("zone2r")).toHaveTextContent("Loading customers...");
  });

  // CUST-02: empty data
  it("CUST-02 empty data shows no data message", () => {
    render(<Zone2RCustomerRenderer data={[]} isLoading={false} />);
    expect(screen.getByTestId("zone2r")).toHaveTextContent("No customer data available");
  });

  // CUST-03: renders customer rows
  it("CUST-03 renders customer rows", () => {
    render(<Zone2RCustomerRenderer data={MOCK_CUSTOMERS} isLoading={false} />);
    expect(screen.getByTestId("customer-row-tenant-A")).toBeInTheDocument();
    expect(screen.getByTestId("customer-row-tenant-B")).toBeInTheDocument();
  });

  // CUST-04: green GM bar for ≥38%
  it("CUST-04 green GM bar for tenant-A (45%)", () => {
    render(<Zone2RCustomerRenderer data={MOCK_CUSTOMERS} isLoading={false} />);
    const bars = screen.getAllByTestId("gm-bar");
    expect(bars[0]).toHaveAttribute("data-color", "green");
  });

  // CUST-05: red GM bar for <0%
  it("CUST-05 red GM bar for tenant-B (-5%)", () => {
    render(<Zone2RCustomerRenderer data={MOCK_CUSTOMERS} isLoading={false} />);
    const bars = screen.getAllByTestId("gm-bar");
    expect(bars[1]).toHaveAttribute("data-color", "red");
  });

  // CUST-06: orange GM bar for 0–29%
  it("CUST-06 orange GM bar for tenant-C (15%)", () => {
    render(<Zone2RCustomerRenderer data={MOCK_CUSTOMERS} isLoading={false} />);
    const bars = screen.getAllByTestId("gm-bar");
    expect(bars[2]).toHaveAttribute("data-color", "orange");
  });

  // CUST-07: yellow GM bar for 30–37%
  it("CUST-07 yellow GM bar for tenant-D (35%)", () => {
    render(<Zone2RCustomerRenderer data={MOCK_CUSTOMERS} isLoading={false} />);
    const bars = screen.getAllByTestId("gm-bar");
    expect(bars[3]).toHaveAttribute("data-color", "yellow");
  });

  // CUST-08: risk FLAG badge shown
  it("CUST-08 risk FLAG badge shown for flagged tenant", () => {
    render(<Zone2RCustomerRenderer data={MOCK_CUSTOMERS} isLoading={false} />);
    const flags = screen.getAllByTestId("risk-flag");
    expect(flags).toHaveLength(1);
    expect(flags[0]).toHaveTextContent("FLAG");
  });

  // CUST-09: CLEAR tenants have no FLAG badge
  it("CUST-09 CLEAR tenants have no FLAG badge", () => {
    const clearOnly: CustomerRecord[] = [MOCK_CUSTOMERS[0]]; // tenant-A CLEAR
    render(<Zone2RCustomerRenderer data={clearOnly} isLoading={false} />);
    expect(screen.queryByTestId("risk-flag")).not.toBeInTheDocument();
  });

  // CUST-10: undefined data shows no data
  it("CUST-10 undefined data shows no data message", () => {
    render(<Zone2RCustomerRenderer data={undefined} isLoading={false} />);
    expect(screen.getByTestId("zone2r")).toHaveTextContent("No customer data available");
  });
});
