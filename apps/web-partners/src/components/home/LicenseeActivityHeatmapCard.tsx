/**
 * Licensee activity heatmap – which licensees are active in the last 7 days.
 * TODO: Prefer GET /v1/vendor/metrics/licensee-activity?range=7d when available.
 * Currently derives from listVendorTransactions (last 7 days).
 */

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getActiveVendorCode } from "frontend-shared";
import { listVendorTransactions } from "../../api/endpoints";
import { homeTopLicenseesKey, STALE_HIGH_CHURN } from "../../api/queryKeys";
import { toISORangeDays } from "../../utils/dateRange";
import {
  licenseeActivityBucketsFromTransactions,
  buildHeatmapRows,
} from "../../utils/licenseeActivityHeatmap";
import { VendorChartSkeleton } from "../vendor/skeleton";

const TOP_N = 5;

function getLast7DayLabels(): string[] {
  const labels: string[] = [];
  const now = new Date();
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    labels.push(`${y}-${m}-${day}`);
  }
  return labels;
}

export function LicenseeActivityHeatmapCard() {
  const activeVendor = getActiveVendorCode();
  const hasKey = !!activeVendor;
  const range7d = useMemo(() => toISORangeDays(new Date(), 7), []);
  const dayLabels = useMemo(() => getLast7DayLabels(), []);

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

  const heatmapRows = useMemo(() => {
    if (!data?.transactions || !activeVendor) return [];
    const buckets = licenseeActivityBucketsFromTransactions(data.transactions, activeVendor);
    return buildHeatmapRows(buckets, dayLabels, TOP_N);
  }, [data?.transactions, activeVendor, dayLabels]);

  const maxCount = useMemo(() => {
    let max = 0;
    for (const row of heatmapRows) {
      for (const day of dayLabels) {
        const c = row.days[day] ?? 0;
        if (c > max) max = c;
      }
    }
    return max;
  }, [heatmapRows, dayLabels]);

  if (!activeVendor || !hasKey) return null;

  if (error) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-900">Licensee activity</h3>
          <span className="text-xs text-slate-500">Last 7 days</span>
        </div>
        <p className="mt-3 text-sm text-slate-500">Could not load licensee activity.</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-900">Licensee activity</h3>
          <span className="text-xs text-slate-500">Last 7 days</span>
        </div>
        <VendorChartSkeleton className="mt-3 h-40 border-0 p-0" />
      </div>
    );
  }

  if (heatmapRows.length === 0) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-900">Licensee activity</h3>
          <span className="text-xs text-slate-500">Last 7 days</span>
        </div>
        <p className="mt-3 text-center text-sm text-slate-500">
          No licensee traffic in the last 7 days. Try running a test from Execute.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900">Licensee activity</h3>
        <span className="text-xs text-slate-500">Last 7 days</span>
      </div>

      <div className="mt-3 overflow-x-auto">
        <div className="min-w-[240px]">
          <table className="w-full text-left text-xs">
            <thead>
              <tr>
                <th className="py-1 pr-2 font-medium text-slate-500" />
                {dayLabels.map((d) => (
                  <th key={d} className="py-1 text-center font-medium text-slate-500" title={d}>
                    {new Date(d).toLocaleDateString(undefined, { month: "numeric", day: "numeric" })}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {heatmapRows.map((row) => (
                <tr key={row.licenseeCode}>
                  <td className="py-1 pr-2 font-medium text-slate-900 truncate max-w-[100px]">
                    {row.licenseeName || row.licenseeCode}
                  </td>
                  {dayLabels.map((day) => {
                    const count = row.days[day] ?? 0;
                    const intensity = maxCount > 0 ? count / maxCount : 0;
                    const opacity = intensity === 0 ? 0.15 : 0.2 + intensity * 0.8;
                    return (
                      <td key={day} className="p-0.5">
                        <div
                          className="flex h-6 w-6 min-w-6 items-center justify-center rounded mx-auto"
                          style={{ backgroundColor: `rgba(99, 102, 241, ${opacity})` }}
                          title={`${count} calls`}
                        >
                          {count > 0 && <span className="text-[10px] font-medium text-white">{count}</span>}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-2 flex items-center gap-2 text-[10px] text-slate-500">
          <span>Lower volume</span>
          <div className="flex gap-0.5">
            {[0.2, 0.5, 0.8, 1].map((q) => (
              <div
                key={q}
                className="h-3 w-3 rounded"
                style={{ backgroundColor: `rgba(99, 102, 241, ${0.2 + q * 0.8})` }}
              />
            ))}
          </div>
          <span>Higher volume</span>
        </div>
      </div>
    </div>
  );
}
