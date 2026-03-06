/**
 * Unified readiness model for the vendor portal.
 * Single source of truth for Home, Configuration Overview, Flows, and Flow Details.
 *
 * Readiness = "Is there at least one legal, end-to-end path for this operation?"
 * - Inbound: am I configured to receive, and do access rules allow callers?
 * - Outbound: am I configured to call, and is there an inbound-ready target I'm allowed to call?
 */

import { getVendorDirectionLabel } from "frontend-shared";
import type {
  VendorOperationCatalogItem,
  VendorSupportedOperation,
  VendorEndpoint,
  VendorContract,
  VendorMapping,
} from "frontend-shared";
import type {
  MyAllowlistEntry,
  MyOperationItem,
  AccessOutcomeItem,
  AccessOutcome,
} from "../api/endpoints";
import type { StatusPillVariant } from "frontend-shared";

/** Overall readiness status for display */
export type OverallReadinessStatus =
  | "ready"
  | "config_missing"
  | "access_blocked"
  | "has_errors";

/**
 * Effective access = hasVendorRule && adminPermits.
 * Backend my-allowlist returns vendor rules only (rule_scope=vendor) and eligibleOperations (admin permits).
 */
function hasAllowedOutboundTargetForOp(
  opCode: string,
  outbound: MyAllowlistEntry[],
  adminPermitsOutbound?: (op: string) => boolean
): boolean {
  const hasVendorRule = outbound.some((r) => (r.operation ?? "").toUpperCase() === opCode.toUpperCase());
  const adminOk = adminPermitsOutbound ? adminPermitsOutbound(opCode) : true;
  return hasVendorRule && adminOk;
}

function hasAllowedInboundAccessForOp(
  opCode: string,
  inbound: MyAllowlistEntry[],
  adminPermitsInbound?: (op: string) => boolean
): boolean {
  const hasVendorRule = inbound.some((r) => (r.operation ?? "").toUpperCase() === opCode.toUpperCase());
  const adminOk = adminPermitsInbound ? adminPermitsInbound(opCode) : true;
  return hasVendorRule && adminOk;
}

export type FlowReadinessDirection = "Inbound" | "Outbound";

/** Descriptive direction text for UI so vendors know "Am I calling out or others calling me?" */
export function formatDirectionForDisplay(direction: FlowReadinessDirection): string {
  return getVendorDirectionLabel(direction === "Outbound" ? "OUTBOUND" : "INBOUND");
}

export interface FlowReadinessRow {
  operationCode: string;
  operationVersion: string;
  direction: FlowReadinessDirection;

  /** Contract configured for this direction */
  hasContract: boolean;
  /** Mapping configured for this direction */
  hasMapping: boolean;
  /** Endpoint configured (outbound) or N/A (inbound) */
  hasEndpoint: boolean;
  /** Endpoint verification status (when hasEndpoint); for inbound N/A */
  endpointVerified: boolean;

  /** This licensee has complete inbound setup (contract + mapping + endpoint for inbound) */
  hasInboundConfig: boolean;
  /** This licensee has complete outbound setup */
  hasOutboundConfig: boolean;

  /** Some caller is allowed to hit my inbound for this op (backend already scoped) */
  hasAllowedInboundAccess: boolean;
  /** There is at least one outbound rule allowing this vendor to call (backend already scoped) */
  hasAllowedOutboundTarget: boolean;
  /** Derived: has access for this op (outbound or inbound) – used by Access column */
  hasAccess: boolean;
  /** access_outcome from backend: ALLOWED_BY_ADMIN | ALLOWED_NARROWED_BY_VENDOR | BLOCKED_BY_ADMIN */
  accessOutcome?: AccessOutcome;
  /** When ALLOWED_NARROWED_BY_VENDOR: count of vendor-selected callers (for "N of M" display). */
  vendorNarrowedCount?: number;
  /** When ALLOWED_NARROWED_BY_VENDOR: count of admin-allowed callers (for "N of M" display). */
  adminEnvelopeCount?: number;

  /** Derived: ready to call outbound */
  readyToCall: boolean;
  /** Derived: ready to receive inbound */
  readyToReceive: boolean;
  /** Derived: ready for traffic (either direction) */
  vendorReady: boolean;

