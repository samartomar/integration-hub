/**
 * Welcome header for Home – vendor name, readiness summary, last activity.
 */

import { useQuery } from "@tanstack/react-query";
import { getActiveVendorCode } from "frontend-shared";
import { listVendors } from "../../api/endpoints";
import { canonicalVendorsKey, STALE_CONFIG } from "../../api/queryKeys";

function formatLastActivity(iso: string | null): string {
  if (!iso) return "No traffic in the last 24 hours yet";
  try {
    const d = new Date(iso);
    const diffMs = Date.now() - d.getTime();
    const mins = Math.floor(diffMs / 60_000);
    const hours = Math.floor(diffMs / 3_600_000);
    if (mins < 60) return `${mins} min ago`;
    if (hours < 24) return `${hours} hr ago`;
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return "No traffic in the last 24 hours yet";
  }
}

interface WelcomeHeaderProps {
  readyCount: number;
  totalCount: number;
  lastActivityIso: string | null;
}

export function WelcomeHeader({ readyCount, totalCount, lastActivityIso }: WelcomeHeaderProps) {
  const activeVendor = getActiveVendorCode();
  const { data: vendorsData } = useQuery({
    queryKey: canonicalVendorsKey,
    queryFn: () => listVendors({ limit: 200 }),
    staleTime: STALE_CONFIG,
  });
  const vendors = vendorsData?.items ?? [];
  const vendorDisplay = activeVendor
    ? vendors.find((v) => (v.vendorCode ?? "").toUpperCase() === activeVendor.toUpperCase())?.vendorName ?? activeVendor
    : activeVendor;

  return (
    <section className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold text-slate-900">Home</h1>
        <p className="mt-1 text-sm text-slate-600">
          Cross-operation health and recent activity. Use <span className="font-medium">Flows</span> for per-operation deep dives.
        </p>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        <div className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 shadow-sm">
          {vendorDisplay ?? activeVendor}
        </div>
        <p className="text-xs text-slate-500">
          {readyCount} / {totalCount} operations ready
        </p>
        <p className="text-xs text-slate-500">{formatLastActivity(lastActivityIso)}</p>
      </div>
    </section>
  );
}
