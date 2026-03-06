/**
 * Vendor Home – readiness snapshot, activity, recent transactions.
 * Home = cross-operation health + recent activity + next actions.
 * Flows = per-operation SRE view (see VendorFlowsPage).
 */

import { useState, useMemo, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  getActiveVendorCode,
} from "frontend-shared";
import {
  getVendorMetricsOverview,
  listVendorTransactions,
  getVendorTransactionDetail,
  getVendorContracts,
  getVendorOperationsCatalog,
  getVendorSupportedOperations,
  getVendorEndpoints,
  getVendorMappings,
  getMyAllowlist,
  getMyOperations,
} from "../api/endpoints";
import { useVendorConfigBundle } from "../hooks/useVendorConfigBundle";
import { StatusPill, type StatusPillVariant } from "frontend-shared";
import { TransactionDetailsDrawer, vendorDetailToTransactionDetails } from "../components/TransactionDetailsDrawer";
import { TopLicenseesCard } from "../components/home/TopLicenseesCard";
import { WelcomeHeader } from "../components/home/WelcomeHeader";
import { ReadinessTimelineCard } from "../components/home/ReadinessTimelineCard";
import { LicenseeActivityHeatmapCard } from "../components/home/LicenseeActivityHeatmapCard";
import {
  vendorMetricsKey,
  vendorTransactionsKey,
  vendorTransactionDetailKey,
  STALE_HIGH_CHURN,
  STALE_CONFIG,
} from "../api/queryKeys";
import { toISORange } from "../utils/dateRange";
import {
  buildReadinessRowsForLicensee,
  getDisplayForOverallStatus,
  getReadinessReadyCta,
  getReadinessConfigMissingCta,
  getReadinessAccessBlockedCta,
} from "../utils/readinessModel";
import { getAdminDirectionLabel } from "frontend-shared";
import { VendorPageLayout } from "../components/layout/VendorPageLayout";
import { computeHomeReadinessCounts } from "../utils/homeReadinessCounts";
import { Skeleton } from "frontend-shared";
import {
  VendorStatCardSkeleton,
} from "../components/vendor/skeleton";

const COMPLETED_STATUS = "completed";

