import { Fragment, useState, useEffect, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listVendors,
  listOperations,
  listAllowlist,
  listEndpoints,
  adminListContracts,
  getBatchReadiness,
  upsertVendor,
  upsertOperation,
  upsertAllowlist,
  deleteAllowlist,
  listChangeRequests,
  decideChangeRequest,
  listFeatureGates,
  updateFeatureGate,
  type ListRegistryResponse,
  type ReadinessItem,
} from "../api/endpoints";
import type { Vendor, Operation, AllowlistEntry, RegistryContract, UpsertAllowlistPayload } from "../types";
import type { ChangeRequestItem } from "../api/endpoints";
import {
  getAdminDirectionLabel,
  getAdminDirectionBadgeTooltip,
  getDirectionPolicyLabel,
  getDirectionPolicyConstraintTooltip,
  PageLayout,
  SectionCard,
  StatusPill,
  type FlowDirection,
  type StatusPillVariant,
} from "frontend-shared";
import { VendorModal } from "../components/registry/VendorModal";
import { OperationModal } from "../components/registry/OperationModal";
import { AllowlistDrawer } from "../components/registry/AllowlistDrawer";
import { ContractSchemaDrawer } from "../components/registry/ContractSchemaDrawer";
import { ModalShell } from "../components/registry/ModalShell";
import { CanonicalContractEditor } from "../components/CanonicalContractEditor";

type TabId = "vendors" | "operations" | "allowlist" | "access-requests";

const TABS: { id: TabId; label: string }[] = [
  { id: "vendors", label: "Licensees" },
  { id: "operations", label: "Operations" },
  { id: "allowlist", label: "Access rules" },
  { id: "access-requests", label: "Access requests" },
];

export function RegistryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab") as string | null;
  const operationParam = searchParams.get("operation") ?? undefined;

  // Derive activeTab from URL to avoid race when switching tabs (no state sync)
  const activeTab: TabId =
    tabParam === "contracts"
      ? "operations"
      : tabParam && TABS.some((t) => t.id === tabParam)
        ? (tabParam as TabId)
        : searchParams.get("source") || searchParams.get("perspective")
          ? "allowlist"
          : "vendors";

  useEffect(() => {
    if (tabParam === "contracts") {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("tab", "operations");
        return next;
      });
      return;
    }
    if (!tabParam && (searchParams.get("source") || searchParams.get("perspective"))) {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("tab", "allowlist");
        return next;
      });
    }
  }, [tabParam, searchParams, setSearchParams]);

  const setActiveTabWithUrl = (id: TabId) => {
    setSearchParams(id === "vendors" ? {} : { tab: id });
  };

  return (
    <PageLayout
      embedded
      title="Registry"
      description="Manage vendors, operations, and access rules."
    >
      <div className="overflow-x-auto -mx-px">
        <div className="flex items-end gap-2 sm:gap-3 border-b border-slate-200 min-w-max">
          {TABS.filter((t) => t.id !== "access-requests").map((item) => {
            const active = item.id === activeTab;
            return (
              <button
                key={item.id}
                type="button"
                className={
                  active
                    ? "relative -mb-px px-3 py-2 sm:pb-2 sm:pt-0 text-sm border-b-2 border-slate-900 text-slate-900 font-medium transition-colors whitespace-nowrap min-h-[44px] sm:min-h-0 flex items-center"
                    : "relative -mb-px px-3 py-2 sm:pb-2 sm:pt-0 text-sm border-b-2 border-transparent text-slate-500 hover:text-slate-800 transition-colors whitespace-nowrap min-h-[44px] sm:min-h-0 flex items-center"
                }
                onClick={() => setActiveTabWithUrl(item.id)}
              >
                {item.label}
              </button>
            );
          })}
          <div className="ml-auto" />
          {TABS.filter((t) => t.id === "access-requests").map((item) => {
            const active = item.id === activeTab;
            return (
              <button
                key={item.id}
                type="button"
                className={
                  active
                    ? "relative -mb-px px-3 py-2 sm:pb-2 sm:pt-0 text-sm border-b-2 border-slate-900 text-slate-900 font-medium transition-colors whitespace-nowrap min-h-[44px] sm:min-h-0 flex items-center"
                    : "relative -mb-px px-3 py-2 sm:pb-2 sm:pt-0 text-sm border-b-2 border-transparent text-slate-500 hover:text-slate-800 transition-colors whitespace-nowrap min-h-[44px] sm:min-h-0 flex items-center"
                }
                onClick={() => setActiveTabWithUrl(item.id)}
              >
                {item.label}
              </button>
            );
          })}
        </div>
      </div>

      {activeTab === "vendors" && <VendorsTab />}
      {activeTab === "operations" && (
        <OperationsTab
          operationParam={operationParam}
          setSearchParams={setSearchParams}
        />
      )}
      {activeTab === "allowlist" && (
        <AllowlistTab searchParams={searchParams} setSearchParams={setSearchParams} />
      )}
      {activeTab === "access-requests" && <AccessRequestsTab />}
    </PageLayout>
  );
}

export interface VendorHealthBadgesData {
  unverifiedCount: number;
  supportedOps: number;
  missingMappingCount: number;
  hasWarnings: boolean;
  /** Partial error from batch readiness when this vendor failed */
  error?: { code: string; message: string };
}

function VendorHealthBadges({
  vendorCode: _vendorCode,
  health,
}: {
  vendorCode: string;
  health?: VendorHealthBadgesData | null;
}) {
  const h = health ?? {
    unverifiedCount: 0,
    supportedOps: 0,
    missingMappingCount: 0,
    hasWarnings: false,
  };
  if (h.error) {
    return (
      <span
        className="px-1.5 py-0.5 rounded text-xs bg-red-100 text-red-800"
        title={h.error.message}
      >
        Error
      </span>
    );
  }
  return (
    <span className="flex flex-wrap gap-1">
      <span
        className="px-1.5 py-0.5 rounded text-xs bg-slate-100 text-slate-700"
        title="Supported operations"
      >
        {h.supportedOps} ops
      </span>
      {h.unverifiedCount > 0 && (
        <span
          className="px-1.5 py-0.5 rounded text-xs bg-amber-100 text-amber-800"
          title="Unverified endpoints"
        >
          {h.unverifiedCount} unverified
        </span>
      )}
      {h.missingMappingCount > 0 && (
        <span
          className="px-1.5 py-0.5 rounded text-xs bg-amber-100 text-amber-800"
          title="Operations missing mapping"
        >
          {h.missingMappingCount} missing map
        </span>
      )}
      {h.hasWarnings && (
        <span className="text-amber-600" title="Has configuration warnings">
          ❗
        </span>
      )}
    </span>
  );
}

