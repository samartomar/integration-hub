import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getVendorContracts, upsertVendorContract } from "../../api/endpoints";
import type { VendorContract } from "../../types";
import { VendorContractModal } from "./VendorContractModal";

export function ContractsTab() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<VendorContract | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["vendor-contracts"],
    queryFn: getVendorContracts,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
  });

  const upsert = useMutation({
    mutationFn: upsertVendorContract,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vendor-contracts"] });
    },
  });

  const contracts = data?.items ?? [];

  const handleSave = async (payload: {
    operationCode: string;
    canonicalVersion?: string;
    requestSchema?: Record<string, unknown>;
    responseSchema?: Record<string, unknown>;
    isActive?: boolean;
  }) => {
    await upsert.mutateAsync(payload);
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-800">My Contracts</h3>
        <button
          type="button"
          onClick={() => {
            setEditing(null);
            setModalOpen(true);
          }}
          className="px-3 py-1.5 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 rounded-lg"
        >
          Add Contract
        </button>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-10 bg-gray-100 rounded animate-pulse" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-amber-600">Unable to load contracts.</p>
      ) : contracts.length === 0 ? (
        <p className="text-sm text-gray-500 py-4">No contracts yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b">
                <th className="py-2">Operation</th>
                <th className="py-2">Version</th>
                <th className="py-2">Active</th>
                <th className="py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {contracts.map((c) => (
                <tr key={c.operationCode} className="border-b border-gray-100">
                  <td className="py-2 font-mono">{c.operationCode}</td>
                  <td className="py-2 text-gray-700">{c.canonicalVersion ?? "—"}</td>
                  <td className="py-2">
                    <span
                      className={`px-2 py-0.5 rounded text-xs ${
                        c.isActive !== false ? "bg-emerald-100 text-emerald-800" : "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {c.isActive !== false ? "Yes" : "No"}
                    </span>
                  </td>
                  <td className="py-2 text-right">
                    <button
                      type="button"
                      onClick={() => {
                        setEditing(c);
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

      <VendorContractModal
        open={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        initialValues={editing}
        onSave={handleSave}
      />
    </div>
  );
}
