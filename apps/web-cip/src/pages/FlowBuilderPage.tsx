import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  listFlowCanonicalOperations,
  getFlowCanonicalOperation,
  validateFlowDraft,
  generateFlowRuntimeHandoff,
  generateFlowRuntimeHandoffPreflight,
  type CanonicalOperationItem,
  type CanonicalOperationDetail,
  type FlowDraftValidateResult,
  type FlowRuntimeHandoffResponse,
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

export function FlowBuilderPage() {
  const [searchParams] = useSearchParams();
  const [selectedOp, setSelectedOp] = useState<CanonicalOperationItem | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState({
    name: "",
    sourceVendor: "",
    targetVendor: "",
    triggerType: "MANUAL" as "MANUAL" | "API",
    notes: "",
  });
  const [validateResult, setValidateResult] = useState<FlowDraftValidateResult | null>(null);
  const [validateError, setValidateError] = useState<string | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [payloadJson, setPayloadJson] = useState("{}");
  const [handoffResult, setHandoffResult] = useState<FlowRuntimeHandoffResponse | null>(null);
  const [handoffError, setHandoffError] = useState<string | null>(null);
  const [isGeneratingHandoff, setIsGeneratingHandoff] = useState(false);

  const { data: opsData, isLoading: opsLoading, error: opsError } = useQuery({
    queryKey: ["flow-canonical-operations"],
    queryFn: listFlowCanonicalOperations,
  });

  const { data: opDetail, isLoading: detailLoading } = useQuery({
    queryKey: ["flow-canonical-operation", selectedOp?.operationCode, selectedOp?.latestVersion],
    queryFn: () =>
      getFlowCanonicalOperation(selectedOp!.operationCode, selectedOp!.latestVersion),
    enabled: !!selectedOp,
  });

  const allItems = opsData?.items ?? [];
  useEffect(() => {
    const opCode = searchParams.get("operationCode");
    const src = searchParams.get("sourceVendor");
    const tgt = searchParams.get("targetVendor");
    if (src) setDraft((d) => ({ ...d, sourceVendor: src }));
    if (tgt) setDraft((d) => ({ ...d, targetVendor: tgt }));
    if (opCode && allItems.length > 0) {
      const op = allItems.find((o) => o.operationCode === opCode) ?? null;
      if (op) setSelectedOp(op);
    }
  }, [searchParams, allItems]);

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

  const handleValidate = useCallback(async () => {
    if (!selectedOp) return;
    setIsValidating(true);
    setValidateError(null);
    setValidateResult(null);
    try {
      const payload = {
        name: draft.name.trim(),
        operationCode: selectedOp.operationCode,
        version: selectedOp.latestVersion,
        sourceVendor: draft.sourceVendor.trim(),
        targetVendor: draft.targetVendor.trim(),
        trigger: { type: draft.triggerType },
        mappingMode: "CANONICAL_FIRST",
        notes: draft.notes.trim() || undefined,
      };
      const result = await validateFlowDraft(payload);
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
  }, [selectedOp, draft]);

  useEffect(() => {
    if (opDetail?.examples?.request && hasSelection) {
      setPayloadJson(JSON.stringify(opDetail.examples.request as Record<string, unknown>, null, 2));
    }
  }, [opDetail?.operationCode, opDetail?.examples?.request, hasSelection]);

  const handleGenerateHandoff = useCallback(
    async (runPreflight: boolean) => {
      if (!selectedOp) return;
      setIsGeneratingHandoff(true);
      setHandoffError(null);
      setHandoffResult(null);
      try {
        let payloadObj: Record<string, unknown> = {};
        try {
          payloadObj = JSON.parse(payloadJson);
        } catch {
          setHandoffError("Invalid JSON in canonical payload");
          return;
        }
        const req = {
          draft: {
            name: draft.name.trim(),
            operationCode: selectedOp.operationCode,
            version: selectedOp.latestVersion,
            sourceVendor: draft.sourceVendor.trim(),
            targetVendor: draft.targetVendor.trim(),
            trigger: { type: draft.triggerType },
            mappingMode: "CANONICAL_FIRST" as const,
            notes: draft.notes.trim() || undefined,
          },
          payload: Object.keys(payloadObj).length > 0 ? payloadObj : undefined,
          context: {},
        };
        const result = runPreflight
          ? await generateFlowRuntimeHandoffPreflight(req)
          : await generateFlowRuntimeHandoff(req);
        setHandoffResult(result);
      } catch (err: unknown) {
        const msg =
          err && typeof err === "object" && "response" in err
            ? (err as { response?: { data?: { error?: { message?: string } } } }).response?.data
                ?.error?.message ?? "Handoff request failed"
            : String(err);
        setHandoffError(msg);
      } finally {
        setIsGeneratingHandoff(false);
      }
    },
    [selectedOp, draft, payloadJson]
  );

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-gray-900">Flow Builder</h1>
      <p className="text-sm text-gray-600">
        Define canonical-driven flows. Select an operation, configure a draft, and validate.
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
              Select an operation to view contract context and define a flow draft.
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
                <h3 className="text-sm font-medium text-gray-900 mb-3">Draft Flow</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                  <div>
                    <label htmlFor="flow-name" className="block text-gray-700 mb-1">
                      Flow Name
                    </label>
                    <input
                      id="flow-name"
                      type="text"
                      value={draft.name}
                      onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
                      placeholder="e.g. Eligibility Check Flow"
                      className="w-full px-2 py-1.5 border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-slate-500"
                    />
                  </div>
                  <div>
                    <label htmlFor="source-vendor" className="block text-gray-700 mb-1">
                      Source Vendor
                    </label>
                    <input
                      id="source-vendor"
                      type="text"
                      value={draft.sourceVendor}
                      onChange={(e) => setDraft((d) => ({ ...d, sourceVendor: e.target.value }))}
                      placeholder="e.g. LH001"
                      className="w-full px-2 py-1.5 border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-slate-500"
                    />
                  </div>
                  <div>
                    <label htmlFor="target-vendor" className="block text-gray-700 mb-1">
                      Target Vendor
                    </label>
                    <input
                      id="target-vendor"
                      type="text"
                      value={draft.targetVendor}
                      onChange={(e) => setDraft((d) => ({ ...d, targetVendor: e.target.value }))}
                      placeholder="e.g. LH002"
                      className="w-full px-2 py-1.5 border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-slate-500"
                    />
                  </div>
                  <div>
                    <label htmlFor="trigger-type" className="block text-gray-700 mb-1">
                      Trigger Type
                    </label>
                    <select
                      id="trigger-type"
                      value={draft.triggerType}
                      onChange={(e) =>
                        setDraft((d) => ({
                          ...d,
                          triggerType: e.target.value as "MANUAL" | "API",
                        }))
                      }
                      className="w-full px-2 py-1.5 border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-slate-500"
                    >
                      <option value="MANUAL">MANUAL</option>
                      <option value="API">API</option>
                    </select>
                  </div>
                  <div className="sm:col-span-2">
                    <label htmlFor="mapping-mode" className="block text-gray-700 mb-1">
                      Mapping Mode
                    </label>
                    <input
                      id="mapping-mode"
                      type="text"
                      value="CANONICAL_FIRST"
                      readOnly
                      className="w-full px-2 py-1.5 border border-gray-200 rounded-md bg-gray-50 text-gray-600"
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label htmlFor="notes" className="block text-gray-700 mb-1">
                      Notes
                    </label>
                    <input
                      id="notes"
                      type="text"
                      value={draft.notes}
                      onChange={(e) => setDraft((d) => ({ ...d, notes: e.target.value }))}
                      placeholder="Optional"
                      className="w-full px-2 py-1.5 border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-slate-500"
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label htmlFor="payload-json" className="block text-gray-700 mb-1">
                      Canonical payload (JSON)
                    </label>
                    <textarea
                      id="payload-json"
                      value={payloadJson}
                      onChange={(e) => setPayloadJson(e.target.value)}
                      rows={8}
                      className="w-full px-2 py-1.5 text-sm font-mono border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-slate-500"
                      placeholder='{"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}'
                      spellCheck={false}
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      Prefilled from example when operation selected. Leave empty or use {"{}"} to use canonical example.
                    </p>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={handleValidate}
                    disabled={isValidating}
                    className="px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg"
                  >
                    {isValidating ? "Validating…" : "Validate Draft"}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleGenerateHandoff(false)}
                    disabled={isGeneratingHandoff}
                    className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 disabled:opacity-50 rounded-lg border border-slate-300"
                  >
                    {isGeneratingHandoff ? "Generating…" : "Generate Runtime Handoff"}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleGenerateHandoff(true)}
                    disabled={isGeneratingHandoff}
                    className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 disabled:opacity-50 rounded-lg border border-slate-300"
                  >
                    {isGeneratingHandoff ? "Generating…" : "Generate Handoff + Preflight"}
                  </button>
                </div>

                {validateError && (
                  <div className="mt-4 p-3 rounded-lg bg-red-50 border border-red-200">
                    <p className="text-sm font-medium text-red-800">Validation failed</p>
                    <p className="text-sm text-red-700 mt-1">{validateError}</p>
                  </div>
                )}
                {validateResult && (
                  <div className="mt-4 space-y-2">
                    <div
                      className={`p-3 rounded-lg border ${
                        validateResult.valid
                          ? "bg-green-50 border-green-200"
                          : "bg-amber-50 border-amber-200"
                      }`}
                    >
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
                              {typeof e === "string" ? e : `${e.field ? `${e.field}: ` : ""}${e.message}`}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                    {validateResult.valid && validateResult.normalizedDraft && (
                      <div>
                        <p className="text-xs font-medium text-gray-600 mb-1">
                          Normalized draft preview
                        </p>
                        <pre className="text-xs text-gray-700 bg-gray-50 rounded-lg p-3 overflow-x-auto border border-gray-200 font-mono">
                          {JSON.stringify(validateResult.normalizedDraft, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                )}

                {handoffError && (
                  <div className="mt-4 p-3 rounded-lg bg-red-50 border border-red-200">
                    <p className="text-sm font-medium text-red-800">Handoff failed</p>
                    <p className="text-sm text-red-700 mt-1">{handoffError}</p>
                  </div>
                )}
                {handoffResult && (
                  <div className="mt-4 p-4 rounded-lg border border-gray-200 bg-gray-50 space-y-3">
                    <h4 className="text-sm font-medium text-gray-900">Runtime Handoff Result</h4>
                    {handoffResult.canonicalExecutionPackage && (
                      <div>
                        <p className="text-xs font-medium text-gray-600 mb-1">Canonical execution package</p>
                        <pre className="text-xs text-gray-700 bg-white rounded-lg p-3 overflow-x-auto border border-gray-200 font-mono">
                          {JSON.stringify(handoffResult.canonicalExecutionPackage, null, 2)}
                        </pre>
                      </div>
                    )}
                    {handoffResult.preflight && (
                      <div>
                        {handoffResult.preflight.mappingSummary && (
                          <div className="mb-2 p-2 rounded-lg bg-slate-50 border border-slate-200 text-xs">
                            <span className="font-medium text-gray-700">Mapping:</span>{" "}
                            {handoffResult.preflight.mappingSummary.available
                              ? `${handoffResult.preflight.mappingSummary.fieldMappings ?? 0} field mappings, direction ${handoffResult.preflight.mappingSummary.direction ?? "—"}`
                              : "Not available"}
                          </div>
                        )}
                        <p className="text-xs font-medium text-gray-600 mb-1">Preflight</p>
                        <pre className="text-xs text-gray-700 bg-white rounded-lg p-3 overflow-x-auto border border-gray-200 font-mono">
                          {JSON.stringify(handoffResult.preflight, null, 2)}
                        </pre>
                      </div>
                    )}
                    {handoffResult.notes && handoffResult.notes.length > 0 && (
                      <ul className="text-xs text-gray-600 list-disc list-inside">
                        {handoffResult.notes.map((n, i) => (
                          <li key={i}>{n}</li>
                        ))}
                      </ul>
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
