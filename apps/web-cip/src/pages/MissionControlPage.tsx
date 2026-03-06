import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PageLayout } from "frontend-shared";
import {
  getMissionControlActivity,
  getMissionControlTopology,
} from "../api/endpoints";
import type {
  MissionControlActivityEvent,
  MissionControlEdge,
  MissionControlStage,
} from "../types";

const OVERLAY_WINDOW_MS = 8_000;

type EdgeStatus = {
  stage: MissionControlStage;
  event?: MissionControlActivityEvent;
};

function edgeKey(edge: Pick<MissionControlEdge, "sourceVendorCode" | "targetVendorCode" | "operationCode">): string {
  return `${edge.sourceVendorCode}__${edge.targetVendorCode}__${edge.operationCode}`;
}

function stageClasses(stage: MissionControlStage | null): string {
  switch (stage) {
    case "EXECUTE_START":
      return "border-blue-200 bg-blue-50 text-blue-700";
    case "EXECUTE_SUCCESS":
      return "border-green-200 bg-green-50 text-green-700";
    case "POLICY_DENY":
      return "border-red-200 bg-red-50 text-red-700";
    case "EXECUTE_ERROR":
      return "border-amber-200 bg-amber-50 text-amber-700";
    default:
      return "border-slate-200 bg-white text-slate-700";
  }
}

function stageLabel(stage: MissionControlStage): string {
  if (stage === "EXECUTE_START") return "Active";
  if (stage === "EXECUTE_SUCCESS") return "Success";
  if (stage === "POLICY_DENY") return "Policy Deny";
  return "Error";
}