function useVendorsTabHealthData(vendorCodes: string[]) {
  const { data: readinessRes } = useQuery({
    queryKey: ["registry-readiness-batch", vendorCodes.join(",")],
    queryFn: async () => {
      const res = await getBatchReadiness(vendorCodes);
      const m = new Map<string, { items: ReadinessItem[]; error?: { code: string; message: string } }>();
      res.items.forEach((item) => {
        m.set(item.vendorCode, {
          items: item.error ? [] : (item.items ?? []),
          error: item.error,
        });
      });
      return m;
    },
    enabled: vendorCodes.length > 0,
  });
  const { data: endpointsRes } = useQuery({
    queryKey: ["registry-endpoints"],
    queryFn: () => listEndpoints(),
    enabled: vendorCodes.length > 0,
  });
  const endpoints = endpointsRes?.items ?? [];
  const readinessByVendor = readinessRes ?? new Map();

  return useMemo(() => {
    const healthMap = new Map<string, VendorHealthBadgesData>();
    for (const vc of vendorCodes) {
      const eps = endpoints.filter((e) => e.vendorCode === vc);
      const unverifiedCount = eps.filter((e) => e.verificationStatus !== "VERIFIED").length;
      const supportedOps = new Set(eps.map((e) => e.operationCode)).size;
      const rd = readinessByVendor.get(vc);
      const readinessItems = rd?.items ?? [];
      const missingMappingCount = readinessItems.filter(
        (r: ReadinessItem) =>
          !r.overallOk &&
          r.checks?.some((c: { name: string; ok: boolean }) => c.name === "mappings_present" && !c.ok)
      ).length;
      healthMap.set(vc, {
        unverifiedCount,
        supportedOps,
        missingMappingCount,
        hasWarnings: unverifiedCount > 0 || missingMappingCount > 0,
        error: rd?.error,
      });
    }
    return healthMap;
  }, [vendorCodes, endpoints, readinessByVendor]);
}

function VendorsTab() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingVendor, setEditingVendor] = useState<Vendor | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const { data, isLoading, error } = useQuery<ListRegistryResponse<Vendor>>({
    queryKey: ["registry-vendors"],
    queryFn: () => listVendors(),
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
  });

  const upsert = useMutation({
    mutationFn: upsertVendor,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["registry-vendors"] });
      setSuccessMsg("Licensee saved.");
      setTimeout(() => setSuccessMsg(null), 3000);
    },
  });

  const vendors = data?.items ?? [];
  const filteredVendors = useMemo(() => {
    if (!searchQuery.trim()) return vendors;
    const q = searchQuery.trim().toLowerCase();
    return vendors.filter(
      (v) =>
        (v.vendorCode ?? "").toLowerCase().includes(q) ||
        (v.vendorName ?? "").toLowerCase().includes(q)
    );
  }, [vendors, searchQuery]);

  const vendorCodes = vendors.map((v) => v.vendorCode);
  const healthByVendor = useVendorsTabHealthData(vendorCodes);

  const handleSave = async (payload: {
    vendor_code: string;
    vendor_name: string;
    is_active?: boolean;
  }) => {
    await upsert.mutateAsync(payload);
  };

  return (
    <div className="space-y-4">
      {successMsg && (
        <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-2 text-sm text-emerald-800">
          {successMsg}
        </div>
      )}
      <SectionCard
        title="Licensees"
        description="All registered vendors."
        headerExtras={
          <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
            <input
              type="search"
              placeholder="Search codes, names…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="flex-1 min-w-0 sm:min-w-[200px] px-3 py-2 text-sm border border-gray-300 rounded-lg min-h-[44px] sm:min-h-0"
            />
            <button
              type="button"
              onClick={() => {
                setEditingVendor(null);
                setModalOpen(true);
              }}
              className="inline-flex items-center rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-slate-800"
            >
              Create
            </button>
          </div>
        }
      >
        {isLoading ? (
          <div className="space-y-2">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-6 bg-gray-100 rounded animate-pulse" />
            ))}
          </div>
        ) : error ? (
          <div className="text-sm text-amber-600">Unable to load list.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50">
                <tr>
                  <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Code</th>
                  <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Name</th>
                  <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Health</th>
                  <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Active</th>
                  <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredVendors.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-3 py-6 text-center text-sm text-slate-500">
                      {vendors.length === 0 ? "No licensees found." : "No licensees match your search."}
                    </td>
                  </tr>
                ) : (
                filteredVendors.map((v) => (
                  <tr key={v.vendorCode} className="hover:bg-slate-50/70">
                    <td className="px-3 py-2 text-sm text-slate-900 font-mono">{v.vendorCode}</td>
                    <td className="px-3 py-2 text-sm text-slate-900">{v.vendorName}</td>
                    <td className="px-3 py-2 text-sm text-slate-900">
                      <VendorHealthBadges
                        vendorCode={v.vendorCode}
                        health={healthByVendor.get(v.vendorCode)}
                      />
                    </td>
                    <td className="px-3 py-2 text-sm text-slate-900">
                      <StatusPill
                        label={v.isActive !== false ? "Active" : "Inactive"}
                        variant={v.isActive !== false ? "primary" : "neutral"}
                      />
                    </td>
                    <td className="px-3 py-2 text-sm text-slate-900 text-right">
                      <button
                        type="button"
                        onClick={() => {
                          setEditingVendor(v);
                          setModalOpen(true);
                        }}
                        className="text-slate-600 hover:text-slate-800 text-xs font-medium mr-3"
                      >
                        Edit
                      </button>
                      <Link
                        to={`/admin/registry/vendors/${v.vendorCode}`}
                        className="text-slate-600 hover:text-slate-800 text-xs font-medium"
                      >
                        Manage
                      </Link>
                    </td>
                  </tr>
                ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      <VendorModal
        open={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setEditingVendor(null);
        }}
        initialValues={editingVendor}
        onSave={handleSave}
      />
    </div>
  );
}

