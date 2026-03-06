import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  Legend,
} from "recharts";
import {
  listOperations,
  listContracts,
  listEndpoints,
  getBatchReadiness,
  listTransactions,
} from "../../api/endpoints";
import type { Transaction, Operation, Endpoint, RegistryContract, Vendor } from "../../types";
import type { ReadinessItem } from "../../api/endpoints";
import { CardSkeleton, ChartSkeleton } from "../Skeleton";
import { OperationDetailDrawer } from "./OperationDetailDrawer";

export type TimeRange = "24h" | "7d" | "30d";

const TIME_RANGE_DAYS: Record<TimeRange, number> = {
  "24h": 1,
  "7d": 7,
  "30d": 30,
};

/** Dashboard transactions: single call with limit=100 (backend max). */
const DASHBOARD_TX_LIMIT = 100;

const ALL_LICENSEES = "ALL";

function formatISODate(date: Date): string {
  return date.toISOString().slice(0, 19);
}

export interface OperationSummary {
  operationCode: string;
  canonicalVersion: string | null;
  activeCanonicalContract: boolean;
  vendorCount: number;
  endpointCount: number;
  unverifiedEndpointCount: number;
  hasFromCanonicalMappings: boolean;
  hasToCanonicalMappings: boolean;
  totalTx: number;
  successTx: number;
  failedTx: number;
  downstreamErrorTx: number;
  lastErrorCode?: string;
  isActive: boolean;
}

export interface PerVendorSummary {
  vendorCode: string;
  endpointUrl?: string;
  verificationStatus?: string;
  hasFromMapping: boolean;
  hasToMapping: boolean;
  hasContractOverride: boolean;
}

function buildOperationSummaries(
  operations: Operation[],
  contracts: RegistryContract[],
  endpoints: Endpoint[],
  readinessByVendor: Map<string, ReadinessItem[]>,
  transactions: Transaction[]
): Map<string, OperationSummary> {
  const opsByCode = new Map<string, OperationSummary>();

  for (const op of operations) {
    const code = op.operationCode;
    const activeContract = contracts.some(
      (c) => c.operationCode === code && c.isActive !== false
    );
    const vendorSet = new Set<string>();
    const opEndpoints = endpoints.filter((e) => e.operationCode === code);
    let unverified = 0;
    for (const ep of opEndpoints) {
      vendorSet.add(ep.vendorCode);
      if (ep.verificationStatus !== "VERIFIED") unverified++;
    }

    let hasFrom = false;
    let hasTo = false;
    for (const [, items] of readinessByVendor) {
      const item = items.find((r) => r.operationCode === code);
      if (!item) continue;
      const mappingsCheck = item.checks?.find((c) => c.name === "mappings_present");
      if (mappingsCheck?.ok) {
        hasFrom = true;
        hasTo = true;
      } else {
        const missing = (mappingsCheck?.details?.missing as string[]) ?? [];
        if (!missing.includes("FROM_CANONICAL")) hasFrom = true;
        if (!missing.includes("TO_CANONICAL")) hasTo = true;
      }
    }

    const opTx = transactions.filter((t) => (t.operation ?? "") === code);
    const successTx = opTx.filter((t) => t.status === "completed").length;
    const failedTx = opTx.filter((t) => t.status !== "completed" && t.status !== "received").length;
    const downstreamErrorTx = opTx.filter((t) =>
      (t.status ?? "").startsWith("downstream_")
    ).length;
    const lastErr = opTx.find((t) => t.status !== "completed")?.errorCode ?? 
      opTx.find((t) => (t.status ?? "").startsWith("downstream_")) ? undefined : undefined;

    opsByCode.set(code, {
      operationCode: code,
      canonicalVersion: op.canonicalVersion ?? null,
      activeCanonicalContract: activeContract,
      vendorCount: vendorSet.size,
      endpointCount: opEndpoints.length,
      unverifiedEndpointCount: unverified,
      hasFromCanonicalMappings: hasFrom,
      hasToCanonicalMappings: hasTo,
      totalTx: opTx.length,
      successTx,
      failedTx,
      downstreamErrorTx,
      lastErrorCode: lastErr,
      isActive: op.isActive !== false,
    });
  }

  return opsByCode;
}

