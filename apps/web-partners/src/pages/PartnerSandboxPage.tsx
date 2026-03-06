import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  listPartnerSyntegrisCanonicalOperations,
  getPartnerSyntegrisCanonicalOperation,
  validatePartnerSandboxRequest,
  runPartnerMockSandboxTest,
  type CanonicalOperationItem,
  type CanonicalOperationDetail,
  type SandboxValidateResponse,
  type SandboxMockRunResponse,
} from "../api/endpoints";

type TabId = "overview" | "request-schema" | "response-schema" | "examples";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "request-schema", label: "Request schema" },
  { id: "response-schema", label: "Response schema" },
  { id: "examples", label: "Examples" },
];

function JsonBlock({
  data,
  label,
}: {
  data: Record<string, unknown> | null;
  label?: string;
}) {
  const text = data ? JSON.stringify(data, null, 2) : "";
  if (!data || Object.keys(data).length === 0) {
    return <p className="text-sm text-gray-500 italic">—</p>;
  }
  return (
    <div>
      {label && <span className="text-xs font-medium text-gray-600 block mb-1">{label}</span>}
      <pre className="text-xs text-gray-700 bg-gray-50 rounded-lg p-4 overflow-x-auto border border-gray-200 font-mono">
        {text}
      </pre>
    </div>
  );
}