  /** Overall status for display (config_missing | access_blocked | ready; has_errors applied by consumer when recent failures exist) */
  overallStatus: OverallReadinessStatus;

  /** Operation is active (not deactivated) */
  isActive: boolean;

  /** Mapping is complete via canonical pass-through (both request and response use canonical format) */
  usesCanonicalPassThrough?: boolean;

  /** True when mapping is configured (explicit or canonical pass-through). Prefer over hasMapping when from my-operations. */
  effectiveMappingConfigured?: boolean;
}

export interface BuildReadinessInput {
  supported: VendorSupportedOperation[];
  catalog: VendorOperationCatalogItem[];
  vendorContracts: VendorContract[];
  endpoints: VendorEndpoint[];
  mappings: VendorMapping[];
  /** Vendor access rules (rule_scope=vendor) – outbound & inbound */
  outboundAllowlist: MyAllowlistEntry[];
  inboundAllowlist: MyAllowlistEntry[];
  /** Admin eligibility per op – from my-allowlist eligibleOperations. Used for hasAllowed when accessOutcomes not provided. */
  eligibleOperations?: { operationCode: string; canCallOutbound: boolean; canReceiveInbound: boolean }[];
  /** Per (op, direction) access outcome from backend. When provided, hasAccess = accessStatus==ALLOWED. */
  accessOutcomes?: AccessOutcomeItem[];
  /** Current vendor code – used by consumers; allowlist is already scoped by backend. */
  vendorCode: string;
  /** My Operations outbound items – used to verify targets are actually inbound-ready. When provided, readyToCall requires at least one target with status "ready". */
  myOperationsOutbound?: MyOperationItem[];
  /** My Operations inbound items – used to derive canonical pass-through mapping status. */
  myOperationsInbound?: MyOperationItem[];
}

/**
 * Direction pairs (per baseline, Flow Builder / provider flow):
 * - OUTBOUND (provider/target: platform calls vendor): request=FROM_CANONICAL, response=TO_CANONICAL_RESPONSE
 * - INBOUND (source: vendor sends to platform): request=TO_CANONICAL, response=FROM_CANONICAL_RESPONSE
 */
function computeMappingOk(
  op: string,
  mappings: VendorMapping[],
  direction: FlowReadinessDirection
): boolean {
  const opMappings = mappings.filter(
    (m) => (m.operationCode ?? "").toUpperCase() === op.toUpperCase() && m.isActive !== false
  );
  if (direction === "Outbound") {
    return (
      opMappings.some((m) => m.direction === "FROM_CANONICAL") &&
      opMappings.some((m) => m.direction === "TO_CANONICAL_RESPONSE")
    );
  }
  return (
    opMappings.some((m) => m.direction === "TO_CANONICAL") &&
    opMappings.some((m) => m.direction === "FROM_CANONICAL_RESPONSE")
  );
}

/**
 * Build per-operation, per-direction readiness rows for the current licensee.
 */
