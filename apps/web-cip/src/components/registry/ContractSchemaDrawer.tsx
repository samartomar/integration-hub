import type { RegistryContract } from "../../types";

interface ContractSchemaDrawerProps {
  contract: RegistryContract | null;
  onClose: () => void;
}

export function ContractSchemaDrawer({ contract, onClose }: ContractSchemaDrawerProps) {
  if (!contract) return null;

  return (
    <>
      <div
        className="fixed inset-0 bg-black/30 z-40"
        aria-hidden
      />
      <div
        className="fixed right-0 top-0 bottom-0 w-full max-w-2xl bg-white shadow-xl z-50 flex flex-col overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-labelledby="schema-drawer-title"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50 shrink-0">
          <div>
            <h2 id="schema-drawer-title" className="font-semibold text-gray-900">
              Canonical contract · {contract.operationCode} ({contract.canonicalVersion ?? "v1"})
            </h2>
            <div className="mt-1 flex items-center gap-2 text-xs text-slate-600">
              <span>Canonical version: {contract.canonicalVersion ?? "v1"}</span>
              <span
                className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium ${
                  contract.isActive !== false ? "bg-emerald-100 text-emerald-800" : "bg-gray-100 text-gray-600"
                }`}
              >
                {contract.isActive !== false ? "Active" : "Inactive"}
              </span>
            </div>
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

        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          <div>
            <h3 className="text-sm font-semibold text-gray-700 mb-2">Request schema</h3>
            <pre className="text-xs text-gray-700 bg-gray-50 rounded-lg p-3 overflow-x-auto border border-gray-200">
              {contract.requestSchema != null && typeof contract.requestSchema === "object"
                ? JSON.stringify(contract.requestSchema, null, 2)
                : "—"}
            </pre>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-700 mb-2">Response schema</h3>
            <pre className="text-xs text-gray-700 bg-gray-50 rounded-lg p-3 overflow-x-auto border border-gray-200">
              {contract.responseSchema != null && typeof contract.responseSchema === "object"
                ? JSON.stringify(contract.responseSchema, null, 2)
                : "—"}
            </pre>
          </div>
        </div>
      </div>
    </>
  );
}
