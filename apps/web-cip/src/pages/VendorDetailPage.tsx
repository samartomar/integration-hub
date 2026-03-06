import { useState, useMemo } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listVendors,
  listEndpoints,
  listAuthProfiles,
  listContracts,
  listAllowlist,
  listOperations,
  getReadiness,
  adminUpsertContract,
  upsertEndpoint,
  upsertAuthProfile,
  upsertVendor,
  listTransactions,
  deleteAuthProfile,
  type ListRegistryResponse,
} from "../api/endpoints";
import type { Vendor, Endpoint, RegistryContract } from "../types";
import type { AuthProfile } from "../api/endpoints";
import type { ReadinessItem } from "../api/endpoints";
import { ContractModal } from "../components/registry/ContractModal";
import { ContractSchemaDrawer } from "../components/registry/ContractSchemaDrawer";
import { EndpointModal } from "../components/registry/EndpointModal";
import { RegistryAuthProfileModal } from "../components/registry/RegistryAuthProfileModal";
import { ModalShell } from "../components/registry/ModalShell";
import { TransactionDetailDrawer } from "../components/TransactionDetailDrawer";
import { usePhiAccess } from "../security/PhiAccessContext";

type TabId = "overview" | "endpoints" | "authProfiles" | "contracts" | "mappings" | "debug";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "endpoints", label: "Endpoints" },
  { id: "authProfiles", label: "Auth Profiles" },
  { id: "contracts", label: "Contracts" },
  { id: "mappings", label: "Mappings" },
  { id: "debug", label: "Debug" },
];

function useVendorHealth(vendorCode: string) {
  const { data: endpoints } = useQuery({
    queryKey: ["registry-endpoints", vendorCode],
    queryFn: () => listEndpoints({ vendorCode }),
    enabled: !!vendorCode,
  });
  const { data: readiness } = useQuery({
    queryKey: ["registry-readiness", vendorCode],
    queryFn: () => getReadiness(vendorCode),
    enabled: !!vendorCode,
  });
  const ops = useMemo(() => {
    const epOps = new Set((endpoints?.items ?? []).map((e) => e.operationCode));
    const rdOps = (readiness?.items ?? []) as ReadinessItem[];
    return { epOps, rdOps };
  }, [endpoints, readiness]);
  const unverifiedCount = (endpoints?.items ?? []).filter(
    (e) => e.verificationStatus !== "VERIFIED"
  ).length;
  const missingMappingCount = (ops.rdOps ?? []).filter(
    (r) => !r.overallOk && r.checks?.some((c) => c.name === "mappings_present" && !c.ok)
  ).length;
  const supportedOps = ops.epOps.size;
  return {
    unverifiedCount,
    missingMappingCount,
    supportedOps,
    hasWarnings: unverifiedCount > 0 || missingMappingCount > 0,
  };
}

