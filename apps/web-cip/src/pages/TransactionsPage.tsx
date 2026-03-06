import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getAdminDirectionLabel } from "frontend-shared";
import { listTransactions, listVendors, type ListRegistryResponse } from "../api/endpoints";
import type { Transaction, Vendor } from "../types";
import { TransactionDetailDrawer } from "../components/TransactionDetailDrawer";
import { TableRowSkeleton } from "../components/Skeleton";
import { usePhiAccess } from "../security/PhiAccessContext";

function shortenId(id: string, head = 8, tail = 4): string {
  if (!id) return "";
  if (id.length <= head + tail + 1) return id;
  return `${id.slice(0, head)}…${id.slice(-tail)}`;
}

const IconClipboard = () => (
  <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
  </svg>
);

const IconSearch = () => (
  <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
  </svg>
);

const ALL_LICENSEES = "ALL";
const TX_LIMIT = 100;

type TimeRange = "24h" | "7d" | "30d";

const TIME_RANGE_DAYS: Record<TimeRange, number> = {
  "24h": 1,
  "7d": 7,
  "30d": 30,
};

function formatISODate(date: Date): string {
  return date.toISOString().slice(0, 19);
}

function formatDisplayDate(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const h = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  const s = String(d.getSeconds()).padStart(2, "0");
  return `${y}-${m}-${day} ${h}:${min}:${s}`;
}

