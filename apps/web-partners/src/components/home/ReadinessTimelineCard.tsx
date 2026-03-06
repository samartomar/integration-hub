/**
 * Readiness timeline – recent config/access/traffic events.
 * TODO: Replace with GET /v1/vendor/home/readiness-timeline when backend implements it.
 * Currently derives synthetic events from flow readiness + transactions.
 */

import { useMemo } from "react";
import { Skeleton } from "frontend-shared";
import { useQuery } from "@tanstack/react-query";
import { getActiveVendorCode } from "frontend-shared";
import {
  listVendorTransactions,
  getVendorContracts,
  getVendorOperationsCatalog,
  getVendorSupportedOperations,
  getVendorEndpoints,
  getVendorMappings,
  getMyAllowlist,
  getMyOperations,
} from "../../api/endpoints";
import { useVendorConfigBundle } from "../../hooks/useVendorConfigBundle";
import { STALE_CONFIG, STALE_HIGH_CHURN } from "../../api/queryKeys";
import { toISORangeDays } from "../../utils/dateRange";
import { buildReadinessRowsForLicensee, type FlowReadinessRow } from "../../utils/readinessModel";

export type ReadinessEventKind =
  | "operation_configured"
  | "operation_config_broken"
  | "access_allowed"
  | "access_blocked"
  | "first_traffic";

export interface ReadinessTimelineEvent {
  id: string;
  occurredAt: string;
  kind: ReadinessEventKind;
  operationCode: string;
  operationVersion?: string;
  licenseeName?: string;
}

const KIND_LABELS: Record<ReadinessEventKind, string> = {
  operation_configured: "Operation configured",
  operation_config_broken: "Configuration broken",
  access_allowed: "Access allowed",
  access_blocked: "Access blocked",
  first_traffic: "First traffic",
};

const MAX_EVENTS = 12;

/**
 * Derive synthetic timeline events from flow readiness + transactions.
 * TODO: Replace with GET /v1/vendor/home/readiness-timeline API.
 */
function deriveTimelineEvents(
  flowReadinessRows: FlowReadinessRow[],
  transactions: { operation?: string; sourceVendor?: string; targetVendor?: string; createdAt?: string }[]
): ReadinessTimelineEvent[] {
  const events: ReadinessTimelineEvent[] = [];
  const now = new Date().toISOString();
  const seenConfig = new Set<string>();
  const seenAccess = new Set<string>();

  for (const row of flowReadinessRows) {
    const op = row.operationCode;
    const ver = row.operationVersion;
    const configOk = row.vendorReady && row.isActive;
    const accessOk =
      (row.direction === "Inbound" && row.hasAllowedInboundAccess) ||
      (row.direction === "Outbound" && row.hasAllowedOutboundTarget);
    const key = `${op}-${row.direction}`;

    if (configOk && !seenConfig.has(op)) {
      seenConfig.add(op);
      events.push({
        id: `config-${op}-${ver}`,
        occurredAt: now,
        kind: "operation_configured",
        operationCode: op,
        operationVersion: ver,
      });
    } else if (!row.vendorReady && !seenConfig.has(`broken-${op}`)) {
      seenConfig.add(`broken-${op}`);
      events.push({
        id: `broken-${op}-${ver}`,
        occurredAt: now,
        kind: "operation_config_broken",
        operationCode: op,
        operationVersion: ver,
      });
    }

    if (accessOk && !seenAccess.has(key)) {
      seenAccess.add(key);
      events.push({
        id: `access-ok-${key}`,
        occurredAt: now,
        kind: "access_allowed",
        operationCode: op,
        operationVersion: ver,
      });
    } else if (!accessOk && (row.hasInboundConfig || row.hasOutboundConfig) && !seenAccess.has(`blocked-${key}`)) {
      seenAccess.add(`blocked-${key}`);
      events.push({
        id: `access-blocked-${key}`,
        occurredAt: now,
        kind: "access_blocked",
        operationCode: op,
        operationVersion: ver,
      });
    }
  }

  const opFirstSeen = new Map<string, string>();
  for (const t of transactions) {
    const op = t.operation;
    if (!op) continue;
    const createdAt = t.createdAt;
    if (!createdAt) continue;
    const existing = opFirstSeen.get(op);
    if (!existing || createdAt < existing) {
      opFirstSeen.set(op, createdAt);
    }
  }
  for (const [op, createdAt] of opFirstSeen) {
    events.push({
      id: `first-${op}-${createdAt}`,
      occurredAt: createdAt,
      kind: "first_traffic",
      operationCode: op,
    });
  }

  events.sort((a, b) => (b.occurredAt > a.occurredAt ? 1 : -1));
  return events.slice(0, MAX_EVENTS);
}

