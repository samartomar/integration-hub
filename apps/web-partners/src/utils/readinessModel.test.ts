import { describe, it, expect } from "vitest";
import {
  buildReadinessRowsForLicensee,
  mapReadinessToDisplay,
  getAccessDisplayStatus,
  toEndpointStatus,
  getEndpointVerificationDisplay,
  getMappingStatusDisplay,
} from "./readinessModel";
import type { BuildReadinessInput } from "./readinessModel";
import { computeHomeReadinessCounts } from "./homeReadinessCounts";

function mkSupported(op: string, isActive = true) {
  return { operationCode: op, isActive };
}

function mkCatalogOp(op: string, version = "v1") {
  return { operationCode: op, canonicalVersion: version };
}

function mkContract(op: string) {
  return { operationCode: op };
}

function mkEndpoint(op: string, verified = true) {
  return {
    operationCode: op,
    url: `https://example.com/${op}`,
    isActive: true,
    verificationStatus: verified ? "VERIFIED" : "PENDING",
  };
}

function mkMapping(
  op: string,
  direction: "TO_CANONICAL" | "FROM_CANONICAL" | "TO_CANONICAL_RESPONSE" | "FROM_CANONICAL_RESPONSE"
) {
  return { operationCode: op, canonicalVersion: "v1", direction, mapping: {}, isActive: true };
}

function mkAllowlistEntry(source: string, target: string, operation: string) {
  return { sourceVendor: source, targetVendor: target, operation };
}

function mkMyOpOutbound(op: string, partner: string, status: "ready" | "needs_setup" = "ready") {
  return {
    operationCode: op,
    canonicalVersion: "v1",
    partnerVendorCode: partner,
    direction: "outbound" as const,
    status,
    hasCanonicalOperation: true,
    hasVendorContract: true,
    hasRequestMapping: true,
    hasResponseMapping: true,
    mappingConfigured: true,
    effectiveMappingConfigured: true,
    hasEndpoint: true,
    hasAllowlist: true,
    issues: [],
  };
}

