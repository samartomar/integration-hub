import { useState, useEffect, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listAuthProfiles,
  getVendorEndpoints,
  getVendorSupportedOperations,
  upsertVendorEndpoint,
  verifyVendorEndpoint,
} from "../api/endpoints";
import {
  getActiveVendorCode,
} from "frontend-shared";
import { STALE_CONFIG } from "../api/queryKeys";
import { EndpointEditDrawer } from "../components/config/EndpointEditDrawer";
import { OpenSettingsLink } from "../components/OpenSettingsLink";
import { CollapsiblePanel } from "../components/CollapsiblePanel";
import { FilterableTableShell } from "../components/FilterableTableShell";
import { PaginationBar } from "../components/PaginatedRows";
import { StatusPill } from "frontend-shared";
import type { AuthProfile } from "../api/endpoints";
import type { VendorEndpoint } from "frontend-shared";
import {
  getEndpointVerificationDisplay,
  deriveHealthFromLegacyFields,
  type EndpointHealth,
} from "../utils/readinessModel";
import { computeStats } from "../utils/authEndpointsUtils";
import { VendorPageLayout } from "../components/layout/VendorPageLayout";

const PAGE_SIZE = 20;
const operationParam = "operation";
const directionParam = "direction";

export function VendorEndpointsConfigPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const authProfileParam = searchParams.get("authProfile") ?? undefined;
  const operationParamValue = searchParams.get(operationParam) ?? undefined;
  const directionParamValue = searchParams.get(directionParam) ?? undefined;

  const queryClient = useQueryClient();
  const activeVendor = getActiveVendorCode();
  const hasKey = !!activeVendor;

  const [endpointModalOpen, setEndpointModalOpen] = useState(false);
  const [editingEndpoint, setEditingEndpoint] = useState<VendorEndpoint | null>(null);
  const [search, setSearch] = useState("");
  const [endpointStatusFilter, setEndpointStatusFilter] = useState<
    "all" | "healthy" | "with_issues"
  >("all");
  const [endpointPage, setEndpointPage] = useState(1);

  const { data: authData } = useQuery({
    queryKey: ["auth-profiles", activeVendor ?? ""],
    queryFn: () => listAuthProfiles(activeVendor!),
    enabled: !!activeVendor,
    retry: false,
    staleTime: STALE_CONFIG,
  });
  const {
    data: endpointsData,
    isLoading: endpointsLoading,
    error: endpointsError,
  } = useQuery({
    queryKey: ["vendor-endpoints"],
    queryFn: getVendorEndpoints,
    enabled: hasKey,
    retry: (_, err) =>
      (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: supportedData } = useQuery({
    queryKey: ["vendor-supported-operations"],
    queryFn: getVendorSupportedOperations,
    enabled: hasKey,
    retry: (_, err) =>
      (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });

  const authProfiles = authData?.items ?? [];
  const allEndpoints = endpointsData?.items ?? [];
  const baseEndpoints = authProfileParam
    ? allEndpoints.filter((e) => e.authProfileId === authProfileParam)
    : allEndpoints;
  const activeAuthProfiles = authProfiles.filter((ap) => ap.isActive !== false);
  const supportedOperationCodes = (supportedData?.items ?? []).map((s) => s.operationCode);

  const {
    healthyEndpoints,
    endpointsWithIssues,
  } = useMemo(
    () => computeStats(authProfiles, allEndpoints),
    [authProfiles, allEndpoints]
  );

  const authProfileById = useMemo(() => {
    const m = new Map<string, AuthProfile>();
    for (const ap of authProfiles) {
      if (ap.id) m.set(ap.id, ap);
    }
    return m;
  }, [authProfiles]);

  const hasEndpointIssues =
    !!endpointsError ||
    baseEndpoints.some((e) => {
      const health =
        (e as { endpointHealth?: string }).endpointHealth ??
        deriveHealthFromLegacyFields(e.verificationStatus, e.isActive);
      return health === "error";
    });

  const formatLastVerifiedDateOnly = (s: string | undefined): string => {
    if (!s) return "—";
    try {
      const d = new Date(s);
      if (Number.isNaN(d.getTime())) return "—";
      const mm = String(d.getMonth() + 1).padStart(2, "0");
      const dd = String(d.getDate()).padStart(2, "0");
      const yyyy = String(d.getFullYear());
      return `${mm}/${dd}/${yyyy}`;
    } catch {
      return "—";
    }
  };

  const formatLastVerifiedTooltip = (s: string | undefined): string => {
    if (!s) return "—";
    try {
      const d = new Date(s);
      if (Number.isNaN(d.getTime())) return "—";
      const datePart = d.toLocaleDateString();
      const timePart = d.toLocaleTimeString();
      return `${datePart}\n${timePart}`;
    } catch {
      return "—";
    }
  };

  const upsertEndpoint = useMutation({
    mutationFn: upsertVendorEndpoint,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vendor-endpoints"] });
      queryClient.invalidateQueries({ queryKey: ["vendor", "config-bundle"] });
    },
  });
  const verifyEndpoint = useMutation({
    mutationFn: verifyVendorEndpoint,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vendor-endpoints"] });
    },
  });

  useEffect(() => {
    if (operationParamValue && !endpointModalOpen) {
      const requestedDirection = (directionParamValue ?? "").trim().toUpperCase();
      const ep = allEndpoints.find((e) => {
        if (e.operationCode !== operationParamValue) return false;
        if (!requestedDirection) return true;
        return (e.flowDirection ?? "").toUpperCase() === requestedDirection;
      });
      setEditingEndpoint(
        ep ??
          ({
            operationCode: operationParamValue,
            flowDirection: requestedDirection || "OUTBOUND",
          } as VendorEndpoint)
      );
      setEndpointModalOpen(true);
    }
  }, [operationParamValue, directionParamValue, endpointModalOpen, allEndpoints]);

  const authProfileName = (id: string | undefined | null) => {
    if (id == null || id === "") return "—";
    const ap = activeAuthProfiles.find((a) => a.id === id);
    return ap?.name ?? id;
  };

  const handleSaveEndpoint = async (payload: {
    id?: string;
    operationCode: string;
    url: string;
    flowDirection?: string;
    httpMethod?: string;
    payloadFormat?: string;
    timeoutMs?: number;
    isActive?: boolean;
    authProfileId?: string | null;
    verificationRequest?: Record<string, unknown> | null;
  }) => {
    const resolvedDirection =
      payload.flowDirection ??
      editingEndpoint?.flowDirection ??
      directionParamValue?.toUpperCase() ??
      "OUTBOUND";
    await upsertEndpoint.mutateAsync({
      ...payload,
      flowDirection: resolvedDirection,
    });
    if (authProfileParam) {
      const savedAuthId = payload.authProfileId?.trim() || null;
      const filterMatches = savedAuthId === authProfileParam;
      if (!filterMatches) {
        setSearchParams((p) => {
          const next = new URLSearchParams(p);
          next.delete("authProfile");
          return next;
        });
      }
    }
  };

  const filteredEndpoints = useMemo(() => {
    let list = baseEndpoints;
    const q = search.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (e) =>
          (e.operationCode ?? "").toLowerCase().includes(q) ||
          (e.url ?? "").toLowerCase().includes(q) ||
          (e.httpMethod ?? "").toLowerCase().includes(q) ||
          authProfileName(e.authProfileId).toLowerCase().includes(q)
      );
    }
    if (endpointStatusFilter === "healthy") {
      list = list.filter(
        (e) =>
          getEndpointVerificationDisplay(
            e.verificationStatus,
            e.isActive,
            (e as { endpointHealth?: EndpointHealth }).endpointHealth
          ).variant === "configured"
      );
    }
    if (endpointStatusFilter === "with_issues") {
      list = list.filter(
        (e) =>
          getEndpointVerificationDisplay(
            e.verificationStatus,
            e.isActive,
            (e as { endpointHealth?: EndpointHealth }).endpointHealth
          ).variant !== "configured"
      );
    }
    return list;
  }, [baseEndpoints, search, endpointStatusFilter, activeAuthProfiles]);

  const paginatedEndpoints = useMemo(() => {
    const start = (endpointPage - 1) * PAGE_SIZE;
    return filteredEndpoints.slice(start, start + PAGE_SIZE);
  }, [filteredEndpoints, endpointPage]);

  const endpointTotalPages = Math.max(1, Math.ceil(filteredEndpoints.length / PAGE_SIZE));

  const handleVerifyEndpoint = async (payload: {
    operationCode: string;
    flowDirection?: string;
  }) => {
    const resolvedDirection =
      payload.flowDirection ??
      editingEndpoint?.flowDirection ??
      directionParamValue?.toUpperCase() ??
      "OUTBOUND";
    const res = await verifyEndpoint.mutateAsync({
      ...payload,
      flowDirection: resolvedDirection,
    });
    const r = res.endpoint?.verificationResult;
    if (!r) {
      return { verified: false, message: "No verification result returned." };
    }
    const verified = (r.status ?? "").toUpperCase() === "VERIFIED";
    return {
      verified,
      httpStatus: r.httpStatus,
      message: verified
        ? "Endpoint verified successfully"
        : r.responseSnippet ?? r.status ?? "Verification failed",
      responseSnippet: r.responseSnippet ?? null,
    };
  };

  if (!activeVendor) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Configuration</h1>
        <div className="rounded-lg bg-gray-50 border border-gray-200 p-4">
          <p className="text-sm font-medium text-gray-700">Select an active licensee above.</p>
        </div>
      </div>
    );
  }

  if (!hasKey) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Configuration</h1>
        <div className="rounded-lg bg-amber-50 border border-amber-200 p-4">
          <p className="text-sm font-medium text-amber-800">Active licensee not selected.</p>
          <OpenSettingsLink>Open Settings →</OpenSettingsLink>
        </div>
      </div>
    );
  }

  return (
    <VendorPageLayout
      title="Endpoints"
      subtitle="Endpoints define where the platform sends vendor API requests for each operation."
      rightContent={
        <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
          <input
            type="search"
            placeholder="Search by operation, URL, or auth…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 min-w-[140px] sm:max-w-[220px] px-3 py-1.5 text-sm border border-gray-300 rounded-lg placeholder-gray-400 focus:ring-2 focus:ring-slate-500 focus:border-slate-500 bg-white shrink-0"
          />
          <select
            value={endpointStatusFilter}
            onChange={(e) => {
              setEndpointStatusFilter(e.target.value as typeof endpointStatusFilter);
              setEndpointPage(1);
            }}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-slate-500 shrink-0"
          >
            <option value="all">All</option>
            <option value="healthy">Healthy</option>
            <option value="with_issues">With issues</option>
          </select>
          <button
            type="button"
            onClick={() => {
              setEditingEndpoint(null);
              setEndpointModalOpen(true);
            }}
            className="px-3 py-1.5 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 rounded-lg shrink-0"
          >
            Add Endpoint
          </button>
        </div>
      }
    >
      <div className="space-y-6">
        <CollapsiblePanel
          title={`${healthyEndpoints} healthy / ${endpointsWithIssues} with issues`}
          defaultExpanded={true}
          forceExpanded={!!operationParamValue || hasEndpointIssues}
        >
          <div className="flex items-center gap-2 mb-3">
            {authProfileParam && (
              <span className="inline-flex items-center gap-1 px-2 py-1 bg-slate-100 text-slate-700 rounded text-xs">
                Filtered by auth profile
                <button
                  type="button"
                  onClick={() =>
                    setSearchParams((p) => {
                      const next = new URLSearchParams(p);
                      next.delete("authProfile");
                      return next;
                    })
                  }
                  className="text-slate-500 hover:text-slate-800"
                >
                  ✕
                </button>
              </span>
            )}
          </div>

          <FilterableTableShell
            searchPlaceholder="Search by operation, URL, auth…"
            searchValue={search}
            onSearchChange={setSearch}
            searchVisible={false}
            showHeader={false}
            footer={
              !endpointsLoading &&
              !endpointsError &&
              baseEndpoints.length > 0 &&
              filteredEndpoints.length > PAGE_SIZE ? (
                <PaginationBar
                  currentPage={endpointPage}
                  totalPages={endpointTotalPages}
                  totalItems={filteredEndpoints.length}
                  pageSize={PAGE_SIZE}
                  onPageChange={setEndpointPage}
                />
              ) : undefined
            }
          >
            {endpointsLoading && (
              <div className="p-8 space-y-2">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="h-10 bg-gray-100 rounded animate-pulse" />
                ))}
              </div>
            )}
            {!endpointsLoading && endpointsError && (
              <div className="p-8 text-sm text-amber-600">Unable to load endpoints.</div>
            )}
            {!endpointsLoading && !endpointsError && baseEndpoints.length === 0 && (
              <div className="p-8 text-sm text-gray-500 space-y-2">
                {authProfileParam && allEndpoints.length > 0 ? (
                  <>
                    <p>
                      No endpoints use this auth profile. {allEndpoints.length} endpoint
                      {allEndpoints.length !== 1 ? "s use" : " uses"} other profiles or no auth.
                    </p>
                    <button
                      type="button"
                      onClick={() =>
                        setSearchParams((p) => {
                          const next = new URLSearchParams(p);
                          next.delete("authProfile");
                          return next;
                        })
                      }
                      className="text-slate-600 hover:text-slate-800 font-medium underline"
                    >
                      Clear filter to see all endpoints
                    </button>
                  </>
                ) : (
                  <p>
                    No endpoints yet. Add supported operations first (via{" "}
                    <Link to="/configuration" className="text-slate-600 hover:underline">
                      Operations
                    </Link>
                    ), then add endpoints here.
                  </p>
                )}
              </div>
            )}
            {!endpointsLoading && !endpointsError && baseEndpoints.length > 0 && (
              <table className="min-w-full text-sm">
                <thead className="sticky top-0 z-10 bg-gray-50 border-b border-gray-200">
                  <tr className="text-left text-gray-500">
                    <th className="py-2 px-3">Operation</th>
                    <th className="py-2 px-3">URL</th>
                    <th className="py-2 px-3">Method</th>
                    <th className="py-2 px-3">Auth Profile</th>
                    <th className="py-2 px-3 text-right">Timeout</th>
                    <th className="py-2 px-3">Status</th>
                    <th className="py-2 px-3 text-right">Last Verified</th>
                    <th className="py-2 px-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedEndpoints.map((ep, i) => {
                    const { label, variant } = getEndpointVerificationDisplay(
                      ep.verificationStatus,
                      ep.isActive,
                      (ep as { endpointHealth?: EndpointHealth }).endpointHealth
                    );
                    return (
                      <tr
                        key={
                          ep.id ??
                          `${ep.operationCode}-${ep.flowDirection ?? "outbound"}-${i}`
                        }
                        className="border-b border-gray-100 hover:bg-slate-50 dark:hover:bg-slate-800/40"
                      >
                        <td className="py-2 px-3 font-mono">{ep.operationCode}</td>
                        <td
                          className="py-2 px-3 text-gray-700 truncate max-w-[200px]"
                          title={ep.url ?? undefined}
                        >
                          {ep.url}
                        </td>
                        <td className="py-2 px-3">{ep.httpMethod ?? "POST"}</td>
                        <td className="py-2 px-3">
                          <span className="inline-flex items-center gap-1">
                            {authProfileName(ep.authProfileId)}
                            {ep.authProfileId &&
                              (() => {
                                const prof = authProfileById.get(ep.authProfileId);
                                if (prof?.isActive === false) {
                                  return (
                                    <span
                                      title="This endpoint uses an inactive auth profile."
                                      className="text-amber-600"
                                      aria-label="Inactive auth profile"
                                    >
                                      ⚠
                                    </span>
                                  );
                                }
                                return null;
                              })()}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-right">{ep.timeoutMs ?? "—"}</td>
                        <td className="py-2 px-3">
                          <StatusPill label={label} variant={variant} />
                        </td>
                        <td className="py-2 px-3 text-right text-gray-600">
                          <span
                            className="inline-block whitespace-nowrap"
                            title={formatLastVerifiedTooltip(ep.lastVerifiedAt ?? undefined)}
                          >
                            {formatLastVerifiedDateOnly(ep.lastVerifiedAt ?? undefined)}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-right">
                          <button
                            type="button"
                            onClick={() => {
                              setEditingEndpoint(ep);
                              setEndpointModalOpen(true);
                            }}
                            className="text-slate-600 hover:text-slate-800 text-xs font-medium whitespace-nowrap"
                          >
                            Edit & Verify
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </FilterableTableShell>
        </CollapsiblePanel>
      </div>

      <EndpointEditDrawer
        open={endpointModalOpen}
        onClose={() => {
          setEndpointModalOpen(false);
          setEditingEndpoint(null);
          if (operationParamValue) {
            setSearchParams((p) => {
              const next = new URLSearchParams(p);
              next.delete(operationParam);
              next.delete(directionParam);
              return next;
            });
          }
        }}
        initialValues={editingEndpoint}
        useModalPattern
        onVerify={handleVerifyEndpoint}
        supportedOperationCodes={supportedOperationCodes}
        authProfiles={activeAuthProfiles}
        onSave={handleSaveEndpoint}
      />
    </VendorPageLayout>
  );
}
