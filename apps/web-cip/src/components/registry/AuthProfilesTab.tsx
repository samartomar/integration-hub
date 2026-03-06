import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listVendors,
  listAuthProfiles,
  upsertAuthProfile,
  deleteAuthProfile,
  type ListRegistryResponse,
} from "../../api/endpoints";
import type { Vendor } from "../../types";
import type { AuthProfile } from "../../api/endpoints";
import { RegistryAuthProfileModal } from "./RegistryAuthProfileModal";

const AUTH_TYPE_HINTS: Record<string, string> = {
  API_KEY_HEADER: "Sends a static value in a header, e.g. Api-Key.",
  API_KEY_QUERY: "Appends a static query param, e.g. ?api_key=...",
  BASIC: "Uses Authorization: Basic <base64(username:password)>.",
  BEARER: "Sends Authorization: Bearer <token>.",
  JWT_BEARER_TOKEN: "Fetches OAuth client-credentials token and sends Bearer token.",
  MTLS: "Uses client certificate and private key for TLS client auth.",
};

export function AuthProfilesTab() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<AuthProfile | null>(null);
  const [vendorFilter, setVendorFilter] = useState<string>("");
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const { data: vendorsData } = useQuery<ListRegistryResponse<Vendor>>({
    queryKey: ["registry-vendors"],
    queryFn: () => listVendors(),
  });

  const { data, isLoading, error } = useQuery({
    queryKey: ["registry-auth-profiles", vendorFilter],
    queryFn: () => listAuthProfiles(vendorFilter.trim() || undefined),
  });

  const upsert = useMutation({
    mutationFn: upsertAuthProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["registry-auth-profiles"] });
      setSuccessMsg("Auth profile saved.");
      setTimeout(() => setSuccessMsg(null), 3000);
    },
  });

  const del = useMutation({
    mutationFn: deleteAuthProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["registry-auth-profiles"] });
      setSuccessMsg("Auth profile deactivated.");
      setTimeout(() => setSuccessMsg(null), 3000);
    },
  });

  const profiles = data?.items ?? [];
  const vendors = vendorsData?.items ?? [];

  const handleSave = async (payload: {
    id?: string;
    vendorCode: string;
    name: string;
    authType: string;
    config?: Record<string, unknown>;
    isActive?: boolean;
  }) => {
    await upsert.mutateAsync(payload);
  };

  const handleDeactivate = async (ap: AuthProfile) => {
    if (ap.id) await del.mutateAsync(ap.id);
  };

  return (
    <div className="space-y-4">
      {successMsg && (
        <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-2 text-sm text-emerald-800">
          {successMsg}
        </div>
      )}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
          <h3 className="text-sm font-semibold text-gray-800">Auth Profiles</h3>
          <div className="flex gap-2 items-center">
            <select
              value={vendorFilter}
              onChange={(e) => setVendorFilter(e.target.value)}
              className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm"
            >
              <option value="">All vendors</option>
              {vendors.map((v) => (
                <option key={v.vendorCode} value={v.vendorCode}>
                  {v.vendorCode}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => {
                setEditing(null);
                setModalOpen(true);
              }}
              className="px-3 py-1.5 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 rounded-lg"
            >
              Create
            </button>
          </div>
        </div>

        {isLoading ? (
          <div className="space-y-2">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-6 bg-gray-100 rounded animate-pulse" />
            ))}
          </div>
        ) : error ? (
          <p className="text-sm text-amber-600">Unable to load auth profiles.</p>
        ) : profiles.length === 0 ? (
          <p className="text-sm text-gray-500 py-4">No auth profiles.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b bg-gray-50">
                  <th className="py-2 px-3">Vendor</th>
                  <th className="py-2 px-3">Name</th>
                  <th className="py-2 px-3">Auth type</th>
                  <th className="py-2 px-3">Active</th>
                  <th className="py-2 px-3">Last updated</th>
                  <th className="py-2 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {profiles.map((ap) => (
                  <tr key={ap.id ?? ap.name} className="border-b border-gray-100">
                    <td className="py-2 px-3 font-mono">{ap.vendorCode}</td>
                    <td className="py-2 px-3 font-medium">{ap.name}</td>
                    <td className="py-2 px-3">{ap.authType}</td>
                    <td className="py-2 px-3">
                      <span
                        className={`px-2 py-0.5 rounded text-xs ${
                          ap.isActive !== false
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {ap.isActive !== false ? "Yes" : "No"}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-gray-500">
                      {ap.updatedAt ? new Date(ap.updatedAt).toLocaleString() : "—"}
                    </td>
                    <td className="py-2 px-3 text-right space-x-2">
                      {ap.isActive !== false && ap.id && (
                        <button
                          type="button"
                          onClick={() => handleDeactivate(ap)}
                          disabled={del.isPending}
                          className="text-amber-600 hover:text-amber-800 text-sm font-medium"
                        >
                          Deactivate
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => {
                          setEditing(ap);
                          setModalOpen(true);
                        }}
                        className="text-slate-600 hover:text-slate-900 text-sm font-medium"
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

      <RegistryAuthProfileModal
        open={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        initialValues={editing}
        vendors={vendors}
        onSave={handleSave}
        authTypeHints={AUTH_TYPE_HINTS}
      />
    </div>
  );
}
