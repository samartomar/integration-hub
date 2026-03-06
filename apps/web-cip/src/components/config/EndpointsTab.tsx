import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getVendorEndpoints,
  getVendorSupportedOperations,
  upsertVendorEndpoint,
  verifyVendorEndpoint,
  listAuthProfiles,
} from "../../api/endpoints";
import { getActiveVendorCode } from "../../utils/vendorStorage";
import type { VendorEndpoint } from "../../types";
import { VendorEndpointModal } from "./VendorEndpointModal";

export function EndpointsTab() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<VendorEndpoint | null>(null);
  const [verifyResult, setVerifyResult] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["vendor-endpoints"],
    queryFn: getVendorEndpoints,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
  });

  const activeVendorCode = getActiveVendorCode();

  const { data: supportedData } = useQuery({
    queryKey: ["vendor-supported-operations"],
    queryFn: getVendorSupportedOperations,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
  });

  const { data: authProfilesData } = useQuery({
    queryKey: ["auth-profiles", activeVendorCode ?? ""],
    queryFn: () => listAuthProfiles(activeVendorCode!),
    enabled: !!activeVendorCode,
    retry: false,
  });
  const authProfiles = (authProfilesData?.items ?? []).filter((ap) => ap.isActive !== false);

  const upsert = useMutation({
    mutationFn: upsertVendorEndpoint,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vendor-endpoints"] });
    },
  });

  const verify = useMutation({
    mutationFn: verifyVendorEndpoint,
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["vendor-endpoints"] });
      const r = res.endpoint?.verificationResult;
      if (r) {
        const msg =
          r.status === "VERIFIED"
            ? `Verified (HTTP ${r.httpStatus ?? "—"})`
            : `Failed: ${r.responseSnippet ?? r.status}`;
        setVerifyResult(msg);
        setTimeout(() => setVerifyResult(null), 4000);
      }
    },
  });

  const endpoints = data?.items ?? [];
  const supportedOperationCodes = (supportedData?.items ?? []).map((s) => s.operationCode);

  const handleSave = async (payload: {
    operationCode: string;
    url: string;
    httpMethod?: string;
    payloadFormat?: string;
    timeoutMs?: number;
    isActive?: boolean;
    authProfileId?: string | null;
    verificationRequest?: Record<string, unknown> | null;
  }) => {
    await upsert.mutateAsync(payload);
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-800">My Endpoints</h3>
        <button
          type="button"
          onClick={() => {
            setEditing(null);
            setModalOpen(true);
          }}
          className="px-3 py-1.5 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 rounded-lg"
        >
          Add Endpoint
        </button>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-10 bg-gray-100 rounded animate-pulse" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-amber-600">Unable to load endpoints.</p>
      ) : endpoints.length === 0 ? (
        <p className="text-sm text-gray-500 py-4">No endpoints yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b">
                <th className="py-2">Operation</th>
                <th className="py-2">URL</th>
                <th className="py-2">Method</th>
                <th className="py-2">Verification</th>
                <th className="py-2">Active</th>
                <th className="py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {endpoints.map((ep) => (
                <tr key={ep.operationCode} className="border-b border-gray-100">
                  <td className="py-2 font-mono">{ep.operationCode}</td>
                  <td className="py-2 text-gray-700 truncate max-w-[200px]" title={ep.url}>
                    {ep.url}
                  </td>
                  <td className="py-2">{ep.httpMethod ?? "POST"}</td>
                  <td className="py-2">
                    <div className="space-y-1">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-xs ${
                          ep.verificationStatus === "VERIFIED"
                            ? "bg-emerald-100 text-emerald-800"
                            : ep.verificationStatus === "FAILED"
                              ? "bg-red-100 text-red-800"
                              : "bg-amber-100 text-amber-800"
                        }`}
                      >
                        {ep.verificationStatus ?? "PENDING"}
                      </span>
                      {ep.lastVerifiedAt && (
                        <div className="text-xs text-gray-500">
                          {new Date(ep.lastVerifiedAt).toLocaleString()}
                        </div>
                      )}
                      {ep.lastVerificationError && (
                        <div className="text-xs text-red-600 truncate max-w-[180px]" title={ep.lastVerificationError}>
                          {ep.lastVerificationError}
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="py-2">
                    <span
                      className={`px-2 py-0.5 rounded text-xs ${
                        ep.isActive !== false ? "bg-emerald-100 text-emerald-800" : "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {ep.isActive !== false ? "Yes" : "No"}
                    </span>
                  </td>
                  <td className="py-2 text-right space-x-2">
                    <button
                      type="button"
                      onClick={() => verify.mutate({ operationCode: ep.operationCode })}
                      disabled={
                        verify.isPending && verify.variables?.operationCode === ep.operationCode
                      }
                      className="text-slate-600 hover:text-slate-900 text-sm font-medium disabled:opacity-50"
                    >
                      {verify.isPending && verify.variables?.operationCode === ep.operationCode
                        ? "Verifying…"
                        : "Verify"}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setEditing(ep);
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

      {verifyResult && (
        <div className="mb-4 px-4 py-2 rounded-lg bg-slate-100 text-slate-800 text-sm">
          {verifyResult}
        </div>
      )}

      <VendorEndpointModal
        open={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        initialValues={editing}
        supportedOperationCodes={supportedOperationCodes}
        authProfiles={authProfiles}
        onSave={handleSave}
      />
    </div>
  );
}
