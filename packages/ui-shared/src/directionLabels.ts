/**
 * Shared direction labels for Admin and Vendor portals.
 * - Admin: source/target language
 * - Vendor: "my system" / "other licensees" language
 */

export type FlowDirection = "OUTBOUND" | "INBOUND" | "BOTH";

/** Admin perspective: OUTBOUND / INBOUND vocabulary */
export function getAdminDirectionLabel(dir: FlowDirection): string {
  switch (dir) {
    case "OUTBOUND":
      return "OUTBOUND";
    case "INBOUND":
      return "INBOUND";
    case "BOTH":
      return "BOTH";
    default:
      return "";
  }
}

/** Admin perspective: tooltip for direction badges */
export function getAdminDirectionBadgeTooltip(dir: FlowDirection): string {
  switch (dir) {
    case "OUTBOUND":
      return "Source sends requests to target on this operation.";
    case "INBOUND":
      return "Target receives requests from source on this operation.";
    case "BOTH":
      return "Source and target can both send and receive on this operation.";
    default:
      return "";
  }
}

/** Admin allowlist modal: radio title (bold line) */
export function getAdminDirectionRadioTitle(dir: FlowDirection): string {
  switch (dir) {
    case "OUTBOUND":
      return "Send requests – source calls target";
    case "INBOUND":
      return "Receive requests – target is called by source";
    case "BOTH":
      return "Two-way – send & receive between source and target";
    default:
      return "";
  }
}


/** Vendor perspective: raw vocabulary OUTBOUND / INBOUND */
export function getVendorDirectionLabel(dir: FlowDirection): string {
  switch (dir) {
    case "OUTBOUND":
      return "OUTBOUND";
    case "INBOUND":
      return "INBOUND";
    case "BOTH":
      return "BOTH";
    default:
      return "";
  }
}

/** Direction policy: map to OUTBOUND/INBOUND for display. No "Provider receives only". */
export function getDirectionPolicyLabel(policy: string | undefined): string {
  const p = (policy || "").toUpperCase().trim();
  if (p === "PROVIDER_RECEIVES_ONLY" || p === "SERVICE_OUTBOUND_ONLY") return "INBOUND";
  if (p === "TWO_WAY" || p === "EXCHANGE_BIDIRECTIONAL") return "BOTH";
  return "";
}

/** @deprecated Use getDirectionPolicyLabel */
export const getHubDirectionPolicyLabel = getDirectionPolicyLabel;

/** Direction policy: constraint tooltip for allowlist modal */
export function getDirectionPolicyConstraintTooltip(policy: string | undefined): string | undefined {
  const p = (policy || "").toUpperCase().trim();
  if (p === "PROVIDER_RECEIVES_ONLY" || p === "SERVICE_OUTBOUND_ONLY") {
    return "INBOUND: provider receives.";
  }
  if (p === "TWO_WAY" || p === "EXCHANGE_BIDIRECTIONAL") {
    return "BOTH: either direction.";
  }
  return undefined;
}

/** @deprecated Use getDirectionPolicyConstraintTooltip */
export const getHubDirectionPolicyConstraintTooltip = getDirectionPolicyConstraintTooltip;

/** Vendor perspective: filter dropdown labels - OUTBOUND / INBOUND */
export function getVendorDirectionFilterLabel(dir: FlowDirection): string {
  switch (dir) {
    case "OUTBOUND":
      return "OUTBOUND";
    case "INBOUND":
      return "INBOUND";
    case "BOTH":
      return "BOTH";
    default:
      return "";
  }
}