function formatShortDate(iso?: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

/** Simple "X minutes/hours ago" without date-fns. */
function formatDistanceToNow(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  if (diffMs < 0) return "just now";
  const mins = Math.floor(diffMs / 60_000);
  const hours = Math.floor(diffMs / 3_600_000);
  const days = Math.floor(diffMs / 86_400_000);
  if (mins < 1) return "less than a minute ago";
  if (mins < 60) return `${mins} minute${mins === 1 ? "" : "s"} ago`;
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  if (days < 7) return `${days} day${days === 1 ? "" : "s"} ago`;
  return formatShortDate(iso);
}

function statusToPill(status: string): { label: string; variant: StatusPillVariant } {
  const s = (status ?? "").toLowerCase();
  if (s === COMPLETED_STATUS) return { label: "Success", variant: "configured" };
  if (s === "validation_failed") return { label: "Validation error", variant: "error" };
  if (["downstream_error", "downstream_timeout", "mapping_failed"].includes(s)) return { label: "Integration error", variant: "error" };
  if (["received", "in_progress", "pending"].includes(s)) return { label: "Pending", variant: "warning" };
  return { label: status?.replace(/_/g, " ") ?? "Unknown", variant: "neutral" };
}

function getFlowDetailsPath(operationCode: string, range: { fromStr: string; toStr: string }): string {
  const p = new URLSearchParams();
  p.set("from", range.fromStr);
  p.set("to", range.toStr);
  return `/flows/${encodeURIComponent(operationCode)}?${p.toString()}`;
}

function IconCheck({ className = "h-3 w-3" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  );
}
function IconAlertTriangle({ className = "h-3 w-3" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
  );
}
function IconShieldOff({ className = "h-3 w-3" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
    </svg>
  );
}

export function VendorDashboard() {
  const navigate = useNavigate();
  const activeVendor = getActiveVendorCode();
  const hasKey = !!activeVendor;
  const [searchParams, setSearchParams] = useSearchParams();
  const txIdFromUrl = searchParams.get("transactionId");
  const [selectedTxId, setSelectedTxId] = useState<string | null>(txIdFromUrl);

  const range24h = useMemo(() => toISORange(new Date(), 24), []);

  useEffect(() => {
    if (txIdFromUrl) setSelectedTxId(txIdFromUrl);
  }, [txIdFromUrl]);

  // Config bundle: single call for all config slices; fallback to individual queries if bundle fails
  const {
    data: bundleData,
    isLoading: bundleLoading,
    isError: bundleError,
  } = useVendorConfigBundle(!!hasKey);

  const useIndividualConfig = hasKey && (bundleError || !bundleData);
  const { data: vendorContractsData } = useQuery({
    queryKey: ["vendor-contracts"],
    queryFn: () => getVendorContracts(),
    enabled: useIndividualConfig,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: catalogData, isLoading: catalogLoading } = useQuery({
    queryKey: ["vendor-operations-catalog"],
    queryFn: () => getVendorOperationsCatalog(),
    enabled: useIndividualConfig,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: supportedData } = useQuery({
    queryKey: ["vendor-supported-operations"],
    queryFn: () => getVendorSupportedOperations(),
    enabled: useIndividualConfig,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: endpointsData } = useQuery({
    queryKey: ["vendor-endpoints"],
    queryFn: () => getVendorEndpoints(),
    enabled: useIndividualConfig,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: mappingsData } = useQuery({
    queryKey: ["vendor-mappings"],
    queryFn: () => getVendorMappings(),
    enabled: useIndividualConfig,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: allowlistData } = useQuery({
    queryKey: ["my-allowlist", activeVendor ?? ""],
    queryFn: getMyAllowlist,
    enabled: !!activeVendor && useIndividualConfig,
    retry: false,
    staleTime: STALE_CONFIG,
  });
  const { data: myOpsData } = useQuery({
    queryKey: ["vendor-my-operations"],
    queryFn: getMyOperations,
    enabled: !!activeVendor && useIndividualConfig,
    staleTime: STALE_CONFIG,
  });

  const contracts = bundleData?.contracts ?? vendorContractsData?.items ?? [];
  const catalogItems = bundleData?.operationsCatalog ?? catalogData?.items ?? [];
  const supportedItems = bundleData?.supportedOperations ?? supportedData?.items ?? [];
  const endpointsItems = bundleData?.endpoints ?? endpointsData?.items ?? [];
  const mappingsItems = bundleData?.mappings ?? mappingsData?.mappings ?? [];
  const allowlist = bundleData?.myAllowlist ?? allowlistData;
  const myOps = bundleData?.myOperations ?? myOpsData;

  const configLoading = (bundleLoading && !bundleData) || (useIndividualConfig && catalogLoading);

  const flowReadinessRows = useMemo(
    () =>
      buildReadinessRowsForLicensee({
        supported: supportedItems,
        catalog: catalogItems,
        vendorContracts: contracts,
        endpoints: endpointsItems,
        mappings: mappingsItems,
        outboundAllowlist: allowlist?.outbound ?? [],
        inboundAllowlist: allowlist?.inbound ?? [],
        eligibleOperations: allowlist?.eligibleOperations,
        accessOutcomes: allowlist?.accessOutcomes,
        vendorCode: activeVendor ?? "",
        myOperationsOutbound: myOps?.outbound,
        myOperationsInbound: myOps?.inbound,
      }),
    [
      supportedItems,
      catalogItems,
      contracts,
      endpointsItems,
      mappingsItems,
      allowlist?.outbound,
      allowlist?.inbound,
      allowlist?.eligibleOperations,
      allowlist?.accessOutcomes,
      activeVendor,
      myOps?.outbound,
      myOps?.inbound,
    ]
  );

  const readinessCounts = useMemo(() => computeHomeReadinessCounts(flowReadinessRows), [flowReadinessRows]);

  // Activity snapshot – 24h metrics
  const { data: metrics24h, isLoading: metricsLoading } = useQuery({
    queryKey: vendorMetricsKey(range24h.fromStr, range24h.toStr),
    queryFn: () => getVendorMetricsOverview({ from: range24h.fromStr, to: range24h.toStr }),
    enabled: !!activeVendor && hasKey,
    retry: false,
    staleTime: STALE_HIGH_CHURN,
  });

  // Recent transactions – for lastActivity and table
  const { data: transactionsData, isLoading: transactionsLoading } = useQuery({
    queryKey: vendorTransactionsKey(range24h.fromStr, range24h.toStr, "all", null, null, null, null),
    queryFn: () =>
      listVendorTransactions({
        from: range24h.fromStr,
        to: range24h.toStr,
        direction: "all",
        limit: 50,
      }),
    enabled: !!activeVendor && hasKey,
    retry: false,
    staleTime: STALE_HIGH_CHURN,
  });

  const activityStats = useMemo(() => {
    const totals = metrics24h?.totals;
    const byOp = metrics24h?.byOperation ?? [];
    const completed = totals?.completed ?? 0;
    const failed = totals?.failed ?? 0;
    const total = totals?.count ?? completed + failed;
    const topOps = [...byOp]
      .filter((o) => (o.count ?? 0) > 0)
      .sort((a, b) => (b.count ?? 0) - (a.count ?? 0))
      .slice(0, 5)
      .map((o) => ({
        operationCode: o.operation ?? "—",
        total: o.count ?? 0,
        failed: o.failed ?? 0,
      }));
    return {
      totalVolume: total,
      errorRate: total > 0 ? (failed / total) * 100 : 0,
      activeOperations: byOp.filter((o) => (o.count ?? 0) > 0).length,
      topOperations: topOps,
    };
  }, [metrics24h]);

  const lastActivity = useMemo(() => {
    const list = (transactionsData?.transactions ?? []).slice();
    list.sort((a, b) => new Date(b.createdAt ?? 0).getTime() - new Date(a.createdAt ?? 0).getTime());
    return list[0]?.createdAt ?? null;
  }, [transactionsData?.transactions]);

  const recentTxns = useMemo(() => {
    const list = (transactionsData?.transactions ?? []).slice();
    list.sort((a, b) => new Date(b.createdAt ?? 0).getTime() - new Date(a.createdAt ?? 0).getTime());
    const failed = list.filter((t) => (t.status ?? "").toLowerCase() !== COMPLETED_STATUS);
    const completed = list.filter((t) => (t.status ?? "").toLowerCase() === COMPLETED_STATUS);
    return [...failed, ...completed].slice(0, 5);
  }, [transactionsData?.transactions]);

  const { data: detailData, isLoading: detailLoading } = useQuery({
    queryKey: selectedTxId ? vendorTransactionDetailKey(selectedTxId) : ["vendor-transaction-detail", null],
    queryFn: () => getVendorTransactionDetail(selectedTxId!),
    enabled: !!selectedTxId && !!activeVendor && hasKey,
    retry: false,
    staleTime: STALE_HIGH_CHURN,
  });

  const handleRowClick = (txId: string) => {
    setSelectedTxId(txId);
    setSearchParams((p) => {
      const next = new URLSearchParams(p);
      next.set("transactionId", txId);
      return next;
    });
  };

  const handleDrawerClose = () => {
    setSelectedTxId(null);
    setSearchParams((p) => {
      const next = new URLSearchParams(p);
      next.delete("transactionId");
      return next;
    });
  };

  if (!activeVendor) {
    return (
      <VendorPageLayout>
        <div className="rounded-lg bg-gray-50 border border-gray-200 p-4">
          <p className="text-sm font-medium text-gray-700">Select an active licensee above.</p>
        </div>
      </VendorPageLayout>
    );
  }

  return (
    <VendorPageLayout>
    <div className="space-y-6">
      <>
      {configLoading ? (
        <section className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="h-8 w-48 animate-pulse rounded bg-gray-200" />
            <div className="mt-2 h-4 w-96 animate-pulse rounded bg-gray-200" />
          </div>
          <div className="flex shrink-0 flex-col items-end gap-2">
            <div className="h-6 w-24 animate-pulse rounded-full bg-gray-200" />
            <div className="h-3 w-32 animate-pulse rounded bg-gray-200" />
            <div className="h-3 w-40 animate-pulse rounded bg-gray-200" />
          </div>
        </section>
      ) : (
        <WelcomeHeader
          readyCount={readinessCounts.ready}
          totalCount={readinessCounts.total}
          lastActivityIso={lastActivity}
        />
      )}

      <div className="space-y-6">
        {/* Readiness overview */}
        {configLoading ? (
          <section className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <div className="h-4 w-40 animate-pulse rounded bg-gray-200" />
              <div className="h-3 w-32 animate-pulse rounded bg-gray-200" />
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              {[...Array(3)].map((_, i) => (
                <VendorStatCardSkeleton key={i} />
              ))}
            </div>
          </section>
        ) : readinessCounts.total === 0 ? (
          <section className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-4">
            <p className="text-sm text-slate-600">
              No operations configured yet. Start by{" "}
              <button
                type="button"
                onClick={() => navigate("/configuration")}
                className="font-medium text-indigo-600 hover:text-indigo-500"
              >
                adding a canonical operation
              </button>
              .
            </p>
          </section>
        ) : (
          <section className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-base font-semibold text-slate-900">Readiness overview</h2>
              <p className="text-xs text-slate-500">Based on configuration and access rules.</p>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <button
                type="button"
                onClick={() => navigate("/configuration?status=ok")}
                className="flex flex-col items-start rounded-2xl border border-slate-200 bg-white px-4 py-4 text-left shadow-sm hover:border-slate-300 hover:bg-slate-50"
              >
                <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  {getDisplayForOverallStatus("ready").label}
                </span>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="text-2xl font-semibold text-slate-900">{readinessCounts.ready}</span>
                  <span className="text-xs text-slate-500">of {readinessCounts.total} operations</span>
                </div>
                <span className={`mt-2 inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-medium ${
                  readinessCounts.ready === 0
                    ? "bg-gray-100 text-gray-600"
                    : "bg-emerald-50 text-emerald-700"
                }`}>
                  <IconCheck className="h-3 w-3" />
                  {getReadinessReadyCta(readinessCounts.ready)}
                </span>
              </button>

              <button
                type="button"
                onClick={() => navigate("/configuration?status=not_configured")}
                className="flex flex-col items-start rounded-2xl border border-amber-100 bg-white px-4 py-4 text-left shadow-sm hover:border-amber-200 hover:bg-amber-50/60"
              >
                <span className="text-xs font-medium uppercase tracking-wide text-amber-700">
                  {getDisplayForOverallStatus("config_missing").label}
                </span>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="text-2xl font-semibold text-slate-900">{readinessCounts.blockedByConfig}</span>
                  <span className="text-xs text-slate-500">operations</span>
                </div>
                <span className="mt-2 inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-1 text-xs font-medium text-amber-800">
                  <IconAlertTriangle className="h-3 w-3" /> {getReadinessConfigMissingCta()}
                </span>
              </button>

              {/* TODO: wire up status=access-blocked filter once Configuration supports it. */}
              <button
                type="button"
                onClick={() => navigate("/configuration?status=access-blocked")}
                className="flex flex-col items-start rounded-2xl border border-rose-100 bg-white px-4 py-4 text-left shadow-sm hover:border-rose-200 hover:bg-rose-50/60"
              >
                <span className="text-xs font-medium uppercase tracking-wide text-rose-700">
                  {getDisplayForOverallStatus("access_blocked").label}
                </span>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="text-2xl font-semibold text-slate-900">{readinessCounts.blockedByAccess}</span>
                  <span className="text-xs text-slate-500">operations</span>
                </div>
                <span className="mt-2 inline-flex items-center gap-1 rounded-full bg-rose-100 px-2 py-1 text-xs font-medium text-rose-800">
                  <IconShieldOff className="h-3 w-3" /> {getReadinessAccessBlockedCta()}
                </span>
              </button>
            </div>
          </section>
        )}

        {/* Recent activity */}
        <section className="space-y-3">
          <h2 className="text-base font-semibold text-slate-900">Recent activity</h2>

          <div className="grid gap-4 grid-cols-1 lg:grid-cols-3">
            {metricsLoading || transactionsLoading ? (
              <>
                <VendorStatCardSkeleton className="shadow-sm" />
                <div className="rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
                  <div className="h-4 w-36 animate-pulse rounded bg-gray-200" />
                  <div className="mt-3 space-y-2">
                    {[...Array(4)].map((_, i) => (
                      <div key={i} className="h-4 w-full animate-pulse rounded bg-gray-200" />
                    ))}
                  </div>
                </div>
                <VendorStatCardSkeleton className="shadow-sm" />
              </>
            ) : (
              <>
            <div className="rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
              <h3 className="text-sm font-semibold text-slate-900">Summary (last 24h)</h3>
              <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
                <div>
                  <dt className="text-slate-500">Total volume</dt>
                  <dd className="mt-0.5 font-medium text-slate-900">{activityStats.totalVolume}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Error rate</dt>
                  <dd className="mt-0.5 font-medium text-slate-900">{activityStats.errorRate.toFixed(1)}%</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Active operations</dt>
                  <dd className="mt-0.5 font-medium text-slate-900">{activityStats.activeOperations}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Most recent traffic</dt>
                  <dd className="mt-0.5 text-slate-900">
                    {lastActivity
                      ? formatDistanceToNow(lastActivity)
                      : "No traffic in the last 24h"}
                  </dd>
                </div>
              </dl>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
              <h3 className="text-sm font-semibold text-slate-900">Top operations – last 24h</h3>
              {activityStats.topOperations.length === 0 ? (
                <p className="mt-3 text-sm text-slate-500">No traffic yet. Try running a test from Execute.</p>
              ) : (
                <ul className="mt-3 space-y-2">
                  {activityStats.topOperations.map((op) => (
                    <li
                      key={op.operationCode}
                      className="flex items-center justify-between gap-3 rounded-lg px-2 py-1.5 hover:bg-slate-50"
                    >
                      <button
                        type="button"
                        onClick={() => navigate(getFlowDetailsPath(op.operationCode, range24h))}
                        className="flex flex-1 flex-col items-start text-left"
                      >
                        <span className="text-sm font-medium text-slate-900">{op.operationCode}</span>
                        <span className="text-xs text-slate-500">
                          {op.total} total · {op.failed} failed
                        </span>
                      </button>
                      <span className="text-xs font-medium text-slate-600">{op.total}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <TopLicenseesCard />
              </>
            )}
          </div>
        </section>

        {/* Timeline + Heatmap */}
        <div className="grid gap-4 grid-cols-1 md:grid-cols-2">
          <ReadinessTimelineCard />
          <LicenseeActivityHeatmapCard />
        </div>

        {/* Recent transactions */}
        <section className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-base font-semibold text-slate-900">Recent transactions</h2>
            <button
              type="button"
              onClick={() => navigate("/transactions")}
              className="text-xs font-medium text-indigo-600 hover:text-indigo-500"
            >
              View all transactions →
            </button>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200">
                <thead>
                  <tr className="bg-slate-50">
                    <th className="px-4 py-2 text-left text-xs font-medium text-slate-500 uppercase">Created</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-slate-500 uppercase">Operation</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-slate-500 uppercase">Direction</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-slate-500 uppercase">Status</th>
                    <th className="px-4 py-2 text-right text-xs font-medium text-slate-500 uppercase">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {transactionsLoading ? (
                    [...Array(5)].map((_, i) => (
                      <tr key={i}>
                        {[...Array(5)].map((_, j) => (
                          <td key={j} className="px-4 py-3">
                            <Skeleton className="h-4 w-full" />
                          </td>
                        ))}
                      </tr>
                    ))
                  ) : recentTxns.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-8 text-center text-sm text-slate-500">
                        No transactions yet. Try running a test from <span className="font-medium">Execute</span>.
                      </td>
                    </tr>
                  ) : (
                    recentTxns.map((t) => {
                      const pill = statusToPill(t.status ?? "unknown");
                      const dir =
                        t.sourceVendor === activeVendor
                          ? getAdminDirectionLabel("OUTBOUND")
                          : getAdminDirectionLabel("INBOUND");
                      const txId = t.transactionId ?? t.id ?? "";
                      return (
                        <tr
                          key={txId}
                          onClick={() => handleRowClick(txId)}
                          className="hover:bg-slate-50 cursor-pointer transition-colors"
                        >
                          <td className="px-4 py-3 text-sm text-slate-600 whitespace-nowrap">
                            {formatShortDate(t.createdAt)}
                          </td>
                          <td className="px-4 py-3 text-sm font-mono text-slate-900">{t.operation ?? "—"}</td>
                          <td className="px-4 py-3 text-sm text-slate-600">{dir}</td>
                          <td className="px-4 py-3">
                            <StatusPill label={pill.label} variant={pill.variant} />
                          </td>
                          <td className="px-4 py-3 text-right">
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleRowClick(txId);
                              }}
                              className="text-sm text-slate-600 hover:text-slate-800 font-medium"
                            >
                              View
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => navigate("/configuration")}
              className="inline-flex items-center justify-center px-4 py-2 text-sm font-medium rounded-lg border border-slate-300 text-slate-700 bg-white hover:bg-slate-50 transition-colors"
            >
              Configure operations
            </button>
            <button
              type="button"
              onClick={() => navigate("/flows")}
              className="inline-flex items-center justify-center px-4 py-2 text-sm font-medium rounded-lg border border-slate-300 text-slate-700 bg-white hover:bg-slate-50 transition-colors"
            >
              View flows
            </button>
            <button
              type="button"
              onClick={() => navigate("/execute")}
              className="inline-flex items-center justify-center px-4 py-2 text-sm font-medium rounded-lg bg-slate-700 text-white hover:bg-slate-600 transition-colors"
            >
              Run test
            </button>
          </div>
        </section>
      </div>

      <TransactionDetailsDrawer
        isOpen={!!selectedTxId}
        onClose={handleDrawerClose}
        transaction={detailLoading ? null : vendorDetailToTransactionDetails(detailData ?? null)}
        onRedriveSuccess={(newTxId) => setSelectedTxId(newTxId)}
      />
      </>
    </div>
    </VendorPageLayout>
  );
}
