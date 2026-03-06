import { describe, it, expect } from "vitest";
import { aggregateLicenseesFromTransactions } from "./topLicenseesFromTransactions";
import type { VendorTransaction } from "../api/endpoints";

describe("aggregateLicenseesFromTransactions", () => {
  const ME = "VENDOR_A";

  it("aggregates transactions by counterparty", () => {
    const transactions: VendorTransaction[] = [
      { sourceVendor: ME, targetVendor: "VENDOR_B", status: "completed", createdAt: "2025-01-01T10:00:00Z" },
      { sourceVendor: ME, targetVendor: "VENDOR_B", status: "completed", createdAt: "2025-01-01T11:00:00Z" },
      { sourceVendor: "VENDOR_C", targetVendor: ME, status: "failed", createdAt: "2025-01-01T12:00:00Z" },
    ];
    const result = aggregateLicenseesFromTransactions(transactions, ME);
    expect(result).toHaveLength(2);

    const b = result.find((r) => r.licenseeCode === "VENDOR_B");
    expect(b).toBeDefined();
    expect(b?.totalVolume).toBe(2);
    expect(b?.failedVolume).toBe(0);
    expect(b?.errorRate).toBe(0);
    expect(b?.direction).toBe("Outbound");

    const c = result.find((r) => r.licenseeCode === "VENDOR_C");
    expect(c).toBeDefined();
    expect(c?.totalVolume).toBe(1);
    expect(c?.failedVolume).toBe(1);
    expect(c?.errorRate).toBe(100);
    expect(c?.direction).toBe("Inbound");
  });

  it("computes Mixed when licensee has both inbound and outbound", () => {
    const transactions: VendorTransaction[] = [
      { sourceVendor: ME, targetVendor: "VENDOR_D", status: "completed", createdAt: "2025-01-01T10:00:00Z" },
      { sourceVendor: "VENDOR_D", targetVendor: ME, status: "completed", createdAt: "2025-01-01T11:00:00Z" },
    ];
    const result = aggregateLicenseesFromTransactions(transactions, ME);
    expect(result).toHaveLength(1);
    expect(result[0].direction).toBe("Mixed");
    expect(result[0].totalVolume).toBe(2);
  });

  it("sorts by totalVolume descending", () => {
    const transactions: VendorTransaction[] = [
      { sourceVendor: ME, targetVendor: "LOW", status: "completed", createdAt: "2025-01-01T10:00:00Z" },
      { sourceVendor: ME, targetVendor: "HIGH", status: "completed", createdAt: "2025-01-01T10:00:00Z" },
      { sourceVendor: ME, targetVendor: "HIGH", status: "completed", createdAt: "2025-01-01T10:00:00Z" },
      { sourceVendor: ME, targetVendor: "HIGH", status: "completed", createdAt: "2025-01-01T10:00:00Z" },
    ];
    const result = aggregateLicenseesFromTransactions(transactions, ME);
    expect(result[0].licenseeCode).toBe("HIGH");
    expect(result[1].licenseeCode).toBe("LOW");
  });

  it("returns empty array when no valid counterparties", () => {
    const transactions: VendorTransaction[] = [
      { sourceVendor: ME, targetVendor: ME, status: "completed", createdAt: "2025-01-01T10:00:00Z" },
      { sourceVendor: "", targetVendor: "", status: "completed", createdAt: "2025-01-01T10:00:00Z" },
    ];
    const result = aggregateLicenseesFromTransactions(transactions, ME);
    expect(result).toHaveLength(0);
  });
});