export function MissionControlPage() {
  const [operationFilter, setOperationFilter] = useState<string>("ALL");
  const [vendorFilter, setVendorFilter] = useState<string>("ALL");
  const [paused, setPaused] = useState(false);

  const topologyQuery = useQuery({
    queryKey: ["mission-control", "topology"],
    queryFn: getMissionControlTopology,
    refetchInterval: paused ? false : 30_000,
  });

  const activityQuery = useQuery({
    queryKey: ["mission-control", "activity"],
    queryFn: () => getMissionControlActivity({ lookbackMinutes: 10, limit: 100 }),
    refetchInterval: paused ? false : 2_000,
  });

  const topology = topologyQuery.data ?? { nodes: [], edges: [] };
  const events = activityQuery.data?.items ?? [];

  const operationOptions = useMemo(
    () => Array.from(new Set(topology.edges.map((e) => e.operationCode))).sort(),
    [topology.edges]
  );
  const vendorOptions = useMemo(
    () => Array.from(new Set(topology.nodes.map((n) => n.vendorCode))).sort(),
    [topology.nodes]
  );

  const filteredEdges = useMemo(
    () =>
      topology.edges.filter((edge) => {
        if (operationFilter !== "ALL" && edge.operationCode !== operationFilter) return false;
        if (
          vendorFilter !== "ALL" &&
          edge.sourceVendorCode !== vendorFilter &&
          edge.targetVendorCode !== vendorFilter
        ) {
          return false;
        }
        return true;
      }),
    [topology.edges, operationFilter, vendorFilter]
  );

  const filteredEvents = useMemo(
    () =>
      events.filter((event) => {
        if (operationFilter !== "ALL" && event.operationCode !== operationFilter) return false;
        if (
          vendorFilter !== "ALL" &&
          event.sourceVendorCode !== vendorFilter &&
          event.targetVendorCode !== vendorFilter
        ) {
          return false;
        }
        return true;
      }),
    [events, operationFilter, vendorFilter]
  );

  const liveEdgeStatus = useMemo(() => {
    const now = Date.now();
    const map = new Map<string, EdgeStatus>();
    for (const event of filteredEvents) {
      if (!event.sourceVendorCode || !event.targetVendorCode || !event.operationCode) continue;
      const tsMs = event.ts ? Date.parse(event.ts) : Number.NaN;
      if (!Number.isFinite(tsMs) || now - tsMs > OVERLAY_WINDOW_MS) continue;
      const key = edgeKey({
        sourceVendorCode: event.sourceVendorCode,
        targetVendorCode: event.targetVendorCode,
        operationCode: event.operationCode,
      });
      if (!map.has(key)) {
        map.set(key, { stage: event.stage, event });
      }
    }
    return map;
  }, [filteredEvents]);

  return (
    <PageLayout
      embedded
      title="Mission Control"
      description="Integration graph with live metadata-only execute and policy activity."
      right={
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={operationFilter}
            onChange={(e) => setOperationFilter(e.target.value)}
            className="px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white"
          >
            <option value="ALL">All operations</option>
            {operationOptions.map((operationCode) => (
              <option key={operationCode} value={operationCode}>
                {operationCode}
              </option>
            ))}
          </select>
          <select
            value={vendorFilter}
            onChange={(e) => setVendorFilter(e.target.value)}
            className="px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white"
          >
            <option value="ALL">All vendors</option>
            {vendorOptions.map((vendorCode) => (
              <option key={vendorCode} value={vendorCode}>
                {vendorCode}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => setPaused((value) => !value)}
            className={`px-3 py-2 text-sm border rounded-lg ${
              paused ? "border-amber-300 bg-amber-50 text-amber-700" : "border-slate-300 bg-white text-slate-700"
            }`}
          >
            {paused ? "Resume live updates" : "Pause live updates"}
          </button>
        </div>
      }
    >
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <section className="xl:col-span-2 border border-slate-200 rounded-lg bg-white overflow-hidden">
          <header className="px-4 py-3 border-b border-slate-200 bg-slate-50">
            <h2 className="text-sm font-semibold text-slate-900">Integration Graph</h2>
            <p className="text-xs text-slate-600">
              Active vendors and explicit admin allowlist links. Overlay reflects recent events.
            </p>
          </header>
          <div className="p-4 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {topology.nodes.map((node) => (
                <div key={node.vendorCode} className="rounded-lg border border-slate-200 px-3 py-2">
                  <p className="text-xs text-slate-500">{node.vendorCode}</p>
                  <p className="text-sm font-medium text-slate-900">{node.vendorName}</p>
                </div>
              ))}
            </div>
            <div className="space-y-2">
              {topologyQuery.isLoading ? (
                <p className="text-sm text-slate-500">Loading topology...</p>
              ) : filteredEdges.length === 0 ? (
                <p className="text-sm text-slate-500">No edges for current filters.</p>
              ) : (
                filteredEdges.map((edge) => {
                  const status = liveEdgeStatus.get(edgeKey(edge));
                  const stage = status?.stage ?? null;
                  const statusEvent = status?.event;
                  const title =
                    statusEvent?.stage === "POLICY_DENY" && statusEvent.decisionCode
                      ? `POLICY_DENY (${statusEvent.decisionCode})`
                      : statusEvent?.stage ?? "NEUTRAL";
                  return (
                    <div
                      key={edgeKey(edge)}
                      title={title}
                      className={`rounded-lg border px-3 py-2 transition-colors ${stageClasses(stage)}`}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="text-sm font-medium">
                          {edge.sourceVendorCode} → {edge.targetVendorCode}
                        </div>
                        <div className="text-xs font-semibold uppercase tracking-wide">
                          {stage ? stageLabel(stage) : "Neutral"}
                        </div>
                      </div>
                      <div className="mt-1 text-xs">
                        {edge.operationCode} · {edge.flowDirection}
                        {statusEvent?.decisionCode ? ` · ${statusEvent.decisionCode}` : ""}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </section>

        <section className="border border-slate-200 rounded-lg bg-white overflow-hidden">
          <header className="px-4 py-3 border-b border-slate-200 bg-slate-50">
            <h2 className="text-sm font-semibold text-slate-900">Live Activity</h2>
            <p className="text-xs text-slate-600">
              Polling every 2s. Metadata only: no payload body exposure.
            </p>
          </header>
          <div className="p-3 max-h-[70vh] overflow-y-auto space-y-2">
            {activityQuery.isLoading ? (
              <p className="text-sm text-slate-500">Loading activity...</p>
            ) : filteredEvents.length === 0 ? (
              <p className="text-sm text-slate-500">No recent activity.</p>
            ) : (
              filteredEvents.map((event, index) => (
                <article
                  key={`${event.ts ?? "no-ts"}-${event.transactionId ?? "no-tx"}-${event.stage}-${index}`}
                  className={`rounded-lg border p-2 ${stageClasses(event.stage)}`}
                >
                  <div className="text-[11px] font-semibold">{event.stage}</div>
                  <div className="text-xs mt-1">
                    {event.sourceVendorCode ?? "-"} → {event.targetVendorCode ?? "-"} · {event.operationCode ?? "-"}
                  </div>
                  <div className="text-[11px] mt-1">
                    {event.ts ?? "-"}
                    {event.statusCode != null ? ` · HTTP ${event.statusCode}` : ""}
                    {event.decisionCode ? ` · ${event.decisionCode}` : ""}
                  </div>
                  <div className="text-[11px] mt-1 font-mono text-slate-600">
                    tx:{event.transactionId ?? "-"} corr:{event.correlationId ?? "-"}
                  </div>
                </article>
              ))
            )}
          </div>
        </section>
      </div>
    </PageLayout>
  );
}
