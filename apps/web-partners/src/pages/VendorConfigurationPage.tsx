import { useMemo, useState, useRef } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getActiveVendorCode,
  getVendorDirectionLabel,
  getVendorDirectionFilterLabel,
  ModalShell,
} from "frontend-shared";
import { VendorPageLayout } from "../components/layout/VendorPageLayout";
import {
  getVendorContracts,
  getVendorOperationsCatalog,
  getVendorSupportedOperations,
  getVendorEndpoints,
  getVendorMappings,
  getMyAllowlist,
  getMyOperations,
  upsertVendorSupportedOperation,
  patchVendorOperation,
  deleteVendorOperation,
} from "../api/endpoints";
import { STALE_CONFIG } from "../api/queryKeys";
import { OpenSettingsLink } from "../components/OpenSettingsLink";
import { StatusPill, type StatusPillVariant } from "frontend-shared";
import { CanonicalOperationsBanner } from "../components/CanonicalOperationsBanner";
import {
  buildReadinessRowsForLicensee,
  getAccessOutcomeDisplay,
  getConfigurationStatusFilterLabel,
  getContractStatusDisplay,
  getEndpointStatusDisplay,
  getMappingStatusDisplay,
  READY_FOR_TRAFFIC_LABEL,
  type FlowReadinessRow,
  getAccessDisplayStatus,
  mapReadinessToDisplay,
} from "../utils/readinessModel";
import {
  getDirectionLabelWithPolicy,
  getDirectionCellTooltip,
  augmentReadyLabel,
} from "../utils/vendorDirectionLabels";
import { getFlowBuilderPath, formatVersionLabel } from "../utils/flowReadiness";
import type { FlowBuilderStageParam } from "../utils/flowReadiness";
import {
  type DirectionFilter,
  type StatusFilter,
  parseFilterParams,
  buildFilterQueryString,
} from "../utils/supportedOperationsFilters";
import { useOperationDirectionCapabilities } from "../hooks/useOperationDirectionCapabilities";
import { useVendorConfigBundle } from "../hooks/useVendorConfigBundle";
import { VendorTableSkeleton } from "../components/vendor/skeleton";

const CONFIG_BUNDLE_KEY = ["vendor", "config-bundle"] as const;

