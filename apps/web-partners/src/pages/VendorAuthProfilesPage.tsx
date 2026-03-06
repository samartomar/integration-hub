import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listAuthProfiles,
  upsertAuthProfile,
  deleteAuthProfile,
  getVendorEndpoints,
} from "../api/endpoints";
import {
  getActiveVendorCode,
} from "frontend-shared";
import { STALE_CONFIG } from "../api/queryKeys";
import { AuthProfileModal } from "../components/config/AuthProfileModal";
import { OpenSettingsLink } from "../components/OpenSettingsLink";
import { CollapsiblePanel } from "../components/CollapsiblePanel";
import { FilterableTableShell } from "../components/FilterableTableShell";
import { PaginationBar } from "../components/PaginatedRows";
import { StatusPill } from "frontend-shared";
import type { AuthProfile } from "../api/endpoints";
import { computeStats, formatConfigDate } from "../utils/authEndpointsUtils";
import { VendorPageLayout } from "../components/layout/VendorPageLayout";
import { VendorTableSkeleton } from "../components/vendor/skeleton";

const PAGE_SIZE = 20;

export function VendorAuthProfilesPage() {
  const queryClient = useQueryClient();
  const activeVendor = getActiveVendorCode();
  const hasKey = !!activeVendor;

  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [editingProfile, setEditingProfile] = useState<AuthProfile | null>(null);
  const [search, setSearch] = useState("");
  const [authStatusFilter, setAuthStatusFilter] = useState<"all" | "active" | "inactive">("all");
  const [authPage, setAuthPage] = useState(1);
  const [authSortByUsed, setAuthSortByUsed] = useState<"asc" | "desc" | null>(null);

  const { data: authData, isLoading: authLoading } = useQuery({
    queryKey: ["auth-profiles", activeVendor ?? ""],
    queryFn: () => listAuthProfiles(activeVendor!),
    enabled: !!activeVendor,
    retry: false,
    staleTime: STALE_CONFIG,
  });
  const { data: endpointsData, isLoading: endpointsLoading } = useQuery({
    queryKey: ["vendor-endpoints"],
    queryFn: getVendorEndpoints,
    enabled: hasKey,
    retry: (_, err) =>
      (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });

  const authProfiles = authData?.items ?? [];
  const allEndpoints = endpointsData?.items ?? [];

  const { endpointCountByProfile, profilesInUse } = useMemo(
    () => computeStats(authProfiles, allEndpoints),
    [authProfiles, allEndpoints]
  );

  const upsertProfile = useMutation({
    mutationFn: upsertAuthProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["auth-profiles", activeVendor ?? ""] });
    },
  });
  const deleteProfile = useMutation({
    mutationFn: deleteAuthProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["auth-profiles", activeVendor ?? ""] });
    },
  });

  const filteredAuthProfiles = useMemo(() => {
    let list = authProfiles;
    const q = search.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (a) =>
          (a.name ?? "").toLowerCase().includes(q) ||
          (a.authType ?? "").toLowerCase().includes(q)
      );
    }
    if (authStatusFilter === "active") list = list.filter((a) => a.isActive !== false);
    if (authStatusFilter === "inactive") list = list.filter((a) => a.isActive === false);
    if (authSortByUsed !== null) {
      list = [...list].sort((a, b) => {
        const ca = a.id ? (endpointCountByProfile[a.id] ?? 0) : 0;
        const cb = b.id ? (endpointCountByProfile[b.id] ?? 0) : 0;
        return authSortByUsed === "asc" ? ca - cb : cb - ca;
      });
    }
    return list;
  }, [
    authProfiles,
    search,
    authStatusFilter,
    authSortByUsed,
    endpointCountByProfile,
  ]);

  const paginatedAuthProfiles = useMemo(() => {
    const start = (authPage - 1) * PAGE_SIZE;
    return filteredAuthProfiles.slice(start, start + PAGE_SIZE);
  }, [filteredAuthProfiles, authPage]);

  const authTotalPages = Math.max(1, Math.ceil(filteredAuthProfiles.length / PAGE_SIZE));

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
      title="Authentication profiles"
      subtitle="Reusable credentials (API key, bearer, basic auth) shared across vendor endpoints."
      rightContent={
        <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
          <input
            type="search"
            placeholder="Search by name or type…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 min-w-[140px] sm:max-w-[220px] px-3 py-1.5 text-sm border border-gray-300 rounded-lg placeholder-gray-400 focus:ring-2 focus:ring-slate-500 focus:border-slate-500 bg-white shrink-0"
          />
          <select
            value={authStatusFilter}
            onChange={(e) => {
              setAuthStatusFilter(e.target.value as typeof authStatusFilter);
              setAuthPage(1);
            }}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-slate-500 shrink-0"
          >
            <option value="all">All</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
          <button
            type="button"
            onClick={() => {
              setEditingProfile(null);
              setProfileModalOpen(true);
            }}
            className="px-3 py-1.5 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 rounded-lg shrink-0"
          >
            Add profile
          </button>
        </div>
      }
    >
      <div className="space-y-6">
        <CollapsiblePanel
          title={authLoading || endpointsLoading ? "— in use / — total" : `${profilesInUse} in use / ${authProfiles.length} total`}
          defaultExpanded={true}
        >
          {authLoading || endpointsLoading ? (
            <VendorTableSkeleton rowCount={6} columnCount={6} />
          ) : (
          <FilterableTableShell
            searchPlaceholder="Search by name or type…"
            searchValue={search}
            onSearchChange={setSearch}
            searchVisible={false}
            showHeader={false}
            footer={
              authProfiles.length > 0 && filteredAuthProfiles.length > PAGE_SIZE ? (
                <PaginationBar
                  currentPage={authPage}
                  totalPages={authTotalPages}
                  totalItems={filteredAuthProfiles.length}
                  pageSize={PAGE_SIZE}
                  onPageChange={setAuthPage}
                />
              ) : undefined
            }
          >
            {authProfiles.length === 0 ? (
              <p className="text-sm text-gray-500 py-4">
                No auth profiles yet. Create one to link to endpoints.
              </p>
            ) : (
              <table className="min-w-full text-sm">
                <thead className="sticky top-0 z-10 bg-gray-50 border-b border-gray-200">
                  <tr className="text-left text-gray-500">
                    <th className="py-2 px-3">Name</th>
                    <th className="py-2 px-3">Type</th>
                    <th className="py-2 px-3">
                      <button
                        type="button"
                        onClick={() =>
                          setAuthSortByUsed((s) =>
                            s === null ? "asc" : s === "asc" ? "desc" : null
                          )
                        }
                        className="hover:text-gray-700 font-medium"
                      >
                        Used by endpoints
                        {authSortByUsed === "asc" && " ↑"}
                        {authSortByUsed === "desc" && " ↓"}
                      </button>
                    </th>
                    <th className="py-2 px-3">Last updated</th>
                    <th className="py-2 px-3">Status</th>
                    <th className="py-2 px-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedAuthProfiles.map((ap) => {
                    const count = ap.id ? (endpointCountByProfile[ap.id] ?? 0) : 0;
                    return (
                      <tr
                        key={ap.id ?? ap.name}
                        className="border-b border-gray-100 hover:bg-slate-50 dark:hover:bg-slate-800/40"
                      >
                        <td className="py-2 px-3 font-medium">{ap.name}</td>
                        <td className="py-2 px-3">{ap.authType || "—"}</td>
                        <td className="py-2 px-3">
                          {ap.id ? (
                            count > 0 ? (
                              <Link
                                to={`/configuration/endpoints?authProfile=${encodeURIComponent(ap.id)}`}
                                className="inline-flex"
                              >
                                <StatusPill
                                  label={`Used by ${count}`}
                                  variant="configured"
                                  showIcon={false}
                                />
                              </Link>
                            ) : (
                              <span>
                                <StatusPill label="Unused" variant="neutral" />
                              </span>
                            )
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="py-2 px-3 text-gray-500">
                          {formatConfigDate(ap.updatedAt ?? ap.createdAt)}
                        </td>
                        <td className="py-2 px-3">
                          <StatusPill
                            label={ap.isActive !== false ? "Active" : "Inactive"}
                            variant={ap.isActive !== false ? "configured" : "neutral"}
                          />
                        </td>
                        <td className="py-2 px-3 text-right">
                          <button
                            type="button"
                            onClick={() => {
                              setEditingProfile(ap);
                              setProfileModalOpen(true);
                            }}
                            className="text-slate-600 hover:text-slate-800 text-xs font-medium"
                          >
                            Edit
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </FilterableTableShell>
          )}
        </CollapsiblePanel>
      </div>

      <AuthProfileModal
        open={profileModalOpen}
        onClose={() => {
          setProfileModalOpen(false);
          setEditingProfile(null);
        }}
        vendorCode={activeVendor ?? ""}
        initialValues={
          editingProfile
            ? {
                id: editingProfile.id ?? undefined,
                name: editingProfile.name ?? "",
                authType: editingProfile.authType ?? "API_KEY_HEADER",
                config: (editingProfile.config ?? {}) as Record<string, unknown>,
                isActive: editingProfile.isActive ?? true,
              }
            : null
        }
        onSave={async (payload) => {
          await upsertProfile.mutateAsync(payload);
        }}
        onDeactivate={
          editingProfile?.id
            ? async (id) => {
                await deleteProfile.mutateAsync(id);
              }
            : undefined
        }
      />
    </VendorPageLayout>
  );
}
