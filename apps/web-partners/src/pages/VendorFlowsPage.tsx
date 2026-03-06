/**
 * Flows overview – Flow Control Center.
 * Flows v2 Milestone 2: summary strip, status chips, operations table with drill-downs.
 * Uses metrics, transactions, and My Operations; no new backend endpoints.
 */

import { useState, useMemo, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  getActiveVendorCode,
} from "frontend-shared";
import {
  getVendorMetricsOverview,
  listVendorTransactions,
  getMyOperations,
  getVendorContracts,
  getVendorOperationsCatalog,
  getVendorSupportedOperations,
  getVendorEndpoints,
  getVendorMappings,
  getMyAllowlist,
} from "../api/endpoints";
import {
  vendorMetricsKey,
  vendorTransactionsKey,
  vendorMyOperationsKey,
  STALE_TRANSACTIONS,
  STALE_CONFIG,
} from "../api/queryKeys";
import { FLOWS_TIME_RANGES_M3 } from "../utils/dateRange";
import {
  buildReadinessRowsForLicensee,
  mapReadinessToDisplay,
  getDisplayForOverallStatus,
  getStatusFilterLabel,
  getFlowHealthAdminPendingLabel,
  type FlowReadinessRow,
} from "../utils/readinessModel";
import {
  getAdminDirectionLabel,
  getAdminDirectionBadgeTooltip,
  type FlowDirection,
} from "frontend-shared";
import { VendorPageLayout } from "../components/layout/VendorPageLayout";
import { Skeleton } from "frontend-shared";
import { VendorStatCardSkeleton } from "../components/vendor/skeleton";
import { augmentReadyLabel } from "../utils/vendorDirectionLabels";
import { StatusPill, type StatusPillVariant } from "frontend-shared";
import { OpenSettingsLink } from "../components/OpenSettingsLink";
import { useVendorConfigBundle } from "../hooks/useVendorConfigBundle";

type FlowHealth = "healthy" | "has_errors" | "needs_attention" | "admin_pending";
type StatusFilter = "all" | "healthy" | "has_errors" | "needs_attention";

function flowHealthFromReadinessAndMetrics(
  vendorReady: boolean,
  count: number,
  failed: number
): FlowHealth {
  if (!vendorReady) return "needs_attention";
  if (count === 0 || failed === 0) return "healthy";
  if (hasRecentErrors(count, failed)) return "needs_attention";
  return "has_errors";
}

