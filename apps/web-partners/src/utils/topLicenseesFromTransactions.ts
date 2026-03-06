/**
 * Aggregate transactions into licensee stats for Top Licensees card.
 * Uses sourceVendor/targetVendor to identify the "other" licensee per transaction.
 */

import type { VendorTransaction } from "../api/endpoints";

const COMPLETED_STATUS = "completed";

export interface LicenseeAggregate {
  licenseeCode: string;
  licenseeName: string;
  totalVolume: number;
  failedVolume: number;
  errorRate: number;
  lastSeenAt: string | null;
  /** "Inbound" | "Outbound" | "Mixed" */
  direction: "Inbound" | "Outbound" | "Mixed";
}

/**
 * For a transaction, get the "other" licensee (counterparty) and direction.
 * If I am sourceVendor → other is targetVendor, direction Outbound.
 * If I am targetVendor → other is sourceVendor, direction Inbound.
 * TODO: API may add otherLicenseeCode/otherLicenseeName; use those when available.
 */
function getOtherLicenseeAndDirection(
  t: VendorTransaction,
  myCode: string
): { code: string; direction: "Inbound" | "Outbound" } | null {
  const src = (t.sourceVendor ?? "").trim();
  const tgt = (t.targetVendor ?? "").trim();
  const me = (myCode ?? "").trim();
  if (!me || (!src && !tgt)) return null;

  if (src === me && tgt && tgt !== me) {
    return { code: tgt, direction: "Outbound" };
  }
  if (tgt === me && src && src !== me) {
    return { code: src, direction: "Inbound" };
  }
  return null;
}

/**
 * Aggregate transactions into licensee aggregates.
 * Groups by licenseeCode, computes totalVolume, failedVolume, errorRate, lastSeenAt, direction.
 * Sorted by totalVolume descending.
 */
export function aggregateLicenseesFromTransactions(
  transactions: VendorTransaction[],
  myVendorCode: string
): LicenseeAggregate[] {
  const map = new Map<string, { total: number; failed: number; lastSeen: string | null; inbound: boolean; outbound: boolean }>();

  for (const t of transactions) {
    const info = getOtherLicenseeAndDirection(t, myVendorCode);
    if (!info) continue;

    const existing = map.get(info.code);
    const failed = (t.status ?? "").toLowerCase() !== COMPLETED_STATUS;
    const last = t.createdAt ?? null;

    if (existing) {
      existing.total += 1;
      if (failed) existing.failed += 1;
      if (last && (!existing.lastSeen || last > existing.lastSeen)) {
        existing.lastSeen = last;
      }
      if (info.direction === "Inbound") existing.inbound = true;
      else existing.outbound = true;
    } else {
      map.set(info.code, {
        total: 1,
        failed: failed ? 1 : 0,
        lastSeen: last,
        inbound: info.direction === "Inbound",
        outbound: info.direction === "Outbound",
      });
    }
  }

  const result: LicenseeAggregate[] = [];
  for (const [code, stats] of map) {
    const direction: "Inbound" | "Outbound" | "Mixed" =
      stats.inbound && stats.outbound ? "Mixed" : stats.inbound ? "Inbound" : "Outbound";
    result.push({
      licenseeCode: code,
      licenseeName: code, // TODO: use vendor name from API when available
      totalVolume: stats.total,
      failedVolume: stats.failed,
      errorRate: stats.total > 0 ? (stats.failed / stats.total) * 100 : 0,
      lastSeenAt: stats.lastSeen,
      direction,
    });
  }

  result.sort((a, b) => b.totalVolume - a.totalVolume);
  return result;
}
