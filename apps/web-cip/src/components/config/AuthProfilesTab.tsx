import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listAuthProfiles, upsertAuthProfile } from "../../api/endpoints";
import { getActiveVendorCode } from "../../utils/vendorStorage";
import { AuthProfileModal } from "./AuthProfileModal";

export function AuthProfilesTab() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const activeVendorCode = getActiveVendorCode();

  const { data } = useQuery({
    queryKey: ["auth-profiles", activeVendorCode ?? ""],
    queryFn: () => listAuthProfiles(activeVendorCode!),
    enabled: !!activeVendorCode,
    retry: false,
  });

  const upsert = useMutation({
    mutationFn: upsertAuthProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["auth-profiles", activeVendorCode ?? ""] });
    },
  });

  const authProfiles = data?.items ?? [];

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-800">Auth Profiles</h3>
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          className="px-3 py-1.5 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 rounded-lg"
        >
          New auth profile
        </button>
      </div>
      {authProfiles.length === 0 ? (
        <p className="text-sm text-gray-500 py-4">
          No auth profiles yet. Create one to link to endpoints (API key, bearer, or basic auth).
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b bg-gray-50">
                <th className="py-2 px-3">Name</th>
                <th className="py-2 px-3">Auth type</th>
                <th className="py-2 px-3">isActive</th>
                <th className="py-2 px-3">Created at</th>
              </tr>
            </thead>
            <tbody>
              {authProfiles.map((ap) => (
                <tr key={ap.id ?? ap.name} className="border-b border-gray-100">
                  <td className="py-2 px-3 font-medium">{ap.name}</td>
                  <td className="py-2 px-3">{ap.authType || "—"}</td>
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
                    {ap.createdAt ? new Date(ap.createdAt).toLocaleString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <AuthProfileModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        vendorCode={activeVendorCode ?? ""}
        onSave={async (payload) => {
          await upsert.mutateAsync(payload);
        }}
      />
    </div>
  );
}