export function buildReadinessRowsForLicensee(input: BuildReadinessInput): FlowReadinessRow[] {
  const {
    supported,
    catalog,
    vendorContracts,
    endpoints,
    mappings,
    outboundAllowlist,
    inboundAllowlist,
    eligibleOperations,
    accessOutcomes,
    vendorCode: _vendorCode,
    myOperationsOutbound,
    myOperationsInbound,
  } = input;

  const outcomeByKey = new Map<string, AccessOutcomeItem>();
  if (accessOutcomes) {
    for (const o of accessOutcomes) {
      outcomeByKey.set(`${(o.operationCode ?? "").toUpperCase()}|${o.direction}`, o);
    }
  }

  const getAccessOutcome = (op: string, direction: "Outbound" | "Inbound"): AccessOutcomeItem | undefined => {
    const dir = direction === "Outbound" ? "OUTBOUND" : "INBOUND";
    return outcomeByKey.get(`${op.toUpperCase()}|${dir}`);
  };

  const adminPermitsOutbound = eligibleOperations
    ? (op: string) =>
        (eligibleOperations.find((e) => (e.operationCode ?? "").toUpperCase() === op.toUpperCase())
          ?.canCallOutbound ?? false)
    : () => true;
  const adminPermitsInbound = eligibleOperations
    ? (op: string) =>
        (eligibleOperations.find((e) => (e.operationCode ?? "").toUpperCase() === op.toUpperCase())
          ?.canReceiveInbound ?? false)
    : () => true;

  const rows: FlowReadinessRow[] = [];

  for (const s of supported) {
    const op = s.operationCode ?? "";
    if (!op) continue;

    const catalogOp = catalog.find((c) => (c.operationCode ?? "").toUpperCase() === op.toUpperCase());
    const version = catalogOp?.canonicalVersion ?? "v1";
    const isActive = s.isActive !== false;

    // hasContract: true when vendor has a contract for this op. Backend GET /vendor/contracts returns:
    // (1) rows from vendor_operation_contracts, or (2) canonical-backed ops (vendor has op in supported,
    // canonical exists in operation_contracts). No version/direction filter; any match by operationCode counts.
    const hasContract = vendorContracts.some(
      (c) => (c.operationCode ?? "").toUpperCase() === op.toUpperCase()
    );
    const hasCatalogOp = !!catalogOp;
    const opEndpoint = endpoints.find(
      (e) =>
        (e.operationCode ?? "").toUpperCase() === op.toUpperCase() && e.isActive !== false
    );
    const hasEndpoint = !!opEndpoint;
    const endpointVerified =
      hasEndpoint &&
      (opEndpoint!.verificationStatus === "VERIFIED" || opEndpoint!.verificationStatus === "OK");

    const hasExplicitOutboundMapping = computeMappingOk(op, mappings, "Outbound");
    const hasExplicitInboundMapping = computeMappingOk(op, mappings, "Inbound");
    // Canonical-backed contract (id null/undefined) = no vendor schema override; no mappings = canonical pass-through
    const opContract = vendorContracts.find(
      (c) => (c.operationCode ?? "").toUpperCase() === op.toUpperCase()
    );
    const hasExplicitVendorContract =
      !!opContract && opContract.id != null && opContract.id !== "";
    const hasOutboundMappingFromMyOps = (myOperationsOutbound ?? []).some(
      (m) =>
        (m.operationCode ?? "").toUpperCase() === op.toUpperCase() &&
        (m.effectiveMappingConfigured === true ||
          m.mappingConfigured === true ||
          m.usesCanonicalPassThrough === true ||
          (m.requiresRequestMapping === false &&
            m.requiresResponseMapping === false &&
            !m.hasRequestMapping &&
            !m.hasResponseMapping))
    );
    const hasInboundMappingFromMyOps = (myOperationsInbound ?? []).some(
      (m) =>
        (m.operationCode ?? "").toUpperCase() === op.toUpperCase() &&
        (m.effectiveMappingConfigured === true ||
          m.mappingConfigured === true ||
          m.usesCanonicalPassThrough === true ||
          (m.requiresRequestMapping === false &&
            m.requiresResponseMapping === false &&
            !m.hasRequestMapping &&
            !m.hasResponseMapping))
    );
    // Fallback: when my-operations has no item (e.g. allowlist not yet producing flow) but we have
    // canonical-backed contract and no explicit mappings → canonical pass-through per alignment spec
    const outboundCanonicalFallback =
      !hasOutboundMappingFromMyOps &&
      !hasExplicitOutboundMapping &&
      hasContract &&
      !hasExplicitVendorContract;
    const inboundCanonicalFallback =
      !hasInboundMappingFromMyOps &&
      !hasExplicitInboundMapping &&
      hasContract &&
      !hasExplicitVendorContract;

    const hasOutboundMapping =
      hasExplicitOutboundMapping || hasOutboundMappingFromMyOps || outboundCanonicalFallback;
    const hasInboundMapping =
      hasExplicitInboundMapping || hasInboundMappingFromMyOps || inboundCanonicalFallback;

    const usesCanonicalOutbound =
      outboundCanonicalFallback ||
      (myOperationsOutbound ?? []).some(
        (m) =>
          (m.operationCode ?? "").toUpperCase() === op.toUpperCase() &&
          (m.usesCanonicalPassThrough === true ||
            (m.usesCanonicalRequestMapping === true &&
              m.usesCanonicalResponseMapping === true) ||
            (m.effectiveMappingConfigured === true &&
              m.usesCanonicalRequestMapping === true &&
              m.usesCanonicalResponseMapping === true))
      ) ||
      (hasOutboundMappingFromMyOps &&
        !hasExplicitOutboundMapping &&
        (myOperationsOutbound ?? []).some(
          (m) =>
            (m.operationCode ?? "").toUpperCase() === op.toUpperCase() &&
            (m.usesCanonicalPassThrough === true ||
              m.effectiveMappingConfigured === true ||
              (m.requiresRequestMapping === false &&
                m.requiresResponseMapping === false))
        ));
    const usesCanonicalInbound =
      inboundCanonicalFallback ||
      (myOperationsInbound ?? []).some(
        (m) =>
          (m.operationCode ?? "").toUpperCase() === op.toUpperCase() &&
          (m.usesCanonicalPassThrough === true ||
            (m.usesCanonicalRequestMapping === true &&
              m.usesCanonicalResponseMapping === true) ||
            (m.effectiveMappingConfigured === true &&
              m.usesCanonicalRequestMapping === true &&
              m.usesCanonicalResponseMapping === true))
      ) ||
      (hasInboundMappingFromMyOps &&
        !hasExplicitInboundMapping &&
        (myOperationsInbound ?? []).some(
          (m) =>
            (m.operationCode ?? "").toUpperCase() === op.toUpperCase() &&
            (m.usesCanonicalPassThrough === true ||
              m.effectiveMappingConfigured === true ||
              (m.requiresRequestMapping === false &&
                m.requiresResponseMapping === false))
        ));

    void outboundAllowlist.some((a) => (a.operation ?? "").toUpperCase() === op.toUpperCase());
    void inboundAllowlist.some((a) => (a.operation ?? "").toUpperCase() === op.toUpperCase());

    const supportsOutbound = s.supportsOutbound !== false;
    const supportsInbound = s.supportsInbound !== false;

    let hasAllowedOutboundTarget: boolean;
    let hasAllowedInboundAccess: boolean;
    if (accessOutcomes) {
      const outOutcome = getAccessOutcome(op, "Outbound");
      const inOutcome = getAccessOutcome(op, "Inbound");
      hasAllowedOutboundTarget = (outOutcome?.accessStatus ?? "BLOCKED") === "ALLOWED";
      hasAllowedInboundAccess = (inOutcome?.accessStatus ?? "BLOCKED") === "ALLOWED";
    } else {
      hasAllowedOutboundTarget = hasAllowedOutboundTargetForOp(
        op,
        outboundAllowlist,
        adminPermitsOutbound
      );
      hasAllowedInboundAccess = hasAllowedInboundAccessForOp(
        op,
        inboundAllowlist,
        adminPermitsInbound
      );
    }

    const hasOutboundConfig =
      (hasContract || hasCatalogOp) &&
      hasEndpoint &&
      endpointVerified &&
      hasOutboundMapping;
    const hasInboundConfig = hasContract && hasInboundMapping && hasEndpoint;

    const readyToCall = hasOutboundConfig && hasAllowedOutboundTarget;
    const readyToReceive = hasInboundConfig && hasAllowedInboundAccess;

    const deriveOverallStatus = (
      _direction: FlowReadinessDirection,
      configComplete: boolean,
      accessOk: boolean
    ): OverallReadinessStatus => {
      if (!configComplete) return "config_missing";
      if (!accessOk) return "access_blocked";
      return "ready";
    };

    if (supportsInbound) {
      const configComplete = hasInboundConfig;
      const accessOk = hasAllowedInboundAccess;
      const hasAccess = hasAllowedInboundAccess;
      const inOutcome = accessOutcomes ? getAccessOutcome(op, "Inbound") : undefined;
      rows.push({
        operationCode: op,
        operationVersion: version,
        direction: "Inbound",
        hasContract,
        hasMapping: hasInboundMapping,
        hasEndpoint,
        endpointVerified: hasEndpoint ? endpointVerified : false,
        hasInboundConfig,
        hasOutboundConfig,
        hasAllowedInboundAccess,
        hasAllowedOutboundTarget,
        hasAccess,
        accessOutcome: inOutcome?.accessOutcome,
        vendorNarrowedCount: inOutcome?.vendorNarrowedCount,
        adminEnvelopeCount: inOutcome?.adminEnvelopeCount,
        readyToCall,
        readyToReceive,
        vendorReady: readyToReceive || readyToCall,
        overallStatus: deriveOverallStatus("Inbound", configComplete, accessOk),
        isActive,
        usesCanonicalPassThrough: usesCanonicalInbound,
        effectiveMappingConfigured: hasInboundMapping,
      });
    }

    if (supportsOutbound) {
      const configComplete = hasOutboundConfig;
      const accessOk = hasAllowedOutboundTarget;
      const hasAccess = hasAllowedOutboundTarget;
      const outOutcome = accessOutcomes ? getAccessOutcome(op, "Outbound") : undefined;
      rows.push({
        operationCode: op,
        operationVersion: version,
        direction: "Outbound",
        hasContract,
        hasMapping: hasOutboundMapping,
        hasEndpoint,
        endpointVerified,
        hasInboundConfig,
        hasOutboundConfig,
        hasAllowedInboundAccess,
        hasAllowedOutboundTarget,
        hasAccess,
        accessOutcome: outOutcome?.accessOutcome,
        vendorNarrowedCount: outOutcome?.vendorNarrowedCount,
        adminEnvelopeCount: outOutcome?.adminEnvelopeCount,
        readyToCall,
        readyToReceive,
        vendorReady: readyToCall || readyToReceive,
        overallStatus: deriveOverallStatus("Outbound", configComplete, accessOk),
        isActive,
        usesCanonicalPassThrough: usesCanonicalOutbound,
        effectiveMappingConfigured: hasOutboundMapping,
      });
    }

    if (!supportsInbound && !supportsOutbound) {
      rows.push({
        operationCode: op,
        operationVersion: version,
        direction: "Outbound",
        hasContract,
        hasMapping: hasOutboundMapping,
        hasEndpoint,
        endpointVerified,
        hasInboundConfig,
        hasOutboundConfig,
        hasAllowedInboundAccess: false,
        hasAllowedOutboundTarget: false,
        hasAccess: false,
        readyToCall: false,
        readyToReceive: false,
        vendorReady: false,
        overallStatus: "config_missing",
        isActive,
        usesCanonicalPassThrough: false,
        effectiveMappingConfigured: false,
      });
    }
  }

  return deduplicateRows(rows);
}