export function VendorConfigurationPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedOperation, setSelectedOperation] = useState("");
  const [addDirection, setAddDirection] = useState<"outbound" | "inbound">("outbound");
  const [removeConfirmOp, setRemoveConfirmOp] = useState<string | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const addSelectRef = useRef<HTMLSelectElement>(null);

  const activeVendor = getActiveVendorCode();
  const hasKey = !!activeVendor;

  const operationParam = searchParams.get("operation") ?? undefined;
  const {
    search: searchQuery = "",
    direction: directionFilter = "all",
    status: statusFilter = "all",
  } = parseFilterParams(searchParams);

  const updateFilters = (
    updates: Partial<{ search: string; direction: DirectionFilter; status: StatusFilter }>
  ) => {
    const next = new URLSearchParams(searchParams);
    const search = updates.search ?? searchQuery ?? "";
    const direction = updates.direction ?? directionFilter ?? "all";
    const status = updates.status ?? statusFilter ?? "all";
    if (search.trim()) next.set("search", search);
    else next.delete("search");
    if (direction !== "all") next.set("direction", direction);
    else next.delete("direction");
    if (status !== "all") next.set("status", status);
    else next.delete("status");
    setSearchParams(next, { replace: true });
  };

  const { data: bundleData, isLoading: bundleLoading, isError: bundleError } = useVendorConfigBundle(!!hasKey);
  const useIndividualConfig = hasKey && (bundleError || !bundleData);

  const { data: vendorContractsData } = useQuery({
    queryKey: ["vendor-contracts"],
    queryFn: () => getVendorContracts(),
    enabled: useIndividualConfig,
    retry: (_, err) =>
      (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: catalogData, isLoading: catalogLoading } = useQuery({
    queryKey: ["vendor-operations-catalog"],
    queryFn: () => getVendorOperationsCatalog(),
    enabled: useIndividualConfig,
    retry: (_, err) =>
      (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: supportedData, isLoading: supportedLoading } = useQuery({
    queryKey: ["vendor-supported-operations"],
    queryFn: () => getVendorSupportedOperations(),
    enabled: useIndividualConfig,
    retry: (_, err) =>
      (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: endpointsData } = useQuery({
    queryKey: ["vendor-endpoints"],
    queryFn: () => getVendorEndpoints(),
    enabled: useIndividualConfig,
    retry: (_, err) =>
      (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: mappingsData } = useQuery({
    queryKey: ["vendor-mappings"],
    queryFn: () => getVendorMappings(),
    enabled: useIndividualConfig,
    retry: (_, err) =>
      (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { directionMap, isLoading: directionLoading } = useOperationDirectionCapabilities();
  const { data: allowlistData, isLoading: accessLoading } = useQuery({
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

  const vendorContracts = bundleData?.contracts ?? vendorContractsData?.items ?? [];
  const catalog = bundleData?.operationsCatalog ?? catalogData?.items ?? [];
  const supportedOps = bundleData?.supportedOperations ?? supportedData?.items ?? [];
  const endpoints = bundleData?.endpoints ?? endpointsData?.items ?? [];
  const mappings = bundleData?.mappings ?? mappingsData?.mappings ?? [];
  const allowlistForPage = bundleData?.myAllowlist ?? allowlistData;
  const myOps = bundleData?.myOperations ?? myOpsData;
  const outboundAllowlist = allowlistForPage?.outbound ?? [];
  const inboundAllowlist = allowlistForPage?.inbound ?? [];

  const upsert = useMutation({
    mutationFn: upsertVendorSupportedOperation,
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["vendor-supported-operations"] });
      queryClient.invalidateQueries({ queryKey: CONFIG_BUNDLE_KEY });
      const version =
        catalog.find((c) => c.operationCode === variables.operationCode)
          ?.canonicalVersion ?? "v1";
      navigate(getFlowBuilderPath(variables.operationCode, version));
    },
  });

  const patchMut = useMutation({
    mutationFn: ({ operationCode, isActive }: { operationCode: string; isActive: boolean }) =>
      patchVendorOperation(operationCode, { isActive }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vendor-supported-operations"] });
      queryClient.invalidateQueries({ queryKey: CONFIG_BUNDLE_KEY });
    },
  });

  const deleteMut = useMutation({
    mutationFn: deleteVendorOperation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vendor-supported-operations"] });
      queryClient.invalidateQueries({ queryKey: ["vendor-contracts"] });
      queryClient.invalidateQueries({ queryKey: ["vendor-endpoints"] });
      queryClient.invalidateQueries({ queryKey: ["vendor-mappings"] });
      queryClient.invalidateQueries({ queryKey: ["my-allowlist"] });
      queryClient.invalidateQueries({ queryKey: ["vendor-my-operations"] });
      queryClient.invalidateQueries({ queryKey: CONFIG_BUNDLE_KEY });
      setRemoveConfirmOp(null);
      setRemoveError(null);
    },
    onError: () => {
      setRemoveError("Could not remove operation. Please try again or contact support.");
    },
  });

  const supportedCodes = new Set(supportedOps.map((s) => s.operationCode));
  const availableToAdd = catalog.filter((c) => !supportedCodes.has(c.operationCode));

  const configLoading =
    (bundleLoading && !bundleData) ||
    (useIndividualConfig && (catalogLoading || supportedLoading));

  const selectedOpCode = selectedOperation.trim().toUpperCase();
  const capability = directionMap[selectedOpCode] ?? (directionLoading
    ? { canConfigureOutbound: true, canConfigureInbound: true }
    : { canConfigureOutbound: false, canConfigureInbound: false });
  const canAddOutbound = capability.canConfigureOutbound;
  const canAddInbound = capability.canConfigureInbound;
  const effectiveAddDirection =
    addDirection === "outbound" && canAddOutbound
      ? "outbound"
      : addDirection === "inbound" && canAddInbound
        ? "inbound"
        : canAddOutbound
          ? "outbound"
          : canAddInbound
            ? "inbound"
            : null;

  const handleAdd = () => {
    if (!selectedOperation.trim() || effectiveAddDirection === null) return;
    upsert.mutate({
      operationCode: selectedOperation.trim(),
      isActive: true,
      supportsOutbound: effectiveAddDirection === "outbound",
      supportsInbound: effectiveAddDirection === "inbound",
    });
    setSelectedOperation("");
  };

  const flowReadinessRows = useMemo(
    () =>
      buildReadinessRowsForLicensee({
        supported: supportedOps,
        catalog,
        vendorContracts,
        endpoints,
        mappings,
        outboundAllowlist,
        inboundAllowlist,
        eligibleOperations: allowlistForPage?.eligibleOperations,
        accessOutcomes: allowlistForPage?.accessOutcomes,
        vendorCode: activeVendor ?? "",
        myOperationsOutbound: myOps?.outbound,
        myOperationsInbound: myOps?.inbound,
      }),
    [
      supportedOps,
      catalog,
      vendorContracts,
      endpoints,
      mappings,
      outboundAllowlist,
      inboundAllowlist,
      allowlistForPage?.eligibleOperations,
      allowlistForPage?.accessOutcomes,
      activeVendor,
      myOps?.outbound,
      myOps?.inbound,
    ]
  );

  const filteredRows = useMemo(() => {
    let rows = flowReadinessRows;

    if (operationParam?.trim()) {
      const op = operationParam.trim().toUpperCase();
      rows = rows.filter(
        (row) => (row.operationCode ?? "").toUpperCase() === op
      );
    }

    if ((searchQuery ?? "").trim()) {
      const q = (searchQuery ?? "").trim().toLowerCase();
      rows = rows.filter((row) => {
        const op = (row.operationCode ?? "").toLowerCase();
        const ver = (row.operationVersion ?? "").toLowerCase();
        const dir = (row.direction ?? "").toLowerCase();
        return op.includes(q) || ver.includes(q) || dir.includes(q);
      });
    }

    if (directionFilter !== "all") {
      const opHasBoth = new Set<string>();
      for (const r of rows) {
        const other = rows.find(
          (x) => x.operationCode === r.operationCode && x.direction !== r.direction
        );
        if (other) opHasBoth.add(r.operationCode);
      }
      rows = rows.filter((row) => {
        const d = row.direction;
        if (directionFilter === "inbound") return d === "Inbound";
        if (directionFilter === "outbound") return d === "Outbound";
        if (directionFilter === "both") return opHasBoth.has(row.operationCode);
        return true;
      });
    }

    if (statusFilter !== "all") {
      rows = rows.filter((row) => {
        const display = mapReadinessToDisplay(row);
        if (statusFilter === "ok") return row.isActive && row.vendorReady;
        if (statusFilter === "partial") return display.variant === "warning";
        if (statusFilter === "not_configured")
          return !row.isActive || display.variant === "error" || display.variant === "warning";
        return true;
      });
    }

    return rows;
  }, [flowReadinessRows, operationParam, searchQuery, directionFilter, statusFilter, accessLoading]);

  const isLoading = configLoading;

  if (!activeVendor) {
    return (
      <VendorPageLayout title="Configuration" subtitle="Manage operations, contracts, and access rules.">
        <div className="rounded-lg bg-gray-50 border border-gray-200 p-4">
          <p className="text-sm font-medium text-gray-700">Select an active licensee above.</p>
        </div>
      </VendorPageLayout>
    );
  }

  if (!hasKey) {
    return (
      <VendorPageLayout title="Configuration" subtitle="Manage operations, contracts, and access rules.">
        <div className="rounded-lg bg-amber-50 border border-amber-200 p-4">
          <p className="text-sm font-medium text-amber-800">Active licensee not selected.</p>
          <OpenSettingsLink>Open Settings →</OpenSettingsLink>
        </div>
      </VendorPageLayout>
    );
  }

  return (
    <VendorPageLayout
      rightContent={
        <div className="w-full min-w-0">
          <CanonicalOperationsBanner
          hasAvailableOperations={availableToAdd.length > 0}
          noAdminApprovedOperations={!configLoading && catalog.length === 0}
          selectControl={
              <select
                id="add-operation-select"
                ref={addSelectRef}
                value={selectedOperation}
                onChange={(e) => {
                  setSelectedOperation(e.target.value);
                  const opCode = e.target.value.trim().toUpperCase();
                  const cap = directionMap[opCode] ?? (directionLoading
                    ? { canConfigureOutbound: true, canConfigureInbound: true }
                    : { canConfigureOutbound: false, canConfigureInbound: false });
                  if (cap.canConfigureOutbound && !cap.canConfigureInbound) setAddDirection("outbound");
                  else if (cap.canConfigureInbound && !cap.canConfigureOutbound) setAddDirection("inbound");
                  else setAddDirection("outbound");
                }}
                disabled={isLoading}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
              >
                <option value="">Select canonical operation…</option>
                {availableToAdd.map((op) => (
                  <option key={op.operationCode} value={op.operationCode}>
                    {op.operationCode}
                    {op.description ? ` — ${op.description}` : ""}
                  </option>
                ))}
              </select>
            }
            directionControl={
              selectedOperation.trim() && (canAddOutbound || canAddInbound) ? (
                canAddOutbound && canAddInbound ? (
                  <div role="group" aria-label="Direction" className="space-y-2">
                    <label className="flex items-start gap-2 cursor-pointer">
                      <input
                        type="radio"
                        name="add-direction"
                        value="outbound"
                        checked={addDirection === "outbound"}
                        onChange={() => setAddDirection("outbound")}
                        className="mt-0.5 shrink-0 rounded-full border-gray-300 text-slate-600 focus:ring-slate-500"
                      />
                      <span className="text-sm leading-snug">
                        {getVendorDirectionLabel("OUTBOUND")}
                      </span>
                    </label>
                    <label className="flex items-start gap-2 cursor-pointer">
                      <input
                        type="radio"
                        name="add-direction"
                        value="inbound"
                        checked={addDirection === "inbound"}
                        onChange={() => setAddDirection("inbound")}
                        className="mt-0.5 shrink-0 rounded-full border-gray-300 text-slate-600 focus:ring-slate-500"
                      />
                      <span className="text-sm leading-snug">
                        {getVendorDirectionLabel("INBOUND")}
                      </span>
                    </label>
                  </div>
                ) : canAddOutbound ? (
                  <div className="space-y-1">
                    <p className="text-sm leading-snug text-sky-900">
                      Direction: {getVendorDirectionLabel("OUTBOUND")}
                    </p>
                    <p className="text-xs text-sky-900/70">
                      Inbound calls for this operation are controlled by admin rules and are not available for this licensee.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-1">
                    <p className="text-sm leading-snug text-sky-900">
                      Direction: {getVendorDirectionLabel("INBOUND")}
                    </p>
                    <p className="text-xs text-sky-900/70">
                      This operation is inbound-only for your organization.
                    </p>
                  </div>
                )
              ) : undefined
            }
            addBlockedMessage={
              selectedOperation.trim() && !canAddOutbound && !canAddInbound
                ? "This operation isn't currently enabled for your organization. Contact the integration administrator to enable access."
                : undefined
            }
            onAdd={handleAdd}
            isAdding={upsert.isPending}
            canAdd={!!selectedOperation.trim() && effectiveAddDirection !== null}
          />
        </div>
      }
      rightContentAlign="start"
    >
    <div className="space-y-6">
      {operationParam && (
        <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-2 text-sm text-slate-700">
          Viewing operation: <strong className="font-mono">{operationParam}</strong>
          <Link to="/configuration" className="ml-2 text-slate-600 hover:text-slate-800 hover:underline">
            Clear filter
          </Link>
        </div>
      )}

      {removeError && (
        <div className="rounded-lg bg-rose-50 border border-rose-200 px-4 py-3 text-sm text-rose-800">
          {removeError}
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 mb-4">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3 flex-1 min-w-0">
            <input
              type="search"
              placeholder="Search by operation, version, or direction…"
              value={searchQuery}
              onChange={(e) => updateFilters({ search: e.target.value })}
              className="flex-1 min-w-0 max-w-[480px] px-3 py-1.5 text-sm border border-gray-300 rounded-lg placeholder-gray-400 focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
            />
            <div className="flex items-center gap-2 flex-wrap">
              <select
                value={directionFilter}
                onChange={(e) => updateFilters({ direction: e.target.value as DirectionFilter })}
                className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-slate-500"
              >
                <option value="all">All directions</option>
                <option value="inbound">{getVendorDirectionFilterLabel("INBOUND")}</option>
                <option value="outbound">{getVendorDirectionFilterLabel("OUTBOUND")}</option>
                <option value="both">{getVendorDirectionFilterLabel("BOTH")}</option>
              </select>
              <select
                value={statusFilter}
                onChange={(e) => updateFilters({ status: e.target.value as StatusFilter })}
                className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-slate-500"
              >
                <option value="all">{getConfigurationStatusFilterLabel("all")}</option>
                <option value="ok">{getConfigurationStatusFilterLabel("ok")}</option>
                <option value="not_configured">{getConfigurationStatusFilterLabel("not_configured")}</option>
                <option value="partial">{getConfigurationStatusFilterLabel("partial")}</option>
              </select>
              <span className="text-xs text-gray-500 shrink-0">
                {filteredRows.length} operation{filteredRows.length !== 1 ? "s" : ""}
              </span>
            </div>
          </div>
        </div>
        <p className="text-xs text-gray-600 mb-3">
          OUTBOUND: I call other licensees. INBOUND: other licensees call me.
        </p>

        {isLoading ? (
          <VendorTableSkeleton rowCount={6} columnCount={8} />
        ) : flowReadinessRows.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 px-6 text-center rounded-lg border border-gray-200 bg-gray-50">
            <h3 className="text-base font-semibold text-gray-900 mb-2">
              No supported operations yet
            </h3>
            <p className="text-sm text-gray-600">
              Use the Add operation panel above to add a canonical operation and start configuring.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b bg-gray-50">
                  <th className="py-1.5 px-3">Operation</th>
                  <th className="py-1.5 px-3">Direction</th>
                  <th className="py-1.5 px-3 text-center">Contract</th>
                  <th className="py-1.5 px-3 text-center">Endpoint</th>
                  <th className="py-1.5 px-3 text-center">Mapping</th>
                  <th className="py-1.5 px-3 text-center">Access</th>
                  <th className="py-1.5 px-3 text-center">Overall</th>
                  <th className="py-1.5 px-3 w-[140px]">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-6 text-center text-sm text-gray-500">
                      No operations match your current filters.
                    </td>
                  </tr>
                ) : (
                  filteredRows.map((row: FlowReadinessRow) => {
                    const accessStatus = getAccessDisplayStatus(row, accessLoading);
                    const narrowCounts =
                      row.vendorNarrowedCount != null || row.adminEnvelopeCount != null
                        ? {
                            narrowCount: row.vendorNarrowedCount,
                            envelopeCount: row.adminEnvelopeCount,
                          }
                        : undefined;
                    const accessDisplay =
                      row.accessOutcome && accessStatus !== "inactive"
                        ? getAccessOutcomeDisplay(row.accessOutcome, row.direction, narrowCounts)
                        : accessStatus === "inactive"
                          ? { label: "Inactive", variant: "neutral" as const, tooltip: "" }
                              : accessStatus === "allowed"
                            ? getAccessOutcomeDisplay("ALLOWED_BY_ADMIN", row.direction)
                            : accessStatus === "blocked"
                              ? getAccessOutcomeDisplay("BLOCKED_BY_ADMIN", row.direction)
                              : getAccessOutcomeDisplay(undefined, row.direction);
                    const overallBase = mapReadinessToDisplay(row);
                    const overallDisplay =
                      overallBase.label === READY_FOR_TRAFFIC_LABEL
                        ? augmentReadyLabel(overallBase.label, overallBase.variant, overallBase.tooltip, [row])
                        : overallBase;
                    const filterParams = {
                      search: searchQuery,
                      direction: (row.direction === "Outbound" ? "outbound" : "inbound") as "outbound" | "inbound",
                      status: statusFilter,
                    };
                    const baseBuilderPath =
                      getFlowBuilderPath(row.operationCode, row.operationVersion);
                    const buildBuilderPath = (stage?: FlowBuilderStageParam) =>
                      baseBuilderPath + buildFilterQueryString(filterParams, stage);
                    const rowBuilderPath = buildBuilderPath();
                    const accessControlPath = `/configuration/access?operation=${encodeURIComponent(row.operationCode)}&direction=${row.direction === "Outbound" ? "outbound" : "inbound"}`;
                    const catalogOp = catalog.find(
                      (c) => (c.operationCode ?? "").toUpperCase() === (row.operationCode ?? "").toUpperCase()
                    );
                    const directionPolicy =
                      (catalogOp as { directionPolicy?: string })?.directionPolicy;
                    const aiMode = (catalogOp as { aiPresentationMode?: string } | undefined)?.aiPresentationMode ?? "RAW_ONLY";
                    const aiLabel =
                      aiMode === "RAW_AND_FORMATTED"
                        ? "AI: Raw + summary"
                        : aiMode === "FORMAT_ONLY"
                          ? "AI: Summary only"
                          : "AI: Off";
                    return (
                      <tr
                        key={`${row.operationCode}-${row.direction}`}
                        role="button"
                        tabIndex={0}
                        onClick={() => navigate(rowBuilderPath)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            navigate(rowBuilderPath);
                          }
                        }}
                        className="border-b border-gray-100 last:border-b-0 hover:bg-slate-50 dark:hover:bg-slate-800/40 cursor-pointer"
                      >
                        <td className="py-1.5 px-3 font-mono">
                          {row.operationCode} {formatVersionLabel(row.operationVersion)}
                          <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
                            {aiLabel}
                          </span>
                        </td>
                        <td
                          className="py-1.5 px-3"
                          title={getDirectionCellTooltip(row.direction, directionPolicy)}
                        >
                          {getDirectionLabelWithPolicy(row.direction, directionPolicy)}
                        </td>
                        <td className="py-1.5 px-3 text-center">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              navigate(buildBuilderPath("contract"));
                            }}
                            onKeyDown={(e) => e.stopPropagation()}
                            className="inline-flex rounded-full focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-1"
                            aria-label={`Contract status: ${getContractStatusDisplay(row.hasContract).label}. Open flow builder to contract.`}
                          >
                            {(() => {
                              const d = getContractStatusDisplay(row.hasContract);
                              return (
                                <StatusPill
                                  label={d.label}
                                  variant={d.variant}
                                  title={d.tooltip}
                                  iconOnlyWhenReady
                                />
                              );}
                            )()}
                          </button>
                        </td>
                        <td className="py-1.5 px-3 text-center">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              navigate(buildBuilderPath("endpoint"));
                            }}
                            onKeyDown={(e) => e.stopPropagation()}
                            className="inline-flex rounded-full focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-1"
                            aria-label={`Endpoint status. Open flow builder to endpoint.`}
                          >
                            {(() => {
                              const d = getEndpointStatusDisplay(
                                row.hasEndpoint,
                                row.endpointVerified,
                                row.direction
                              );
                              return (
                                <StatusPill
                                  label={d.label}
                                  variant={d.variant}
                                  title={d.tooltip}
                                  iconOnlyWhenReady
                                />
                              );
                            })()}
                          </button>
                        </td>
                        <td className="py-1.5 px-3 text-center">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              navigate(buildBuilderPath("request-mapping"));
                            }}
                            onKeyDown={(e) => e.stopPropagation()}
                            className="inline-flex rounded-full focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-1"
                            aria-label={`Mapping status. Open flow builder to request mapping.`}
                          >
                            {(() => {
                              const d = getMappingStatusDisplay(
                                row.hasMapping,
                                row.usesCanonicalPassThrough,
                                row.effectiveMappingConfigured
                              );
                              return (
                                <StatusPill
                                  label={d.label}
                                  variant={d.variant}
                                  title={d.tooltip}
                                  iconOnlyWhenReady
                                />
                              );
                            })()}
                          </button>
                        </td>
                        <td className="py-1.5 px-3 text-center">
                          <Link
                            to={accessControlPath}
                            onClick={(e) => e.stopPropagation()}
                            onKeyDown={(e) => e.stopPropagation()}
                            className="inline-flex rounded-full focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-1"
                            aria-label={`Access status: ${accessDisplay.label}. Open access control.`}
                          >
                            <StatusPill
                              label={accessDisplay.label}
                              variant={accessDisplay.variant as StatusPillVariant}
                              title={accessDisplay.tooltip || undefined}
                              iconOnlyWhenReady
                            />
                          </Link>
                        </td>
                        <td className="py-1.5 px-3 text-center">
                          <StatusPill
                            label={overallDisplay.label}
                            variant={overallDisplay.variant as StatusPillVariant}
                            title={overallDisplay.tooltip}
                            iconOnlyWhenReady
                          />
                        </td>
                        <td className="py-1.5 px-3" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center gap-2">
                            <label className="flex items-center gap-1.5 cursor-pointer shrink-0">
                              <input
                                type="checkbox"
                                checked={row.isActive}
                                onChange={() =>
                                  patchMut.mutate({
                                    operationCode: row.operationCode,
                                    isActive: !row.isActive,
                                  })
                                }
                                disabled={patchMut.isPending}
                                className="rounded border-gray-300 text-slate-600 focus:ring-slate-500"
                              />
                              <span className="text-xs text-gray-600">
                                {row.isActive ? "Active" : "Inactive"}
                              </span>
                            </label>
                            <button
                              type="button"
                              onClick={() => setRemoveConfirmOp(row.operationCode)}
                              disabled={deleteMut.isPending}
                              className="text-xs text-red-600 hover:text-red-800 hover:underline"
                            >
                              Remove
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {removeConfirmOp && (
        <ModalShell
          open
          onClose={() => {
            setRemoveConfirmOp(null);
            setRemoveError(null);
          }}
          title="Remove operation from configuration?"
        >
          <div className="text-sm text-gray-600 mb-4 space-y-3">
            <p>Removing this operation will delete all vendor-specific configuration for this operation:</p>
            <ul className="list-disc list-inside space-y-1 ml-2">
              <li>Contracts and schemas</li>
              <li>Request and response mappings</li>
              <li>Endpoint settings</li>
              <li>Access rules involving this operation</li>
            </ul>
            <p>
              You can add this operation again later from canonical operations,
              but you will need to reconfigure it from scratch.
            </p>
          </div>
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={() => setRemoveConfirmOp(null)}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => deleteMut.mutate(removeConfirmOp)}
              disabled={deleteMut.isPending}
              className="px-4 py-2 text-sm font-medium text-white bg-rose-600 hover:bg-rose-700 rounded-lg disabled:opacity-50"
            >
              {deleteMut.isPending ? "Removing…" : "Remove"}
            </button>
          </div>
        </ModalShell>
      )}
    </div>
    </VendorPageLayout>
  );
}