function VersionsDrawer({
  operation,
  schemaDrawerContract: _schemaDrawerContract,
  onClose,
  onViewContract,
}: {
  operation: Operation;
  schemaDrawerContract: RegistryContract | null;
  onClose: () => void;
  onViewContract: (c: RegistryContract | null) => void;
}) {
  const [versionSearch, setVersionSearch] = useState("");

  const { data: allContracts = [], isLoading, error } = useQuery<RegistryContract[]>({
    queryKey: ["registry-contracts", { operationCode: operation.operationCode }],
    queryFn: () => adminListContracts({ operationCode: operation.operationCode }),
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
  });

  const contracts = useMemo(() => {
    if (!versionSearch.trim()) return allContracts;
    const q = versionSearch.trim().toLowerCase();
    return allContracts.filter(
      (c) =>
        (c.canonicalVersion ?? "").toLowerCase().includes(q)
    );
  }, [allContracts, versionSearch]);

  const formatDate = (s: string | undefined) => {
    if (!s) return "—";
    try {
      return new Date(s).toLocaleString();
    } catch {
      return s;
    }
  };

  return (
    <>
      <div
        className="fixed inset-0 bg-black/30 z-40"
        aria-hidden
      />
      <div
        className="fixed right-0 top-0 bottom-0 w-full sm:max-w-2xl bg-white shadow-xl z-50 flex flex-col overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-labelledby="versions-drawer-title"
      >
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 px-4 py-3 border-b border-gray-200 bg-gray-50 shrink-0">
          <div className="flex-1 min-w-0">
            <h2 id="versions-drawer-title" className="font-semibold text-gray-900">
              Versions - {operation.operationCode}
            </h2>
            <p className="text-sm text-slate-600 mt-0.5">
              Use this view for quick search and read-only inspection.
            </p>
            <button
              type="button"
              onClick={onClose}
              className="text-sm font-medium text-slate-600 hover:text-slate-800 mt-1"
            >
              Edit in Operations →
            </button>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-200"
            aria-label="Close drawer"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          <input
            type="text"
            placeholder="Search version…"
            value={versionSearch}
            onChange={(e) => setVersionSearch(e.target.value)}
            className="mb-4 px-2 py-1.5 text-sm border border-gray-300 rounded min-w-[160px]"
          />
          {isLoading ? (
            <div className="space-y-3 animate-pulse">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-10 bg-gray-100 rounded" />
              ))}
            </div>
          ) : error ? (
            <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800">
              Unable to load contracts. Check your connection and VITE_ADMIN_API_BASE_URL.
            </div>
          ) : contracts.length === 0 ? (
            <div className="text-sm text-gray-500 py-4">No contracts.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="border-b border-slate-200 bg-slate-50">
                  <tr>
                    <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Operation Code</th>
                    <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Canonical Version</th>
                    <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Active</th>
                    <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Updated At</th>
                    <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {contracts.map((c) => (
                    <tr
                      key={`${c.operationCode}-${c.canonicalVersion}`}
                      className="border-b border-gray-100 cursor-pointer hover:bg-gray-50"
                      onClick={() => onViewContract(c)}
                    >
                      <td className="py-2 font-mono">{c.operationCode}</td>
                      <td className="py-2">{c.canonicalVersion ?? "—"}</td>
                      <td className="py-2">
                        <StatusPill
                          label={c.isActive !== false ? "Active" : "Inactive"}
                          variant={c.isActive !== false ? "configured" : "neutral"}
                        />
                      </td>
                      <td className="py-2 text-gray-600">{formatDate(c.updatedAt)}</td>
                      <td className="py-2 text-right" onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          onClick={() => onViewContract(c)}
                          className="text-slate-600 hover:text-slate-800 text-xs font-medium"
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function OperationsTab({
  operationParam,
  setSearchParams,
}: {
  operationParam?: string;
  setSearchParams: (next: URLSearchParams | ((prev: URLSearchParams) => URLSearchParams)) => void;
}) {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingOp, setEditingOp] = useState<Operation | null>(null);
  const [contractDrawerOp, setContractDrawerOp] = useState<Operation | null>(null);
  const [drawerSelectedVersion, setDrawerSelectedVersion] = useState<string>("v1");
  const [versionsDrawerOp, setVersionsDrawerOp] = useState<Operation | null>(null);
  const [schemaDrawerContract, setSchemaDrawerContract] = useState<RegistryContract | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filterMode, setFilterMode] = useState<"all" | "active" | "missing">("all");
  const [filtersExpanded, setFiltersExpanded] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);

  const { data, isLoading, error } = useQuery<ListRegistryResponse<Operation>>({
    queryKey: ["registry-operations"],
    queryFn: () => listOperations(),
  });

  const { data: contractsData } = useQuery({
    queryKey: ["registry-contracts"],
    queryFn: () => adminListContracts(),
  });
  const operationsWithContract = useMemo(() => {
    const codes = new Set<string>();
    const list = Array.isArray(contractsData) ? contractsData : [];
    for (const c of list) {
      if (c.operationCode) codes.add(c.operationCode);
    }
    return codes;
  }, [contractsData]);

  const upsert = useMutation({
    mutationFn: upsertOperation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["registry-operations"] });
      setSuccessMsg("Operation saved.");
      setTimeout(() => setSuccessMsg(null), 3000);
    },
  });

  const { data: featureGatesData } = useQuery({
    queryKey: ["registry-feature-gates"],
    queryFn: listFeatureGates,
  });

  const operations = data?.items ?? [];
  const aiFormatterGate = (featureGatesData ?? []).find((g) => g.gateKey === "ai_formatter_enabled");
  const aiFormatterEnabled = Boolean(aiFormatterGate?.enabled);

  const filteredOperations = useMemo(
    () =>
      operations.filter((op) => {
        if (filterMode === "active" && op.isActive === false) return false;
        if (filterMode === "missing" && operationsWithContract.has(op.operationCode ?? "")) return false;
        if (!search.trim()) return true;
        return op.operationCode.toLowerCase().includes(search.trim().toLowerCase());
      }),
    [operations, search, filterMode, operationsWithContract]
  );

  const activeCount = operations.filter((o) => o.isActive !== false).length;
  const missingCount = operations.filter((o) => !operationsWithContract.has(o.operationCode ?? "")).length;

  // Open versions drawer when ?operation= is in URL (version link / deep links)
  useEffect(() => {
    if (!operationParam || operations.length === 0) return;
    const op = operations.find((o) => o.operationCode === operationParam);
    if (op && versionsDrawerOp?.operationCode !== operationParam) {
      setVersionsDrawerOp(op);
    }
  }, [operationParam, operations, versionsDrawerOp?.operationCode]);

  // Close versions drawer when operation param is cleared (e.g. browser back)
  useEffect(() => {
    if (!operationParam && versionsDrawerOp) {
      setVersionsDrawerOp(null);
      setSchemaDrawerContract(null);
    }
  }, [operationParam, versionsDrawerOp]);

  const closeVersionsDrawer = () => {
    setVersionsDrawerOp(null);
    setSchemaDrawerContract(null);
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("tab", "operations");
      next.delete("operation");
      return next;
    });
  };

  const openContractDrawer = (op: Operation) => {
    setContractDrawerOp(op);
    setDrawerSelectedVersion(op.canonicalVersion ?? "v1");
  };

  const closeContractDrawer = () => {
    setContractDrawerOp(null);
  };

  const handleSave = async (payload: {
    operation_code: string;
    description?: string;
    canonical_version?: string;
    is_async_capable?: boolean;
    is_active?: boolean;
    direction_policy?: import("../types").OperationDirectionPolicy;
  }) => {
    await upsert.mutateAsync(payload);
  };

  const toggleAiFormatter = async () => {
    setAiBusy(true);
    try {
      await updateFeatureGate("ai_formatter_enabled", !aiFormatterEnabled);
      queryClient.invalidateQueries({ queryKey: ["registry-feature-gates"] });
      setSuccessMsg(`AI formatter ${!aiFormatterEnabled ? "enabled" : "disabled"} globally.`);
      setTimeout(() => setSuccessMsg(null), 3000);
    } finally {
      setAiBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      {successMsg && (
        <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-2 text-sm text-emerald-800">
          {successMsg}
        </div>
      )}
      <SectionCard
        title="Operations"
        description={`Canonical operations. ${operations.length} operations (${activeCount} active | ${missingCount} missing).`}
        headerExtras={
          <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
            <input
              type="search"
              placeholder="Search by code…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="flex-1 min-w-0 sm:min-w-[200px] px-3 py-2 text-sm border border-gray-300 rounded-lg min-h-[44px] sm:min-h-0"
            />
            <button
              type="button"
              onClick={() => setFiltersExpanded((e) => !e)}
              title={filtersExpanded ? "Hide filters" : "Show filters"}
              className="p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={filtersExpanded ? "" : "-rotate-90"}>
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>
            <button
              type="button"
              onClick={() => {
                setEditingOp(null);
                setModalOpen(true);
              }}
              className="inline-flex items-center rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-slate-800"
            >
              Create
            </button>
          </div>
        }
      >
        <div className="mb-4 flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
          <div>
            <p className="text-sm font-medium text-slate-800">AI formatter globally enabled</p>
            <p className="text-xs text-slate-600">
              When off, DATA returns raw execute result and PROMPT returns AI disabled.
            </p>
          </div>
          <button
            type="button"
            onClick={toggleAiFormatter}
            disabled={aiBusy}
            className={`inline-flex items-center rounded-full px-3 py-1.5 text-xs font-medium ${
              aiFormatterEnabled ? "bg-emerald-100 text-emerald-800" : "bg-slate-200 text-slate-700"
            } disabled:opacity-60`}
            title={aiFormatterEnabled ? "Disable AI formatter globally" : "Enable AI formatter globally"}
          >
            {aiBusy ? "Saving..." : aiFormatterEnabled ? "Enabled" : "Disabled"}
          </button>
        </div>
        <div className="mb-4">
          {filtersExpanded && (
            <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 overflow-hidden">
              <button
                type="button"
                onClick={() => setFilterMode("all")}
                className={`px-2.5 py-1.5 text-sm font-medium ${
                  filterMode === "all" ? "bg-slate-600 text-white" : "bg-transparent text-slate-600 hover:bg-slate-100"
                }`}
              >
                All
              </button>
              <button
                type="button"
                onClick={() => setFilterMode("active")}
                className={`px-2.5 py-1.5 text-sm font-medium ${
                  filterMode === "active" ? "bg-slate-600 text-white" : "bg-transparent text-slate-600 hover:bg-slate-100"
                }`}
              >
                Active only
              </button>
              <button
                type="button"
                onClick={() => setFilterMode("missing")}
                title="Operations missing contract"
                className={`px-2.5 py-1.5 text-sm font-medium inline-flex items-center gap-1 ${
                  filterMode === "missing" ? "bg-slate-600 text-white" : "bg-transparent text-slate-600 hover:bg-slate-100"
                }`}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={filterMode === "missing" ? "text-white" : "text-red-500"}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
                Missing
              </button>
            </div>
          )}
        </div>
        {isLoading ? (
            <div className="space-y-2">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="h-6 bg-gray-100 rounded animate-pulse" />
              ))}
            </div>
          ) : error ? (
            <div className="text-sm text-amber-600">Unable to load list.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="border-b border-slate-200 bg-slate-50">
                  <tr>
                    <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Code</th>
                    <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Description</th>
                    <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Version</th>
                    <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Direction policy</th>
                    <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">AI</th>
                    <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Active</th>
                    <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500 text-center">Contract</th>
                    <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredOperations.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="px-3 py-6 text-center text-sm text-slate-500">
                        {operations.length === 0 ? "No operations." : "No operations match the filters."}
                      </td>
                    </tr>
                  ) : (
                  filteredOperations.map((o) => (
                    <tr
                      key={o.operationCode}
                      className="hover:bg-slate-50/70"
                    >
                      <td className="px-3 py-2 text-sm text-slate-900 font-mono">{o.operationCode}</td>
                      <td className="px-3 py-2 text-sm text-slate-900">{o.description ?? "—"}</td>
                      <td className="px-3 py-2 text-sm text-slate-900">
                        <Link
                          to={`/admin/registry?tab=operations&operation=${encodeURIComponent(o.operationCode)}`}
                          className="text-slate-600 hover:text-slate-900 font-medium underline underline-offset-1"
                        >
                          {o.canonicalVersion ?? "v1"}
                        </Link>
                      </td>
                      <td className="px-3 py-2 text-sm text-slate-500">
                        {getDirectionPolicyLabel(
                          (o as Operation & { directionPolicy?: string }).directionPolicy ??
                          (o as Operation & { directionPolicy?: string }).directionPolicy
                        ) || "—"}
                      </td>
                      <td className="px-3 py-2 text-sm text-slate-500">
                        {(o as Operation & { aiPresentationMode?: string }).aiPresentationMode ?? "RAW_ONLY"}
                      </td>
                      <td className="px-3 py-2 text-sm text-slate-900">
                        <StatusPill
                          label={o.isActive !== false ? "Active" : "Inactive"}
                          variant={o.isActive !== false ? "configured" : "neutral"}
                        />
                      </td>
                      <td className="px-3 py-2 text-sm text-slate-900 text-center">
                        {operationsWithContract.has(o.operationCode ?? "") ? (
                          <span className="inline-flex items-center justify-center text-emerald-600" title="Contract defined">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                            </svg>
                          </span>
                        ) : (
                          <span className="inline-flex items-center justify-center text-red-500" title="No contract defined">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-sm text-slate-900 text-right">
                        <button
                          type="button"
                          onClick={() => {
                            setEditingOp(o);
                            setModalOpen(true);
                          }}
                          className="text-slate-600 hover:text-slate-800 text-xs font-medium mr-2"
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => openContractDrawer(o)}
                          className="text-slate-600 hover:text-slate-800 text-xs font-medium"
                        >
                          Contract
                        </button>
                      </td>
                    </tr>
                  ))
                  )}
                </tbody>
              </table>
            </div>
          )}
      </SectionCard>

      {/* Versions drawer: read-only contracts list (opened by version link) */}
      {versionsDrawerOp && (
        <VersionsDrawer
          operation={versionsDrawerOp}
          schemaDrawerContract={schemaDrawerContract}
          onClose={closeVersionsDrawer}
          onViewContract={setSchemaDrawerContract}
        />
      )}

      {/* Contract editor drawer (opened by Contract button) */}
      {contractDrawerOp && (
        <>
          <div
            className="fixed inset-0 bg-black/30 z-40"
            aria-hidden
          />
          <div
            className="fixed inset-4 md:inset-6 lg:inset-8 w-auto bg-white shadow-xl z-50 flex flex-col overflow-hidden rounded-xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="contract-drawer-title"
          >
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 px-4 py-3 border-b border-gray-200 bg-gray-50 shrink-0">
              <div>
                <h2 id="contract-drawer-title" className="font-semibold text-gray-900">
                  Canonical contract · {contractDrawerOp.operationCode} ({drawerSelectedVersion})
                </h2>
                <div className="mt-1 flex items-center gap-2 text-xs text-slate-600">
                  <span>Canonical version: {contractDrawerOp.canonicalVersion ?? "v1"}</span>
                  <span
                    className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium ${
                      contractDrawerOp.isActive !== false ? "bg-emerald-100 text-emerald-800" : "bg-gray-100 text-gray-600"
                    }`}
                  >
                    {contractDrawerOp.isActive !== false ? "Active" : "Inactive"}
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={closeContractDrawer}
                className="p-2 text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-200"
                aria-label="Close drawer"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <div className="max-w-6xl mx-auto">
                <CanonicalContractEditor
                  operation={contractDrawerOp}
                  onSelectedVersionChange={setDrawerSelectedVersion}
                  onOperationUpdated={(newDefaultVersion) => {
                    queryClient.invalidateQueries({ queryKey: ["registry-operations"] });
                    setContractDrawerOp((prev) =>
                      prev ? { ...prev, canonicalVersion: newDefaultVersion } : null
                    );
                    setDrawerSelectedVersion(newDefaultVersion);
                  }}
                />
              </div>
            </div>
          </div>
        </>
      )}

      <ContractSchemaDrawer
        contract={schemaDrawerContract}
        onClose={() => setSchemaDrawerContract(null)}
      />

      <OperationModal
        open={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setEditingOp(null);
        }}
        initialValues={editingOp}
        aiFormatterEnabled={aiFormatterEnabled}
        onSave={handleSave}
      />
    </div>
  );
}

/** Compute combined direction label from flow_direction values in a set of rules. */
function getCombinedDirectionLabel(entries: AllowlistEntry[]): string {
  const dirs = new Set(
    entries.map((a) => ((a as AllowlistEntry & { flowDirection?: string })?.flowDirection ?? "BOTH").toUpperCase())
  );
  const hasOutbound = dirs.has("OUTBOUND") || dirs.has("BOTH");
  const hasInbound = dirs.has("INBOUND") || dirs.has("BOTH");
  if (hasOutbound && hasInbound) return getAdminDirectionLabel("BOTH");
  if (hasOutbound) return getAdminDirectionLabel("OUTBOUND");
  if (hasInbound) return getAdminDirectionLabel("INBOUND");
  return "No direction configured";
}

/** Direction label for table: base direction + optional direction policy suffix. */
function getDirectionLabelWithPolicy(
  entries: AllowlistEntry[],
  operationCode: string,
  operations: Operation[]
): string {
  const base = getCombinedDirectionLabel(entries);
  const op = operations.find(
    (o) => (o.operationCode ?? "").toUpperCase() === (operationCode ?? "").toUpperCase()
  );
  const policyValue =
    (op as Operation & { directionPolicy?: string })?.directionPolicy ??
    (op as Operation & { directionPolicy?: string })?.directionPolicy;
  const policyLabel = getDirectionPolicyLabel(policyValue);
  if (policyLabel) return `${base} · ${policyLabel}`;
  return base;
}

/** Augment direction tooltip with direction policy context when operation has a policy. */
function getDirectionTooltipWithPolicy(
  effectiveDir: FlowDirection | null,
  operationCode: string,
  operations: Operation[]
): string | undefined {
  const baseTooltip = effectiveDir ? getAdminDirectionBadgeTooltip(effectiveDir) : undefined;
  const op = operations.find(
    (o) => (o.operationCode ?? "").toUpperCase() === (operationCode ?? "").toUpperCase()
  );
  const policy =
    (op as Operation & { directionPolicy?: string })?.directionPolicy ??
    (op as Operation & { directionPolicy?: string })?.directionPolicy;
  const policyTooltip = getDirectionPolicyConstraintTooltip(policy);
  if (policyTooltip && baseTooltip) return `${baseTooltip} ${policyTooltip}`;
  if (policyTooltip) return policyTooltip;
  return baseTooltip;
}

function formatVendorDisplay(
  vendorCode: string | null | undefined,
  vendors: Vendor[]
): string {
  if (!vendorCode) return "—";
  const v = vendors.find((x) => x.vendorCode === vendorCode);
  if (v) return `${v.vendorCode} – ${v.vendorName}`;
  return vendorCode;
}

function formatTimestamp(iso?: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

type DirectionFilterChip = "all" | "OUTBOUND" | "INBOUND" | "BOTH";
type ScopeFilter = "global" | "vendor_specific" | "all";
function AccessRequestsTab() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<"PENDING" | "APPROVED" | "REJECTED">("PENDING");
  const [decisionModal, setDecisionModal] = useState<{
    item: ChangeRequestItem;
    action: "APPROVE" | "REJECT";
  } | null>(null);
  const [decisionReason, setDecisionReason] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["registry-change-requests", "allowlist", statusFilter],
    queryFn: () =>
      listChangeRequests({
        status: statusFilter,
        source: "allowlist",
        limit: 100,
      }),
  });

  const [toastMsg, setToastMsg] = useState<string | null>(null);

  const decideMutation = useMutation({
    mutationFn: ({ id, action, reason }: { id: string; action: "APPROVE" | "REJECT"; reason?: string }) =>
      decideChangeRequest(id, action, reason),
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: ["registry-change-requests"] });
      setDecisionModal(null);
      setDecisionReason("");
      setToastMsg(
        vars.action === "APPROVE"
          ? "Access request approved"
          : "Access request rejected"
      );
      setTimeout(() => setToastMsg(null), 3000);
    },
  });

  const items = data?.items ?? [];

  const formatDate = (s: string | undefined) => {
    if (!s) return "—";
    try {
      return new Date(s).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
    } catch {
      return s;
    }
  };

  const handleApproveClick = (item: ChangeRequestItem) => {
    setDecisionModal({ item, action: "APPROVE" });
    setDecisionReason("");
  };

  const handleRejectClick = (item: ChangeRequestItem) => {
    setDecisionModal({ item, action: "REJECT" });
    setDecisionReason("");
  };

  const handleDecisionConfirm = () => {
    if (!decisionModal) return;
    decideMutation.mutate({
      id: decisionModal.item.id,
      action: decisionModal.action,
      reason: decisionReason.trim() || undefined,
    });
  };

  const getRequestStatusVariant = (status?: string): StatusPillVariant => {
    if (status === "PENDING") return "warning";
    if (status === "APPROVED") return "configured";
    if (status === "REJECTED") return "error";
    return "neutral";
  };

  return (
    <div className="space-y-4">
      <SectionCard
        title="Access requests"
        description="Vendor-submitted allowlist change requests. Approve or reject with optional reason."
      >
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-gray-700">Status:</span>
          <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 overflow-hidden">
            {(["PENDING", "APPROVED", "REJECTED"] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setStatusFilter(s)}
                className={`px-2 py-1 text-sm font-medium ${
                  statusFilter === s ? "bg-slate-600 text-white" : "bg-transparent text-slate-600 hover:bg-slate-100"
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        {isLoading && (
          <div className="py-8 text-center text-sm text-gray-500">Loading…</div>
        )}
        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-2 text-sm text-red-700">
            {(error as Error).message}
          </div>
        )}
        {!isLoading && !error && items.length === 0 && (
          <div className="py-8 text-center text-sm text-gray-500">
            No {statusFilter.toLowerCase()} access requests.
          </div>
        )}
        {!isLoading && !error && items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b bg-gray-50">
                  <th className="py-2 px-4">Requested at</th>
                  <th className="py-2 px-4">Source</th>
                  <th className="py-2 px-4">Direction</th>
                  <th className="py-2 px-4">Operation</th>
                  <th className="py-2 px-4">Targets</th>
                  <th className="py-2 px-4">Request type</th>
                  <th className="py-2 px-4">Status</th>
                  {statusFilter === "PENDING" && (
                    <th className="py-2 px-4 text-right">Actions</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const targets =
                    (item.targetVendorCodes ?? []).length === 0
                      ? "—"
                      : (item.targetVendorCodes ?? []).join(", ");
                  const source = item.sourceVendorCode ?? item.requestingVendorCode ?? "—";
                  const reqAt = item.createdAt ?? (item as { requestedAt?: string }).requestedAt;
                  return (
                    <tr key={item.id} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="py-2 px-4 text-gray-700">{formatDate(reqAt)}</td>
                      <td className="py-2 px-4 font-mono">{source}</td>
                      <td className="py-2 px-4">{item.direction ?? "—"}</td>
                      <td className="py-2 px-4 font-mono">{item.operationCode ?? "—"}</td>
                      <td className="py-2 px-4">{targets}</td>
                      <td className="py-2 px-4">{item.requestType ?? "—"}</td>
                      <td className="py-2 px-4">
                        <StatusPill
                          label={item.status ?? "—"}
                          variant={getRequestStatusVariant(item.status)}
                        />
                      </td>
                      {statusFilter === "PENDING" && (
                        <td className="py-2 px-4 text-right">
                          <div className="flex gap-2 justify-end">
                            <button
                              type="button"
                              onClick={() => handleApproveClick(item)}
                              disabled={decideMutation.isPending}
                              className="px-2 py-1 text-xs font-medium text-white bg-emerald-600 hover:bg-emerald-700 rounded disabled:opacity-50"
                            >
                              Approve
                            </button>
                            <button
                              type="button"
                              onClick={() => handleRejectClick(item)}
                              disabled={decideMutation.isPending}
                              className="px-2 py-1 text-xs font-medium text-white bg-red-600 hover:bg-red-700 rounded disabled:opacity-50"
                            >
                              Reject
                            </button>
                          </div>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {decisionModal && (
        <ModalShell
          open
          onClose={() => setDecisionModal(null)}
          title={decisionModal.action === "APPROVE" ? "Approve access request" : "Reject access request"}
        >
          <div className="space-y-4">
            <div className="text-sm text-gray-700">
              <p>
                <strong>Source:</strong> {decisionModal.item.sourceVendorCode ?? decisionModal.item.requestingVendorCode}
              </p>
              <p><strong>Direction:</strong> {decisionModal.item.direction}</p>
              <p><strong>Operation:</strong> {decisionModal.item.operationCode}</p>
              <p>
                <strong>Targets:</strong>{" "}
                {(decisionModal.item.targetVendorCodes ?? []).join(", ") || "—"}
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Decision reason (optional)
              </label>
              <textarea
                value={decisionReason}
                onChange={(e) => setDecisionReason(e.target.value)}
                placeholder="Reason for approval or rejection"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                rows={3}
              />
            </div>
            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => setDecisionModal(null)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDecisionConfirm}
                disabled={decideMutation.isPending}
                className={`px-4 py-2 text-sm font-medium text-white rounded-lg disabled:opacity-50 ${
                  decisionModal.action === "APPROVE"
                    ? "bg-emerald-600 hover:bg-emerald-700"
                    : "bg-red-600 hover:bg-red-700"
                }`}
              >
                {decideMutation.isPending ? "Processing…" : decisionModal.action}
              </button>
            </div>
          </div>
        </ModalShell>
      )}

      {toastMsg && (
        <div
          className="fixed bottom-4 right-4 px-4 py-2 bg-emerald-600 text-white rounded-lg shadow-lg text-sm"
          role="status"
        >
          {toastMsg}
        </div>
      )}
    </div>
  );
}

type PerspectiveFilter = "all" | "caller" | "receiver";

function AllowlistTab({
  searchParams,
  setSearchParams,
}: {
  searchParams: URLSearchParams;
  setSearchParams: (fn: (prev: URLSearchParams) => URLSearchParams) => void;
}) {
  const queryClient = useQueryClient();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingEntry, setEditingEntry] = useState<AllowlistEntry | null>(null);
  const [deleteConfirmEntry, setDeleteConfirmEntry] = useState<AllowlistEntry | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>("all");
  const [perspectiveFilter, setPerspectiveFilter] = useState<PerspectiveFilter>("all");
  const [filterSource, setFilterSource] = useState(() => searchParams.get("source") ?? "");
  const [filterTarget, setFilterTarget] = useState("");
  const [filterOperation, setFilterOperation] = useState("");
  const [filterDirection, setFilterDirection] = useState<DirectionFilterChip>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [filtersExpanded, setFiltersExpanded] = useState(false);

  useEffect(() => {
    const src = searchParams.get("source") ?? "";
    const pers = (searchParams.get("perspective") ?? "all") as PerspectiveFilter;
    setFilterSource(src);
    if (["all", "caller", "receiver"].includes(pers)) {
      setPerspectiveFilter(pers);
    }
  }, [searchParams]);

  const { data, isLoading, error } = useQuery<ListRegistryResponse<AllowlistEntry>>({
    queryKey: [
      "registry-allowlist",
      scopeFilter,
      filterSource,
      filterTarget,
      filterOperation,
      perspectiveFilter,
    ],
    queryFn: () =>
      listAllowlist({
        limit: 200,
        scope: scopeFilter,
        sourceVendorCode: filterSource || undefined,
        targetVendorCode: filterTarget || undefined,
        operationCode: filterOperation || undefined,
      }),
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
  });

  const { data: endpointsData } = useQuery({
    queryKey: ["registry-endpoints-all"],
    queryFn: () => listEndpoints({ limit: 200 }),
    enabled: drawerOpen,
  });

  const providerVendorCodesByOperation = useMemo(() => {
    const eps = endpointsData?.items ?? [];
    const map: Record<string, string[]> = {};
    for (const ep of eps) {
      const op = (ep.operationCode ?? "").toUpperCase();
      const vc = (ep.vendorCode ?? "").trim();
      if (!op || !vc) continue;
      if (!map[op]) map[op] = [];
      if (!map[op].includes(vc)) map[op].push(vc);
    }
    for (const op of Object.keys(map)) {
      map[op].sort();
    }
    return map;
  }, [endpointsData]);

  const { data: vendorsData } = useQuery<ListRegistryResponse<Vendor>>({
    queryKey: ["registry-vendors"],
    queryFn: () => listVendors(),
  });

  const { data: operationsData } = useQuery<ListRegistryResponse<Operation>>({
    queryKey: ["registry-operations"],
    queryFn: () => listOperations(),
  });

  const upsert = useMutation({
    mutationFn: upsertAllowlist,
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: ["registry-allowlist"] });
      queryClient.refetchQueries({ queryKey: ["registry-allowlist"], type: "active" });
      const savedOp = (vars?.operation_code || "").trim();
      if (savedOp) {
        setExpandedGroups((prev) => {
          const next = new Set(prev);
          next.add(savedOp);
          return next;
        });
      }
      setSuccessMsg("Access rule saved.");
      setTimeout(() => setSuccessMsg(null), 3000);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteAllowlist(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["registry-allowlist"] });
      setDeleteConfirmEntry(null);
      setSuccessMsg("Access rule removed.");
      setTimeout(() => setSuccessMsg(null), 3000);
    },
  });

  const vendors = vendorsData?.items ?? [];
  const operations = operationsData?.items ?? [];
  const activeVendors = vendors.filter((v) => v.isActive !== false);
  const activeOperations = operations.filter((o) => o.isActive !== false);

  const allEntries = data?.items ?? [];
  const filteredEntries = useMemo(() => {
    let list = allEntries;
    if (filterSource && perspectiveFilter !== "receiver")
      list = list.filter((a) => a.sourceVendorCode === filterSource);
    if (filterTarget && perspectiveFilter !== "caller")
      list = list.filter((a) => a.targetVendorCode === filterTarget);
    if (filterOperation) list = list.filter((a) => a.operationCode === filterOperation);
    if (perspectiveFilter === "caller") {
      list = list.filter((a) => {
        const fd = (a as AllowlistEntry & { flowDirection?: string })?.flowDirection ?? "BOTH";
        return fd === "OUTBOUND" || fd === "BOTH";
      });
    } else if (perspectiveFilter === "receiver") {
      list = list.filter((a) => {
        const fd = (a as AllowlistEntry & { flowDirection?: string })?.flowDirection ?? "BOTH";
        return fd === "INBOUND" || fd === "BOTH";
      });
    } else if (filterDirection !== "all") {
      const fd = filterDirection as "OUTBOUND" | "INBOUND" | "BOTH";
      list = list.filter((a) => {
        const entryDir = (a as AllowlistEntry & { flowDirection?: string })?.flowDirection ?? "BOTH";
        return entryDir === fd;
      });
    }
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      list = list.filter((a) => {
        const src = formatVendorDisplay(a.sourceVendorCode, vendors).toLowerCase();
        const tgt = formatVendorDisplay(a.targetVendorCode, vendors).toLowerCase();
        const op = (a.operationCode ?? "").toLowerCase();
        return src.includes(q) || tgt.includes(q) || op.includes(q);
      });
    }
    return list;
  }, [allEntries, filterSource, filterTarget, filterOperation, filterDirection, perspectiveFilter, searchQuery, vendors]);

  const groupedEntries = useMemo(() => {
    const groups = new Map<string, AllowlistEntry[]>();
    for (const a of filteredEntries) {
      const key = a.operationCode ?? "";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(a);
    }
    return Array.from(groups.entries()).map(([operationCode, entries]) => {
      const dirs = new Set(
        entries.map((a) => ((a as AllowlistEntry & { flowDirection?: string })?.flowDirection ?? "BOTH").toUpperCase())
      );
      const hasOutbound = dirs.has("OUTBOUND") || dirs.has("BOTH");
      const hasInbound = dirs.has("INBOUND") || dirs.has("BOTH");
      const effectiveDir: FlowDirection | null =
        hasOutbound && hasInbound ? "BOTH" : hasOutbound ? "OUTBOUND" : hasInbound ? "INBOUND" : null;
      return {
        key: operationCode,
        operationCode,
        entries,
        directionLabel: getDirectionLabelWithPolicy(entries, operationCode, activeOperations),
        directionTooltip: getDirectionTooltipWithPolicy(effectiveDir, operationCode, activeOperations),
      };
    });
  }, [filteredEntries, activeOperations]);

  const toggleGroup = (key: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const updateUrlParams = (updates: { source?: string; perspective?: string }) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (updates.source !== undefined) {
        if (updates.source) next.set("source", updates.source);
        else next.delete("source");
      }
      if (updates.perspective !== undefined) {
        if (updates.perspective && updates.perspective !== "all")
          next.set("perspective", updates.perspective);
        else next.delete("perspective");
      }
      return next;
    });
  };

  const handleSave = async (payload: UpsertAllowlistPayload) => {
    await upsert.mutateAsync(payload);
  };

  const handleAddRuleClick = () => {
    setEditingEntry(null);
    setDrawerOpen(true);
  };

  return (
    <div className="space-y-4">
      {successMsg && (
        <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-2 text-sm text-emerald-800">
          {successMsg}
        </div>
      )}

      <SectionCard
        title="Access rules"
        description="Control explicit source-target licensee pairs by operation and direction."
        headerExtras={
          <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
            <input
              type="search"
              placeholder="Search vendor codes, names, operation…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="flex-1 min-w-0 sm:min-w-[320px] px-3 py-2 text-sm border border-gray-300 rounded-lg min-h-[44px] sm:min-h-0"
            />
            <button
              type="button"
              onClick={() => setFiltersExpanded((e) => !e)}
              title={filtersExpanded ? "Hide filters" : "Show filters"}
              className="p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={filtersExpanded ? "" : "-rotate-90"}>
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>
            <button
              type="button"
              onClick={handleAddRuleClick}
              className="inline-flex items-center rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-slate-800"
            >
              Add rule
            </button>
          </div>
        }
      >
        <div className="mb-4">
          {filtersExpanded && (
            <div className="flex flex-wrap items-center gap-2">
              <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 overflow-hidden">
                {(["global", "vendor_specific", "all"] as const).map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setScopeFilter(s)}
                    className={`px-2 py-1 text-sm font-medium ${
                      scopeFilter === s ? "bg-slate-600 text-white" : "bg-transparent text-slate-600 hover:bg-slate-100"
                    }`}
                  >
                    {s === "global" ? "Global" : s === "vendor_specific" ? "Vendor overrides" : "All"}
                  </button>
                ))}
              </div>
              <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 overflow-hidden">
                {(["all", "caller", "receiver"] as const).map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => {
                      setPerspectiveFilter(p);
                      updateUrlParams({ perspective: p === "all" ? "" : p });
                    }}
                    className={`px-2 py-1 text-sm font-medium ${
                      perspectiveFilter === p ? "bg-slate-600 text-white" : "bg-transparent text-slate-600 hover:bg-slate-100"
                    }`}
                  >
                    {p === "all" ? "All" : p === "caller" ? "Caller" : "Receiver"}
                  </button>
                ))}
              </div>
              <span className="text-slate-300 mx-0.5">|</span>
              {perspectiveFilter !== "receiver" && (
                <select
                  value={filterSource}
                  onChange={(e) => {
                    const v = e.target.value;
                    setFilterSource(v);
                    updateUrlParams({ source: v });
                  }}
                  className="px-2 py-1 text-sm border border-gray-300 rounded-lg min-w-[100px]"
                >
                  <option value="">{perspectiveFilter === "caller" ? "All callers" : "All"}</option>
                  {activeVendors.map((v) => (
                    <option key={v.vendorCode} value={v.vendorCode}>
                      {v.vendorCode}
                    </option>
                  ))}
                </select>
              )}
              {perspectiveFilter !== "caller" && (
                <select
                  value={filterTarget}
                  onChange={(e) => setFilterTarget(e.target.value)}
                  className="px-2 py-1 text-sm border border-gray-300 rounded-lg min-w-[100px]"
                >
                  <option value="">{perspectiveFilter === "receiver" ? "All receivers" : "All"}</option>
                  {activeVendors.map((v) => (
                    <option key={v.vendorCode} value={v.vendorCode}>
                      {v.vendorCode}
                    </option>
                  ))}
                </select>
              )}
              <span className="text-slate-300 mx-0.5">|</span>
              <select
                value={filterOperation}
                onChange={(e) => setFilterOperation(e.target.value)}
                className="px-2 py-1 text-sm border border-gray-300 rounded-lg min-w-[110px]"
              >
                <option value="">All operations</option>
                {activeOperations.map((o) => (
                  <option key={o.operationCode} value={o.operationCode}>
                    {o.operationCode}
                  </option>
                ))}
              </select>
              {perspectiveFilter === "all" && (
                <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 overflow-hidden">
                  {(["all", "OUTBOUND", "INBOUND", "BOTH"] as const).map((d) => (
                    <button
                      key={d}
                      type="button"
                      onClick={() => setFilterDirection(d)}
                      title={d !== "all" ? getAdminDirectionBadgeTooltip(d as FlowDirection) : undefined}
                      className={`px-2 py-1 text-sm font-medium ${
                        filterDirection === d ? "bg-slate-600 text-white" : "bg-transparent text-slate-600 hover:bg-slate-100"
                      }`}
                    >
                      {d === "all" ? "All dirs" : d === "OUTBOUND" ? "Send" : d === "INBOUND" ? "Receive" : "Two-way"}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {isLoading ? (
          <div className="space-y-2">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-6 bg-gray-100 rounded animate-pulse" />
            ))}
          </div>
        ) : error ? (
          <div className="text-sm text-amber-600">Unable to load list.</div>
        ) : groupedEntries.length === 0 ? (
          <div className="text-sm text-slate-500 py-4">
            {allEntries.length === 0
              ? "No access rules found for current scope."
              : "No rules match the current filters."}
          </div>
        ) : (
          <div className="space-y-1">
            {groupedEntries.map(({ key, operationCode, entries, directionLabel, directionTooltip }) => {
              const expanded = expandedGroups.has(key);
              const groupedBySource = entries.reduce<Record<string, AllowlistEntry[]>>((acc, entry) => {
                const source = (entry.sourceVendorCode || "").trim().toUpperCase() || "UNKNOWN";
                if (!acc[source]) acc[source] = [];
                acc[source].push(entry);
                return acc;
              }, {});
              const sourceGroups = Object.entries(groupedBySource)
                .map(([source, rows]) => ({
                  source,
                  rows: [...rows].sort((a, b) =>
                    String(a.targetVendorCode || "").localeCompare(String(b.targetVendorCode || ""))
                  ),
                }))
                .sort((a, b) => a.source.localeCompare(b.source));
              const globalCount = entries.filter((a) => a.isGlobal).length;
              const overrideCount = entries.length - globalCount;
              const badgeParts: string[] = [`${entries.length} rule${entries.length !== 1 ? "s" : ""}`];
              if (globalCount > 0 && overrideCount > 0) {
                badgeParts.push(`${globalCount} global`, `${overrideCount} override`);
              } else if (globalCount > 0) {
                badgeParts.push(`${globalCount} global`);
              } else if (overrideCount > 0) {
                badgeParts.push(`${overrideCount} override`);
              }
              return (
                <div key={key} className="border border-slate-200 rounded-lg overflow-hidden">
                  <button
                    type="button"
                    onClick={() => toggleGroup(key)}
                    className="w-full flex items-center justify-between px-4 py-2.5 bg-slate-50 hover:bg-slate-100 text-left"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-gray-500 transform transition-transform">{expanded ? "▼" : "▶"}</span>
                      <span className="font-medium text-gray-900 font-mono">{operationCode}</span>
                      <span className="text-gray-400">·</span>
                      <span className="text-gray-600" title={directionTooltip}>
                        {directionLabel}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      {badgeParts.map((b) => (
                        <span
                          key={b}
                          className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium bg-slate-100 text-slate-700"
                        >
                          {b}
                        </span>
                      ))}
                    </div>
                  </button>
                  {expanded && (
                    <div className="overflow-x-auto overflow-y-auto max-h-[28rem] border-t border-slate-200">
                      <table className="min-w-full text-left text-sm">
                        <thead className="border-b border-slate-200 bg-slate-50">
                          <tr>
                            <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Source</th>
                            <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Target</th>
                            <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Scope</th>
                            <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Created / Updated</th>
                            <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500 text-right">Actions</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {sourceGroups.map(({ source, rows }) => (
                            <Fragment key={`${operationCode}-${source}`}>
                              <tr className="bg-slate-50">
                                <td colSpan={5} className="sticky top-0 z-10 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-700 border-y border-slate-200">
                                  Source: {formatVendorDisplay(source, vendors)} ({rows.length})
                                </td>
                              </tr>
                              {rows.map((a) => (
                                <tr
                                  key={a.id ?? `${a.sourceVendorCode}-${a.targetVendorCode}-${a.operationCode}-${a.flowDirection ?? "BOTH"}`}
                                  className="hover:bg-slate-50/70"
                                >
                                  <td className="px-3 py-2 text-sm text-slate-500">—</td>
                                  <td className="px-3 py-2 text-sm text-slate-900">{formatVendorDisplay(a.targetVendorCode, vendors)}</td>
                                  <td className="px-3 py-2 text-sm text-slate-900">
                                    {a.isGlobal ? (
                                      <span
                                        className="text-xs font-medium text-slate-600 bg-slate-100 px-1.5 py-0.5 rounded"
                                        title="Admin access rule. Vendors can only narrow access further; they cannot override this in the vendor portal."
                                      >
                                        Global
                                      </span>
                                    ) : (
                                      <span className="text-xs text-slate-500">Override</span>
                                    )}
                                  </td>
                                  <td className="px-3 py-2 text-sm text-slate-500">
                                    {formatTimestamp((a as AllowlistEntry & { updatedAt?: string })?.updatedAt ?? a.createdAt)}
                                  </td>
                                  <td className="px-3 py-2 text-sm text-slate-900 text-right">
                                    <button
                                      type="button"
                                      onClick={() => {
                                        setEditingEntry(a);
                                        setDrawerOpen(true);
                                      }}
                                      className="text-slate-600 hover:text-slate-800 text-xs font-medium mr-2"
                                    >
                                      Edit
                                    </button>
                                    {a.id && (
                                      <button
                                        type="button"
                                        onClick={() => setDeleteConfirmEntry(a)}
                                        className="text-rose-600 hover:text-rose-800 text-xs font-medium"
                                      >
                                        Delete
                                      </button>
                                    )}
                                  </td>
                                </tr>
                              ))}
                            </Fragment>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </SectionCard>

      <AllowlistDrawer
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false);
          setEditingEntry(null);
        }}
        initialValues={editingEntry}
        vendors={activeVendors}
        operations={activeOperations}
        existingOperationCodes={Array.from(new Set(allEntries.map((a) => a.operationCode).filter(Boolean)))}
        providerVendorCodesByOperation={providerVendorCodesByOperation}
        onSave={handleSave}
      />

      <ModalShell
        open={!!deleteConfirmEntry}
        onClose={() => setDeleteConfirmEntry(null)}
        title="Remove this access rule?"
      >
        {deleteConfirmEntry && (
          <div className="space-y-4">
            <p className="text-sm text-gray-600">
              Remove this access rule? Requests matching this source, target, operation, and direction will be
              blocked by admin rules.
            </p>
            <p className="text-xs text-gray-500">
              {formatVendorDisplay(deleteConfirmEntry.sourceVendorCode, vendors)} →{" "}
              {formatVendorDisplay(deleteConfirmEntry.targetVendorCode, vendors)} · {deleteConfirmEntry.operationCode}
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setDeleteConfirmEntry(null)}
                className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  if (deleteConfirmEntry.id) {
                    deleteMutation.mutate(deleteConfirmEntry.id);
                  }
                }}
                disabled={!deleteConfirmEntry.id || deleteMutation.isPending}
                className="px-3 py-1.5 text-sm font-medium text-white bg-rose-600 hover:bg-rose-700 rounded-lg disabled:opacity-50"
              >
                {deleteMutation.isPending ? "Removing…" : "Remove"}
              </button>
            </div>
          </div>
        )}
      </ModalShell>
    </div>
  );
}