function deduplicateRows(rows: FlowReadinessRow[]): FlowReadinessRow[] {
  const seen = new Set<string>();
  return rows.filter((r) => {
    const key = `${r.operationCode}|${r.direction}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export type AccessDisplayStatus = "allowed" | "blocked" | "inactive" | "unknown";

export type ReadinessDisplay = { label: string; variant: StatusPillVariant; tooltip?: string };

/** Re-export for consumers that need the variant type */
export type { StatusPillVariant };

/** Canonical label for ready state. Use when comparing or displaying. */
export const READY_FOR_TRAFFIC_LABEL = "Ready for traffic";

/**
 * Display for a given overallStatus (for Home cards, filter chips, etc. where you don't have a full row).
 */
export function getDisplayForOverallStatus(status: OverallReadinessStatus): ReadinessDisplay {
  switch (status) {
    case "ready":
      return { label: READY_FOR_TRAFFIC_LABEL, variant: "configured" };
    case "config_missing":
      return {
        label: "Needs configuration",
        variant: "error",
        tooltip: "Complete the missing items above before you can use this operation in flows.",
      };
    case "access_blocked":
      return {
        label: "Blocked by access rules",
        variant: "warning",
        tooltip: "This operation is blocked by access rules. Contact the integration administrator to enable access.",
      };
    case "has_errors":
      return { label: "Has recent errors", variant: "warning" };
    default:
      return { label: "Needs configuration", variant: "error" };
  }
}

/**
 * Central display mapping for readiness → pill label + variant.
 * Use this everywhere readiness is shown (Home, Configuration, Flows, Flow Details).
 */
export function mapReadinessToDisplay(
  row: FlowReadinessRow,
  opts?: { hasRecentErrors?: boolean }
): ReadinessDisplay {
  if (!row.isActive) {
    return { label: "Inactive", variant: "neutral" };
  }
  if (row.vendorReady && opts?.hasRecentErrors) {
    return { label: "Has recent errors", variant: "warning" };
  }
  switch (row.overallStatus) {
    case "ready":
      return { label: READY_FOR_TRAFFIC_LABEL, variant: "configured" };
    case "config_missing":
      return {
        label: "Needs configuration",
        variant: "error",
        tooltip: "Complete the missing items above before you can use this operation in flows.",
      };
    case "access_blocked":
      return {
        label: "Blocked by access rules",
        variant: "warning",
        tooltip: "This operation is blocked by access rules. Contact the integration administrator to enable access.",
      };
    case "has_errors":
      return { label: "Has recent errors", variant: "warning" };
    default:
      return {
        label: "Needs configuration",
        variant: "error",
        tooltip: "Complete the missing items above before you can use this operation in flows.",
      };
  }
}

/** Alias for mapReadinessToDisplay – use for overall chip. */
export function getOverallStatus(
  row: FlowReadinessRow,
  opts?: { hasRecentErrors?: boolean }
): ReadinessDisplay {
  return mapReadinessToDisplay(row, opts);
}

/** @deprecated Use mapReadinessToDisplay instead */
export function getOverallDisplayStatus(row: FlowReadinessRow): ReadinessDisplay {
  return mapReadinessToDisplay(row);
}

/** For Configuration Overview Access column. Purely about allowlist – not tied to contract/mapping/endpoint. */
export function getAccessDisplayStatus(
  row: FlowReadinessRow,
  isLoading: boolean
): AccessDisplayStatus {
  if (isLoading) return "unknown";
  if (!row.isActive) return "inactive";
  return row.hasAccess ? "allowed" : "blocked";
}

/** Label for access outcome (Access control page, Configuration Overview). */
export function getAccessOutcomeLabel(accessOutcome?: AccessOutcome): string {
  return getAccessOutcomeDisplay(accessOutcome, "Outbound").label;
}

/** Optional narrow counts for "Allowed – narrowed (N of M)" display */
export interface AccessOutcomeNarrowCounts {
  narrowCount?: number;
  envelopeCount?: number;
}

/** Label + variant + tooltip for access outcome (vendor-facing). Use with StatusPill. */
export function getAccessOutcomeDisplay(
  accessOutcome?: AccessOutcome,
  _direction?: FlowReadinessDirection,
  narrowCounts?: AccessOutcomeNarrowCounts
): { label: string; variant: StatusPillVariant; tooltip: string } {
  switch (accessOutcome) {
    case "ALLOWED_BY_ADMIN":
      return {
        label: "Allowed by admin",
        variant: "configured",
        tooltip:
          "Admin access rules allow at least one licensee for this operation and direction. You can add your own rules to narrow which licensees you can call or be called by.",
      };
    case "ALLOWED_NARROWED_BY_VENDOR": {
      const n = narrowCounts?.narrowCount;
      const m = narrowCounts?.envelopeCount;
      const label =
        n != null && m != null && m > 0 ? `Allowed – narrowed by your rules (${n} of ${m})` : "Allowed – narrowed by your rules";
      return {
        label,
        variant: "configured",
        tooltip:
          "Admin access rules allow this operation. Your own access rules restrict which licensees you can call or be called by.",
      };
    }
    case "BLOCKED_BY_ADMIN":
      return {
        label: "Blocked by admin",
        variant: "warning",
        tooltip:
          "Admin has not allowed any licensees for this operation and direction yet. Contact the integration administrator to enable access before configuring flows.",
      };
    default:
      return { label: "—", variant: "neutral", tooltip: "" };
  }
}

/** FlowDimensionStatus for Contract/Endpoint/Mapping columns - matches FlowReadinessPill */
export type FlowDimensionStatus = "configured" | "partial" | "missing";

/** Map to display status for Contract column */
export function toContractStatus(hasContract: boolean): FlowDimensionStatus {
  return hasContract ? "configured" : "missing";
}

/** Map to display status for Mapping column */
export function toMappingStatus(hasMapping: boolean): FlowDimensionStatus {
  return hasMapping ? "configured" : "missing";
}

/** Map to display status for Endpoint column (partial = has endpoint but not verified). */
export function toEndpointStatus(
  hasEndpoint: boolean,
  endpointVerified: boolean,
  _direction: FlowReadinessDirection
): FlowDimensionStatus {
  if (!hasEndpoint) return "missing";
  return endpointVerified ? "configured" : "partial";
}

/** Display (label, variant, tooltip) for Contract column. Use with StatusPill. */
export function getContractStatusDisplay(hasContract: boolean): ReadinessDisplay {
  const status = toContractStatus(hasContract);
  const label = status === "configured" ? "Configured" : "Missing";
  const variant: StatusPillVariant = status === "configured" ? "configured" : "error";
  const tooltip =
    status === "configured"
      ? "Vendor contract is configured."
      : "Contract not yet configured. Add from canonical operations.";
  return { label, variant, tooltip };
}

/** Display (label, variant, tooltip) for Endpoint column. Use with StatusPill. */
export function getEndpointStatusDisplay(
  hasEndpoint: boolean,
  endpointVerified: boolean,
  _direction: FlowReadinessDirection
): ReadinessDisplay {
  const status = toEndpointStatus(hasEndpoint, endpointVerified, "Outbound");
  const label =
    status === "configured" ? "Configured" : status === "partial" ? "Partial" : "Missing";
  const variant: StatusPillVariant =
    status === "configured" ? "configured" : status === "partial" ? "warning" : "error";
  const tooltip =
    !hasEndpoint
      ? "Endpoint URL is required. Configure in Auth & Endpoints."
      : endpointVerified
        ? "Endpoint verified and ready."
        : "Endpoint pending verification.";
  return { label, variant, tooltip };
}

/** Display (label, variant, tooltip) for Mapping column. Use with StatusPill. */
export function getMappingStatusDisplay(
  hasMapping: boolean,
  usesCanonicalPassThrough?: boolean,
  effectiveMappingConfigured?: boolean
): ReadinessDisplay {
  const isConfigured = effectiveMappingConfigured ?? hasMapping;
  const status = toMappingStatus(isConfigured);
  const label =
    status === "configured"
      ? usesCanonicalPassThrough
        ? "Using canonical format"
        : "Configured"
      : "Missing";
  const variant: StatusPillVariant = status === "configured" ? "configured" : "error";
  const tooltip =
    status === "configured"
      ? usesCanonicalPassThrough
        ? "Mapping uses canonical pass-through. No changes required."
        : "Request and response mappings are configured."
      : "Mapping not yet configured. Add request and response mappings in the Flow Builder.";
  return { label, variant, tooltip };
}

/** CTA text for Home readiness card when status is ready. */
export function getReadinessReadyCta(readyCount: number): string {
  return readyCount === 0 ? "No operations are ready yet" : "All checks passed";
}

/** CTA text for Home readiness card when status is config_missing. */
export function getReadinessConfigMissingCta(): string {
  return "Fix contract, mapping, or endpoint";
}

/** CTA text for Home readiness card when status is access_blocked. */
export function getReadinessAccessBlockedCta(): string {
  return "Update access control";
}

/** Label for admin-pending flow health state. */
export function getFlowHealthAdminPendingLabel(): string {
  return "Admin pending";
}

/** Label for status filter (Flows page). Uses getDisplayForOverallStatus. */
export function getStatusFilterLabel(
  value: "all" | "healthy" | "has_errors" | "needs_attention"
): string {
  if (value === "all") return "All";
  return getDisplayForOverallStatus(
    value === "healthy" ? "ready" : value === "has_errors" ? "has_errors" : "config_missing"
  ).label;
}

/** Label for Configuration Overview status filter dropdown. */
export function getConfigurationStatusFilterLabel(
  value: "all" | "ok" | "partial" | "not_configured"
): string {
  if (value === "all") return "All statuses";
  if (value === "ok") return getDisplayForOverallStatus("ready").label;
  if (value === "not_configured") return getDisplayForOverallStatus("config_missing").label;
  if (value === "partial") return getFlowDimensionLabel("partial");
  return "All statuses";
}

/** Label for FlowDimensionStatus (Configured, Partial, Missing). Used by FlowReadinessPill. */
export function getFlowDimensionLabel(status: FlowDimensionStatus): string {
  const labels: Record<FlowDimensionStatus, string> = {
    configured: "Configured",
    partial: "Partial",
    missing: "Missing",
  };
  return labels[status] ?? "Missing";
}

/** Display for MappingStatusChip. Mapping-specific labels. */
export type MappingStatusChipStatus =
  | "ok"
  | "ok_canonical_passthrough"
  | "warning_optional_missing"
  | "error_required_missing"
  | "not_configured";

export function getMappingStatusChipDisplay(
  status: MappingStatusChipStatus
): { label: string; variant: StatusPillVariant } {
  switch (status) {
    case "ok":
      return { label: "Configured", variant: "configured" };
    case "ok_canonical_passthrough":
      return { label: "Using canonical format", variant: "configured" };
    case "warning_optional_missing":
      return { label: "Using canonical format", variant: "info" };
    case "error_required_missing":
      return { label: "Mapping required", variant: "error" };
    case "not_configured":
    default:
      return { label: "Not configured", variant: "neutral" };
  }
}

/** Subtitle for pipeline stage when using canonical passthrough. */
export function getUsingCanonicalFormatLabel(): string {
  return "Using canonical format";
}

export type EndpointHealth = "healthy" | "error" | "inactive" | "not_verified";

/** Derive endpoint health from legacy fields when endpointHealth is not yet from backend. */
export function deriveHealthFromLegacyFields(
  verificationStatus?: string,
  isActive?: boolean,
  status?: string
): EndpointHealth {
  if (isActive === false) return "inactive";
  const s = (verificationStatus ?? "").toUpperCase();
  const st = (status ?? "").toLowerCase();
  if (st === "healthy" || s === "VERIFIED" || s === "OK" || s === "SUCCESS") return "healthy";
  if (st === "error" || s === "FAILED" || s === "FAILURE" || s === "ERROR") return "error";
  return "not_verified";
}

/** Display for endpoint verification status. Used by Auth & Endpoints, EndpointSummaryPanel.
 * Do NOT use authProfileId – no-auth endpoints that verify successfully show as Verified. */
export function getEndpointVerificationDisplay(
  verificationStatus?: string,
  isActive?: boolean,
  endpointHealth?: EndpointHealth
): { label: string; variant: StatusPillVariant } {
  const health =
    endpointHealth ?? deriveHealthFromLegacyFields(verificationStatus, isActive);

  if (health === "inactive") return { label: "Inactive", variant: "neutral" };
  if (health === "healthy") return { label: "Verified", variant: "configured" };
  if (health === "error") return { label: "Verification failed", variant: "error" };
  return { label: "Not verified", variant: "warning" };
}

/** Labels for operation readiness views. */
export function getMyOperationsContractLabel(
  status: string | undefined
): string {
  if (status === "OK") return "OK";
  if (status === "INACTIVE") return "Inactive";
  return getFlowDimensionLabel("missing");
}

export function getMyOperationsMappingMissingLabel(
  type: "both" | "request" | "response"
): string {
  return type === "both"
    ? `${getFlowDimensionLabel("missing")} (both)`
    : type === "request"
      ? `${getFlowDimensionLabel("missing")} (request)`
      : `${getFlowDimensionLabel("missing")} (response)`;
}

export function getMyOperationsEndpointLabel(
  direction: string,
  status: string | undefined
): string {
  if (direction === "inbound") return "—";
  if (status === "OK") return "OK";
  if (status === "UNVERIFIED") return "Unverified";
  return getFlowDimensionLabel("missing");
}

export function getMyOperationsAllowlistLabel(status: string | undefined): string {
  if (status === "OK") return "OK";
  return getFlowDimensionLabel("missing");
}

/** Label for ChecklistCard status (ok/partial/missing). */
export function getChecklistStatusLabel(status: "ok" | "partial" | "missing"): string {
  switch (status) {
    case "ok":
      return "Ready";
    case "partial":
      return "Needs Attention";
    case "missing":
      return "Not Configured";
    default:
      return "Not Configured";
  }
}

/** Whether the Run test button in Flow Builder Test tab should be enabled. Uses same stage logic as Overview. */
export function canRunTest(row: FlowReadinessRow | null): {
  allowed: boolean;
  reason?: string;
} {
  if (!row) return { allowed: false, reason: "Configuration not loaded. Configure this flow before running tests." };
  const contractStatus = toContractStatus(row.hasContract);
  const endpointStatus = toEndpointStatus(row.hasEndpoint, row.endpointVerified, row.direction);
  if (contractStatus !== "configured") {
    return { allowed: false, reason: "Contract not configured yet. Configure the contract to run tests." };
  }
  if (endpointStatus !== "configured") {
    return { allowed: false, reason: "Endpoint not configured yet. Configure an endpoint to run tests." };
  }
  return { allowed: true };
}