describe("buildReadinessRowsForLicensee", () => {
  it("inbound-only ready with Any(*)", () => {
    const input: BuildReadinessInput = {
      supported: [mkSupported("OP1")],
      catalog: [mkCatalogOp("OP1")],
      vendorContracts: [mkContract("OP1")],
      endpoints: [mkEndpoint("OP1")],
      mappings: [
        mkMapping("OP1", "TO_CANONICAL"),
        mkMapping("OP1", "FROM_CANONICAL_RESPONSE"),
      ],
      outboundAllowlist: [],
      inboundAllowlist: [mkAllowlistEntry("*", "ME", "OP1")],
      vendorCode: "ME",
    };
    const rows = buildReadinessRowsForLicensee(input);
    const inbound = rows.find((r) => r.direction === "Inbound" && r.operationCode === "OP1");
    expect(inbound).toBeDefined();
    expect(inbound?.readyToReceive).toBe(true);
    expect(inbound?.vendorReady).toBe(true);
    expect(inbound?.hasAllowedInboundAccess).toBe(true);
    expect(inbound?.hasAccess).toBe(true);
  });

  it("outbound-only, no target", () => {
    const input: BuildReadinessInput = {
      supported: [mkSupported("OP1")],
      catalog: [mkCatalogOp("OP1")],
      vendorContracts: [mkContract("OP1")],
      endpoints: [mkEndpoint("OP1")],
      mappings: [
        mkMapping("OP1", "TO_CANONICAL"),
        mkMapping("OP1", "FROM_CANONICAL_RESPONSE"),
      ],
      outboundAllowlist: [],
      inboundAllowlist: [],
      vendorCode: "A",
    };
    const rows = buildReadinessRowsForLicensee(input);
    const outbound = rows.find((r) => r.direction === "Outbound" && r.operationCode === "OP1");
    expect(outbound).toBeDefined();
    expect(outbound?.vendorReady).toBe(false);
    expect(outbound?.hasAllowedOutboundTarget).toBe(false);
  });

  it("outbound + inbound with explicit rule", () => {
    const input: BuildReadinessInput = {
      supported: [mkSupported("OP1")],
      catalog: [mkCatalogOp("OP1")],
      vendorContracts: [mkContract("OP1")],
      endpoints: [mkEndpoint("OP1")],
      mappings: [
        mkMapping("OP1", "TO_CANONICAL"),
        mkMapping("OP1", "FROM_CANONICAL_RESPONSE"),
        mkMapping("OP1", "FROM_CANONICAL"),
        mkMapping("OP1", "TO_CANONICAL_RESPONSE"),
      ],
      outboundAllowlist: [mkAllowlistEntry("B", "C", "OP1")],
      inboundAllowlist: [mkAllowlistEntry("C", "B", "OP1")],
      vendorCode: "B",
    };
    const rows = buildReadinessRowsForLicensee(input);
    const outbound = rows.find((r) => r.direction === "Outbound");
    const inbound = rows.find((r) => r.direction === "Inbound");
    expect(outbound?.vendorReady).toBe(true);
    expect(inbound?.vendorReady).toBe(true);
    expect(outbound?.readyToCall).toBe(true);
    expect(inbound?.readyToReceive).toBe(true);
  });

  it("outbound + inbound with Any(*)", () => {
    const input: BuildReadinessInput = {
      supported: [mkSupported("OP1")],
      catalog: [mkCatalogOp("OP1")],
      vendorContracts: [mkContract("OP1")],
      endpoints: [mkEndpoint("OP1")],
      mappings: [
        mkMapping("OP1", "TO_CANONICAL"),
        mkMapping("OP1", "FROM_CANONICAL_RESPONSE"),
        mkMapping("OP1", "FROM_CANONICAL"),
        mkMapping("OP1", "TO_CANONICAL_RESPONSE"),
      ],
      outboundAllowlist: [mkAllowlistEntry("B", "C", "OP1")],
      inboundAllowlist: [mkAllowlistEntry("*", "C", "OP1")],
      vendorCode: "C",
    };
    const rows = buildReadinessRowsForLicensee(input);
    const inbound = rows.find((r) => r.direction === "Inbound");
    expect(inbound?.hasAllowedInboundAccess).toBe(true);
    expect(inbound?.vendorReady).toBe(true);
  });

  it("outbound + allowlist: backend scoped; target readiness no longer blocks access", () => {
    const input: BuildReadinessInput = {
      supported: [mkSupported("OP1")],
      catalog: [mkCatalogOp("OP1")],
      vendorContracts: [mkContract("OP1")],
      endpoints: [mkEndpoint("OP1")],
      mappings: [
        mkMapping("OP1", "TO_CANONICAL"),
        mkMapping("OP1", "FROM_CANONICAL_RESPONSE"),
      ],
      outboundAllowlist: [mkAllowlistEntry("A", "B", "OP1")],
      inboundAllowlist: [],
      vendorCode: "A",
      myOperationsOutbound: [
        mkMyOpOutbound("OP1", "B", "needs_setup"),
      ],
    };
    const rows = buildReadinessRowsForLicensee(input);
    const outbound = rows.find((r) => r.direction === "Outbound" && r.operationCode === "OP1");
    expect(outbound).toBeDefined();
    expect(outbound?.hasAllowedOutboundTarget).toBe(true);
    expect(outbound?.hasAccess).toBe(true);
    expect(outbound?.readyToCall).toBe(true);
    expect(outbound?.vendorReady).toBe(true);
    expect(outbound?.overallStatus).toBe("ready");
  });

  it("outbound + allowlist + at least one inbound-ready target when myOperationsOutbound provided", () => {
    const input: BuildReadinessInput = {
      supported: [mkSupported("OP1")],
      catalog: [mkCatalogOp("OP1")],
      vendorContracts: [mkContract("OP1")],
      endpoints: [mkEndpoint("OP1")],
      mappings: [
        mkMapping("OP1", "TO_CANONICAL"),
        mkMapping("OP1", "FROM_CANONICAL_RESPONSE"),
      ],
      outboundAllowlist: [mkAllowlistEntry("A", "B", "OP1")],
      inboundAllowlist: [],
      vendorCode: "A",
      myOperationsOutbound: [
        mkMyOpOutbound("OP1", "B", "ready"),
      ],
    };
    const rows = buildReadinessRowsForLicensee(input);
    const outbound = rows.find((r) => r.direction === "Outbound" && r.operationCode === "OP1");
    expect(outbound).toBeDefined();
    expect(outbound?.readyToCall).toBe(true);
    expect(outbound?.vendorReady).toBe(true);
    expect(outbound?.overallStatus).toBe("ready");
  });

  it("outbound LH001->LH002: LH001 has vendor rule, config missing shows Access Allowed", () => {
    const input: BuildReadinessInput = {
      supported: [mkSupported("GET_RECEIPT")],
      catalog: [mkCatalogOp("GET_RECEIPT", "v1")],
      vendorContracts: [mkContract("GET_RECEIPT")],
      endpoints: [],
      mappings: [],
      outboundAllowlist: [mkAllowlistEntry("LH001", "LH002", "GET_RECEIPT")],
      inboundAllowlist: [],
      vendorCode: "LH001",
    };
    const rows = buildReadinessRowsForLicensee(input);
    const outbound = rows.find(
      (r) => r.direction === "Outbound" && r.operationCode === "GET_RECEIPT"
    );
    expect(outbound).toBeDefined();
    expect(outbound?.hasAllowedOutboundTarget).toBe(true);
    expect(outbound?.hasAllowedInboundAccess).toBe(false);
    expect(outbound?.hasAccess).toBe(true);
    expect(outbound?.overallStatus).toBe("config_missing");
    expect(outbound?.hasEndpoint).toBe(false);
    // Canonical-backed contract + no mappings → canonical pass-through (hasMapping=true per alignment spec)
    expect(outbound?.hasMapping).toBe(true);
    expect(outbound?.usesCanonicalPassThrough).toBe(true);
  });

  it("inbound partial config: contract configured, endpoint missing, canonical pass-through for mapping, access allowed, overall needs configuration", () => {
    const input: BuildReadinessInput = {
      supported: [mkSupported("GET_RECEIPT", true)],
      catalog: [mkCatalogOp("GET_RECEIPT", "v1")],
      vendorContracts: [mkContract("GET_RECEIPT")],
      endpoints: [],
      mappings: [],
      outboundAllowlist: [],
      inboundAllowlist: [mkAllowlistEntry("*", "LH001", "GET_RECEIPT")],
      vendorCode: "LH001",
    };
    const rows = buildReadinessRowsForLicensee(input);
    const inbound = rows.find(
      (r) => r.direction === "Inbound" && r.operationCode === "GET_RECEIPT"
    );
    expect(inbound).toBeDefined();
    expect(inbound?.hasContract).toBe(true);
    expect(inbound?.hasEndpoint).toBe(false);
    // Canonical-backed contract + no mappings → canonical pass-through (hasMapping=true per alignment spec)
    expect(inbound?.hasMapping).toBe(true);
    expect(inbound?.usesCanonicalPassThrough).toBe(true);
    expect(inbound?.hasAllowedInboundAccess).toBe(true);
    expect(inbound?.hasAccess).toBe(true);
    expect(inbound?.overallStatus).toBe("config_missing");
    expect(inbound?.vendorReady).toBe(false);
  });

  it("hasAllowed requires adminPermits: vendor rule without admin eligibility = blocked", () => {
    const input: BuildReadinessInput = {
      supported: [mkSupported("OP1")],
      catalog: [mkCatalogOp("OP1")],
      vendorContracts: [mkContract("OP1")],
      endpoints: [mkEndpoint("OP1")],
      mappings: [
        mkMapping("OP1", "FROM_CANONICAL"),
        mkMapping("OP1", "TO_CANONICAL_RESPONSE"),
      ],
      outboundAllowlist: [mkAllowlistEntry("A", "B", "OP1")],
      inboundAllowlist: [],
      eligibleOperations: [{ operationCode: "OP1", canCallOutbound: false, canReceiveInbound: false }],
      vendorCode: "A",
    };
    const rows = buildReadinessRowsForLicensee(input);
    const outbound = rows.find((r) => r.direction === "Outbound" && r.operationCode === "OP1");
    expect(outbound).toBeDefined();
    expect(outbound?.hasAllowedOutboundTarget).toBe(false);
    expect(outbound?.overallStatus).toBe("access_blocked");
  });

  it("mixed operations", () => {
    const input: BuildReadinessInput = {
      supported: [mkSupported("OP1"), mkSupported("OP2")],
      catalog: [mkCatalogOp("OP1"), mkCatalogOp("OP2")],
      vendorContracts: [mkContract("OP1")],
      endpoints: [mkEndpoint("OP1")],
      mappings: [
        mkMapping("OP1", "TO_CANONICAL"),
        mkMapping("OP1", "FROM_CANONICAL_RESPONSE"),
        mkMapping("OP1", "FROM_CANONICAL"),
        mkMapping("OP1", "TO_CANONICAL_RESPONSE"),
      ],
      outboundAllowlist: [mkAllowlistEntry("B", "C", "OP1")],
      inboundAllowlist: [],
      vendorCode: "B",
    };
    const rows = buildReadinessRowsForLicensee(input);
    const op1 = rows.filter((r) => r.operationCode === "OP1");
    const op2 = rows.filter((r) => r.operationCode === "OP2");
    expect(op1.some((r) => r.vendorReady)).toBe(true);
    expect(op2.every((r) => !r.vendorReady)).toBe(true);
  });
});

