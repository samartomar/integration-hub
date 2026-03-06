import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getVendorOperationsCatalog,
  getVendorSupportedOperations,
  upsertVendorSupportedOperation,
} from "../../api/endpoints";

export function SupportedOpsTab() {
  const queryClient = useQueryClient();

  const { data: catalogData, isLoading: catalogLoading } = useQuery({
    queryKey: ["vendor-operations-catalog"],
    queryFn: getVendorOperationsCatalog,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
  });

  const { data: supportedData, isLoading: supportedLoading } = useQuery({
    queryKey: ["vendor-supported-operations"],
    queryFn: getVendorSupportedOperations,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
  });

  const upsert = useMutation({
    mutationFn: upsertVendorSupportedOperation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vendor-supported-operations"] });
    },
  });

  const catalog = catalogData?.items ?? [];
  const supported = supportedData?.items ?? [];
  const supportedCodes = new Set(supported.map((s) => s.operationCode));
  const availableToAdd = catalog.filter((c) => !supportedCodes.has(c.operationCode));

  const handleAdd = (operationCode: string) => {
    upsert.mutate({ operationCode, isActive: true });
  };

  const handleToggle = (item: { operationCode: string; isActive?: boolean }) => {
    upsert.mutate({
      operationCode: item.operationCode,
      isActive: item.isActive !== true,
    });
  };

  const isLoading = catalogLoading || supportedLoading;

  const noAdminApprovedOps = !isLoading && catalog.length === 0;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <label className="text-sm font-medium text-gray-700">Add operation</label>
        <select
          value=""
          onChange={(e) => {
            const v = e.target.value;
            if (v) {
              handleAdd(v);
              e.target.value = "";
            }
          }}
          disabled={isLoading || availableToAdd.length === 0 || upsert.isPending}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
        >
          <option value="">Select…</option>
          {availableToAdd.map((op) => (
            <option key={op.operationCode} value={op.operationCode}>
              {op.operationCode}
              {op.description ? ` — ${op.description}` : ""}
            </option>
          ))}
        </select>
        {noAdminApprovedOps && (
          <p className="text-sm text-amber-700">
            No admin-approved operations are available for this vendor.
          </p>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-10 bg-gray-100 rounded animate-pulse" />
          ))}
        </div>
      ) : noAdminApprovedOps ? (
        <p className="text-sm text-gray-500 py-4">
          No operations are available for configuration. This vendor does not have any admin-approved operations yet.
        </p>
      ) : supported.length === 0 ? (
        <p className="text-sm text-gray-500 py-4">No supported operations yet. Add one above.</p>
      ) : (
        <div className="space-y-2">
          {supported.map((item) => (
            <div
              key={item.operationCode}
              className="flex items-center justify-between py-2 px-3 rounded-lg bg-gray-50 border border-gray-200"
            >
              <span className="font-mono text-sm text-gray-800">{item.operationCode}</span>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={item.isActive !== false}
                  onChange={() => handleToggle(item)}
                  disabled={upsert.isPending}
                  className="rounded border-gray-300 text-slate-600 focus:ring-slate-500"
                />
                <span className="text-sm text-gray-600">Active</span>
              </label>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
