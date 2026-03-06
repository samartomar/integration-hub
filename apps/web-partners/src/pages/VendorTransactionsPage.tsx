import { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { OpenSettingsLink } from "../components/OpenSettingsLink";
import { useQuery } from "@tanstack/react-query";
import {
  getActiveVendorCode,
} from "frontend-shared";
import { VendorPageLayout } from "../components/layout/VendorPageLayout";
import {
  listVendorTransactions,
  getVendorTransactionDetail,
  listOperations,
  getVendorMetricsOverview,
} from "../api/endpoints";
import {
  vendorTransactionsKey,
  vendorTransactionDetailKey,
  vendorMetricsKey,
  STALE_HIGH_CHURN,
} from "../api/queryKeys";
import { toISORangeDays } from "../utils/dateRange";
import { TransactionDetailsDrawer, vendorDetailToTransactionDetails } from "../components/TransactionDetailsDrawer";
import { StatusPill, type StatusPillVariant } from "frontend-shared";
import { VendorTableSkeleton } from "../components/vendor/skeleton";

const STATUS_OPTIONS = [
  "completed",
  "validation_failed",
  "downstream_error",
  "downstream_timeout",
  "mapping_failed",
  "received",
  "in_progress",
  "pending",
] as const;

function statusToPill(status: string): { label: string; variant: StatusPillVariant } {
  const s = (status ?? "").toLowerCase();
  if (s === "completed") return { label: "Success", variant: "configured" };
  if (s === "validation_failed") return { label: "Validation error", variant: "error" };
  if (["downstream_error", "downstream_timeout", "mapping_failed"].includes(s)) return { label: "Integration error", variant: "error" };
  if (["received", "in_progress", "pending"].includes(s)) return { label: "Pending", variant: "warning" };
  return { label: status?.replace(/_/g, " ") ?? "Unknown", variant: "neutral" };
}

function formatDate(iso?: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function parseFromTo(fromParam: string | null, toParam: string | null): {
  fromStr: string;
  toStr: string;
  rangeDays: number;
} | null {
  if (!fromParam || !toParam) return null;
  try {
    const from = new Date(fromParam);
    const to = new Date(toParam);
    if (isNaN(from.getTime()) || isNaN(to.getTime())) return null;
    const rangeDays = Math.ceil((to.getTime() - from.getTime()) / (24 * 60 * 60 * 1000)) || 1;
    return {
      fromStr: from.toISOString().slice(0, 19) + "Z",
      toStr: to.toISOString().slice(0, 19) + "Z",
      rangeDays: Math.min(30, Math.max(1, rangeDays)),
    };
  } catch {
    return null;
  }
}

export function VendorTransactionsPage() {
  const activeVendor = getActiveVendorCode();
  const hasKey = !!activeVendor;
  const [searchParams, setSearchParams] = useSearchParams();
  const fromParam = searchParams.get("from");
  const toParam = searchParams.get("to");
  const txIdFromUrl = searchParams.get("transactionId");
  const [selectedTxId, setSelectedTxId] = useState<string | null>(txIdFromUrl);
  const operationParam = searchParams.get("operation") ?? "";
  const statusParam = searchParams.get("status") ?? "";
  const searchParam = searchParams.get("search") ?? "";
  const [direction, setDirection] = useState<"all" | "outbound" | "inbound">(
    (searchParams.get("direction") as "all" | "outbound" | "inbound") ?? "all",
  );
  const [operationFilter, setOperationFilter] = useState(operationParam);
  const [statusFilter, setStatusFilter] = useState(statusParam);
  const [searchFilter, setSearchFilter] = useState(searchParam);
  const [searchInput, setSearchInput] = useState(searchParam);
  const [rangeDays, setRangeDays] = useState(() => {
    const p = parseFromTo(fromParam, toParam);
    return p ? p.rangeDays : 1;
  });
  const [timeRange, setTimeRange] = useState(() => {
    const p = parseFromTo(fromParam, toParam);
    if (p) return { fromStr: p.fromStr, toStr: p.toStr };
    return toISORangeDays(new Date(), 1);
  });
  const [nextCursor, setNextCursor] = useState<string | null>(null);

  useEffect(() => {
    const parsed = parseFromTo(fromParam, toParam);
    if (parsed) {
      setTimeRange({ fromStr: parsed.fromStr, toStr: parsed.toStr });
      setRangeDays(parsed.rangeDays);
    }
  }, [fromParam, toParam]);

  useEffect(() => {
    if (txIdFromUrl) setSelectedTxId(txIdFromUrl);
  }, [txIdFromUrl]);

  useEffect(() => {
    if (operationParam) setOperationFilter(operationParam);
  }, [operationParam]);
  useEffect(() => {
    if (statusParam) setStatusFilter(statusParam);
  }, [statusParam]);
  useEffect(() => {
    setSearchFilter(searchParam);
    setSearchInput(searchParam);
  }, [searchParam]);

  const { fromStr, toStr } = timeRange;

  const { data: opsData } = useQuery({
    queryKey: ["vendor-canonical-operations"],
    queryFn: () => listOperations(),
    staleTime: 5 * 60 * 1000,
  });
  const operations = opsData?.items ?? [];

  const { data: metricsData } = useQuery({
    queryKey: vendorMetricsKey(fromStr, toStr),
    queryFn: () => getVendorMetricsOverview({ from: fromStr, to: toStr }),
    enabled: !!activeVendor && hasKey,
    retry: false,
    staleTime: STALE_HIGH_CHURN,
  });
  const totals = metricsData?.totals;

  const handleRangeChange = (days: number) => {
    setRangeDays(days);
    setTimeRange(toISORangeDays(new Date(), days));
    setNextCursor(null);
  };
  const { data, isLoading, error } = useQuery({
    queryKey: vendorTransactionsKey(
      fromStr,
      toStr,
      direction,
      operationFilter || null,
      statusFilter || null,
      searchFilter || null,
      nextCursor
    ),
    queryFn: () =>
      listVendorTransactions({
        from: fromStr,
        to: toStr,
        direction: direction === "all" ? undefined : direction,
        operation: operationFilter || undefined,
        status: statusFilter || undefined,
        search: searchFilter || undefined,
        limit: 50,
        cursor: nextCursor ?? undefined,
      }),
    enabled: !!activeVendor && hasKey,
    retry: false,
    staleTime: STALE_HIGH_CHURN,
  });

  const handleLoadMore = () => {
    if (data?.nextCursor) setNextCursor(data.nextCursor);
  };

  const { data: detailData, isLoading: detailLoading } = useQuery({
    queryKey: selectedTxId ? vendorTransactionDetailKey(selectedTxId) : ["vendor-transaction-detail", null],
    queryFn: () => getVendorTransactionDetail(selectedTxId!),
    enabled: !!selectedTxId && !!activeVendor && hasKey,
    retry: false,
    staleTime: STALE_HIGH_CHURN,
  });

  const transactions = data?.transactions ?? [];
  const hasMore = !!(data?.nextCursor);

  const handleDirectionChange = (d: "all" | "outbound" | "inbound") => {
    setDirection(d);
    setNextCursor(null);
    setSearchParams((p) => {
      const next = new URLSearchParams(p);
      if (d === "all") next.delete("direction");
      else next.set("direction", d);
      return next;
    });
  };

  const handleOperationChange = (op: string) => {
    setOperationFilter(op);
    setNextCursor(null);
    setSearchParams((p) => {
      const next = new URLSearchParams(p);
      if (op) next.set("operation", op);
      else next.delete("operation");
      return next;
    });
  };

  const handleStatusChange = (st: string) => {
    setStatusFilter(st);
    setNextCursor(null);
    setSearchParams((p) => {
      const next = new URLSearchParams(p);
      if (st) next.set("status", st);
      else next.delete("status");
      return next;
    });
  };

  const handleSearchApply = (val: string) => {
    const trimmed = val.trim();
    setSearchFilter(trimmed);
    setSearchInput(trimmed);
    setNextCursor(null);
    setSearchParams((p) => {
      const next = new URLSearchParams(p);
      if (trimmed) next.set("search", trimmed);
      else next.delete("search");
      return next;
    });
  };

  useEffect(() => {
    if (searchInput === searchFilter) return;
    const t = setTimeout(() => {
      const trimmed = searchInput.trim();
      setSearchFilter(trimmed);
      setSearchInput(trimmed);
      setNextCursor(null);
      setSearchParams((p) => {
        const next = new URLSearchParams(p);
        if (trimmed) next.set("search", trimmed);
        else next.delete("search");
        return next;
      });
    }, 400);
    return () => clearTimeout(t);
  }, [searchInput, searchFilter]);

  if (!activeVendor) {
    return (
      <VendorPageLayout title="Transactions" subtitle="View and filter integration transactions.">
        <div className="rounded-lg bg-gray-50 border border-gray-200 p-4">
          <p className="text-sm font-medium text-gray-700">
            Select an active licensee above.
          </p>
        </div>
      </VendorPageLayout>
    );
  }

  if (!hasKey) {
    return (
      <VendorPageLayout title="Transactions" subtitle="View and filter integration transactions.">
        <div className="rounded-lg bg-amber-50 border border-amber-200 p-4">
          <p className="text-sm font-medium text-amber-800">Active licensee not selected.</p>
          <OpenSettingsLink>Open Settings →</OpenSettingsLink>
        </div>
      </VendorPageLayout>
    );
  }

  if (error) {
    return (
      <VendorPageLayout title="Transactions" subtitle="View and filter integration transactions.">
        <div className="rounded-lg bg-red-50 border border-red-200 p-4">
          <p className="text-red-800 font-medium">Failed to load transactions</p>
          <p className="text-red-600 text-sm mt-1">
            {(error as Error)?.message ?? "Unknown error"}
          </p>
        </div>
      </VendorPageLayout>
    );
  }

  return (
    <VendorPageLayout
      title="Transactions"
      subtitle="Transactions where you are source (outbound) or target (inbound). Filter by time, direction, operation, status or ID."
    >
    <div className="space-y-6">

      {totals != null && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="rounded-xl border border-gray-200 bg-white p-3">
            <p className="text-xs font-medium text-gray-500">Total</p>
            <p className="text-xl font-bold text-gray-900">{totals.count}</p>
          </div>
          <div className="rounded-xl border border-gray-200 bg-white p-3">
            <p className="text-xs font-medium text-gray-500">Completed</p>
            <p className="text-xl font-bold text-emerald-700">{totals.completed}</p>
          </div>
          <div className="rounded-xl border border-gray-200 bg-white p-3">
            <p className="text-xs font-medium text-gray-500">Failed</p>
            <p className="text-xl font-bold text-red-700">{totals.failed}</p>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-lg border border-slate-200 overflow-hidden bg-slate-50">
          {(["all", "outbound", "inbound"] as const).map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => handleDirectionChange(d)}
              className={`px-3 py-2 text-sm font-medium ${
                direction === d
                  ? "bg-slate-600 text-white"
                  : "bg-transparent text-slate-600 hover:bg-slate-100"
              }`}
            >
              {d === "all" ? "All" : d === "outbound" ? "Outbound" : "Inbound"}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          {[1, 7, 30].map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => handleRangeChange(d)}
              className={`px-3 py-2 text-sm font-medium rounded-lg border ${
                rangeDays === d
                  ? "bg-slate-600 text-white border-slate-600"
                  : "bg-white text-gray-700 border-gray-200 hover:bg-gray-50"
              }`}
            >
              {d === 1 ? "24h" : `${d}d`}
            </button>
          ))}
        </div>
        <select
          value={operationFilter}
          onChange={(e) => handleOperationChange(e.target.value)}
          className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-slate-500"
        >
          <option value="">All operations</option>
          {operations.map((op) => (
            <option key={op.operationCode} value={op.operationCode}>
              {op.description ?? op.operationCode}
            </option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => handleStatusChange(e.target.value)}
          className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-slate-500"
        >
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        <input
          type="search"
          placeholder="Search by transaction ID, correlation ID, idempotency key…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearchApply(searchInput)}
          className="flex-1 min-w-[200px] px-3 py-2 text-sm border border-gray-200 rounded-lg placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-slate-500"
        />
      </div>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {isLoading ? (
          <VendorTableSkeleton rowCount={6} columnCount={9} />
        ) : (
        <>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead>
              <tr className="bg-gray-50">
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">Direction</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">Source</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">Target</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">Operation</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">HTTP</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">Idempotency key</th>
                <th className="px-4 py-2.5 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {transactions.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-gray-500 text-sm">
                    No transactions found
                  </td>
                </tr>
              ) : (
                transactions.map((t) => {
                  const pill = statusToPill(t.status ?? "unknown");
                  const dir = t.sourceVendor === activeVendor ? "Outbound" : "Inbound";
                  const txId = t.transactionId ?? null;
                  const handleRowClick = () => {
                    setSelectedTxId(txId);
                    setSearchParams((p) => {
                      const next = new URLSearchParams(p);
                      if (txId) next.set("transactionId", txId);
                      else next.delete("transactionId");
                      return next;
                    });
                  };
                  return (
                    <tr
                      key={t.transactionId ?? t.id ?? ""}
                      onClick={handleRowClick}
                      className="hover:bg-slate-50 cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3 text-sm text-gray-600 whitespace-nowrap">
                        {formatDate(t.createdAt)}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">{dir}</td>
                      <td className="px-4 py-3 text-sm font-mono text-gray-600">
                        {t.sourceVendor ?? "—"}
                      </td>
                      <td className="px-4 py-3 text-sm font-mono text-gray-600">
                        {t.targetVendor ?? "—"}
                      </td>
                      <td className="px-4 py-3 text-sm font-mono text-gray-600">
                        {t.operation ? (
                          <Link
                            to={`/flows/${encodeURIComponent(t.operation)}?from=${encodeURIComponent(fromStr)}&to=${encodeURIComponent(toStr)}`}
                            className="text-slate-700 hover:text-slate-900"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {t.operation}
                          </Link>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <StatusPill label={pill.label} variant={pill.variant} />
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {/* HTTP status not in list API; shown in detail drawer */}
                        —
                      </td>
                      <td className="px-4 py-3 text-sm font-mono text-gray-600 truncate max-w-[120px]" title={t.idempotencyKey}>
                        {t.idempotencyKey ?? "—"}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRowClick();
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
        <div className="px-4 py-3 border-t border-gray-200 bg-gray-50 flex justify-between items-center">
          {nextCursor ? (
            <button
              type="button"
              onClick={() => setNextCursor(null)}
              className="text-sm text-slate-600 hover:text-slate-800 font-medium"
            >
              ← First page
            </button>
          ) : (
            <span />
          )}
          {hasMore && (
            <button
              type="button"
              onClick={handleLoadMore}
              className="text-sm text-slate-600 hover:text-slate-800 font-medium"
            >
              Next page →
            </button>
          )}
        </div>
        </>
        )}
      </div>

      <TransactionDetailsDrawer
        isOpen={!!selectedTxId}
        onClose={() => {
          setSelectedTxId(null);
          setSearchParams((p) => {
            const next = new URLSearchParams(p);
            next.delete("transactionId");
            return next;
          });
        }}
        transaction={detailLoading ? null : vendorDetailToTransactionDetails(detailData ?? null)}
        onRedriveSuccess={(newTxId) => setSelectedTxId(newTxId)}
      />

      <div className="pt-4">
        <Link
          to="/"
          className="text-slate-600 hover:text-slate-800 font-medium text-sm"
        >
          View dashboard →
        </Link>
      </div>
    </div>
    </VendorPageLayout>
  );
}
