/**
 * Top Licensees card for Home – aggregates transactions by counterparty (last 7 days).
 * Self-contained: owns its useQuery to listVendorTransactions.
 */

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getActiveVendorCode } from "frontend-shared";
import { listVendorTransactions } from "../../api/endpoints";
import { homeTopLicenseesKey, STALE_HIGH_CHURN } from "../../api/queryKeys";
import { toISORangeDays } from "../../utils/dateRange";
import {
  aggregateLicenseesFromTransactions,
  type LicenseeAggregate,
} from "../../utils/topLicenseesFromTransactions";
import { VendorStatCardSkeleton } from "../vendor/skeleton";

const TOP_N = 3;

export function TopLicenseesCard() {
  const activeVendor = getActiveVendorCode();
  const hasKey = !!activeVendor;
  const range7d = useMemo(() => toISORangeDays(new Date(), 7), []);

  const { data, isLoading, error } = useQuery({
    queryKey: homeTopLicenseesKey(range7d.fromStr, range7d.toStr),
    queryFn: () =>
      listVendorTransactions({
        from: range7d.fromStr,
        to: range7d.toStr,
        direction: "all",
        limit: 200,
      }),
    enabled: !!activeVendor && hasKey,
    retry: false,
    staleTime: STALE_HIGH_CHURN,
  });

  const topLicensees: LicenseeAggregate[] = useMemo(() => {
    if (!data?.transactions || !activeVendor) return [];
    const agg = aggregateLicenseesFromTransactions(data.transactions, activeVendor);
    return agg.slice(0, TOP_N);
  }, [data?.transactions, activeVendor]);

  if (!activeVendor || !hasKey) {
    return null;
  }

  if (error) {
    console.error("TopLicenseesCard: failed to load licensee stats", error);
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-900">Top licensees</h3>
          <span className="text-xs text-slate-500">Last 7 days</span>
        </div>
        <p className="mt-3 text-sm text-slate-500">Could not load licensee stats.</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-900">Top licensees</h3>
          <span className="text-xs text-slate-500">Last 7 days</span>
        </div>
        <VendorStatCardSkeleton className="mt-3 border-0 p-0 shadow-none" />
      </div>
    );
  }

  if (topLicensees.length === 0) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-900">Top licensees</h3>
          <span className="text-xs text-slate-500">Last 7 days</span>
        </div>
        <p className="mt-3 text-center text-sm text-slate-500">
          No licensees with traffic in the last 7 days. Try running a test from Execute.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900">Top licensees</h3>
        <span className="text-xs text-slate-500">Last 7 days</span>
      </div>
      <ul className="mt-3 space-y-0">
        {topLicensees.map((agg) => (
          <li key={agg.licenseeCode} className="flex items-center justify-between py-1.5">
            <div className="min-w-0 flex-1">
              <span className="text-sm font-medium text-slate-900">{agg.licenseeName || agg.licenseeCode}</span>
              <p className="text-xs text-slate-500">
                {agg.totalVolume} calls · {agg.errorRate.toFixed(1)}% error rate
              </p>
            </div>
            <span className="ml-2 shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
              {agg.direction}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
