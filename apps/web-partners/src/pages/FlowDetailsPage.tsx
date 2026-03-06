/**
 * Flow Details Page – dedicated dashboard per operation.
 * Flows v2 Milestone 1: health, stats, volume chart, error breakdown, recent transactions.
 * Reuses existing metrics + transactions APIs; no new backend endpoints.
 */

import { useState, useMemo, useEffect } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import {
  getActiveVendorCode,
} from "frontend-shared";
import {
  getVendorMetricsOverview,
  listVendorTransactions,
  getVendorTransactionDetail,
  getMyOperations,
  getVendorContracts,
  getVendorOperationsCatalog,
  getVendorSupportedOperations,
  getVendorEndpoints,
  getVendorMappings,
  getMyAllowlist,
} from "../api/endpoints";
import type { VendorTransaction } from "../api/endpoints";
import {
  vendorMetricsKey,
  vendorTransactionsKey,
  vendorTransactionDetailKey,
  vendorMyOperationsKey,
  STALE_TRANSACTIONS,
  STALE_CONFIG,
} from "../api/queryKeys";
import { FLOWS_TIME_RANGES_M3 } from "../utils/dateRange";
import {
  getStoredFlowTimeRange,
  setStoredFlowTimeRange,
  TIME_RANGE_INDEX_TO_LABEL,
} from "../utils/flowTimeRangeStorage";
import { getFlowBuilderPath } from "../utils/flowReadiness";
import {
  buildReadinessRowsForLicensee,
  mapReadinessToDisplay,
} from "../utils/readinessModel";
import { augmentReadyLabel } from "../utils/vendorDirectionLabels";
import { TransactionDetailsDrawer, vendorDetailToTransactionDetails } from "../components/TransactionDetailsDrawer";
import { StatusPill, type StatusPillVariant } from "frontend-shared";
import { OpenSettingsLink } from "../components/OpenSettingsLink";
import { VendorPageLayout } from "../components/layout/VendorPageLayout";
import { Skeleton } from "frontend-shared";

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

function formatBucketLabel(bucket: string, is24h: boolean): string {
  try {
    const d = new Date(bucket);
    return is24h
      ? d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
      : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return bucket.slice(0, 10) ?? bucket;
  }
}

function statusToPill(status: string | undefined): {
  label: string;
  variant: StatusPillVariant;
} {
  const s = (status ?? "").toLowerCase();
  if (s === "completed") return { label: "Success", variant: "configured" };
  if (s === "validation_failed")
    return { label: "Validation error", variant: "error" };
  if (
    s === "downstream_error" ||
    s === "downstream_timeout" ||
    s === "mapping_failed"
  )
    return { label: "Integration error", variant: "error" };
  if (s === "received" || s === "in_progress" || s === "pending")
    return { label: "Pending", variant: "warning" };
  if (s === "replayed") return { label: "Replayed", variant: "info" };
  return { label: status ?? "Unknown", variant: "neutral" };
}

function vendorDisplay(t: VendorTransaction): string {
  const src = t.sourceVendor;
  const tgt = t.targetVendor;
  if (src && tgt) return `${src} • ${tgt}`;
  return src ?? tgt ?? "—";
}

const CHART_HEIGHT = 128;

function VolumeChart({
  data,
  title,
  is24h,
}: {
  data: { bucket: string; count: number }[];
  title: string;
  is24h: boolean;
}) {
  const chartData = useMemo(
    () =>
      data.map((d) => ({
        ...d,
        bucketLabel: formatBucketLabel(d.bucket, is24h),
      })),
    [data, is24h]
  );
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3 shadow-sm min-w-0">
      <h3 className="text-xs font-semibold text-gray-700 mb-2">{title}</h3>
      <div style={{ height: CHART_HEIGHT }}>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 4, right: 4, left: -8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 2" stroke="#e5e7eb" vertical={false} />
              <XAxis
                dataKey="bucketLabel"
                tick={{ fontSize: 9 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis tick={{ fontSize: 9 }} axisLine={false} tickLine={false} width={24} />
              <Tooltip
                formatter={(v: number | undefined) => [v ?? 0, "Count"]}
                labelFormatter={(l) => l}
                contentStyle={{ borderRadius: 6, fontSize: 11 }}
              />
              <Line
                type="natural"
                dataKey="count"
                stroke="#6366f1"
                strokeWidth={1.5}
                dot={false}
                name="Transactions"
                connectNulls
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-400 text-xs">
            No data
          </div>
        )}
      </div>
    </div>
  );
}