function StatusBadge({ status }: { status: string }) {
  const variant: Record<string, string> = {
    completed: "bg-emerald-100 text-emerald-800",
    validation_failed: "bg-amber-100 text-amber-800",
    downstream_error: "bg-red-100 text-red-800",
    downstream_timeout: "bg-red-100 text-red-800",
    received: "bg-indigo-100 text-indigo-800",
  };
  return (
    <span
      className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
        variant[status] ?? "bg-gray-100 text-gray-700"
      }`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

function copyToClipboard(text: string, e: React.MouseEvent) {
  e.stopPropagation();
  navigator.clipboard.writeText(text);
}

export function TransactionsPage() {
  const { phiModeEnabled, reason } = usePhiAccess();
  const [selectedLicensee, setSelectedLicensee] = useState(ALL_LICENSEES);
  const [timeRange, setTimeRange] = useState<TimeRange>("7d");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterOperation, setFilterOperation] = useState("");
  const [filterDirection, setFilterDirection] = useState<"all" | "outbound" | "inbound">("all");
  const [search, setSearch] = useState("");
  const [selectedTx, setSelectedTx] = useState<{
    transactionId: string;
    sourceVendor: string;
  } | null>(null);

  const days = TIME_RANGE_DAYS[timeRange];
  const now = new Date();
  const from = new Date(now);
  from.setDate(from.getDate() - days);
  const fromStr = formatISODate(from);
  const toStr = formatISODate(now);

  const { data: vendorsData } = useQuery<ListRegistryResponse<Vendor>>({
    queryKey: ["registry-vendors"],
    queryFn: () => listVendors(),
  });
  const vendors = vendorsData?.items ?? [];
  const activeVendors = vendors.filter((v) => v.isActive !== false);

  const { data, isLoading, error } = useQuery({
    queryKey: ["transactions", selectedLicensee, fromStr, toStr],
    queryFn: () =>
      listTransactions({
        ...(selectedLicensee !== ALL_LICENSEES && selectedLicensee
          ? { vendorCode: selectedLicensee }
          : {}),
        from: fromStr,
        to: toStr,
        limit: TX_LIMIT,
      }),
    staleTime: 30_000,
  });

  const rawTransactions = data?.transactions ?? [];

  const filteredTransactions = useMemo(() => {
    let list = rawTransactions;

    if (filterStatus) {
      list = list.filter((t) => (t.status ?? "") === filterStatus);
    }
    if (filterOperation) {
      list = list.filter((t) => (t.operation ?? "") === filterOperation);
    }
    if (selectedLicensee !== ALL_LICENSEES && filterDirection !== "all") {
      if (filterDirection === "outbound") {
        list = list.filter((t) => (t.source_vendor ?? "") === selectedLicensee);
      } else {
        list = list.filter((t) => (t.target_vendor ?? "") === selectedLicensee);
      }
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter(
        (t) =>
          (t.transaction_id ?? "").toLowerCase().includes(q) ||
          (t.correlation_id ?? "").toLowerCase().includes(q) ||
          (t.idempotency_key ?? "").toLowerCase().includes(q)
      );
    }
    return list;
  }, [
    rawTransactions,
    filterStatus,
    filterOperation,
    filterDirection,
    selectedLicensee,
    search,
  ]);

  const statusOptions = useMemo(() => {
    const set = new Set<string>();
    rawTransactions.forEach((t) => {
      const s = t.status ?? "unknown";
      if (s !== "unknown") set.add(s);
    });
    return Array.from(set).sort();
  }, [rawTransactions]);

  const operationOptions = useMemo(() => {
    const set = new Set<string>();
    rawTransactions.forEach((t) => {
      const o = t.operation ?? "";
      if (o) set.add(o);
    });
    return Array.from(set).sort();
  }, [rawTransactions]);

  const detailVendorCode =
    selectedTx?.sourceVendor && selectedTx.sourceVendor
      ? selectedTx.sourceVendor
      : selectedLicensee !== ALL_LICENSEES
        ? selectedLicensee
        : undefined;

  return (
    <div className="space-y-4 sm:space-y-6">
      <h1 className="text-lg sm:text-2xl font-semibold text-slate-900 tracking-tight">Transactions</h1>

      {/* Filters */}
      <div className="rounded-lg bg-white shadow-sm border border-gray-200 p-3 sm:p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Licensee</label>
            <select
              value={selectedLicensee}
              onChange={(e) => setSelectedLicensee(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
            >
              <option value={ALL_LICENSEES}>All licensees</option>
              {activeVendors.map((v) => (
                <option key={v.vendorCode} value={v.vendorCode}>
                  {v.vendorCode} ({v.vendorName ?? v.vendorCode})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Status</label>
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
            >
              <option value="">All</option>
              {statusOptions.map((s) => (
                <option key={s} value={s}>
                  {s.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Operation</label>
            <select
              value={filterOperation}
              onChange={(e) => setFilterOperation(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
            >
              <option value="">All</option>
              {operationOptions.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">
              Search (transaction ID, correlation ID, idempotency key)
            </label>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter results…"
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
            />
          </div>
          <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 overflow-hidden md:col-span-2">
            {(["24h", "7d", "30d"] as TimeRange[]).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setTimeRange(r)}
                className={`px-3 py-2 text-sm font-medium ${
                  timeRange === r
                    ? "bg-slate-600 text-white"
                    : "bg-transparent text-slate-600 hover:bg-slate-100"
                }`}
              >
                {r === "24h" ? "Last 24h" : r === "7d" ? "Last 7d" : "Last 30d"}
              </button>
            ))}
          </div>
          {selectedLicensee !== ALL_LICENSEES && (
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Direction</label>
              <select
                value={filterDirection}
                onChange={(e) =>
                  setFilterDirection(e.target.value as "all" | "outbound" | "inbound")
                }
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
              >
                <option value="all">All directions</option>
                <option value="outbound">{getAdminDirectionLabel("OUTBOUND")}</option>
                <option value="inbound">{getAdminDirectionLabel("INBOUND")}</option>
              </select>
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 p-4">
          <p className="text-red-800 font-medium">Failed to load transactions</p>
          <p className="text-red-600 text-sm mt-1">
            {(error as Error)?.message ?? "Unknown error"}
          </p>
        </div>
      )}

      {/* Table */}
      <div className="rounded-lg bg-white shadow-sm border border-gray-200 overflow-hidden">
        <div className="px-3 py-2 border-b border-gray-200 bg-gray-50 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-800">
            Results {data ? `(${filteredTransactions.length} of ${rawTransactions.length})` : ""}
          </h3>
          <span className="text-xs text-slate-500">Limit: {TX_LIMIT}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="px-3 py-2 text-left">Created</th>
                <th className="px-3 py-2 text-left">Transaction ID</th>
                <th className="px-3 py-2 text-left">Source</th>
                <th className="px-3 py-2 text-left">Target</th>
                <th className="px-3 py-2 text-left">Operation</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-left">Error / HTTP</th>
                <th className="px-3 py-2 text-left">Redrives</th>
                <th className="px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {isLoading ? (
                [...Array(5)].map((_, i) => (
                  <TableRowSkeleton key={i} />
                ))
              ) : filteredTransactions.length === 0 ? (
                <tr>
                  <td
                    colSpan={9}
                    className="px-3 py-6 text-center text-gray-500 text-sm"
                  >
                    No transactions found
                  </td>
                </tr>
              ) : (
                filteredTransactions.map((t) => (
                  <TransactionRow
                    key={t.transaction_id}
                    transaction={t}
                    onSelect={() =>
                      setSelectedTx({
                        transactionId: t.transaction_id,
                        sourceVendor: t.source_vendor ?? "",
                      })
                    }
                    onCopyId={copyToClipboard}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <TransactionDetailDrawer
        transactionId={selectedTx?.transactionId ?? null}
        vendorCode={detailVendorCode}
        expandSensitive={phiModeEnabled}
        sensitiveReason={reason}
        onClose={() => setSelectedTx(null)}
      />
    </div>
  );
}

function TransactionRow({
  transaction: t,
  onSelect,
  onCopyId,
}: {
  transaction: Transaction;
  onSelect: () => void;
  onCopyId: (text: string, e: React.MouseEvent) => void;
}) {
  const tAny = t as unknown as Record<string, unknown>;
  const errorCode = t.errorCode ?? tAny.error_code;
  const httpStatus = t.httpStatus ?? tAny.http_status;
  const redriveCount = t.redrive_count ?? tAny.redrive_count ?? 0;
  const hasRedrive = typeof redriveCount === "number" ? redriveCount > 0 : false;
  const isAi = (t.idempotency_key ?? "").toLowerCase().startsWith("ai-");

  return (
    <tr
      onClick={onSelect}
      className="hover:bg-slate-50 cursor-pointer transition-colors"
    >
      <td className="px-3 py-2 text-gray-600">
        {formatDisplayDate(t.created_at)}
      </td>
      <td className="px-3 py-2 font-mono text-xs">
        <div className="flex items-center gap-2">
          <span
            className="inline-block max-w-[170px] truncate align-middle"
            title={t.transaction_id}
          >
            {shortenId(t.transaction_id)}
          </span>
          {isAi && (
            <span className="inline-flex items-center rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-medium text-violet-700">
              AI
            </span>
          )}
        </div>
      </td>
      <td className="px-3 py-2 text-gray-600">
        {t.source_vendor ?? "—"}
      </td>
      <td className="px-3 py-2 text-gray-600">
        {t.target_vendor ?? "—"}
      </td>
      <td className="px-3 py-2 text-gray-600">
        {t.operation ?? "—"}
      </td>
      <td className="px-3 py-2">
        <StatusBadge status={t.status ?? "unknown"} />
      </td>
      <td className="px-3 py-2 text-gray-600">
        {errorCode || httpStatus ? (
          <span>
            {errorCode != null && errorCode !== "" && (
              <span className="text-red-600">{String(errorCode)}</span>
            )}
            {errorCode != null && errorCode !== "" && httpStatus != null && " · "}
            {httpStatus != null && (
              <span>HTTP {String(httpStatus)}</span>
            )}
          </span>
        ) : (
          "—"
        )}
      </td>
      <td className="px-3 py-2 text-gray-600">
        {hasRedrive ? (
          <span className="inline-flex items-center rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800">
            ↻ {String(redriveCount)}
          </span>
        ) : (
          "—"
        )}
      </td>
      <td className="px-3 py-2">
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onCopyId(t.transaction_id, e);
            }}
            className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 hover:bg-slate-50"
            title="Copy transaction ID"
          >
            <IconClipboard />
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onSelect();
            }}
            className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 hover:bg-slate-50"
            title="View debug"
          >
            <IconSearch />
          </button>
        </div>
      </td>
    </tr>
  );
}