export function VendorDetailPage() {
  const { phiModeEnabled, reason } = usePhiAccess();
  const { vendorCode } = useParams<{ vendorCode: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [vendorSearch, setVendorSearch] = useState("");
  const [contractModalOpen, setContractModalOpen] = useState(false);
  const [schemaDrawerContract, setSchemaDrawerContract] = useState<RegistryContract | null>(null);
  const [endpointModalOpen, setEndpointModalOpen] = useState(false);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [editingEndpoint, setEditingEndpoint] = useState<Endpoint | null>(null);
  const [editingAuth, setEditingAuth] = useState<AuthProfile | null>(null);

  const contractUpsert = useMutation({
    mutationFn: adminUpsertContract,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["registry-contracts"] });
      queryClient.invalidateQueries({ queryKey: ["registry-readiness"] });
    },
  });
  const endpointUpsert = useMutation({
    mutationFn: upsertEndpoint,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["registry-endpoints"] });
      queryClient.invalidateQueries({ queryKey: ["registry-readiness"] });
    },
  });
  const authUpsert = useMutation({
    mutationFn: upsertAuthProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["registry-auth-profiles"] });
    },
  });
  const vendorUpsert = useMutation({
    mutationFn: upsertVendor,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["registry-vendors"] });
    },
  });

  const [activateConfirmOpen, setActivateConfirmOpen] = useState(false);
  const [debugTransactionId, setDebugTransactionId] = useState<string | null>(null);

  const { data: vendorsData } = useQuery<ListRegistryResponse<Vendor>>({
    queryKey: ["registry-vendors"],
    queryFn: () => listVendors(),
  });
  const vendors = vendorsData?.items ?? [];
  const filteredVendors = useMemo(() => {
    if (!vendorSearch.trim()) return vendors;
    const q = vendorSearch.trim().toLowerCase();
    return vendors.filter(
      (v) =>
        v.vendorName?.toLowerCase().includes(q) ||
        v.vendorCode?.toLowerCase().includes(q)
    );
  }, [vendors, vendorSearch]);

  const currentVendor = vendors.find((v) => v.vendorCode === vendorCode);

  const { data: authProfilesData } = useQuery({
    queryKey: ["registry-auth-profiles", vendorCode],
    queryFn: () => listAuthProfiles(vendorCode),
    enabled: !!vendorCode,
  });
  const authProfiles = authProfilesData?.items ?? [];

  if (!vendorCode) {
    return (
      <div className="p-6">
        <p className="text-amber-600">No vendor selected.</p>
        <Link to="/admin/registry" className="text-slate-600 hover:underline mt-2 inline-block">
          ← Back to Registry
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col lg:flex-row min-h-0 flex-1">
      {/* Sidebar - hidden on mobile, shown on lg+ */}
      <aside className="hidden lg:flex w-64 shrink-0 border-r border-gray-200 bg-gray-50 flex-col">
        <div className="p-3 border-b border-gray-200">
          <input
            type="text"
            placeholder="Filter vendors…"
            value={vendorSearch}
            onChange={(e) => setVendorSearch(e.target.value)}
            className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
          />
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {filteredVendors.map((v) => (
            <VendorSidebarRow
              key={v.vendorCode}
              vendor={v}
              isActive={v.vendorCode === vendorCode}
              onSelect={() => navigate(`/admin/registry/vendors/${v.vendorCode}`)}
            />
          ))}
          {filteredVendors.length === 0 && (
            <p className="text-sm text-gray-500 px-2 py-4">No vendors match.</p>
          )}
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto p-4 sm:p-6 min-w-0">
        {/* Mobile vendor selector - shown when sidebar hidden */}
        <div className="lg:hidden mb-4">
          <label htmlFor="vendor-select-mobile" className="block text-xs font-medium text-slate-500 mb-1">
            Licensee
          </label>
          <select
            id="vendor-select-mobile"
            value={vendorCode}
            onChange={(e) => navigate(`/admin/registry/vendors/${e.target.value}`)}
            className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg min-h-[44px] focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
          >
            {filteredVendors.map((v) => (
              <option key={v.vendorCode} value={v.vendorCode}>
                {v.vendorName ?? v.vendorCode}
              </option>
            ))}
          </select>
        </div>
        <div className="mb-3 flex items-center justify-between gap-4">
          <Link
            to="/admin/registry"
            className="text-slate-600 hover:text-slate-800 text-sm shrink-0"
          >
            ← Registry
          </Link>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4 pb-3 border-b border-gray-200">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-xl font-bold text-gray-900">
              {currentVendor?.vendorCode ?? vendorCode}
            </h1>
            <span className="text-gray-500 text-sm">
              {currentVendor?.vendorName ?? "—"}
            </span>
            <span
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                currentVendor?.isActive !== false
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-gray-100 text-gray-600"
              }`}
            >
              {currentVendor?.isActive !== false ? "Active" : "Inactive"}
            </span>
          </div>
          {currentVendor && (
            <button
              type="button"
              onClick={() => setActivateConfirmOpen(true)}
              disabled={vendorUpsert.isPending}
              className={`px-3 py-1.5 text-sm font-medium rounded-lg shrink-0 ${
                currentVendor.isActive !== false
                  ? "text-amber-700 bg-amber-100 hover:bg-amber-200"
                  : "text-emerald-700 bg-emerald-100 hover:bg-emerald-200"
              }`}
            >
              {currentVendor.isActive !== false
                ? "Deactivate licensee"
                : "Activate licensee"}
            </button>
          )}
        </div>

        <div className="border-b border-gray-200 mb-4 overflow-x-auto -mx-px">
          <nav className="flex gap-2 sm:gap-4 min-w-max">
            {TABS.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                onClick={() => setActiveTab(id)}
                className={`py-3 px-1 border-b-2 font-medium text-sm whitespace-nowrap min-h-[44px] sm:min-h-0 flex items-center ${
                  activeTab === id
                    ? "border-slate-600 text-slate-600"
                    : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
                }`}
              >
                {label}
              </button>
            ))}
          </nav>
        </div>

        {activeTab === "overview" && (
          <VendorOverviewTab vendorCode={vendorCode} currentVendor={currentVendor} />
        )}
        {activeTab === "endpoints" && (
          <VendorEndpointsTab
            vendorCode={vendorCode}
            authProfiles={authProfiles}
            onEdit={(ep) => {
              setEditingEndpoint(ep);
              setEndpointModalOpen(true);
            }}
            onAdd={() => {
              setEditingEndpoint(null);
              setEndpointModalOpen(true);
            }}
          />
        )}
        {activeTab === "authProfiles" && (
          <VendorAuthProfilesTab
            vendorCode={vendorCode}
            onEdit={(ap) => {
              setEditingAuth(ap);
              setAuthModalOpen(true);
            }}
            onAdd={() => {
              setEditingAuth(null);
              setAuthModalOpen(true);
            }}
            onDeactivate={async (ap) => {
              if (ap.id) await deleteAuthProfile(ap.id);
              queryClient.invalidateQueries({ queryKey: ["registry-auth-profiles"] });
            }}
          />
        )}
        {activeTab === "contracts" && (
          <VendorContractsTab
            vendorCode={vendorCode}
            onAddContract={() => setContractModalOpen(true)}
            onViewSchema={(c) => setSchemaDrawerContract(c)}
          />
        )}
        {activeTab === "mappings" && <VendorMappingsTab vendorCode={vendorCode} />}
        {activeTab === "debug" && (
          <VendorDebugTab
            vendorCode={vendorCode}
            onSelectTransaction={(id) => setDebugTransactionId(id)}
          />
        )}
      </main>

      <ContractModal
        open={contractModalOpen}
        onClose={() => setContractModalOpen(false)}
        initialValues={null}
        onSave={async (payload) => {
          await contractUpsert.mutateAsync(payload);
          setContractModalOpen(false);
        }}
      />
      <ContractSchemaDrawer
        contract={schemaDrawerContract}
        onClose={() => setSchemaDrawerContract(null)}
      />
      <EndpointModal
        open={endpointModalOpen}
        onClose={() => {
          setEndpointModalOpen(false);
          setEditingEndpoint(null);
        }}
        initialValues={editingEndpoint}
        defaultVendorCode={vendorCode}
        authProfiles={authProfiles}
        onSave={async (payload) => {
          await endpointUpsert.mutateAsync(payload);
          setEndpointModalOpen(false);
          setEditingEndpoint(null);
        }}
      />
      <RegistryAuthProfileModal
        open={authModalOpen}
        onClose={() => {
          setAuthModalOpen(false);
          setEditingAuth(null);
        }}
        initialValues={editingAuth ?? (vendorCode ? { vendorCode, name: "", authType: "API_KEY_HEADER" } : null)}
        vendors={vendors}
        onSave={async (payload) => {
          await authUpsert.mutateAsync(payload);
          setAuthModalOpen(false);
          setEditingAuth(null);
        }}
        authTypeHints={{
          API_KEY_HEADER: "Sends a static value in a header, e.g. Api-Key.",
          API_KEY_QUERY: "Appends a static query param, e.g. ?api_key=...",
          STATIC_BEARER: "Sends a static bearer token in the Authorization header.",
        }}
      />

      <ModalShell
        open={activateConfirmOpen}
        onClose={() => setActivateConfirmOpen(false)}
        title={
          currentVendor?.isActive !== false
            ? `Deactivate licensee ${vendorCode}?`
            : `Activate licensee ${vendorCode}?`
        }
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            {currentVendor?.isActive !== false
              ? `This will temporarily disable ${vendorCode} from calling or being called. All configurations remain preserved.`
              : `This will re-enable ${vendorCode} to call and be called.`}
          </p>
          <div className="flex gap-2 pt-2 justify-end">
            <button
              type="button"
              onClick={() => setActivateConfirmOpen(false)}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={async () => {
                if (!currentVendor) return;
                await vendorUpsert.mutateAsync({
                  vendor_code: currentVendor.vendorCode,
                  vendor_name: currentVendor.vendorName,
                  is_active: currentVendor.isActive === false,
                });
                setActivateConfirmOpen(false);
              }}
              disabled={vendorUpsert.isPending}
              className={`px-4 py-2 text-sm font-medium text-white rounded-lg ${
                currentVendor?.isActive !== false
                  ? "bg-amber-600 hover:bg-amber-700"
                  : "bg-emerald-600 hover:bg-emerald-700"
              }`}
            >
              {vendorUpsert.isPending ? "Updating…" : "Confirm"}
            </button>
          </div>
        </div>
      </ModalShell>

      <TransactionDetailDrawer
        transactionId={debugTransactionId}
        vendorCode={vendorCode}
        expandSensitive={phiModeEnabled}
        sensitiveReason={reason}
        onClose={() => setDebugTransactionId(null)}
      />
    </div>
  );
}

function VendorSidebarRow({
  vendor,
  isActive,
  onSelect,
}: {
  vendor: Vendor;
  isActive: boolean;
  onSelect: () => void;
}) {
  const health = useVendorHealth(vendor.vendorCode ?? "");
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full text-left px-3 py-2 rounded-lg mb-1 ${
        isActive ? "bg-slate-100 text-slate-900 font-medium" : "hover:bg-gray-100 text-gray-700"
      }`}
    >
      <div className="flex items-center justify-between gap-1">
        <span className="truncate font-medium">{vendor.vendorName ?? vendor.vendorCode}</span>
        {health.hasWarnings && (
          <span className="shrink-0 text-amber-600" title="Unverified endpoints or missing mappings">
            ❗
          </span>
        )}
      </div>
      <div className="text-xs text-gray-500 font-mono mt-0.5">{vendor.vendorCode}</div>
      <div className="flex flex-wrap gap-1 mt-1">
        <span className="px-1.5 py-0.5 rounded text-xs bg-slate-100 text-slate-700">
          {health.supportedOps} ops
        </span>
        {health.unverifiedCount > 0 && (
          <span className="px-1.5 py-0.5 rounded text-xs bg-amber-100 text-amber-800">
            {health.unverifiedCount} unverified
          </span>
        )}
        {health.missingMappingCount > 0 && (
          <span className="px-1.5 py-0.5 rounded text-xs bg-amber-100 text-amber-800">
            {health.missingMappingCount} missing map
          </span>
        )}
      </div>
    </button>
  );
}