function parseFromTo(fromParam: string | null, toParam: string | null): {
  fromStr: string;
  toStr: string;
} | null {
  if (!fromParam || !toParam) return null;
  try {
    const from = new Date(fromParam);
    const to = new Date(toParam);
    if (isNaN(from.getTime()) || isNaN(to.getTime())) return null;
    return {
      fromStr: from.toISOString().slice(0, 19) + "Z",
      toStr: to.toISOString().slice(0, 19) + "Z",
    };
  } catch {
    return null;
  }
}

export function FlowDetailsPage() {
  const { operationCode } = useParams<{ operationCode: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const fromParam = searchParams.get("from");
  const toParam = searchParams.get("to");

  const activeVendor = getActiveVendorCode();
  const hasKey = !!activeVendor;
  const txIdFromUrl = searchParams.get("transactionId");
  const getInitialTimeRangeIdx = () => {
    const parsed = parseFromTo(fromParam, toParam);
    if (parsed) {
      const hours = (new Date(parsed.toStr).getTime() - new Date(parsed.fromStr).getTime()) / (60 * 60 * 1000);
      if (Math.abs(hours - 24) < 2) return 0;
      if (Math.abs(hours - 24 * 7) < 24) return 1;
      if (Math.abs(hours - 24 * 30) < 48) return 2;
      return 0;
    }
    const stored = operationCode ? getStoredFlowTimeRange(operationCode) : null;
    if (stored === "7d") return 1;
    if (stored === "30d") return 2;
    return 0;
  };
  const [timeRangeIdx, setTimeRangeIdx] = useState(getInitialTimeRangeIdx);
  const [selectedTxId, setSelectedTxId] = useState<string | null>(txIdFromUrl);
  const [copyToast, setCopyToast] = useState(false);

  useEffect(() => {
    if (txIdFromUrl) setSelectedTxId(txIdFromUrl);
  }, [txIdFromUrl]);

  useEffect(() => {
    const parsed = parseFromTo(fromParam, toParam);
    if (parsed) {
      const hours = (new Date(parsed.toStr).getTime() - new Date(parsed.fromStr).getTime()) / (60 * 60 * 1000);
      if (Math.abs(hours - 24) < 2) setTimeRangeIdx(0);
      else if (Math.abs(hours - 24 * 7) < 24) setTimeRangeIdx(1);
      else if (Math.abs(hours - 24 * 30) < 48) setTimeRangeIdx(2);
    }
  }, [fromParam, toParam]);

  // On load, if no from/to in URL, sync URL with stored/default range so URL is canonical
  useEffect(() => {
    if (fromParam && toParam) return;
    if (!operationCode) return;
    const idx = getInitialTimeRangeIdx();
    setTimeRangeIdx(idx);
    const preset = FLOWS_TIME_RANGES_M3[idx];
    const { fromStr: f, toStr: t } = preset.getRange(new Date());
    setSearchParams(
      (p) => {
        const next = new URLSearchParams(p);
        next.set("from", f);
        next.set("to", t);
        return next;
      },
      { replace: true }
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { fromStr, toStr } = useMemo(() => {
    const parsed = parseFromTo(fromParam, toParam);
    if (parsed) return parsed;
    const preset = FLOWS_TIME_RANGES_M3[timeRangeIdx];
    return preset.getRange(new Date());
  }, [fromParam, toParam, timeRangeIdx]);

  const handleTimeRangeChange = (idx: number) => {
    setTimeRangeIdx(idx);
    const label = TIME_RANGE_INDEX_TO_LABEL[idx] ?? "24h";
    if (operationCode) setStoredFlowTimeRange(operationCode, label);
    const preset = FLOWS_TIME_RANGES_M3[idx];
    const { fromStr: f, toStr: t } = preset.getRange(new Date());
    setSearchParams(
      (p) => {
        const next = new URLSearchParams(p);
        next.set("from", f);
        next.set("to", t);
        return next;
      },
      { replace: true }
    );
  };

  const handleCopyLink = async () => {
    try {
      const url = window.location.href;
      await navigator.clipboard.writeText(url);
      setCopyToast(true);
      setTimeout(() => setCopyToast(false), 2000);
    } catch {
      /* fallback: no toast */
    }
  };

  const is24h =
    Math.abs(
      new Date(toStr).getTime() -
        new Date(fromStr).getTime() -
        24 * 60 * 60 * 1000
    ) < 60 * 1000;

  // Readiness – for header pill and health classification
  const { data: contractsData } = useQuery({
    queryKey: ["vendor-contracts"],
    queryFn: getVendorContracts,
    enabled: !!activeVendor && hasKey,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: catalogData } = useQuery({
    queryKey: ["vendor-operations-catalog"],
    queryFn: getVendorOperationsCatalog,
    enabled: !!activeVendor && hasKey,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: supportedData } = useQuery({
    queryKey: ["vendor-supported-operations"],
    queryFn: getVendorSupportedOperations,
    enabled: !!activeVendor && hasKey,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: endpointsData } = useQuery({
    queryKey: ["vendor-endpoints"],
    queryFn: getVendorEndpoints,
    enabled: !!activeVendor && hasKey,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: mappingsData } = useQuery({
    queryKey: ["vendor-mappings"],
    queryFn: () => getVendorMappings(),
    enabled: !!activeVendor && hasKey,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: allowlistData } = useQuery({
    queryKey: ["my-allowlist", activeVendor ?? ""],
    queryFn: getMyAllowlist,
    enabled: !!activeVendor && hasKey,
    retry: false,
    staleTime: STALE_CONFIG,
  });

  const { data: myOpsData } = useQuery({
    queryKey: vendorMyOperationsKey,
    queryFn: () => getMyOperations(),
    enabled: !!activeVendor && hasKey,
    staleTime: 2 * 60 * 1000,
  });

  const readinessRows = useMemo(
    () =>
      buildReadinessRowsForLicensee({
        supported: supportedData?.items ?? [],
        catalog: catalogData?.items ?? [],
        vendorContracts: contractsData?.items ?? [],
        endpoints: endpointsData?.items ?? [],
        mappings: mappingsData?.mappings ?? [],
        outboundAllowlist: allowlistData?.outbound ?? [],
        inboundAllowlist: allowlistData?.inbound ?? [],
        eligibleOperations: allowlistData?.eligibleOperations,
        accessOutcomes: allowlistData?.accessOutcomes,
        vendorCode: activeVendor ?? "",
        myOperationsOutbound: myOpsData?.outbound ?? [],
        myOperationsInbound: myOpsData?.inbound ?? [],
      }),
    [
      supportedData?.items,
      catalogData?.items,
      contractsData?.items,
      endpointsData?.items,
      mappingsData?.mappings,
      allowlistData?.outbound,
      allowlistData?.inbound,
      allowlistData?.eligibleOperations,
      allowlistData?.accessOutcomes,
      activeVendor,
      myOpsData?.outbound,
      myOpsData?.inbound,
    ]
  );

  const readinessRowsForOp = useMemo(() => {
    const opLower = operationCode?.toUpperCase() ?? "";
    return readinessRows.filter(
      (r) => r.operationCode.toUpperCase() === opLower
    );
  }, [readinessRows, operationCode]);

  const readinessRowForOp = useMemo(
    () => readinessRowsForOp[0] ?? null,
    [readinessRowsForOp]
  );

  // Supported operations (for invalid op check) – myOpsData fetched above for readiness
  const supportedOperationCodes = useMemo(() => {
    const out = myOpsData?.outbound ?? [];
    const inb = myOpsData?.inbound ?? [];
    const codes = new Set<string>();
    for (const o of [...out, ...inb]) {
      const code = (o.operationCode ?? "").toLowerCase();
      if (code) codes.add(code);
      // Also add "code version" format in case transaction operation is "GetPatient v1"
      const ver = o.canonicalVersion ?? "v1";
      if (code) codes.add(`${code} ${ver}`.toLowerCase());
    }
    return codes;
  }, [myOpsData]);

  // Metrics (reuse same API as Flows overview)
  const { data: metricsData, isLoading: metricsLoading } = useQuery({
    queryKey: vendorMetricsKey(fromStr, toStr),
    queryFn: () => getVendorMetricsOverview({ from: fromStr, to: toStr }),
    enabled: !!activeVendor && hasKey && !!operationCode,
    retry: false,
    staleTime: STALE_TRANSACTIONS,
  });

  // Transactions filtered by operation
  const { data: txData, isLoading: txLoading } = useQuery({
    queryKey: vendorTransactionsKey(
      fromStr,
      toStr,
      "all",
      operationCode ?? null,
      null,
      null,
      null
    ),
    queryFn: () =>
      listVendorTransactions({
        from: fromStr,
        to: toStr,
        operation: operationCode ?? undefined,
        limit: 20,
      }),
    enabled: !!activeVendor && hasKey && !!operationCode,
    retry: false,
    staleTime: STALE_TRANSACTIONS,
  });

  const { data: detailData, isLoading: detailLoading } = useQuery({
    queryKey: selectedTxId
      ? vendorTransactionDetailKey(selectedTxId)
      : ["vendor-transaction-detail", null],
    queryFn: () => getVendorTransactionDetail(selectedTxId!),
    enabled: !!selectedTxId && !!activeVendor && hasKey,
    retry: false,
    staleTime: STALE_TRANSACTIONS,
  });

  const transactions = txData?.transactions ?? [];
  const byOperation = metricsData?.byOperation ?? [];

  // Per-operation stats from metrics or derived from transactions
  const opStats = useMemo(() => {
    const metricRow = byOperation.find(
      (r) =>
        r.operation?.toLowerCase() === operationCode?.toLowerCase() ||
        r.operation?.toLowerCase().startsWith(`${operationCode?.toLowerCase()} `)
    );
    if (metricRow) {
      return {
        count: metricRow.count ?? 0,
        failed: metricRow.failed ?? 0,
        success: (metricRow.count ?? 0) - (metricRow.failed ?? 0),
      };
    }
    const errorStatuses = new Set([
      "validation_failed",
      "downstream_error",
      "downstream_timeout",
      "mapping_failed",
      "internal_error",
    ]);
    let count = 0;
    let failed = 0;
    for (const t of transactions) {
      count++;
      if (errorStatuses.has((t.status ?? "").toLowerCase())) failed++;
    }
    return {
      count,
      failed,
      success: count - failed,
    };
  }, [byOperation, transactions, operationCode]);

  const lastActivity = useMemo(() => {
    if (transactions.length === 0) return "";
    return transactions.reduce((best, t) => {
      const created = t.createdAt ?? "";
      return !best || (created && created > best) ? created : best;
    }, "");
  }, [transactions]);

  const ERROR_RATE_THRESHOLD = 0.02;
  const hasRecentErrors =
    opStats.count > 0 &&
    opStats.failed > 0 &&
    (opStats.failed >= 5 ||
      opStats.failed / opStats.count >= ERROR_RATE_THRESHOLD);
  const healthPill = readinessRowForOp
    ? (() => {
        const base = mapReadinessToDisplay(readinessRowForOp, { hasRecentErrors });
        return augmentReadyLabel(
          base.label,
          base.variant,
          base.tooltip,
          readinessRowsForOp
        ) as { label: string; variant: StatusPillVariant; tooltip?: string };
      })()
    : { label: "—", variant: "neutral" as StatusPillVariant, tooltip: undefined };
  const errorRate =
    opStats.count > 0 ? ((opStats.failed / opStats.count) * 100).toFixed(1) : "0";

  // Volume chart: bucket transactions by time (derive from tx for this op)
  const volumeChartData = useMemo(() => {
    const bucketMap = new Map<string, number>();
    for (const t of transactions) {
      const created = t.createdAt ?? "";
      if (!created) continue;
      const d = new Date(created);
      let key: string;
      if (is24h) {
        key = new Date(d.getFullYear(), d.getMonth(), d.getDate(), d.getHours(), 0, 0, 0).toISOString();
      } else {
        key = new Date(d.getFullYear(), d.getMonth(), d.getDate()).toISOString().slice(0, 10) + "T00:00:00.000Z";
      }
      bucketMap.set(key, (bucketMap.get(key) ?? 0) + 1);
    }
    return [...bucketMap.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([bucket, count]) => ({ bucket, count }));
  }, [transactions, is24h]);

  // Error breakdown by status
  const errorBreakdown = useMemo(() => {
    const errorStatuses = new Set([
      "validation_failed",
      "downstream_error",
      "downstream_timeout",
      "mapping_failed",
      "internal_error",
    ]);
    const m: Record<string, number> = {};
    for (const t of transactions) {
      const s = (t.status ?? "unknown").toLowerCase();
      if (errorStatuses.has(s) || s !== "completed") {
        const label =
          s === "validation_failed"
            ? "VALIDATION"
            : s === "downstream_error" || s === "downstream_timeout"
              ? "DOWNSTREAM"
              : s === "mapping_failed"
                ? "MAPPING"
                : s === "internal_error"
                  ? "CONFIG"
                  : s.replace(/_/g, " ").toUpperCase() || "OTHER";
        m[label] = (m[label] ?? 0) + 1;
      }
    }
    return Object.entries(m).sort(([, a], [, b]) => b - a);
  }, [transactions]);

  const isLoading = metricsLoading || txLoading;
  const myOpsLoaded = myOpsData != null;
  const opLower = operationCode?.toLowerCase() ?? "";
  const isOperationConfigured =
    !operationCode ||
    !myOpsLoaded ||
    supportedOperationCodes.has(opLower) ||
    supportedOperationCodes.has(opLower.split(/\s+/)[0] ?? "");

  // Resolve canonical version for builder link (from my ops or default v1)
  const canonicalVersion = (() => {
    const ops = [...(myOpsData?.outbound ?? []), ...(myOpsData?.inbound ?? [])];
    const opLower = operationCode?.toLowerCase() ?? "";
    const exact = ops.find((o) => (o.operationCode ?? "").toLowerCase() === opLower);
    if (exact?.canonicalVersion) return exact.canonicalVersion;
    const base = opLower.split(/\s+/)[0];
    const byBase = ops.find((o) => (o.operationCode ?? "").toLowerCase() === base);
    return byBase?.canonicalVersion ?? "v1";
  })();

  const buildTransactionsLink = () => {
    const p = new URLSearchParams();
    if (operationCode) p.set("operation", operationCode);
    p.set("from", fromStr);
    p.set("to", toStr);
    return `/transactions?${p.toString()}`;
  };

  if (!activeVendor) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Flow</h1>
        <div className="rounded-lg bg-gray-50 border border-gray-200 p-4">
          <p className="text-sm font-medium text-gray-700">
            Select an active licensee above.
          </p>
        </div>
      </div>
    );
  }

  if (!hasKey) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Flow</h1>
        <div className="rounded-lg bg-amber-50 border border-amber-200 p-4">
          <p className="text-sm font-medium text-amber-800">Active licensee not selected.</p>
          <OpenSettingsLink>Open Settings →</OpenSettingsLink>
        </div>
      </div>
    );
  }

  if (!operationCode) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Flow</h1>
        <div className="rounded-lg bg-gray-50 border border-gray-200 p-4">
          <p className="text-sm font-medium text-gray-700">No operation specified.</p>
          <Link to="/flows" className="text-slate-600 hover:text-slate-800 font-medium text-sm mt-2 inline-block">
            ← Back to Flows
          </Link>
        </div>
      </div>
    );
  }

  if (!isOperationConfigured && !isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Operation not configured</h1>
        <div className="rounded-lg bg-gray-50 border border-gray-200 p-4">
          <p className="text-sm font-medium text-gray-700">
            This operation is not configured for your licensee.
          </p>
          <Link
            to="/configuration"
            className="inline-flex items-center justify-center px-4 py-2 mt-3 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 bg-white hover:bg-gray-50 transition-colors"
          >
            Go to Configuration
          </Link>
        </div>
      </div>
    );
  }

  return (
    <VendorPageLayout>
    <div className="space-y-6">
      {/* Top header: title left, actions right */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-gray-900">
            Flow – {operationCode}
          </h1>
          <p className="text-sm text-gray-600 mt-1">
            End-to-end health, traffic, and recent transactions for this operation.
          </p>
          <div className="mt-2">
            <StatusPill label={healthPill.label} variant={healthPill.variant} title={healthPill.tooltip} />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={timeRangeIdx}
            onChange={(e) => handleTimeRangeChange(Number(e.target.value))}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm bg-white text-gray-900 focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
          >
            {FLOWS_TIME_RANGES_M3.map((r, i) => (
              <option key={r.label} value={i}>
                {r.label}
              </option>
            ))}
          </select>
          <Link
            to={`/execute?operation=${encodeURIComponent(operationCode)}`}
            className="inline-flex items-center justify-center px-3 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 bg-white hover:bg-gray-50 transition-colors"
          >
            Send test from Execute
          </Link>
          <Link
            to={getFlowBuilderPath(operationCode, canonicalVersion)}
            className="inline-flex items-center justify-center px-3 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 bg-white hover:bg-gray-50 transition-colors"
          >
            Open Visual Builder
          </Link>
          <Link
            to={`/configuration?operation=${encodeURIComponent(operationCode)}`}
            className="inline-flex items-center justify-center px-3 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 bg-white hover:bg-gray-50 transition-colors"
          >
            Go to Configuration
          </Link>
          <Link
            to={`/configuration/access?operation=${encodeURIComponent(operationCode)}`}
            className="inline-flex items-center justify-center px-3 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 bg-white hover:bg-gray-50 transition-colors"
          >
            View access rules
          </Link>
          <button
            type="button"
            onClick={handleCopyLink}
            className="inline-flex items-center justify-center p-2 rounded-lg border border-gray-200 text-gray-600 bg-white hover:bg-gray-50 transition-colors"
            title="Copy flow link"
            aria-label="Copy flow link"
          >
            {copyToast ? (
              <span className="text-xs font-medium">Copied</span>
            ) : (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Section 1: Flow health & stats */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-gray-800 mb-3">Flow health & stats</h2>
        {isLoading ? (
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
            {[...Array(5)].map((_, i) => (
              <div key={i}>
                <Skeleton className="h-3 w-20 mb-2" />
                <Skeleton className="h-6 w-12" />
              </div>
            ))}
          </div>
        ) : opStats.count === 0 && !lastActivity ? (
          <p className="text-gray-500 text-sm">
            No activity yet for this operation in the selected range.
          </p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
            <div>
              <p className="text-xs font-medium text-gray-500">Health</p>
              <div className="mt-0.5">
                <StatusPill label={healthPill.label} variant={healthPill.variant} title={healthPill.tooltip} />
              </div>
            </div>
            <div>
              <p className="text-xs font-medium text-gray-500">Last activity</p>
              <p className="text-sm font-medium text-gray-900 mt-0.5">
                {formatDate(lastActivity) || "—"}
              </p>
            </div>
            <div>
              <p className="text-xs font-medium text-gray-500">Total volume</p>
              <p className="text-xl font-bold text-gray-900 tabular-nums mt-0.5">{opStats.count}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-gray-500">Success</p>
              <p className="text-xl font-bold text-emerald-700 tabular-nums mt-0.5">{opStats.success}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-gray-500">Failed / Error rate</p>
              <p className="text-xl font-bold text-red-700 tabular-nums mt-0.5">
                {opStats.failed} / {errorRate}%
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Section 2: Volume chart */}
      {opStats.count > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <VolumeChart
            data={volumeChartData}
            title="Volume over time"
            is24h={is24h}
          />
        </div>
      )}

      {/* Section 3: Error breakdown */}
      {errorBreakdown.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-800 mb-3">Error breakdown</h2>
          <div className="space-y-2">
            {errorBreakdown.map(([label, count]) => {
              const pct =
                opStats.count > 0
                  ? ((count / opStats.count) * 100).toFixed(1)
                  : "0";
              return (
                <div
                  key={label}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="font-mono text-gray-700">{label}</span>
                  <span className="text-gray-600">
                    {count} ({pct}%)
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Section 4: Recent transactions */}
      <div className="rounded-xl border border-gray-200 bg-white overflow-hidden shadow-sm">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50">
          <h2 className="text-sm font-semibold text-gray-800">Recent transactions</h2>
          <Link
            to={buildTransactionsLink()}
            className="text-sm font-medium text-slate-600 hover:text-slate-800 transition-colors"
          >
            View all →
          </Link>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead>
              <tr className="bg-gray-50">
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">
                  Created
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">
                  Source / Target
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">
                  Status
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">
                  HTTP
                </th>
                <th className="px-4 py-2.5 text-right text-xs font-medium text-gray-500 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {isLoading ? (
                [...Array(5)].map((_, i) => (
                  <tr key={i}>
                    {[...Array(5)].map((_, j) => (
                      <td key={j} className="px-4 py-3">
                        <Skeleton className="h-4 w-full" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : transactions.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-gray-500 text-sm">
                    No transactions in the selected range.
                    <Link
                      to="/execute"
                      className="block mt-1 text-slate-600 hover:text-slate-800 font-medium text-sm"
                    >
                      Send a test request from Execute
                    </Link>
                  </td>
                </tr>
              ) : (
                transactions.map((t) => {
                  const pill = statusToPill(t.status);
                  const txId = t.transactionId ?? t.id ?? "";
                  const handleView = () => {
                    setSelectedTxId(txId);
                    setSearchParams(
                      (p) => {
                        const next = new URLSearchParams(p);
                        if (txId) next.set("transactionId", txId);
                        return next;
                      },
                      { replace: true }
                    );
                  };
                  return (
                    <tr
                      key={txId}
                      onClick={handleView}
                      className="hover:bg-slate-50 cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3 text-sm text-gray-600 whitespace-nowrap">
                        {formatDate(t.createdAt)}
                      </td>
                      <td className="px-4 py-3 text-sm font-mono text-gray-600">
                        {vendorDisplay(t)}
                      </td>
                      <td className="px-4 py-3">
                        <StatusPill label={pill.label} variant={pill.variant} />
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {/* HTTP status from list API - not available in VendorTransaction */}
                        —
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleView();
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

      <TransactionDetailsDrawer
        isOpen={!!selectedTxId}
        onClose={() => {
          setSelectedTxId(null);
          setSearchParams(
            (p) => {
              const next = new URLSearchParams(p);
              next.delete("transactionId");
              return next;
            },
            { replace: true }
          );
        }}
        transaction={
          detailLoading ? null : vendorDetailToTransactionDetails(detailData ?? null)
        }
        onRedriveSuccess={(newTxId) => setSelectedTxId(newTxId)}
      />
    </div>
    </VendorPageLayout>
  );
}