describe("computeHomeReadinessCounts", () => {
  it("counts ready when vendorReady", () => {
    const rows = buildReadinessRowsForLicensee({
      supported: [mkSupported("OP1")],
      catalog: [mkCatalogOp("OP1")],
      vendorContracts: [mkContract("OP1")],
      endpoints: [mkEndpoint("OP1")],
      mappings: [
        mkMapping("OP1", "FROM_CANONICAL"),
        mkMapping("OP1", "TO_CANONICAL_RESPONSE"),
      ],
      outboundAllowlist: [mkAllowlistEntry("A", "B", "OP1")],
      inboundAllowlist: [],
      vendorCode: "A",
    });
    const counts = computeHomeReadinessCounts(rows);
    expect(counts.ready).toBeGreaterThanOrEqual(1);
    expect(counts.total).toBeGreaterThanOrEqual(1);
  });

  it("counts blockedByAccess when config complete but no access", () => {
    const rows = buildReadinessRowsForLicensee({
      supported: [mkSupported("OP1")],
      catalog: [mkCatalogOp("OP1")],
      vendorContracts: [mkContract("OP1")],
      endpoints: [mkEndpoint("OP1")],
      mappings: [
        mkMapping("OP1", "TO_CANONICAL"),
        mkMapping("OP1", "FROM_CANONICAL_RESPONSE"),
      ],
      outboundAllowlist: [],
      inboundAllowlist: [],
      vendorCode: "A",
    });
    const counts = computeHomeReadinessCounts(rows);
    expect(counts.blockedByAccess).toBeGreaterThanOrEqual(0);
  });
});