function buildPerVendorSummaries(
  operationCode: string,
  endpoints: Endpoint[],
  readinessByVendor: Map<string, ReadinessItem[]>
): PerVendorSummary[] {
  const opEndpoints = endpoints.filter((e) => e.operationCode === operationCode);
  const vendorCodes = [...new Set(opEndpoints.map((e) => e.vendorCode))];
  return vendorCodes.map((vendorCode) => {
    const ep = opEndpoints.find((e) => e.vendorCode === vendorCode);
    const items = readinessByVendor.get(vendorCode) ?? [];
    const item = items.find((r) => r.operationCode === operationCode);
    const mappingsCheck = item?.checks?.find((c) => c.name === "mappings_present");
    const missing = (mappingsCheck?.details?.missing as string[]) ?? [];
    return {
      vendorCode,
      endpointUrl: ep?.url,
      verificationStatus: ep?.verificationStatus,
      hasFromMapping: !missing.includes("FROM_CANONICAL"),
      hasToMapping: !missing.includes("TO_CANONICAL"),
      hasContractOverride: false, // No admin API for vendor contracts
    };
  });
}

function ConfigHealthPill({ summary }: { summary: OperationSummary }) {
  const hasIssues =
    !summary.activeCanonicalContract ||
    summary.unverifiedEndpointCount > 0 ||
    !summary.hasFromCanonicalMappings ||
    !summary.hasToCanonicalMappings;

  const isMissing =
    !summary.activeCanonicalContract || summary.endpointCount === 0;

  if (isMissing) {
    return (
      <span className="px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">
        Missing
      </span>
    );
  }
  if (hasIssues) {
    return (
      <span className="px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-800">
        Partial
      </span>
    );
  }
  return (
    <span className="px-2 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-800">
      OK
    </span>
  );
}

interface OperationsDashboardProps {
  selectedLicensee: string;
  vendors: Vendor[];
  subtitle: string;
}

