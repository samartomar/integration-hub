import type { PerVendorSummary } from "./OperationsDashboard";

interface OperationDetailDrawerProps {
  operationCode: string | null;
  perVendorSummaries: PerVendorSummary[];
  onClose: () => void;
}

export function OperationDetailDrawer({
  operationCode,
  perVendorSummaries,
  onClose,
}: OperationDetailDrawerProps) {
  const isOpen = !!operationCode;

  if (!isOpen) return null;

  return (
    <>
      <div
        className="fixed inset-0 bg-black/30 z-40"
        aria-hidden="true"
      />
      <div
        className="fixed right-0 top-0 bottom-0 w-full max-w-lg bg-white shadow-xl z-50 flex flex-col"
        role="dialog"
        aria-modal="true"
        aria-labelledby="operation-drawer-title"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          <h2 id="operation-drawer-title" className="text-lg font-semibold text-gray-900">
            {operationCode} — Config by vendor
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-2 text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-100"
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {perVendorSummaries.length === 0 ? (
            <p className="text-sm text-gray-500">No vendors configured for this operation.</p>
          ) : (
            <div className="space-y-4">
              {perVendorSummaries.map((vs) => (
                <div
                  key={vs.vendorCode}
                  className="rounded-lg border border-gray-200 p-4 space-y-2"
                >
                  <h3 className="font-medium text-gray-900 font-mono">{vs.vendorCode}</h3>
                  <dl className="text-sm space-y-1">
                    <div className="flex justify-between">
                      <dt className="text-gray-500">Endpoint</dt>
                      <dd className="font-mono text-gray-700 truncate max-w-[200px]" title={vs.endpointUrl}>
                        {vs.endpointUrl ?? "—"}
                      </dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-gray-500">Verified</dt>
                      <dd>
                        <span
                          className={`px-2 py-0.5 rounded text-xs ${
                            vs.verificationStatus === "VERIFIED"
                              ? "bg-emerald-100 text-emerald-800"
                              : "bg-amber-100 text-amber-800"
                          }`}
                        >
                          {vs.verificationStatus ?? "—"}
                        </span>
                      </dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-gray-500">FROM_CANONICAL</dt>
                      <dd>
                        {vs.hasFromMapping ? (
                          <span className="text-emerald-600">✓</span>
                        ) : (
                          <span className="text-amber-600">Missing</span>
                        )}
                      </dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-gray-500">TO_CANONICAL</dt>
                      <dd>
                        {vs.hasToMapping ? (
                          <span className="text-emerald-600">✓</span>
                        ) : (
                          <span className="text-amber-600">Missing</span>
                        )}
                      </dd>
                    </div>
                  </dl>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