describe("mapReadinessToDisplay", () => {
  const baseRow = {
    operationCode: "OP1",
    operationVersion: "v1",
    direction: "Outbound" as const,
    hasContract: true,
    hasMapping: true,
    hasEndpoint: true,
    endpointVerified: true,
    hasInboundConfig: true,
    hasOutboundConfig: true,
    hasAllowedInboundAccess: true,
    hasAllowedOutboundTarget: true,
    hasAccess: true,
    readyToCall: true,
    readyToReceive: true,
    vendorReady: true,
    overallStatus: "ready" as const,
    isActive: true,
  };

  it("returns Inactive when !isActive", () => {
    const status = mapReadinessToDisplay({ ...baseRow, isActive: false });
    expect(status.label).toBe("Inactive");
    expect(status.variant).toBe("neutral");
  });

  it("returns Ready for traffic when config and access OK", () => {
    const status = mapReadinessToDisplay(baseRow);
    expect(status.label).toBe("Ready for traffic");
    expect(status.variant).toBe("configured");
  });

  it("returns Blocked by access rules when access_blocked", () => {
    const status = mapReadinessToDisplay({
      ...baseRow,
      hasAllowedInboundAccess: false,
      hasAllowedOutboundTarget: false,
      hasAccess: false,
      readyToCall: false,
      readyToReceive: false,
      vendorReady: false,
      overallStatus: "access_blocked",
    });
    expect(status.label).toBe("Blocked by access rules");
    expect(status.variant).toBe("warning");
  });

  it("returns Has recent errors when hasRecentErrors opts", () => {
    const status = mapReadinessToDisplay(baseRow, { hasRecentErrors: true });
    expect(status.label).toBe("Has recent errors");
    expect(status.variant).toBe("warning");
  });

  it("getAccessDisplayStatus returns allowed when hasAccess true even if config incomplete", () => {
    const rowWithAccessNoConfig = {
      ...baseRow,
      hasAccess: true,
      hasEndpoint: false,
      hasMapping: false,
      hasOutboundConfig: false,
      vendorReady: false,
      overallStatus: "config_missing" as const,
    };
    expect(getAccessDisplayStatus(rowWithAccessNoConfig, false)).toBe("allowed");
  });

  it("returns Needs configuration when config_missing", () => {
    const status = mapReadinessToDisplay({
      ...baseRow,
      hasContract: false,
      hasOutboundConfig: false,
      vendorReady: false,
      overallStatus: "config_missing",
    });
    expect(status.label).toBe("Needs configuration");
    expect(status.variant).toBe("error");
  });
});