export function OperationsDashboard({
  selectedLicensee,
  vendors,
  subtitle,
}: OperationsDashboardProps) {
  const [timeRange, setTimeRange] = useState<TimeRange>("24h");
  const [opFilter, setOpFilter] = useState("");
  const [selectedOp, setSelectedOp] = useState<string | null>(null);

  const days = TIME_RANGE_DAYS[timeRange];
  const now = new Date();
  const from = new Date(now);
  from.setDate(from.getDate() - days);
  const fromStr = formatISODate(from);
  const toStr = formatISODate(now);

  const vendorCodes = vendors.map((v) => v.vendorCode);

  const { data: opsData } = useQuery({
    queryKey: ["registry-operations"],
    queryFn: () => listOperations(),
  });
  const operations = opsData?.items ?? [];

  const { data: contractsData } = useQuery({
    queryKey: ["registry-contracts"],
    queryFn: () => listContracts(),
  });
  const contracts = contractsData?.items ?? [];

  const { data: endpointsData } = useQuery({
    queryKey: ["registry-endpoints"],
    queryFn: () => listEndpoints(),
  });
  const endpoints = endpointsData?.items ?? [];

  const { data: readinessByVendorData } = useQuery({
    queryKey: ["registry-readiness-batch", vendorCodes.join(",")],
    queryFn: async () => {
      const res = await getBatchReadiness(vendorCodes);
      const m = new Map<string, ReadinessItem[]>();
      res.items.forEach((item) => {
        if (item.error) m.set(item.vendorCode, []);
        else m.set(item.vendorCode, item.items ?? []);
      });
      return m;
    },
    enabled: vendorCodes.length > 0,
  });
  const readinessByVendor = readinessByVendorData ?? new Map<string, ReadinessItem[]>();

  const { data: txData, isLoading: txLoading, error: txError } = useQuery({
    queryKey: ["ops-dashboard-transactions", selectedLicensee, fromStr, toStr, opFilter],
    queryFn: async () => {
      const res = await listTransactions({
        ...(selectedLicensee !== ALL_LICENSEES && selectedLicensee
          ? { vendorCode: selectedLicensee }
          : {}),
        from: fromStr,
        to: toStr,
        operation: opFilter || undefined,
        limit: DASHBOARD_TX_LIMIT,
      });
      return res.transactions ?? [];
    },
    enabled: true,
    retry: (failureCount, err) => {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 400 && failureCount < 2) return true;
      return failureCount < 2;
    },
  });
  const transactions = txData ?? [];

  const summaries = useMemo(() => {
    return buildOperationSummaries(
      operations,
      contracts,
      endpoints,
      readinessByVendor,
      transactions
    );
  }, [operations, contracts, endpoints, readinessByVendor, transactions]);

  const filteredSummaries = useMemo(() => {
    let list = Array.from(summaries.values());
    if (opFilter) {
      list = list.filter((s) => s.operationCode === opFilter);
    }
    return list.sort((a, b) => b.totalTx - a.totalTx);
  }, [summaries, opFilter]);

  const activeOpsCount = filteredSummaries.filter((s) => s.isActive).length;
  const opsWithConfigIssues = filteredSummaries.filter(
    (s) =>
      !s.activeCanonicalContract ||
      s.unverifiedEndpointCount > 0 ||
      !s.hasFromCanonicalMappings ||
      !s.hasToCanonicalMappings
  ).length;
  const opsWithErrors = filteredSummaries.filter((s) => s.failedTx > 0).length;
  const opsWithZeroTraffic = filteredSummaries.filter(
    (s) => s.totalTx === 0 && s.isActive
  ).length;

  const volumeData = filteredSummaries
    .slice(0, 15)
    .map((s) => ({ name: s.operationCode, total: s.totalTx }));

  const statusData = opFilter
    ? (() => {
        const s = summaries.get(opFilter);
        if (!s) return [];
        return [
          { name: "Success", value: s.successTx, color: "#10b981" },
          { name: "Failed", value: s.failedTx - s.downstreamErrorTx, color: "#f59e0b" },
          { name: "Downstream", value: s.downstreamErrorTx, color: "#ef4444" },
        ].filter((d) => d.value > 0);
      })()
    : filteredSummaries.slice(0, 5).map((s) => ({
        name: s.operationCode,
        success: s.successTx,
        failed: s.failedTx,
      }));

  const perVendorSummaries = selectedOp
    ? buildPerVendorSummaries(selectedOp, endpoints, readinessByVendor)
    : [];

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-medium text-gray-800">
        Operations Dashboard – {subtitle}
      </h2>
      {txError && (
        <div className="rounded-lg bg-amber-50 border border-amber-200 p-4">
          <p className="text-amber-800 font-medium">Unable to load operations summary</p>
          <p className="text-amber-600 text-sm mt-1">
            {(txError as Error)?.message ?? "Transaction data could not be fetched."}
          </p>
        </div>
      )}
      {/* Time range + operation filter */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 overflow-hidden">
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
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-slate-600">Filter by operation</label>
          <select
            value={opFilter}
            onChange={(e) => setOpFilter(e.target.value)}
            className="px-2 py-1.5 text-sm border border-gray-300 rounded"
          >
            <option value="">All</option>
            {operations.map((o) => (
              <option key={o.operationCode} value={o.operationCode}>
                {o.operationCode}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid gap-4 md:grid-cols-4">
        {txLoading ? (
          [...Array(4)].map((_, i) => <CardSkeleton key={i} />)
        ) : (
          <>
            <div className="rounded-xl border border-gray-200 bg-white p-5">
              <p className="text-sm font-medium text-gray-500">Active operations</p>
              <p className="text-2xl font-bold mt-1 text-gray-900">{activeOpsCount}</p>
            </div>
            <div className="rounded-xl border border-gray-200 bg-white p-5">
              <p className="text-sm font-medium text-gray-500">Ops with config issues</p>
              <p className="text-2xl font-bold mt-1 text-amber-700">{opsWithConfigIssues}</p>
            </div>
            <div className="rounded-xl border border-gray-200 bg-white p-5">
              <p className="text-sm font-medium text-gray-500">Ops with errors in window</p>
              <p className="text-2xl font-bold mt-1 text-red-700">{opsWithErrors}</p>
            </div>
            <div className="rounded-xl border border-gray-200 bg-white p-5">
              <p className="text-sm font-medium text-gray-500">Ops with zero traffic</p>
              <p className="text-2xl font-bold mt-1 text-gray-900">{opsWithZeroTraffic}</p>
            </div>
          </>
        )}
      </div>

      {/* Charts */}
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Volume by operation</h3>
          {txLoading ? (
            <ChartSkeleton />
          ) : volumeData.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={volumeData} layout="vertical" margin={{ left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200" />
                <XAxis type="number" tick={{ fontSize: 11 }} stroke="#94a3b8" />
                <YAxis dataKey="name" type="category" width={100} tick={{ fontSize: 10 }} stroke="#94a3b8" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#fff",
                    border: "1px solid #e2e8f0",
                    borderRadius: "8px",
                  }}
                />
                <Bar dataKey="total" fill="#6366f1" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
              No data in this range
            </div>
          )}
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">
            {opFilter ? `Status breakdown: ${opFilter}` : "Top ops by status"}
          </h3>
          {txLoading ? (
            <ChartSkeleton />
          ) : opFilter && statusData.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={statusData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200" />
                <XAxis type="number" tick={{ fontSize: 11 }} stroke="#94a3b8" />
                <YAxis dataKey="name" type="category" width={80} tick={{ fontSize: 10 }} stroke="#94a3b8" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#fff",
                    border: "1px solid #e2e8f0",
                    borderRadius: "8px",
                  }}
                />
                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                  {statusData.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={"color" in entry ? entry.color : "#94a3b8"}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : !opFilter && statusData.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={statusData} margin={{ top: 20 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200" />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} stroke="#94a3b8" />
                <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#fff",
                    border: "1px solid #e2e8f0",
                    borderRadius: "8px",
                  }}
                />
                <Legend />
                <Bar dataKey="success" stackId="a" fill="#10b981" />
                <Bar dataKey="failed" stackId="a" fill="#ef4444" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
              {opFilter ? "Select an operation with traffic" : "No data in this range"}
            </div>
          )}
        </div>
      </div>

      {/* Operations table */}
      <div className="mt-4 bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
          <h3 className="text-sm font-semibold text-gray-800">Operations</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead>
              <tr className="bg-gray-50">
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">
                  Operation
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">
                  Canonical version
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">
                  Vendors
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">
                  Endpoints (Verified/Total)
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">
                  Traffic
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">
                  Success rate
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">
                  Downstream errors
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">
                  Config health
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {filteredSummaries.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-gray-500 text-sm">
                    No operations found
                  </td>
                </tr>
              ) : (
                filteredSummaries.map((s) => (
                  <tr
                    key={s.operationCode}
                    onClick={() => setSelectedOp(s.operationCode)}
                    className="hover:bg-slate-50 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 text-sm font-mono font-medium">{s.operationCode}</td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {s.canonicalVersion ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">{s.vendorCount}</td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {s.endpointCount - s.unverifiedEndpointCount}/{s.endpointCount}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">{s.totalTx}</td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {s.totalTx > 0
                        ? `${Math.round((s.successTx / s.totalTx) * 100)}%`
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">{s.downstreamErrorTx}</td>
                    <td className="px-4 py-3">
                      <ConfigHealthPill summary={s} />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <OperationDetailDrawer
        operationCode={selectedOp}
        perVendorSummaries={perVendorSummaries}
        onClose={() => setSelectedOp(null)}
      />
    </div>
  );
}