export function PartnerSandboxPage() {
  const [selectedOp, setSelectedOp] = useState<CanonicalOperationItem | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [search, setSearch] = useState("");
  const [requestPayload, setRequestPayload] = useState("{}");
  const [contextPayload, setContextPayload] = useState("{}");
  const [validateResult, setValidateResult] = useState<SandboxValidateResponse | null>(null);
  const [mockResult, setMockResult] = useState<SandboxMockRunResponse | null>(null);
  const [validateError, setValidateError] = useState<string | null>(null);
  const [mockError, setMockError] = useState<string | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [isRunningMock, setIsRunningMock] = useState(false);

  const { data: opsData, isLoading: opsLoading, error: opsError } = useQuery({
    queryKey: ["partner-syntegris-canonical-operations"],
    queryFn: listPartnerSyntegrisCanonicalOperations,
  });

  const { data: opDetail, isLoading: detailLoading } = useQuery({
    queryKey: ["partner-syntegris-canonical-operation", selectedOp?.operationCode, selectedOp?.latestVersion],
    queryFn: () =>
      getPartnerSyntegrisCanonicalOperation(selectedOp!.operationCode, selectedOp!.latestVersion),
    enabled: !!selectedOp,
  });

  const allItems = opsData?.items ?? [];
  const items = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return allItems;
    return allItems.filter(
      (op) =>
        (op.operationCode ?? "").toLowerCase().includes(q) ||
        (op.title ?? "").toLowerCase().includes(q)
    );
  }, [allItems, search]);
  const hasSelection = !!selectedOp;

  useEffect(() => {
    if (opDetail?.examples?.request) {
      setRequestPayload(JSON.stringify(opDetail.examples.request, null, 2));
    }
  }, [opDetail?.operationCode, opDetail?.examples?.request]);

  const handleValidate = useCallback(async () => {
    if (!selectedOp) return;
    setIsValidating(true);
    setValidateError(null);
    setValidateResult(null);
    try {
      let payload: Record<string, unknown>;
      try {
        payload = JSON.parse(requestPayload);
      } catch {
        setValidateError("Invalid JSON in request payload");
        return;
      }
      const result = await validatePartnerSandboxRequest({
        operationCode: selectedOp.operationCode,
        version: selectedOp.latestVersion,
        payload,
      });
      setValidateResult(result);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { error?: { message?: string } } } }).response?.data
              ?.error?.message ?? "Validation request failed"
          : String(err);
      setValidateError(msg);
    } finally {
      setIsValidating(false);
    }
  }, [selectedOp, requestPayload]);

  const handleRunMock = useCallback(async () => {
    if (!selectedOp) return;
    setIsRunningMock(true);
    setMockError(null);
    setMockResult(null);
    try {
      let payload: Record<string, unknown>;
      try {
        payload = JSON.parse(requestPayload);
      } catch {
        setMockError("Invalid JSON in request payload");
        return;
      }
      let context: Record<string, unknown> = {};
      try {
        if (contextPayload.trim()) context = JSON.parse(contextPayload);
      } catch {
        setMockError("Invalid JSON in context");
        return;
      }
      const result = await runPartnerMockSandboxTest({
        operationCode: selectedOp.operationCode,
        version: selectedOp.latestVersion,
        payload,
        context: Object.keys(context).length ? context : undefined,
      });
      setMockResult(result);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { error?: { message?: string } } } }).response?.data
              ?.error?.message ?? "Mock run failed"
          : String(err);
      setMockError(msg);
    } finally {
      setIsRunningMock(false);
    }
  }, [selectedOp, requestPayload, contextPayload]);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-gray-900">Sandbox</h1>
      <p className="text-sm text-gray-600">
        Test canonical operations safely with mock execution. No vendor endpoints are called.
      </p>

      <div className="flex flex-col lg:flex-row gap-4">
        <div className="w-full lg:w-64 shrink-0">
          <h2 className="text-sm font-medium text-gray-700 mb-2">Operations</h2>
          {opsLoading && <p className="text-sm text-gray-500">Loading…</p>}
          {opsError && (
            <p className="text-sm text-red-600">
              Failed to load operations. Check your connection.
            </p>
          )}
          {!opsLoading && !opsError && items.length === 0 && (
            <p className="text-sm text-gray-500">No canonical operations registered.</p>
          )}
          {!opsLoading && allItems.length > 0 && (
            <>
              <input
                type="search"
                placeholder="Search by code or title…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full mb-2 px-2 py-1.5 text-sm border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-slate-500"
                aria-label="Search operations"
              />
              <ul className="border border-gray-200 rounded-lg divide-y divide-gray-200 bg-white">
                {items.length === 0 ? (
                  <li className="px-3 py-4 text-sm text-gray-500 text-center">
                    No operations match your search.
                  </li>
                ) : (
                  items.map((op) => (
                    <li key={op.operationCode}>
                      <button
                        type="button"
                        onClick={() => setSelectedOp(op)}
                        className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 ${
                          selectedOp?.operationCode === op.operationCode
                            ? "bg-slate-100 text-slate-900 font-medium"
                            : "text-gray-700"
                        }`}
                      >
                        {op.title ?? op.operationCode}
                        <span className="block text-xs text-gray-500">
                          {op.operationCode}
                          {op.latestVersion ? ` · ${op.latestVersion}` : ""}
                        </span>
                      </button>
                    </li>
                  ))
                )}
              </ul>
            </>
          )}
        </div>

        <div className="flex-1 min-w-0 space-y-4">
          {!hasSelection && (
            <div className="border border-gray-200 rounded-lg p-8 bg-gray-50 text-center text-gray-500 text-sm">
              Select an operation to test request shape and run mock execution.
            </div>
          )}
          {hasSelection && (
            <>
              <div>
                <h2 className="text-lg font-medium text-gray-900 mb-2">
                  {opDetail?.title ?? selectedOp!.operationCode} ({selectedOp!.latestVersion})
                </h2>
                {opDetail?.description && (
                  <p className="text-sm text-gray-600 mb-3">{opDetail.description}</p>
                )}
              </div>

              <div className="border border-gray-200 rounded-lg overflow-hidden bg-white">
                <div className="flex border-b border-gray-200">
                  {TABS.map(({ id, label }) => (
                    <button
                      key={id}
                      type="button"
                      onClick={() => setActiveTab(id)}
                      className={`px-4 py-2 text-sm font-medium ${
                        activeTab === id
                          ? "bg-slate-100 text-slate-900 border-b-2 border-slate-600"
                          : "text-gray-600 hover:bg-gray-50"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <div className="p-4">
                  {detailLoading && <p className="text-sm text-gray-500">Loading details…</p>}
                  {!detailLoading && opDetail && (
                    <>
                      {activeTab === "overview" && (
                        <div className="space-y-4 text-sm">
                          <div>
                            <h3 className="font-medium text-gray-700 mb-1">Metadata</h3>
                            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-gray-600">
                              <dt>Operation:</dt>
                              <dd className="font-mono">{opDetail.operationCode}</dd>
                              <dt>Version:</dt>
                              <dd>{opDetail.version}</dd>
                              {opDetail.versionAliases?.length ? (
                                <>
                                  <dt>Aliases:</dt>
                                  <dd>{opDetail.versionAliases.join(", ")}</dd>
                                </>
                              ) : null}
                            </dl>
                          </div>
                        </div>
                      )}
                      {activeTab === "request-schema" && (
                        <JsonBlock
                          data={opDetail.requestPayloadSchema as Record<string, unknown>}
                          label="Request payload schema"
                        />
                      )}
                      {activeTab === "response-schema" && (
                        <JsonBlock
                          data={opDetail.responsePayloadSchema as Record<string, unknown>}
                          label="Response payload schema"
                        />
                      )}
                      {activeTab === "examples" && (
                        <div className="space-y-4">
                          <JsonBlock
                            data={opDetail.examples?.request ?? null}
                            label="Request payload"
                          />
                          <JsonBlock
                            data={opDetail.examples?.response ?? null}
                            label="Response payload"
                          />
                          <JsonBlock
                            data={
                              (opDetail.examples?.requestEnvelope as Record<string, unknown>) ??
                              null
                            }
                            label="Request envelope"
                          />
                          <JsonBlock
                            data={
                              (opDetail.examples?.responseEnvelope as Record<string, unknown>) ??
                              null
                            }
                            label="Response envelope"
                          />
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>

              <div className="border border-gray-200 rounded-lg p-4 bg-white">
                <h3 className="text-sm font-medium text-gray-900 mb-3">Request payload</h3>
                <textarea
                  value={requestPayload}
                  onChange={(e) => setRequestPayload(e.target.value)}
                  rows={8}
                  className="w-full px-2 py-1.5 text-sm font-mono border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-slate-500"
                  placeholder='{"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}'
                  aria-label="Request payload JSON"
                />
                <div className="mt-2">
                  <label htmlFor="context-json" className="block text-xs text-gray-600 mb-1">
                    Context (optional JSON)
                  </label>
                  <textarea
                    id="context-json"
                    value={contextPayload}
                    onChange={(e) => setContextPayload(e.target.value)}
                    rows={2}
                    className="w-full px-2 py-1.5 text-sm font-mono border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-slate-500"
                    placeholder="{}"
                    aria-label="Context JSON"
                  />
                </div>
                <div className="mt-4 flex gap-2">
                  <button
                    type="button"
                    onClick={handleValidate}
                    disabled={isValidating}
                    className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-200 hover:bg-slate-300 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg"
                  >
                    {isValidating ? "Validating…" : "Validate Request"}
                  </button>
                  <button
                    type="button"
                    onClick={handleRunMock}
                    disabled={isRunningMock}
                    className="px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg"
                  >
                    {isRunningMock ? "Running…" : "Run Mock Test"}
                  </button>
                </div>

                {validateError && (
                  <div className="mt-4 p-3 rounded-lg bg-red-50 border border-red-200">
                    <p className="text-sm font-medium text-red-800">Validation failed</p>
                    <p className="text-sm text-red-700 mt-1">{validateError}</p>
                  </div>
                )}
                {validateResult && (
                  <div className="mt-4 p-3 rounded-lg border bg-gray-50 border-gray-200">
                    <p
                      className={`text-sm font-medium ${
                        validateResult.valid ? "text-green-800" : "text-amber-800"
                      }`}
                    >
                      {validateResult.valid ? "Valid" : "Invalid"}
                    </p>
                    {validateResult.errors?.length ? (
                      <ul className="text-sm text-amber-700 mt-1 list-disc list-inside">
                        {validateResult.errors.map((e, i) => (
                          <li key={i}>
                            {e.field}: {e.message}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                )}

                {mockError && (
                  <div className="mt-4 p-3 rounded-lg bg-red-50 border border-red-200">
                    <p className="text-sm font-medium text-red-800">Mock run failed</p>
                    <p className="text-sm text-red-700 mt-1">{mockError}</p>
                  </div>
                )}
                {mockResult && (
                  <div className="mt-4 space-y-3">
                    <div
                      className={`p-3 rounded-lg border ${
                        mockResult.valid
                          ? "bg-green-50 border-green-200"
                          : "bg-amber-50 border-amber-200"
                      }`}
                    >
                      <p className="text-sm font-medium">
                        {mockResult.valid ? "Pass" : "Fail"} · mode={mockResult.mode}
                      </p>
                      {mockResult.notes?.length ? (
                        <ul className="text-sm text-gray-700 mt-1">
                          {mockResult.notes.map((n, i) => (
                            <li key={i}>{n}</li>
                          ))}
                        </ul>
                      ) : null}
                      {mockResult.errors?.length ? (
                        <ul className="text-sm text-amber-700 mt-1 list-disc list-inside">
                          {mockResult.errors.map((e, i) => (
                            <li key={i}>
                              {e.field}: {e.message}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                    {mockResult.requestEnvelope && (
                      <JsonBlock
                        data={mockResult.requestEnvelope}
                        label="Request envelope"
                      />
                    )}
                    {mockResult.responseEnvelope && (
                      <JsonBlock
                        data={mockResult.responseEnvelope}
                        label="Response envelope"
                      />
                    )}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