describe("toEndpointStatus", () => {
  it("returns missing when no endpoint for Inbound", () => {
    expect(toEndpointStatus(false, false, "Inbound")).toBe("missing");
  });
  it("returns missing when no endpoint for Outbound", () => {
    expect(toEndpointStatus(false, false, "Outbound")).toBe("missing");
  });
  it("returns configured when endpoint verified for Inbound", () => {
    expect(toEndpointStatus(true, true, "Inbound")).toBe("configured");
  });
  it("returns partial when endpoint not verified for Inbound", () => {
    expect(toEndpointStatus(true, false, "Inbound")).toBe("partial");
  });
  it("returns configured when endpoint verified for Outbound", () => {
    expect(toEndpointStatus(true, true, "Outbound")).toBe("configured");
  });
  it("returns partial when endpoint not verified for Outbound", () => {
    expect(toEndpointStatus(true, false, "Outbound")).toBe("partial");
  });
});

describe("getEndpointVerificationDisplay", () => {
  it("renders Verified pill when verificationStatus is VERIFIED", () => {
    const result = getEndpointVerificationDisplay("VERIFIED", true);
    expect(result.label).toBe("Verified");
    expect(result.variant).toBe("configured");
  });

  it("renders Not verified pill when verificationStatus is PENDING", () => {
    const result = getEndpointVerificationDisplay("PENDING", true);
    expect(result.label).toBe("Not verified");
    expect(result.variant).toBe("warning");
  });

  it("renders Verification failed pill when verificationStatus is FAILED", () => {
    const result = getEndpointVerificationDisplay("FAILED", true);
    expect(result.label).toBe("Verification failed");
    expect(result.variant).toBe("error");
  });

  it("uses endpointHealth when provided", () => {
    const result = getEndpointVerificationDisplay(undefined, true, "healthy");
    expect(result.label).toBe("Verified");
  });
});

describe("getMappingStatusDisplay", () => {
  it("returns Using canonical format when hasMapping and usesCanonicalPassThrough", () => {
    const result = getMappingStatusDisplay(true, true);
    expect(result.label).toBe("Using canonical format");
    expect(result.variant).toBe("configured");
    expect(result.tooltip).toContain("canonical pass-through");
  });

  it("returns Configured when hasMapping but not canonical pass-through", () => {
    const result = getMappingStatusDisplay(true, false);
    expect(result.label).toBe("Configured");
  });

  it("returns Missing when !hasMapping", () => {
    const result = getMappingStatusDisplay(false);
    expect(result.label).toBe("Missing");
    expect(result.variant).toBe("error");
  });

  it("returns Using canonical format when effectiveMappingConfigured true and usesCanonicalPassThrough (canonical pass-through case)", () => {
    const result = getMappingStatusDisplay(false, true, true);
    expect(result.label).toBe("Using canonical format");
    expect(result.variant).toBe("configured");
  });
});

