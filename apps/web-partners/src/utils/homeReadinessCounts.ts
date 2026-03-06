/**
 * Derive readiness counts for Home dashboard from FlowReadinessRow.
 * Used by VendorDashboard to show Ready / Blocked by config / Blocked by access.
 */

import type { FlowReadinessRow } from "./readinessModel";

export interface HomeReadinessCounts {
  ready: number;
  blockedByConfig: number;
  blockedByAccess: number;
  total: number;
}

/**
 * Count rows by readiness category.
 * - Ready: vendorReady && isActive
 * - Blocked by config: vendorReady === false AND at least one of contract/mapping/endpoint missing
 * - Blocked by access: config complete (for that direction) AND access blocked
 */
export function computeHomeReadinessCounts(rows: FlowReadinessRow[]): HomeReadinessCounts {
  let ready = 0;
  let blockedByConfig = 0;
  let blockedByAccess = 0;

  for (const row of rows) {
    const configComplete =
      (row.direction === "Inbound" && row.hasInboundConfig) ||
      (row.direction === "Outbound" && row.hasOutboundConfig);
    const hasConfigIssue =
      (row.direction === "Inbound" && !row.hasInboundConfig) ||
      (row.direction === "Outbound" && !row.hasOutboundConfig);

    const accessBlocked =
      row.direction === "Inbound"
        ? configComplete && !row.hasAllowedInboundAccess
        : configComplete && !row.hasAllowedOutboundTarget;

    if (row.isActive && row.vendorReady) {
      ready++;
    }
    if (!row.vendorReady && hasConfigIssue) {
      blockedByConfig++;
    }
    if (accessBlocked) {
      blockedByAccess++;
    }
  }

  return { ready, blockedByConfig, blockedByAccess, total: rows.length };
}
