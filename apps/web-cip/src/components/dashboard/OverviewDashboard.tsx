import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { listTransactions } from "../../api/endpoints";
import type { Transaction, Vendor } from "../../types";
import { CardSkeleton, TableRowSkeleton, ChartSkeleton } from "../Skeleton";
import { TransactionDetailDrawer } from "../TransactionDetailDrawer";
import { usePhiAccess } from "../../security/PhiAccessContext";

const STATUS_COLORS: Record<string, string> = {
  completed: "#10b981",
  validation_failed: "#f59e0b",
  downstream_error: "#ef4444",
  downstream_timeout: "#ef4444",
  received: "#6366f1",
};
const DEFAULT_COLOR = "#94a3b8";

function formatISODate(date: Date): string {
  return date.toISOString().slice(0, 19);
}

function useDashboardData(
  selectedLicensee: string,
  rangeDays: number
) {
  const now = new Date();
  const from = new Date(now);
  from.setDate(from.getDate() - rangeDays);
  const toStr = formatISODate(now);
  const fromStr = formatISODate(from);

  return useQuery({
    queryKey: ["dashboard-transactions", selectedLicensee, fromStr, toStr],
    queryFn: () =>
      listTransactions({
        ...(selectedLicensee !== "ALL" && selectedLicensee
          ? { vendorCode: selectedLicensee }
          : {}),
        from: fromStr,
        to: toStr,
        limit: 100,
      }),
    retry: (failureCount, error) => {
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status === 400 && failureCount < 2) return true;
      return failureCount < 2;
    },
  });
}

function aggregateByStatus(transactions: Transaction[]) {
  const byStatus: Record<string, number> = {};
  for (const t of transactions) {
    const s = t.status ?? "unknown";
    byStatus[s] = (byStatus[s] ?? 0) + 1;
  }
  return byStatus;
}

function computeCounts(transactions: Transaction[]) {
  const byStatus = aggregateByStatus(transactions);
  const completed = byStatus["completed"] ?? 0;
  const validationFailed = byStatus["validation_failed"] ?? 0;
  const downstreamErrors = Object.entries(byStatus).reduce(
    (acc, [k, v]) => (k.startsWith("downstream_") ? acc + v : acc),
    0
  );
  const total = transactions.length;
  const failed = validationFailed + downstreamErrors;
  return {
    total,
    completed,
    failed,
    validationFailed,
    downstreamErrors,
  };
}