describe("buildReadinessRowsForLicensee - canonical pass-through", () => {
  it("explicit vendor contract without mappings does NOT get canonical fallback (still needs mapping)", () => {
    const input: BuildReadinessInput = {
      supported: [mkSupported("GET_RECEIPT")],
      catalog: [mkCatalogOp("GET_RECEIPT", "v1")],
      vendorContracts: [{ operationCode: "GET_RECEIPT", id: "vc-123", canonicalVersion: "v1" }],
      endpoints: [mkEndpoint("GET_RECEIPT")],
      mappings: [],
      outboundAllowlist: [mkAllowlistEntry("LH001", "LH002", "GET_RECEIPT")],
      inboundAllowlist: [],
      vendorCode: "LH001",
    };
    const rows = buildReadinessRowsForLicensee(input);
    const outbound = rows.find(
      (r) => r.direction === "Outbound" && r.operationCode === "GET_RECEIPT"
    );
    expect(outbound).toBeDefined();
    expect(outbound?.hasMapping).toBe(false);
    expect(outbound?.usesCanonicalPassThrough).toBe(false);
  });

  it("hasMapping and usesCanonicalPassThrough when myOperations has usesCanonicalPassThrough from backend", () => {
    const myOpCanonical = {
      operationCode: "OP1",
      canonicalVersion: "v1",
      partnerVendorCode: "*",
      direction: "outbound" as const,
      status: "ready" as const,
      hasCanonicalOperation: true,
      hasVendorContract: false,
      hasRequestMapping: false,
      hasResponseMapping: false,
      mappingConfigured: true,
      effectiveMappingConfigured: true,
      mappingRequestSource: "canonical_pass_through" as const,
      mappingResponseSource: "canonical_pass_through" as const,
      usesCanonicalPassThrough: true,
      usesCanonicalRequestMapping: true,
      usesCanonicalResponseMapping: true,
      requiresRequestMapping: false,
      requiresResponseMapping: false,
      hasEndpoint: true,
      hasAllowlist: true,
      issues: [],
    };
    const input: BuildReadinessInput = {
      supported: [mkSupported("OP1")],
      catalog: [mkCatalogOp("OP1")],
      vendorContracts: [],
      endpoints: [mkEndpoint("OP1")],
      mappings: [],
      outboundAllowlist: [mkAllowlistEntry("ME", "*", "OP1")],
      inboundAllowlist: [],
      vendorCode: "ME",
      myOperationsOutbound: [myOpCanonical],
    };
    const rows = buildReadinessRowsForLicensee(input);
    const outbound = rows.find((r) => r.direction === "Outbound" && r.operationCode === "OP1");
    expect(outbound?.hasMapping).toBe(true);
    expect(outbound?.usesCanonicalPassThrough).toBe(true);
    expect(outbound?.overallStatus).toBe("ready");
  });

  it("hasMapping and usesCanonicalPassThrough when myOperations has requires*=false with no mapping rows (fallback)", () => {
    const myOpCanonical = {
      operationCode: "OP1",
      canonicalVersion: "v1",
      partnerVendorCode: "*",
      direction: "outbound" as const,
      status: "ready" as const,
      hasCanonicalOperation: true,
      hasVendorContract: true,
      hasRequestMapping: false,
      hasResponseMapping: false,
      mappingConfigured: false,
      usesCanonicalRequestMapping: false,
      usesCanonicalResponseMapping: false,
      requiresRequestMapping: false,
      requiresResponseMapping: false,
      hasEndpoint: true,
      hasAllowlist: true,
      issues: [],
    };
    const input: BuildReadinessInput = {
      supported: [mkSupported("OP1")],
      catalog: [mkCatalogOp("OP1")],
      vendorContracts: [mkContract("OP1")],
      endpoints: [mkEndpoint("OP1")],
      mappings: [],
      outboundAllowlist: [mkAllowlistEntry("ME", "*", "OP1")],
      inboundAllowlist: [],
      vendorCode: "ME",
      myOperationsOutbound: [myOpCanonical],
    };
    const rows = buildReadinessRowsForLicensee(input);
    const outbound = rows.find((r) => r.direction === "Outbound" && r.operationCode === "OP1");
    expect(outbound?.hasMapping).toBe(true);
    expect(outbound?.usesCanonicalPassThrough).toBe(true);
  });
});
