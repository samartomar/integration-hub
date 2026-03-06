/**
 * Derive licensee activity per-day buckets for heatmap.
 * TODO: prefer GET /v1/vendor/metrics/licensee-activity?range=7d when available.
 */

import type { VendorTransaction } from "../api/endpoints";

function getOtherLicensee(t: VendorTransaction, myCode: string): string | null {
  const src = (t.sourceVendor ?? "").trim();
  const tgt = (t.targetVendor ?? "").trim();
  const me = (myCode ?? "").trim();
  if (!me || (!src && !tgt)) return null;
  if (src === me && tgt && tgt !== me) return tgt;
  if (tgt === me && src && src !== me) return src;
  return null;
}

function toYYYYMMDD(iso: string): string {
  const d = new Date(iso);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export interface LicenseeDayBucket {
  licenseeCode: string;
  licenseeName: string;
  day: string;
  count: number;
}

/**
 * Group transactions by (licenseeCode, day) and count.
 * licenseeName defaults to code; TODO: resolve from vendor registry.
 */
export function licenseeActivityBucketsFromTransactions(
  transactions: VendorTransaction[],
  myVendorCode: string
): LicenseeDayBucket[] {
  const map = new Map<string, number>();

  for (const t of transactions) {
    const code = getOtherLicensee(t, myVendorCode);
    if (!code) continue;

    const day = t.createdAt ? toYYYYMMDD(t.createdAt) : "";
    if (!day) continue;

    const key = `${code}|${day}`;
    map.set(key, (map.get(key) ?? 0) + 1);
  }

  const result: LicenseeDayBucket[] = [];
  for (const [key, count] of map) {
    const [licenseeCode, day] = key.split("|");
    result.push({
      licenseeCode,
      licenseeName: licenseeCode,
      day,
      count,
    });
  }
  return result;
}

export interface LicenseeHeatmapRow {
  licenseeCode: string;
  licenseeName: string;
  days: Record<string, number>;
  total: number;
}

/**
 * Build heatmap rows: top N licensees by total volume, with per-day counts.
 */
export function buildHeatmapRows(
  buckets: LicenseeDayBucket[],
  _dayLabels: string[],
  topN: number
): LicenseeHeatmapRow[] {
  const byLicensee = new Map<string, { name: string; days: Record<string, number>; total: number }>();

  for (const b of buckets) {
    const existing = byLicensee.get(b.licenseeCode);
    if (existing) {
      existing.days[b.day] = (existing.days[b.day] ?? 0) + b.count;
      existing.total += b.count;
    } else {
      const days: Record<string, number> = { [b.day]: b.count };
      byLicensee.set(b.licenseeCode, {
        name: b.licenseeName,
        days,
        total: b.count,
      });
    }
  }

  const rows = Array.from(byLicensee.entries())
    .map(([code, { name, days, total }]) => ({ licenseeCode: code, licenseeName: name, days, total }))
    .sort((a, b) => b.total - a.total)
    .slice(0, topN);

  return rows;
}