function formatDate(iso?: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

const ERROR_RATE_THRESHOLD = 0.02;

function hasRecentErrors(count: number, failed: number): boolean {
  if (count === 0 || failed === 0) return false;
  const errorRate = failed / count;
  return errorRate >= ERROR_RATE_THRESHOLD || failed >= 5;
}

function flowHealthToPill(
  health: FlowHealth,
  readinessRow?: FlowReadinessRow,
  allRowsForOp?: FlowReadinessRow[]
): { label: string; variant: StatusPillVariant; tooltip?: string } {
  if (health === "admin_pending")
    return { label: getFlowHealthAdminPendingLabel(), variant: "neutral" };
  if (readinessRow) {
    const hasRecentErrorsFlag =
      health === "has_errors" || health === "needs_attention";
    const base = mapReadinessToDisplay(readinessRow, {
      hasRecentErrors: hasRecentErrorsFlag,
    });
    return augmentReadyLabel(
      base.label,
      base.variant,
      base.tooltip,
      allRowsForOp ?? [readinessRow]
    ) as { label: string; variant: StatusPillVariant; tooltip?: string };
  }
  switch (health) {
    case "healthy":
      return getDisplayForOverallStatus("ready");
    case "has_errors":
      return getDisplayForOverallStatus("has_errors");
    case "needs_attention":
      return getDisplayForOverallStatus("config_missing");
    default:
      return { label: "—", variant: "neutral" };
  }
}

function buildFlowDetailsLink(
  operation: string,
  fromStr: string,
  toStr: string
): string {
  const p = new URLSearchParams();
  p.set("from", fromStr);
  p.set("to", toStr);
  return `/flows/${encodeURIComponent(operation)}?${p.toString()}`;
}

function buildTransactionsLink(
  operation: string,
  fromStr: string,
  toStr: string
): string {
  const p = new URLSearchParams();
  if (operation) p.set("operation", operation);
  p.set("from", fromStr);
  p.set("to", toStr);
  return `/transactions?${p.toString()}`;
}

const VALID_STATUS_FILTERS: StatusFilter[] = ["all", "healthy", "has_errors", "needs_attention"];

export function VendorFlowsPage() {
  const activeVendor = getActiveVendorCode();
  const hasKey = !!activeVendor;
  const [searchParams, setSearchParams] = useSearchParams();
  const filterParam = searchParams.get("filter");

  const [timeRangeIdx, setTimeRangeIdx] = useState(0);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(() => {
    const f = filterParam ?? "all";
    return VALID_STATUS_FILTERS.includes(f as StatusFilter) ? (f as StatusFilter) : "all";
  });

  useEffect(() => {
    const f = filterParam ?? "all";
    if (VALID_STATUS_FILTERS.includes(f as StatusFilter)) {
      setStatusFilter(f as StatusFilter);
    }
  }, [filterParam]);

  const { fromStr, toStr } = useMemo(() => {
    const preset = FLOWS_TIME_RANGES_M3[timeRangeIdx];
    return preset.getRange(new Date());
  }, [timeRangeIdx]);

  const timeRangeLabel = FLOWS_TIME_RANGES_M3[timeRangeIdx]?.label ?? "Last 24h";

  // Readiness – unified model for health classification; prefer config bundle
  const { data: bundleData, isError: bundleError } = useVendorConfigBundle(!!activeVendor && hasKey);
  const useIndividualConfig = !!activeVendor && hasKey && (bundleError || !bundleData);

  const { data: contractsData } = useQuery({
    queryKey: ["vendor-contracts"],
    queryFn: getVendorContracts,
    enabled: useIndividualConfig,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: catalogData } = useQuery({
    queryKey: ["vendor-operations-catalog"],
    queryFn: getVendorOperationsCatalog,
    enabled: useIndividualConfig,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: supportedData } = useQuery({
    queryKey: ["vendor-supported-operations"],
    queryFn: getVendorSupportedOperations,
    enabled: useIndividualConfig,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: endpointsData } = useQuery({
    queryKey: ["vendor-endpoints"],
    queryFn: getVendorEndpoints,
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
    enabled: useIndividualConfig,
    retry: false,
    staleTime: STALE_CONFIG,
  });
  const { data: myOpsData, isLoading: myOpsLoading } = useQuery({
    queryKey: vendorMyOperationsKey,
    queryFn: () => getMyOperations(),
    enabled: !!activeVendor && hasKey,
    staleTime: STALE_TRANSACTIONS,
  });

  const contracts = bundleData?.contracts ?? contractsData?.items ?? [];
  const catalogItems = bundleData?.operationsCatalog ?? catalogData?.items ?? [];
  const supportedItems = bundleData?.supportedOperations ?? supportedData?.items ?? [];
  const endpointsItems = bundleData?.endpoints ?? endpointsData?.items ?? [];
  const mappingsItems = bundleData?.mappings ?? mappingsData?.mappings ?? [];
  const allowlist = bundleData?.myAllowlist ?? allowlistData;

  const readinessRows = useMemo(
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
        myOperationsOutbound: myOpsData?.outbound,
        myOperationsInbound: myOpsData?.inbound,
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
      myOpsData?.outbound,
      myOpsData?.inbound,
    ]
  );

  const opToVendorReady = useMemo(() => {
    const m = new Map<string, boolean>();
    for (const r of readinessRows) {
      const cur = m.get(r.operationCode);
      m.set(r.operationCode, cur === true || r.vendorReady);
    }
    return m;
  }, [readinessRows]);

  const opToReadinessRow = useMemo(() => {
    const m = new Map<string, (typeof readinessRows)[0]>();
    for (const r of readinessRows) {
      if (!m.has(r.operationCode)) m.set(r.operationCode, r);
    }
    return m;
  }, [readinessRows]);

  const opToReadinessRows = useMemo(() => {
    const m = new Map<string, (typeof readinessRows)[0][]>();
    for (const r of readinessRows) {
      const list = m.get(r.operationCode) ?? [];
      list.push(r);
      m.set(r.operationCode, list);
    }
    return m;
  }, [readinessRows]);

  const outbound = myOpsData?.outbound ?? [];
  const inbound = myOpsData?.inbound ?? [];
  const allMyOps = [...outbound, ...inbound];
  const totalOperations = new Set(allMyOps.map((o) => o.operationCode)).size;

  // Metrics and transactions – same as before
  const { data: metricsData, isLoading: metricsLoading } = useQuery({
    queryKey: vendorMetricsKey(fromStr, toStr),
    queryFn: () => getVendorMetricsOverview({ from: fromStr, to: toStr }),
    enabled: !!activeVendor && hasKey,
    retry: false,
    staleTime: STALE_TRANSACTIONS,
  });

  const { data: txData, isLoading: txLoading } = useQuery({
    queryKey: vendorTransactionsKey(
      fromStr,
      toStr,
      "all",
      null,
      null,
      null,
      null
    ),
    queryFn: () =>
      listVendorTransactions({
        from: fromStr,
        to: toStr,
        limit: 200,
      }),
    enabled: !!activeVendor && hasKey,
    retry: false,
    staleTime: STALE_TRANSACTIONS,
  });

  const transactions = txData?.transactions ?? [];
  const byOperation = metricsData?.byOperation ?? [];
  const totals = metricsData?.totals;

  const errorStatuses = new Set([
    "validation_failed",
    "downstream_error",
    "downstream_timeout",
    "mapping_failed",
    "internal_error",
  ]);

  // Build per-op stats from metrics + transactions
  const opToStats = useMemo(() => {
    const opToLastActivity: Record<string, string> = {};
    const opToCount: Record<string, number> = {};
    const opToFailed: Record<string, number> = {};
    for (const t of transactions) {
      const op = t.operation ?? "";
      if (!op) continue;
      opToCount[op] = (opToCount[op] ?? 0) + 1;
      if (errorStatuses.has((t.status ?? "").toLowerCase())) {
        opToFailed[op] = (opToFailed[op] ?? 0) + 1;
      }
      const created = t.createdAt ?? "";
      const existing = opToLastActivity[op];
      if (!existing || (created && created > existing)) {
        opToLastActivity[op] = created;
      }
    }
    const result: Record<
      string,
      { count: number; failed: number; lastActivity: string }
    > = {};
    for (const r of byOperation) {
      const key = r.operation ?? "";
      if (!key) continue;
      result[key] = {
        count: r.count ?? 0,
        failed: r.failed ?? 0,
        lastActivity: opToLastActivity[key] ?? "",
      };
    }
    for (const op of Object.keys(opToCount)) {
      if (!(op in result)) {
        result[op] = {
          count: opToCount[op] ?? 0,
          failed: opToFailed[op] ?? 0,
          lastActivity: opToLastActivity[op] ?? "",
        };
      }
    }
    return result;
  }, [byOperation, transactions]);

  const matchesOp = (opKey: string, metricOp: string): boolean => {
    const opLower = opKey.toLowerCase();
    const mLower = (metricOp ?? "").toLowerCase();
    return opLower === mLower || mLower.startsWith(opLower + " ");
  };

  // Flow rows: from My Operations, enriched with metrics and readiness
  const flowRows = useMemo(() => {
    const opToDirections = new Map<string, Set<"inbound" | "outbound">>();
    const opToAdminPending = new Map<string, boolean>();
    for (const o of allMyOps) {
      const code = o.operationCode ?? "";
      if (!code) continue;
      if (!opToDirections.has(code)) opToDirections.set(code, new Set());
      opToDirections.get(code)!.add(o.direction);
      if (o.status === "admin_pending") opToAdminPending.set(code, true);
    }
    const uniqueOps = [...opToDirections.keys()].sort();
    return uniqueOps.map((operationCode) => {
      const dirs = opToDirections.get(operationCode)!;
      const direction =
        dirs.size >= 2 ? "Both" : dirs.has("outbound") ? "Outbound" : "Inbound";
      const stats =
        Object.entries(opToStats).find(([k]) =>
          matchesOp(operationCode, k)
        )?.[1] ?? { count: 0, failed: 0, lastActivity: "" };
      const adminPending = opToAdminPending.get(operationCode);
      const vendorReady = opToVendorReady.get(operationCode) ?? false;
      const health = adminPending
        ? ("admin_pending" as const)
        : flowHealthFromReadinessAndMetrics(
            vendorReady,
            stats.count,
            stats.failed
          );
      return {
        operation: operationCode,
        direction,
        count: stats.count,
        failed: stats.failed,
        lastActivity: stats.lastActivity,
        health,
        vendorReady,
      };
    });
  }, [allMyOps, opToStats, opToVendorReady]);

  const healthCounts = useMemo(() => {
    let healthy = 0;
    let hasErrors = 0;
    let needsAttention = 0;
    for (const r of flowRows) {
      if (r.health === "healthy") healthy++;
      else if (r.health === "has_errors") hasErrors++;
      else if (r.health === "needs_attention") needsAttention++;
    }
    return { healthy, hasErrors, needsAttention, withIssues: hasErrors + needsAttention };
  }, [flowRows]);

  const filteredFlows = useMemo(() => {
    let rows = flowRows;
    if (statusFilter !== "all") {
      rows = rows.filter((r) => r.health === statusFilter);
    }
    const order: Record<FlowHealth, number> = {
      needs_attention: 0,
      has_errors: 1,
      healthy: 2,
      admin_pending: 3,
    };
    return [...rows].sort(
      (a, b) =>
        (order[a.health] ?? 3) - (order[b.health] ?? 3) ||
        new Date(b.lastActivity || 0).getTime() -
          new Date(a.lastActivity || 0).getTime()
    );
  }, [flowRows, statusFilter]);

  const isLoading = myOpsLoading || metricsLoading || txLoading;

  const handleFilterChange = (filter: StatusFilter) => {
    setStatusFilter(filter);
    setSearchParams(
      (p) => {
        const next = new URLSearchParams(p);
        if (filter === "all") next.delete("filter");
        else next.set("filter", filter);
        return next;
      },
      { replace: true }
    );
  };

  if (!activeVendor) {
    return (
      <VendorPageLayout title="Flows" subtitle="Monitor flow health and volume across operations.">
        <div className="rounded-lg bg-gray-50 border border-gray-200 p-3">
          <p className="text-sm font-medium text-gray-700">
            Select an active licensee above.
          </p>
        </div>
      </VendorPageLayout>
    );
  }

  if (!hasKey) {
    return (
      <VendorPageLayout title="Flows" subtitle="Monitor flow health and volume across operations.">
        <div className="rounded-lg bg-amber-50 border border-amber-200 p-3">
          <p className="text-sm font-medium text-amber-800">Active licensee not selected.</p>
          <OpenSettingsLink>Open Settings →</OpenSettingsLink>
        </div>
      </VendorPageLayout>
    );
  }

  return (
    <VendorPageLayout
      title="Flows"
      subtitle="Monitor flow health and volume across all operations. Click an operation to drill into details."
      rightContent={
        <div className="inline-flex flex-wrap sm:flex-nowrap items-start justify-end gap-2">
          {FLOWS_TIME_RANGES_M3.map((r, i) => {
            const isActive = i === timeRangeIdx;
            return (
              <button
                key={r.label}
                type="button"
                onClick={() => setTimeRangeIdx(i)}
                className={`px-2 py-0.5 rounded-full text-xs font-medium border transition-colors whitespace-nowrap ${
                  isActive
                    ? "bg-slate-200 text-slate-800 border-slate-300"
                    : "bg-white text-gray-600 border-gray-200 hover:bg-gray-50 hover:text-gray-800"
                }`}
              >
                {r.label}
              </button>
            );
          })}
        </div>
      }
    >
    <div className="space-y-3">
      {/* Summary strip */}
      <div className="flex flex-wrap gap-3 items-end">
        <div className="flex flex-wrap gap-3 flex-1">
          {isLoading ? (
            [...Array(4)].map((_, i) => (
              <VendorStatCardSkeleton key={i} className="min-w-[140px]" />
            ))
          ) : (
            <>
          <div className="rounded-lg border border-gray-200 bg-white dark:bg-slate-900 px-3 py-2.5 min-w-[140px]">
            <p className="text-xs font-medium text-gray-500">Total operations</p>
            <p className="text-xl font-bold text-gray-900 tabular-nums mt-0.5">
              {totalOperations}
            </p>
            <p className="text-xs text-gray-400 mt-0.5">{timeRangeLabel}</p>
          </div>
          <div className="rounded-lg border border-gray-200 bg-white dark:bg-slate-900 px-3 py-2.5 min-w-[140px]">
            <p className="text-xs font-medium text-gray-500">Healthy flows</p>
            <p className="text-xl font-bold text-emerald-700 tabular-nums mt-0.5">
              {healthCounts.healthy}
            </p>
            <p className="text-xs text-gray-400 mt-0.5">{timeRangeLabel}</p>
          </div>
          <div className="rounded-lg border border-gray-200 bg-white dark:bg-slate-900 px-3 py-2.5 min-w-[140px]">
            <p className="text-xs font-medium text-gray-500">Flows with issues</p>
            <p className="text-xl font-bold text-amber-700 tabular-nums mt-0.5">
              {healthCounts.withIssues}
            </p>
            <p className="text-xs text-gray-400 mt-0.5">{timeRangeLabel}</p>
          </div>
          {totals != null && (
            <div className="rounded-lg border border-gray-200 bg-white dark:bg-slate-900 px-3 py-2.5 min-w-[140px]">
              <p className="text-xs font-medium text-gray-500">Total volume</p>
              <p className="text-xl font-bold text-gray-900 tabular-nums mt-0.5">
                {totals.count}
              </p>
              <p className="text-xs text-gray-400 mt-0.5">{timeRangeLabel}</p>
            </div>
          )}
            </>
          )}
        </div>
        <div className="inline-flex flex-wrap sm:flex-nowrap gap-2 items-center self-end">
          {(
            [
              { value: "all" as const },
              { value: "healthy" as const },
              { value: "has_errors" as const },
              { value: "needs_attention" as const },
            ] as const
          ).map(({ value }) => {
            const isActive = statusFilter === value;
            const pill = value === "all" ? { label: "All", variant: "neutral" as StatusPillVariant } : flowHealthToPill(value, undefined);
            const activeStyles =
              pill.variant === "configured"
                ? "bg-emerald-100 text-emerald-800 border-emerald-200"
                : pill.variant === "warning"
                  ? "bg-amber-100 text-amber-800 border-amber-200"
                  : pill.variant === "error"
                    ? "bg-red-100 text-red-800 border-red-200"
                    : "bg-gray-200 text-gray-800 border-gray-300";
            return (
              <button
                key={value}
                type="button"
                onClick={() => handleFilterChange(value)}
                className={`px-2 py-0.5 rounded-full text-xs font-medium border transition-colors whitespace-nowrap ${
                  isActive ? activeStyles : "bg-white text-gray-600 border-gray-200 hover:bg-gray-50 hover:text-gray-800"
                }`}
              >
                {getStatusFilterLabel(value)}
              </button>
            );
          })}
        </div>
      </div>

      {/* Operations table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead>
              <tr className="bg-gray-50">
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                  Operation
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                  Direction
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                  Health
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                  Volume
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                  Errors
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                  Last activity
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {isLoading ? (
                [...Array(6)].map((_, i) => (
                  <tr key={i}>
                    {[...Array(7)].map((_, j) => (
                      <td key={j} className="px-3 py-2.5">
                        <Skeleton className="h-4 w-full" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : totalOperations === 0 ? (
                <tr>
                  <td colSpan={7} className="px-3 py-6 text-center">
                    <p className="text-gray-500 text-sm font-medium">
                      No flows configured yet.
                    </p>
                    <Link
                      to="/configuration"
                      className="inline-flex items-center justify-center px-3 py-1.5 mt-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 bg-white hover:bg-gray-50 transition-colors"
                    >
                      Go to Configuration → Overview
                    </Link>
                  </td>
                </tr>
              ) : filteredFlows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-3 py-6 text-center text-gray-500 text-sm">
                    No flows match your filters. Try a different status.
                  </td>
                </tr>
              ) : (
                filteredFlows.map((row) => {
                  const readinessRow = opToReadinessRow.get(row.operation);
                  const pill = flowHealthToPill(
                    row.health,
                    readinessRow,
                    opToReadinessRows.get(row.operation)
                  );
                  return (
                    <tr
                      key={row.operation}
                      className="hover:bg-slate-50 transition-colors"
                    >
                      <td className="px-3 py-1.5 text-sm font-mono text-gray-900">
                        <Link
                          to={buildFlowDetailsLink(
                            row.operation,
                            fromStr,
                            toStr
                          )}
                          className="font-mono text-slate-700 hover:text-slate-900"
                        >
                          {row.operation}
                        </Link>
                      </td>
                      <td className="px-3 py-1.5">
                        <span
                          className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                            row.direction === "Both"
                              ? "bg-slate-100 text-slate-700"
                              : row.direction === "Outbound"
                                ? "bg-blue-50 text-blue-700"
                                : "bg-purple-50 text-purple-700"
                          }`}
                          title={getAdminDirectionBadgeTooltip(
                            (row.direction === "Both"
                              ? "BOTH"
                              : row.direction === "Outbound"
                                ? "OUTBOUND"
                                : "INBOUND") as FlowDirection
                          )}
                        >
                          {getAdminDirectionLabel(
                            (row.direction === "Both"
                              ? "BOTH"
                              : row.direction === "Outbound"
                                ? "OUTBOUND"
                                : "INBOUND") as FlowDirection
                          )}
                        </span>
                      </td>
                      <td className="px-3 py-1.5">
                        <StatusPill label={pill.label} variant={pill.variant} title={pill.tooltip} />
                      </td>
                      <td className="px-3 py-1.5 text-sm text-gray-600 tabular-nums">
                        {row.count}
                      </td>
                      <td className="px-3 py-1.5 text-sm text-gray-600 tabular-nums">
                        {row.failed}
                      </td>
                      <td className="px-3 py-1.5 text-sm text-gray-500 whitespace-nowrap">
                        {formatDate(row.lastActivity)}
                      </td>
                      <td className="px-3 py-1.5">
                        <div className="flex flex-wrap gap-2">
                          <Link
                            to={buildTransactionsLink(
                              row.operation,
                              fromStr,
                              toStr
                            )}
                            className="text-sm text-slate-600 hover:text-slate-800 font-medium"
                          >
                            View transactions
                          </Link>
                          <Link
                            to={`/configuration?operation=${encodeURIComponent(row.operation)}`}
                            className="text-sm text-slate-600 hover:text-slate-800 font-medium"
                          >
                            Go to Configuration
                          </Link>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
    </VendorPageLayout>
  );
}