function groupByHour(transactions: Transaction[]) {
  const buckets: Record<string, number> = {};
  for (const t of transactions) {
    const ts = t.created_at;
    if (!ts) continue;
    const d = new Date(ts);
    const key =
      d.getFullYear() +
      "-" +
      String(d.getMonth() + 1).padStart(2, "0") +
      "-" +
      String(d.getDate()).padStart(2, "0") +
      " " +
      String(d.getHours()).padStart(2, "0") +
      ":00";
    buckets[key] = (buckets[key] ?? 0) + 1;
  }
  return Object.entries(buckets)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

function groupByDay(transactions: Transaction[]) {
  const buckets: Record<string, number> = {};
  for (const t of transactions) {
    const ts = t.created_at;
    if (!ts) continue;
    const d = new Date(ts);
    const key =
      d.getFullYear() +
      "-" +
      String(d.getMonth() + 1).padStart(2, "0") +
      "-" +
      String(d.getDate()).padStart(2, "0");
    buckets[key] = (buckets[key] ?? 0) + 1;
  }
  return Object.entries(buckets)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

function statusToPieData(transactions: Transaction[]) {
  const byStatus = aggregateByStatus(transactions);
  return Object.entries(byStatus).map(([name, value]) => ({
    name: name.replace(/_/g, " "),
    value,
  }));
}

function SummaryCard({
  label,
  value,
  suffix = "",
  variant = "default",
}: {
  label: string;
  value: number;
  suffix?: string;
  variant?: "default" | "success" | "warning" | "danger";
}) {
  const colors: Record<string, string> = {
    default: "bg-white border-gray-200 shadow-sm",
    success: "bg-white border-emerald-200 shadow-sm",
    warning: "bg-white border-amber-200 shadow-sm",
    danger: "bg-white border-red-200 shadow-sm",
  };
  const valueColors: Record<string, string> = {
    default: "text-gray-900",
    success: "text-emerald-600",
    warning: "text-amber-600",
    danger: "text-red-600",
  };
  return (
    <div className={`rounded-lg border p-5 ${colors[variant]}`}>
      <p className="text-sm font-medium text-gray-500">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${valueColors[variant]}`}>
        {value}
        {suffix}
      </p>
    </div>
  );
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

function formatDate(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

interface OverviewDashboardProps {
  selectedLicensee: string;
  vendors: Vendor[];
  subtitle: string;
}

export function OverviewDashboard({
  selectedLicensee,
  vendors: _vendors,
  subtitle,
}: OverviewDashboardProps) {
  const { phiModeEnabled, reason } = usePhiAccess();
  const [rangeDays, setRangeDays] = useState(7);
  const [selectedTransaction, setSelectedTransaction] = useState<{
    transactionId: string;
    sourceVendor: string;
  } | null>(null);

  const { data, isLoading, error } = useDashboardData(selectedLicensee, rangeDays);
  const transactions = data?.transactions ?? [];
  const counts = computeCounts(transactions);
  const lineData = rangeDays <= 1 ? groupByHour(transactions) : groupByDay(transactions);
  const pieData = statusToPieData(transactions);
  const recent = transactions.slice(0, 20);

  if (error) {
    return (
      <div className="space-y-6">
        <div className="rounded-lg bg-red-50 border border-red-200 p-4">
          <p className="text-red-800 font-medium">Failed to load dashboard data</p>
          <p className="text-red-600 text-sm mt-1">
            {(error as Error)?.message ?? "Unknown error"}
          </p>
          <p className="text-red-500 text-xs mt-2">
            Ensure you are logged in via Okta and the API is reachable.
          </p>
        </div>
      </div>
    );
  }

  const detailVendorCode =
    (selectedTransaction?.sourceVendor && selectedTransaction.sourceVendor)
      ? selectedTransaction.sourceVendor
      : (selectedLicensee !== "ALL" ? selectedLicensee : undefined);

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-medium text-gray-800">
        Overview Dashboard – {subtitle}
      </h2>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex rounded-lg border border-slate-200 overflow-hidden bg-slate-50">
            <button
              type="button"
              onClick={() => setRangeDays(1)}
              className={`px-3 py-2 text-sm font-medium ${
                rangeDays === 1
                  ? "bg-slate-600 text-white"
                  : "bg-transparent text-slate-600 hover:bg-slate-100"
              }`}
            >
              24h
            </button>
            <button
              type="button"
              onClick={() => setRangeDays(7)}
              className={`px-3 py-2 text-sm font-medium border-l border-slate-200 ${
                rangeDays === 7
                  ? "bg-slate-600 text-white"
                  : "bg-transparent text-slate-600 hover:bg-slate-100"
              }`}
            >
              7d
            </button>
          </div>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {isLoading ? (
          [...Array(4)].map((_, i) => <CardSkeleton key={i} />)
        ) : (
          <>
            <SummaryCard label="Total" value={counts.total} />
            <SummaryCard label="Failed" value={counts.failed} variant="danger" />
            <SummaryCard label="Downstream Errors" value={counts.downstreamErrors} variant="danger" />
            <SummaryCard
              label="Success rate"
              value={counts.total > 0 ? Math.round((counts.completed / counts.total) * 100) : 0}
              suffix="%"
              variant={counts.total > 0 && counts.completed / counts.total >= 0.9 ? "success" : "default"}
            />
          </>
        )}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">
            Transactions over time
          </h3>
          {isLoading ? (
            <ChartSkeleton />
          ) : lineData.length > 0 ? (
            <ResponsiveContainer width="100%" height={230}>
              <LineChart data={lineData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 11 }}
                  stroke="#94a3b8"
                />
                <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#fff",
                    border: "1px solid #e2e8f0",
                    borderRadius: "8px",
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#6366f1"
                  strokeWidth={2}
                  dot={{ fill: "#6366f1", r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[230px] flex items-center justify-center text-gray-400 text-sm">
              No transaction data in this range
            </div>
          )}
        </div>

        <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">
            Status breakdown
          </h3>
          {isLoading ? (
            <ChartSkeleton />
          ) : pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={230}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="45%"
                  innerRadius={42}
                  outerRadius={65}
                  paddingAngle={2}
                  dataKey="value"
                >
                  {pieData.map((entry, index) => {
                    const statusKey = entry.name.replace(/ /g, "_");
                    const color = STATUS_COLORS[statusKey] ?? DEFAULT_COLOR;
                    return <Cell key={index} fill={color} />;
                  })}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#fff",
                    border: "1px solid #e2e8f0",
                    borderRadius: "8px",
                  }}
                />
                <Legend layout="horizontal" align="center" verticalAlign="bottom" wrapperStyle={{ paddingTop: 8 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[230px] flex items-center justify-center text-gray-400 text-sm">
              No transaction data in this range
            </div>
          )}
        </div>
      </div>

      {/* Recent transactions table */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
          <h3 className="text-sm font-semibold text-gray-800">
            Recent transactions
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead>
              <tr className="bg-gray-50">
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">
                  Created
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">
                  Transaction ID
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">
                  Source
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">
                  Target
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">
                  Operation
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">
                  Status
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">
                  Redrives
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {isLoading ? (
                [...Array(5)].map((_, i) => <TableRowSkeleton key={i} />)
              ) : recent.length === 0 ? (
                <tr>
                  <td
                    colSpan={7}
                    className="px-4 py-8 text-center text-gray-500 text-sm"
                  >
                    No transactions found
                  </td>
                </tr>
              ) : (
                recent.map((t) => (
                  <tr
                    key={t.transaction_id}
                    onClick={() =>
                      setSelectedTransaction({
                        transactionId: t.transaction_id,
                        sourceVendor: t.source_vendor ?? "",
                      })
                    }
                    className="hover:bg-slate-50 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {formatDate(t.created_at)}
                    </td>
                    <td className="px-4 py-3 text-sm font-mono text-gray-900">
                      {t.transaction_id}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {t.source_vendor ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {t.target_vendor ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {t.operation ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={t.status ?? "unknown"} />
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {t.redrive_count ?? 0}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <TransactionDetailDrawer
        transactionId={selectedTransaction?.transactionId ?? null}
        vendorCode={detailVendorCode}
        expandSensitive={phiModeEnabled}
        sensitiveReason={reason}
        onClose={() => setSelectedTransaction(null)}
      />
    </div>
  );
}