function formatEventTime(iso: string): string {
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

export function ReadinessTimelineCard() {
  const activeVendor = getActiveVendorCode();
  const hasKey = !!activeVendor;
  const range30d = useMemo(() => toISORangeDays(new Date(), 30), []);

  const { data: bundleData, isLoading: bundleLoading, isError: bundleError } = useVendorConfigBundle(!!hasKey);
  const useIndividualConfig = hasKey && (bundleError || !bundleData);

  const { data: vendorContractsData } = useQuery({
    queryKey: ["vendor-contracts"],
    queryFn: getVendorContracts,
    enabled: useIndividualConfig,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: catalogData, isLoading: catalogLoading } = useQuery({
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

  const { data: txData, isLoading: txLoading } = useQuery({
    queryKey: ["home", "readiness-timeline-tx", range30d.fromStr, range30d.toStr] as const,
    queryFn: () =>
      listVendorTransactions({
        from: range30d.fromStr,
        to: range30d.toStr,
        direction: "all",
        limit: 500,
      }),
    enabled: !!activeVendor && hasKey,
    retry: false,
    staleTime: STALE_HIGH_CHURN,
  });

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

  const events = useMemo(
    () => deriveTimelineEvents(flowReadinessRows, txData?.transactions ?? []),
    [flowReadinessRows, txData?.transactions]
  );

  if (!activeVendor || !hasKey) return null;

  const configLoading = (bundleLoading && !bundleData) || (useIndividualConfig && catalogLoading);
  const isInitialLoading = configLoading || txLoading;

  if (isInitialLoading) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-900">Readiness timeline</h3>
          <span className="text-xs text-slate-500">Last 30 days</span>
        </div>
        <ul className="mt-3 border-l-2 border-slate-200 pl-4">
          {[...Array(5)].map((_, i) => (
            <li key={i} className="relative -ml-[21px] mb-3 last:mb-0">
              <div className="absolute left-0 top-1.5 h-2 w-2 rounded-full -translate-x-1/2">
                <Skeleton className="h-full w-full rounded-full" />
              </div>
              <div className="pl-2 space-y-1">
                <Skeleton className="h-4 w-32 rounded" />
                <Skeleton className="h-3 w-48 rounded" />
                <Skeleton className="h-3 w-24 rounded" />
              </div>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900">Readiness timeline</h3>
        <span className="text-xs text-slate-500">Last 30 days</span>
      </div>
      {events.length === 0 ? (
        <p className="mt-3 text-center text-sm text-slate-500">No timeline events yet.</p>
      ) : (
        <ul className="mt-3 border-l-2 border-slate-200 pl-4">
          {events.map((evt) => (
            <li key={evt.id} className="relative -ml-[21px] mb-3 last:mb-0">
              <div className="absolute left-0 top-1.5 h-2 w-2 rounded-full bg-slate-400 -translate-x-1/2" />
              <div className="pl-2">
                <p className="text-sm font-medium text-slate-900">{KIND_LABELS[evt.kind]}</p>
                <p className="text-xs text-slate-600">
                  {evt.operationCode}
                  {evt.operationVersion ? ` ${evt.operationVersion}` : ""}
                  {evt.licenseeName ? ` · ${evt.licenseeName}` : ""}
                </p>
                <p className="text-xs text-slate-500 mt-0.5">{formatEventTime(evt.occurredAt)}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