function VendorOverviewTab({
  vendorCode,
  currentVendor,
}: {
  vendorCode: string;
  currentVendor?: Vendor | null;
}) {
  const { data: endpoints } = useQuery({
    queryKey: ["registry-endpoints", vendorCode],
    queryFn: () => listEndpoints({ vendorCode }),
  });
  const { data: authProfiles } = useQuery({
    queryKey: ["registry-auth-profiles", vendorCode],
    queryFn: () => listAuthProfiles(vendorCode),
  });
  const { data: contracts } = useQuery({
    queryKey: ["registry-contracts"],
    queryFn: () => listContracts(),
  });
  const { data: allowlist } = useQuery({
    queryKey: ["registry-allowlist", vendorCode],
    queryFn: () => listAllowlist({ vendorCode }),
  });
  const { data: readiness } = useQuery({
    queryKey: ["registry-readiness", vendorCode],
    queryFn: () => getReadiness(vendorCode),
  });
  const { data: transactionsData } = useQuery({
    queryKey: ["transactions", vendorCode, "recent"],
    queryFn: () =>
      listTransactions({
        vendorCode,
        limit: 5,
      }),
    enabled: !!vendorCode,
  });

  const eps = endpoints?.items ?? [];
  const verifiedCount = eps.filter((e) => e.verificationStatus === "VERIFIED").length;
  const opsSet = new Set(eps.map((e) => e.operationCode));
  const vendorContracts = (contracts?.items ?? []).filter((c) =>
    opsSet.has(c.operationCode)
  );
  const profiles = authProfiles?.items ?? [];
  const mappingsFromReadiness = (readiness?.items ?? []) as ReadinessItem[];
  const missingFromCanonical = mappingsFromReadiness.flatMap((r) => {
    const m = r.checks?.find((c) => c.name === "mappings_present" && !c.ok);
    return (m?.details?.missing as string[] ?? []).filter((d) => d === "FROM_CANONICAL");
  }).length;
  const missingToCanonical = mappingsFromReadiness.flatMap((r) => {
    const m = r.checks?.find((c) => c.name === "mappings_present" && !c.ok);
    return (m?.details?.missing as string[] ?? []).filter((d) => d === "TO_CANONICAL");
  }).length;
  const unverifiedCount = eps.length - verifiedCount;
  const recentTx = transactionsData?.transactions ?? [];

  const formatDate = (s: string | undefined) => {
    if (!s) return "—";
    try {
      return new Date(s).toLocaleString();
    } catch {
      return s;
    }
  };

  return (
    <div className="space-y-6">
      {/* Basic info card */}
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="text-sm font-semibold text-gray-800 mb-3">Basic info</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <div>
            <span className="text-gray-500">Code</span>
            <div className="font-mono font-medium">{vendorCode}</div>
          </div>
          <div>
            <span className="text-gray-500">Name</span>
            <div>{currentVendor?.vendorName ?? "—"}</div>
          </div>
          <div>
            <span className="text-gray-500">Created</span>
            <div>{formatDate(currentVendor?.createdAt)}</div>
          </div>
          <div>
            <span className="text-gray-500">Updated</span>
            <div>{formatDate(currentVendor?.updatedAt)}</div>
          </div>
          <div>
            <span className="text-gray-500">Status</span>
            <span
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                currentVendor?.isActive !== false
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-gray-100 text-gray-600"
              }`}
            >
              {currentVendor?.isActive !== false ? "Active" : "Inactive"}
            </span>
          </div>
        </div>
      </div>

      {/* Capabilities card */}
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="text-sm font-semibold text-gray-800 mb-3">Capabilities</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <SummaryCard title="Supported operations" value={opsSet.size} />
          <SummaryCard title="Endpoints configured" value={eps.length} />
          <SummaryCard title="Auth profiles defined" value={profiles.length} />
          <SummaryCard title="Verified endpoints" value={`${verifiedCount} / ${eps.length}`} />
          <SummaryCard title="Contracts (canonical)" value={vendorContracts.length} />
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="text-sm text-gray-500">Allowlist</div>
            <div className="text-2xl font-semibold text-gray-900 mt-1 flex items-center gap-2 flex-wrap">
              <span>{allowlist?.items?.length ?? 0}</span>
              <Link
                to={`/admin/registry?tab=allowlist&source=${encodeURIComponent(vendorCode)}&perspective=caller`}
                className="text-sm font-normal text-slate-600 hover:text-slate-900 underline underline-offset-1"
              >
                View access rules →
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* Recent activity */}
      {recentTx.length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <h3 className="text-sm font-semibold text-gray-800 mb-3">Recent activity</h3>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b">
                  <th className="py-2">Time</th>
                  <th className="py-2">Operation</th>
                  <th className="py-2">Source → Target</th>
                  <th className="py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {recentTx.map((tx) => (
                  <tr key={tx.transaction_id} className="border-b border-gray-100">
                    <td className="py-2 text-gray-600">{formatDate(tx.created_at)}</td>
                    <td className="py-2 font-mono">{tx.operation ?? "—"}</td>
                    <td className="py-2">
                      {tx.source_vendor ?? "—"} → {tx.target_vendor ?? "—"}
                    </td>
                    <td className="py-2">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                          tx.status === "completed"
                            ? "bg-emerald-100 text-emerald-700"
                            : tx.status === "failed" || (tx.status ?? "").includes("error")
                              ? "bg-red-100 text-red-700"
                              : "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {tx.status ?? "—"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {recentTx.length === 0 && (
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <h3 className="text-sm font-semibold text-gray-800 mb-2">Recent activity</h3>
          <p className="text-sm text-gray-500">No recent transactions for this licensee.</p>
        </div>
      )}

      {(missingFromCanonical > 0 || missingToCanonical > 0 || unverifiedCount > 0) && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <h3 className="font-medium text-amber-900 mb-2">Status Warnings</h3>
          <ul className="space-y-1 text-sm text-amber-800">
            {missingFromCanonical > 0 && (
              <li>• Missing FROM_CANONICAL mappings</li>
            )}
            {missingToCanonical > 0 && (
              <li>• Missing TO_CANONICAL mappings</li>
            )}
            {unverifiedCount > 0 && (
              <li>• {unverifiedCount} unverified endpoint(s)</li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

function SummaryCard({ title, value }: { title: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="text-sm text-gray-500">{title}</div>
      <div className="text-2xl font-semibold text-gray-900 mt-1">{value}</div>
    </div>
  );
}

function VendorContractsTab({
  vendorCode,
  onAddContract,
  onViewSchema,
}: {
  vendorCode: string;
  onAddContract: () => void;
  onViewSchema: (c: RegistryContract) => void;
}) {
  const [opFilter, setOpFilter] = useState("");
  const [activeFilter, setActiveFilter] = useState<boolean | null>(null);
  const [search, setSearch] = useState("");

  const { data: endpoints } = useQuery({
    queryKey: ["registry-endpoints", vendorCode],
    queryFn: () => listEndpoints({ vendorCode }),
  });
  const { data: contractsData } = useQuery({
    queryKey: ["registry-contracts"],
    queryFn: () => listContracts(),
  });
  const { data: opsData } = useQuery({
    queryKey: ["registry-operations"],
    queryFn: () => listOperations(),
  });

  const ops = opsData?.items ?? [];
  const vendorOps = new Set((endpoints?.items ?? []).map((e) => e.operationCode));
  let contracts = (contractsData?.items ?? []).filter((c) => vendorOps.has(c.operationCode));
  if (opFilter) contracts = contracts.filter((c) => c.operationCode === opFilter);
  if (activeFilter !== null) contracts = contracts.filter((c) => (c.isActive !== false) === activeFilter);
  if (search.trim()) {
    const q = search.trim().toLowerCase();
    contracts = contracts.filter(
      (c) =>
        c.operationCode?.toLowerCase().includes(q) ||
        (c.canonicalVersion ?? "").toLowerCase().includes(q)
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 items-center">
        <select
          value={opFilter}
          onChange={(e) => setOpFilter(e.target.value)}
          className="px-2 py-1.5 text-sm border border-gray-300 rounded"
        >
          <option value="">All operations</option>
          {ops.map((o) => (
            <option key={o.operationCode} value={o.operationCode}>
              {o.operationCode}
            </option>
          ))}
        </select>
        <select
          value={activeFilter === null ? "" : String(activeFilter)}
          onChange={(e) =>
            setActiveFilter(e.target.value === "" ? null : e.target.value === "true")
          }
          className="px-2 py-1.5 text-sm border border-gray-300 rounded"
        >
          <option value="">All</option>
          <option value="true">Active</option>
          <option value="false">Inactive</option>
        </select>
        <input
          type="text"
          placeholder="Search operation_code, canonical_version…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="px-2 py-1.5 text-sm border border-gray-300 rounded min-w-[200px]"
        />
        <button
          type="button"
          onClick={onAddContract}
          className="px-3 py-1.5 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 rounded-lg"
        >
          Add contract
        </button>
      </div>
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left text-gray-500 border-b">
              <th className="py-2 px-3">Operation</th>
              <th className="py-2 px-3">Canonical Version</th>
              <th className="py-2 px-3">Active</th>
              <th className="py-2 px-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {contracts.map((c) => (
              <tr key={`${c.operationCode}-${c.canonicalVersion}`} className="border-b border-gray-100">
                <td className="py-2 px-3 font-mono">{c.operationCode}</td>
                <td className="py-2 px-3">{c.canonicalVersion ?? "—"}</td>
                <td className="py-2 px-3">
                  <span
                    className={`px-2 py-0.5 rounded text-xs ${
                      c.isActive !== false ? "bg-emerald-100 text-emerald-800" : "bg-gray-100 text-gray-600"
                    }`}
                  >
                    {c.isActive !== false ? "Yes" : "No"}
                  </span>
                </td>
                <td className="py-2 px-3 text-right">
                  <button
                    type="button"
                    onClick={() => onViewSchema(c)}
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
      {contracts.length === 0 && (
        <p className="text-sm text-gray-500 py-4">No contracts for this vendor.</p>
      )}
    </div>
  );
}

function VendorEndpointsTab({
  vendorCode,
  authProfiles,
  onEdit,
  onAdd,
}: {
  vendorCode: string;
  authProfiles: AuthProfile[];
  onEdit: (ep: Endpoint) => void;
  onAdd: () => void;
}) {
  const [verifiedFilter, setVerifiedFilter] = useState<string>("");
  const [opFilter, setOpFilter] = useState("");

  const { data: endpoints } = useQuery({
    queryKey: ["registry-endpoints", vendorCode],
    queryFn: () => listEndpoints({ vendorCode }),
  });
  const { data: opsData } = useQuery({
    queryKey: ["registry-operations"],
    queryFn: () => listOperations(),
  });

  let eps = endpoints?.items ?? [];
  if (verifiedFilter === "verified") eps = eps.filter((e) => e.verificationStatus === "VERIFIED");
  if (verifiedFilter === "unverified") eps = eps.filter((e) => e.verificationStatus !== "VERIFIED");
  if (opFilter) eps = eps.filter((e) => e.operationCode === opFilter);

  const ops = opsData?.items ?? [];
  const authProfileByName = (id: string | null | undefined) =>
    id ? authProfiles.find((ap) => ap.id === id)?.name ?? "—" : "—";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 items-center">
        <select
          value={verifiedFilter}
          onChange={(e) => setVerifiedFilter(e.target.value)}
          className="px-2 py-1.5 text-sm border border-gray-300 rounded-lg"
        >
          <option value="">All</option>
          <option value="verified">Verified</option>
          <option value="unverified">Unverified</option>
        </select>
        <select
          value={opFilter}
          onChange={(e) => setOpFilter(e.target.value)}
          className="px-2 py-1.5 text-sm border border-gray-300 rounded-lg"
        >
          <option value="">All operations</option>
          {ops.map((o) => (
            <option key={o.operationCode} value={o.operationCode}>
              {o.operationCode}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={onAdd}
          className="px-3 py-1.5 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 rounded-lg"
        >
          Add endpoint
        </button>
      </div>
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left text-gray-500 border-b">
              <th className="py-2 px-3">Operation</th>
              <th className="py-2 px-3">URL</th>
              <th className="py-2 px-3">HTTP method</th>
              <th className="py-2 px-3">Auth profile</th>
              <th className="py-2 px-3">Verification</th>
              <th className="py-2 px-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {eps.map((ep) => (
              <tr key={`${ep.vendorCode}-${ep.operationCode}`} className="border-b border-gray-100">
                <td className="py-2 px-3 font-mono">{ep.operationCode}</td>
                <td className="py-2 px-3 truncate max-w-[200px]" title={ep.url}>
                  {ep.url}
                </td>
                <td className="py-2 px-3">{ep.httpMethod ?? "—"}</td>
                <td className="py-2 px-3">{authProfileByName(ep.authProfileId)}</td>
                <td className="py-2 px-3">
                  <span
                    className={`px-2 py-0.5 rounded text-xs ${
                      ep.verificationStatus === "VERIFIED"
                        ? "bg-emerald-100 text-emerald-800"
                        : "bg-amber-100 text-amber-800"
                    }`}
                  >
                    {ep.verificationStatus ?? "—"}
                  </span>
                </td>
                <td className="py-2 px-3 text-right">
                  <button
                    type="button"
                    onClick={() => onEdit(ep)}
                    className="text-slate-600 hover:text-slate-800 text-xs font-medium"
                  >
                    Edit
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function VendorMappingsTab({ vendorCode }: { vendorCode: string }) {
  const { data: readiness } = useQuery({
    queryKey: ["registry-readiness", vendorCode],
    queryFn: () => getReadiness(vendorCode),
  });
  const items = (readiness?.items ?? []) as ReadinessItem[];

  const fromCanonical = items.filter((r) => {
    const m = r.checks?.find((c) => c.name === "mappings_present");
    const missing = (m?.details?.missing as string[] ?? []) as string[];
    return !missing.includes("FROM_CANONICAL");
  });
  const toCanonical = items.filter((r) => {
    const m = r.checks?.find((c) => c.name === "mappings_present");
    const missing = (m?.details?.missing as string[] ?? []) as string[];
    return !missing.includes("TO_CANONICAL");
  });
  const missingFrom = items.filter((r) => {
    const m = r.checks?.find((c) => c.name === "mappings_present");
    return m && !m.ok && (m.details?.missing as string[] ?? []).includes("FROM_CANONICAL");
  });
  const missingTo = items.filter((r) => {
    const m = r.checks?.find((c) => c.name === "mappings_present");
    return m && !m.ok && (m.details?.missing as string[] ?? []).includes("TO_CANONICAL");
  });

  return (
    <div className="space-y-6">
      <div>
        <h3 className="font-medium text-gray-900 mb-2">FROM_CANONICAL mappings</h3>
        <ul className="space-y-1 text-sm">
          {fromCanonical.map((r) => (
            <li key={r.operationCode} className="text-gray-700">
              • {r.operationCode} — present
            </li>
          ))}
          {missingFrom.map((r) => (
            <li key={r.operationCode} className="text-amber-700">
              • {r.operationCode} — missing
            </li>
          ))}
          {items.length === 0 && <li className="text-gray-500">No operations configured.</li>}
        </ul>
      </div>
      <div>
        <h3 className="font-medium text-gray-900 mb-2">TO_CANONICAL mappings</h3>
        <ul className="space-y-1 text-sm">
          {toCanonical.map((r) => (
            <li key={r.operationCode} className="text-gray-700">
              • {r.operationCode} — present
            </li>
          ))}
          {missingTo.map((r) => (
            <li key={r.operationCode} className="text-amber-700">
              • {r.operationCode} — missing
            </li>
          ))}
          {items.length === 0 && <li className="text-gray-500">No operations configured.</li>}
        </ul>
      </div>
    </div>
  );
}

function VendorDebugTab({
  vendorCode,
  onSelectTransaction,
}: {
  vendorCode: string;
  onSelectTransaction: (transactionId: string) => void;
}) {
  const { data: txData, isLoading } = useQuery({
    queryKey: ["transactions-debug", vendorCode],
    queryFn: () =>
      listTransactions({
        vendorCode,
        limit: 10,
      }),
    enabled: !!vendorCode,
  });

  const transactions = txData?.transactions ?? [];

  const formatDate = (s: string | undefined) => {
    if (!s) return "—";
    try {
      return new Date(s).toLocaleString();
    } catch {
      return s;
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-600">
        Most recent 10 transactions where this licensee is source or target. Click a row to open the debug view.
      </p>
      {isLoading ? (
        <div className="animate-pulse space-y-2">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-10 bg-gray-100 rounded" />
          ))}
        </div>
      ) : transactions.length === 0 ? (
        <p className="text-sm text-gray-500 py-4">No transactions found.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left text-gray-500 border-b">
                <th className="py-2 px-3">Time</th>
                <th className="py-2 px-3">Source</th>
                <th className="py-2 px-3">Target</th>
                <th className="py-2 px-3">Operation</th>
                <th className="py-2 px-3">Status</th>
                <th className="py-2 px-3">Error</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((tx) => (
                <tr
                  key={tx.transaction_id}
                  className="border-b border-gray-100 cursor-pointer hover:bg-slate-50"
                  onClick={() => onSelectTransaction(tx.transaction_id)}
                >
                  <td className="py-2 px-3 text-gray-600">{formatDate(tx.created_at)}</td>
                  <td className="py-2 px-3 font-mono">{tx.source_vendor ?? "—"}</td>
                  <td className="py-2 px-3 font-mono">{tx.target_vendor ?? "—"}</td>
                  <td className="py-2 px-3 font-mono">{tx.operation ?? "—"}</td>
                  <td className="py-2 px-3">
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                        tx.status === "completed"
                          ? "bg-emerald-100 text-emerald-700"
                          : tx.status === "failed" || (tx.status ?? "").includes("error")
                            ? "bg-red-100 text-red-700"
                            : "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {tx.status ?? "—"}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-red-600 text-xs">
                    {(tx as { error_code?: string }).error_code ?? tx.errorCode ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function VendorAuthProfilesTab({
  vendorCode,
  onEdit,
  onAdd,
  onDeactivate,
}: {
  vendorCode: string;
  onEdit: (ap: AuthProfile) => void;
  onAdd: () => void;
  onDeactivate: (ap: AuthProfile) => Promise<void>;
}) {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["registry-auth-profiles", vendorCode],
    queryFn: () => listAuthProfiles(vendorCode),
  });
  const { data: endpoints } = useQuery({
    queryKey: ["registry-endpoints", vendorCode],
    queryFn: () => listEndpoints({ vendorCode }),
  });
  const profiles = data?.items ?? [];
  const eps = endpoints?.items ?? [];

  const usage = useMemo(() => {
    const m: Record<string, number> = {};
    eps.forEach((e) => {
      const aid = e.authProfileId;
      if (aid) m[aid] = (m[aid] ?? 0) + 1;
    });
    return m;
  }, [eps]);

  const formatDate = (s: string | undefined) => {
    if (!s) return "—";
    try {
      return new Date(s).toLocaleString();
    } catch {
      return s;
    }
  };

  const handleDeactivate = async (ap: AuthProfile) => {
    await onDeactivate(ap);
    queryClient.invalidateQueries({ queryKey: ["registry-auth-profiles", vendorCode] });
  };

  return (
    <div className="space-y-4">
      <button
        type="button"
        onClick={onAdd}
        className="px-3 py-1.5 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 rounded-lg"
      >
        Add auth profile
      </button>
      {isLoading ? (
        <div className="animate-pulse space-y-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-10 bg-gray-100 rounded" />
          ))}
        </div>
      ) : profiles.length === 0 ? (
        <p className="text-sm text-gray-500 py-4">No auth profiles.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left text-gray-500 border-b">
                <th className="py-2 px-3">Name</th>
                <th className="py-2 px-3">Auth Type</th>
                <th className="py-2 px-3">Active</th>
                <th className="py-2 px-3">Created / Updated</th>
                <th className="py-2 px-3">Used by endpoints</th>
                <th className="py-2 px-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {profiles.map((ap) => (
                <tr key={ap.id ?? ap.name} className="border-b border-gray-100">
                  <td className="py-2 px-3">{ap.name}</td>
                  <td className="py-2 px-3 font-mono">{ap.authType}</td>
                  <td className="py-2 px-3">
                    <span
                      className={`px-2 py-0.5 rounded text-xs ${
                        ap.isActive !== false
                          ? "bg-emerald-100 text-emerald-700"
                          : "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {ap.isActive !== false ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-gray-500 text-xs">
                    {formatDate(ap.createdAt)} / {formatDate(ap.updatedAt)}
                  </td>
                  <td className="py-2 px-3">{usage[ap.id ?? ""] ?? 0}</td>
                  <td className="py-2 px-3 text-right space-x-2">
                    {ap.isActive !== false && ap.id && (
                      <button
                        type="button"
                        onClick={() => handleDeactivate(ap)}
                        className="text-amber-600 hover:text-amber-800 text-xs font-medium"
                      >
                        Deactivate
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => onEdit(ap)}
                      className="text-slate-600 hover:text-slate-800 text-xs font-medium"
                    >
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
