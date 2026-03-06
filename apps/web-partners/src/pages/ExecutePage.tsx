import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  executeAiIntegration,
  getVendorSupportedOperations,
  getVendorOperationsCatalog,
  getMyOperations,
  getVendorContracts,
  getMyAllowlist,
  listVendors,
  listContracts,
  previewPolicy,
} from "../api/endpoints";
import { useVendorConfigBundle } from "../hooks/useVendorConfigBundle";
import { vendorCanonicalContractsKey, STALE_CONFIG } from "../api/queryKeys";
import {
  getActiveVendorCode,
  buildSkeletonFromSchema,
  buildExecuteSelectionModel,
} from "frontend-shared";
import { VendorPageLayout } from "../components/layout/VendorPageLayout";
import { PolicyExplainPanel } from "../components/PolicyExplainPanel";

function generateIdempotencyKey(): string {
  return `poc-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

function parseParametersJson(value: string): Record<string, unknown> | null {
  const trimmed = value.trim();
  if (!trimmed) return {};
  try {
    const parsed = JSON.parse(trimmed);
    if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}

export function ExecutePage() {
  const [searchParams] = useSearchParams();
  const [targetVendor, setTargetVendor] = useState("");
  const [operation, setOperation] = useState("");
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [aiFormatter, setAiFormatter] = useState(false);
  const [parametersText, setParametersText] = useState("{}");
  const [parametersError, setParametersError] = useState<string | null>(null);
  const [schemaInfo, setSchemaInfo] = useState<{
    operationCode: string;
    canonicalVersion: string;
    source: "vendor" | "canonical" | null;
  } | null>(null);
  const [schemaWarning, setSchemaWarning] = useState<string | null>(null);

  const activeVendor = getActiveVendorCode();
  const hasActiveVendor = !!activeVendor;

  // Operations: vendor supported + catalog (vendor API)
  const { data: supportedData } = useQuery({
    queryKey: ["vendor-supported-operations"],
    queryFn: getVendorSupportedOperations,
    enabled: !!activeVendor,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: catalogData, isLoading: catalogLoading } = useQuery({
    queryKey: ["vendor-operations-catalog"],
    queryFn: getVendorOperationsCatalog,
    enabled: !!activeVendor,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });

  // Allowlist for target dropdown: prefer config-bundle (single source), fallback to my-allowlist
  const { data: bundleData, isLoading: bundleLoading } = useVendorConfigBundle(!!activeVendor);
  const { data: myAllowlistData, isLoading: allowlistDirectLoading } = useQuery({
    queryKey: ["my-allowlist", activeVendor ?? ""],
    queryFn: getMyAllowlist,
    enabled: !!activeVendor && !bundleData?.myAllowlist,
    retry: false,
    staleTime: STALE_CONFIG,
  });
  const { data: myOperationsData, isLoading: myOperationsDirectLoading } = useQuery({
    queryKey: ["my-operations", activeVendor ?? ""],
    queryFn: getMyOperations,
    enabled: !!activeVendor && !bundleData?.myOperations,
    retry: false,
    staleTime: STALE_CONFIG,
  });
  const { data: vendorsData, isLoading: vendorsLoading } = useQuery({
    queryKey: ["vendor-canonical-vendors"],
    queryFn: () => listVendors({ limit: 500 }),
    enabled: !!activeVendor,
    retry: false,
    staleTime: STALE_CONFIG,
  });

  const allowlist = bundleData?.myAllowlist ?? myAllowlistData;
  const myOperations = bundleData?.myOperations ?? myOperationsData;
  const allowlistOutbound = allowlist?.outbound ?? [];
  const outboundReadiness = myOperations?.outbound ?? [];
  const allowlistLoading =
    (bundleLoading && !bundleData) ||
    (!!activeVendor && !bundleData?.myAllowlist && allowlistDirectLoading);
  const myOperationsLoading =
    (bundleLoading && !bundleData) ||
    (!!activeVendor && !bundleData?.myOperations && myOperationsDirectLoading);
  const selectionLoading = allowlistLoading || myOperationsLoading || vendorsLoading;

  // Vendor contracts for schema (vendor API)
  const { data: vendorContractsData } = useQuery({
    queryKey: ["vendor-contracts"],
    queryFn: getVendorContracts,
    enabled: !!activeVendor,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });

  // Canonical contracts (Vendor API proxy) - fetched when operation selected and no vendor schema
  const selectedOp = operation.trim() || null;
  const catalogItem = catalogData?.items?.find((c) => c.operationCode === selectedOp);
  const canonicalVersion = catalogItem?.canonicalVersion ?? "v1";
  const { data: canonicalContractsData } = useQuery({
    queryKey: vendorCanonicalContractsKey(selectedOp ?? undefined, canonicalVersion),
    queryFn: () =>
      listContracts({
        operationCode: selectedOp ?? "",
        canonicalVersion,
        isActive: true,
      }),
    enabled: !!selectedOp && hasActiveVendor,
    retry: false,
    staleTime: STALE_CONFIG,
  });

  const supportedOps = supportedData?.items ?? [];
  const catalog = catalogData?.items ?? [];
  const allVendorCodes = (vendorsData?.items ?? [])
    .map((v) => String(v.vendorCode ?? "").trim().toUpperCase())
    .filter(Boolean);
  const selectionModel = buildExecuteSelectionModel({
    activeVendorCode: activeVendor ?? "",
    catalog,
    supportedOperations: supportedOps,
    outboundAllowlist: allowlistOutbound,
    outboundReadiness,
    allVendorCodes,
  });
  const operationsForDropdown = selectionModel.operations;
  const selectedOperationMeta = operationsForDropdown.find((o) => o.operationCode === operation) ?? null;
  const aiModeLabel = (() => {
    const mode = (selectedOperationMeta?.aiPresentationMode ?? "RAW_ONLY").toUpperCase();
    if (mode === "RAW_AND_FORMATTED") return "AI: Raw + summary";
    if (mode === "FORMAT_ONLY") return "AI: Summary only";
    return "AI: Off";
  })();
  const targetsForSelectedOperation =
    selectionModel.targetsByOperation[(operation || "").trim().toUpperCase()] ?? [];

  const vendorContracts = vendorContractsData?.items ?? [];
  const canonicalContracts = canonicalContractsData?.items ?? [];
  const vendorContract = selectedOp
    ? vendorContracts.find((c) => c.operationCode === selectedOp)
    : null;
  const canonicalContract = selectedOp
    ? canonicalContracts.find(
        (c) => c.operationCode === selectedOp && (c.canonicalVersion ?? "v1") === canonicalVersion
      )
    : null;
  const requestSchema =
    (vendorContract?.requestSchema as Record<string, unknown>) ??
    (canonicalContract?.requestSchema as Record<string, unknown>) ??
    null;

  // Keep selection coherent when operation changes.
  useEffect(() => {
    if (!operation.trim()) {
      if (targetVendor) setTargetVendor("");
      return;
    }
    const selectedTargets = selectionModel.targetsByOperation[operation.trim().toUpperCase()] ?? [];
    if (!selectedTargets.includes(targetVendor.trim().toUpperCase())) {
      setTargetVendor(selectedTargets.length === 1 ? selectedTargets[0]! : "");
    }
  }, [operation, targetVendor, selectionModel.targetsByOperation]);

  // Pre-fill from URL params (e.g. /execute?operation=GET_RECEIPT&preset=sample)
  useEffect(() => {
    const op = searchParams.get("operation");
    const target = searchParams.get("targetVendor");
    if (op) setOperation(op);
    if (target) setTargetVendor(target);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-populate Parameters when operation changes (skeleton from schema)
  useEffect(() => {
    if (!selectedOp) return;
    if (requestSchema && Object.keys(requestSchema).length > 0) {
      const skeleton = buildSkeletonFromSchema(requestSchema);
      setParametersText(JSON.stringify(skeleton, null, 2));
      setSchemaInfo({
        operationCode: selectedOp,
        canonicalVersion,
        source: vendorContract ? "vendor" : "canonical",
      });
      setSchemaWarning(null);
    } else {
      setSchemaInfo(null);
      setSchemaWarning(
        "No request schema found for this operation. You can still enter parameters manually."
      );
    }
  }, [selectedOp, canonicalVersion, requestSchema, vendorContract]);

  const mutation = useMutation({
    mutationFn: executeAiIntegration,
    onError: () => {
      setParametersError(null);
    },
  });

  const handleParametersChange = (value: string) => {
    setParametersText(value);
    setParametersError(null);
    const parsed = parseParametersJson(value);
    if (value.trim() && parsed === null) {
      setParametersError("Invalid JSON");
    }
  };

  const handleGenerateIdempotency = () => {
    setIdempotencyKey(generateIdempotencyKey());
  };

  const handleResetFromSchema = () => {
    if (!requestSchema || Object.keys(requestSchema).length === 0) return;
    const skeleton = buildSkeletonFromSchema(requestSchema);
    setParametersText(JSON.stringify(skeleton, null, 2));
    setParametersError(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setParametersError(null);

    const parameters = parseParametersJson(parametersText);
    if (parameters === null) {
      setParametersError("Parameters must be valid JSON object");
      return;
    }

    const targetVendorTrimmed = targetVendor.trim();
    const operationTrimmed = operation.trim();
    const idempotencyKeyTrimmed = idempotencyKey.trim();

    if (!targetVendorTrimmed) return;
    if (!operationTrimmed) return;

    const payload: {
      targetVendor: string;
      operation: string;
      idempotencyKey?: string;
      parameters?: Record<string, unknown>;
      includeActuals?: boolean;
      aiFormatter?: boolean;
    } = {
      targetVendor: targetVendorTrimmed,
      operation: operationTrimmed,
      parameters: Object.keys(parameters).length > 0 ? parameters : undefined,
      includeActuals: true,
      aiFormatter,
    };
    if (idempotencyKeyTrimmed) payload.idempotencyKey = idempotencyKeyTrimmed;

    mutation.mutate(payload);
  };

  const apiError =
    mutation.error &&
    (mutation.error as { response?: { data?: unknown } })?.response?.data;
  const response = mutation.data;
  const isExecuteDisabled = !hasActiveVendor;
  const previewEnabled = hasActiveVendor && !!operation.trim() && !!targetVendor.trim();

  const { data: policyPreview, isFetching: policyPreviewLoading, error: policyPreviewError } = useQuery({
    queryKey: [
      "policy-preview",
      activeVendor ?? "",
      operation.trim().toUpperCase(),
      targetVendor.trim().toUpperCase(),
      aiFormatter,
    ],
    queryFn: () =>
      previewPolicy(
        operation.trim().toUpperCase(),
        targetVendor.trim().toUpperCase(),
        aiFormatter,
      ),
    enabled: previewEnabled,
    retry: false,
    staleTime: 0,
  });

  return (
    <VendorPageLayout
      title="Execute Playground"
      rightContent={
        activeVendor ? (
          <span
            className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700"
            title="Acting as this vendor"
          >
            {activeVendor}
          </span>
        ) : undefined
      }
    >
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)] gap-6">
      <div className="space-y-6 max-w-2xl">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Operation</label>
          <select
            value={operation}
            onChange={(e) => {
              setOperation(e.target.value);
            }}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
            required
          >
            <option value="">
              {selectionLoading ? "Loading operations…" : "Select operation…"}
            </option>
            {operationsForDropdown.map((op) => (
              <option key={op.operationCode} value={op.operationCode}>
                {op.operationCode}
                {op.description ? ` — ${op.description}` : ""}
              </option>
            ))}
          </select>
          {!selectionLoading && operationsForDropdown.length === 0 && activeVendor && !catalogLoading && (
            <p className="mt-1 text-sm text-amber-600">
              {catalog.length === 0
                ? "No admin-approved operations are available for this vendor."
                : "No ready operations available. Configure missing flow readiness in Configuration."}
            </p>
          )}
          {operation && (
            <p className="mt-1 text-xs text-slate-600">{aiModeLabel}</p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Target Licensee</label>
          <select
            value={targetVendor}
            onChange={(e) => setTargetVendor(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
            required
            disabled={!operation.trim() || selectionLoading}
          >
            <option value="">
              {!operation.trim()
                ? "Select operation first…"
                : selectionLoading
                  ? "Loading allowed targets…"
                  : "Select target…"}
            </option>
            {targetsForSelectedOperation.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          {!!operation.trim() && !selectionLoading && targetsForSelectedOperation.length === 0 && (
            <p className="mt-1 text-sm text-amber-600">
              No ready target licensees for this operation.
            </p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Idempotency Key</label>
          <div className="flex gap-2">
            <input
              type="text"
              value={idempotencyKey}
              onChange={(e) => setIdempotencyKey(e.target.value)}
              placeholder="Optional; Generate for replay protection"
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-slate-500 focus:border-slate-500 font-mono text-sm"
            />
            <button
              type="button"
              onClick={handleGenerateIdempotency}
              className="px-4 py-2 text-sm font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-lg"
            >
              Generate
            </button>
          </div>
        </div>

        <div>
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
            <input
              type="checkbox"
              checked={aiFormatter}
              onChange={(e) => setAiFormatter(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-slate-600 focus:ring-slate-500"
            />
            AI summary
          </label>
          <p className="mt-1 text-xs text-slate-500">
            Enabled sends <code>aiFormatter: true</code> in DATA requests.
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Parameters (JSON)</label>
          <textarea
            value={parametersText}
            onChange={(e) => handleParametersChange(e.target.value)}
            placeholder='{"transactionId": "tx-123"}'
            rows={6}
            className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-slate-500 focus:border-slate-500 font-mono text-sm ${
              parametersError ? "border-red-500" : "border-gray-300"
            }`}
          />
          <div className="mt-1 flex items-center gap-3 flex-wrap">
            {requestSchema && Object.keys(requestSchema).length > 0 && (
              <button
                type="button"
                onClick={handleResetFromSchema}
                className="px-3 py-1.5 text-sm font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-lg"
              >
                Reset from schema
              </button>
            )}
          </div>
          {schemaInfo && (
            <p className="mt-1 text-sm text-gray-500">
              Using {schemaInfo.source === "vendor" ? "vendor" : "canonical"} schema for:{" "}
              {schemaInfo.operationCode} {schemaInfo.canonicalVersion}
            </p>
          )}
          {schemaWarning && (
            <p className="mt-1 text-sm text-amber-600">{schemaWarning}</p>
          )}
          {parametersError && (
            <p className="mt-1 text-sm text-red-600">{parametersError}</p>
          )}
        </div>

        <button
          type="submit"
          disabled={mutation.isPending || !!parametersError || isExecuteDisabled}
          className="px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg"
        >
          {mutation.isPending ? "Executing…" : "Execute"}
        </button>
      </form>

      {mutation.isError && apiError != null ? (
        <div className="rounded-lg bg-red-50 border border-red-200 p-4">
          <h3 className="text-sm font-semibold text-red-800 mb-2">Request failed</h3>
          <pre className="text-xs text-red-700 overflow-x-auto">
            {JSON.stringify(apiError, null, 2)}
          </pre>
        </div>
      ) : null}

      {response != null && !mutation.isError ? (
        <div className="space-y-4 rounded-lg bg-white border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-emerald-50 border-b border-emerald-200">
            <h3 className="text-sm font-semibold text-emerald-800">Response</h3>
            {response.transactionId && (
              <p className="text-sm text-emerald-700 mt-1">
                Transaction:{" "}
                {(import.meta.env.VITE_ADMIN_APP_URL ?? "").trim() ? (
                  <a
                    href={`${String(import.meta.env.VITE_ADMIN_APP_URL).replace(/\/$/, "")}/admin/transactions/${response.transactionId}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-mono underline hover:text-emerald-900"
                  >
                    {response.transactionId}
                  </a>
                ) : (
                  <span className="font-mono">{response.transactionId}</span>
                )}
              </p>
            )}
          </div>
          <div className="p-4 space-y-4">
            {(() => {
              const ai = (response as { aiFormatter?: { applied?: boolean; formattedText?: string; reason?: string } }).aiFormatter;
              const reason = ai?.reason ?? "UNKNOWN";
              const badgeText = ai?.applied ? "AI: APPLIED" : `AI: ${reason}`;
              return (
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <h4 className="text-sm font-semibold text-slate-700">AI Summary</h4>
                    <span className="rounded bg-slate-200 px-2 py-0.5 text-[11px] font-medium text-slate-700">
                      {badgeText}
                    </span>
                  </div>
                  {ai?.applied && ai.formattedText ? (
                    <details className="mt-2" open>
                      <summary className="cursor-pointer text-xs text-slate-600">Show summary</summary>
                      <pre className="mt-2 text-xs text-slate-700 whitespace-pre-wrap break-words bg-white rounded border border-slate-200 p-2">
                        {ai.formattedText}
                      </pre>
                    </details>
                  ) : (
                    <p className="mt-2 text-xs text-slate-600">
                      Formatter did not run for this response.
                    </p>
                  )}
                </div>
              );
            })()}

            {(response as { responseBody?: { actuals?: Record<string, unknown> } }).responseBody?.actuals ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {(
                  [
                    "canonicalRequest",
                    "vendorRequest" as const,
                    "vendorResponse" as const,
                    "canonicalResponse",
                  ] as const
                ).map((key) => {
                  const actuals = (response as { responseBody?: { actuals?: Record<string, unknown> } })
                    .responseBody?.actuals;
                  const dataKey =
                    key === "vendorRequest"
                      ? ("vendorRequest" in (actuals ?? {}) ? "vendorRequest" : "targetRequest")
                      : key === "vendorResponse"
                        ? ("vendorResponse" in (actuals ?? {}) ? "vendorResponse" : "targetResponse")
                        : key;
                  const label =
                    key === "canonicalRequest"
                      ? "Canonical request"
                      : key === "vendorRequest"
                        ? "Vendor request"
                        : key === "vendorResponse"
                          ? "Vendor response"
                          : "Canonical response";
                  const badge =
                    key === "canonicalRequest" || key === "canonicalResponse"
                      ? actuals?.contractSource
                      : key === "vendorRequest"
                        ? actuals?.mappingRequestSource
                        : actuals?.mappingResponseSource;
                  const badgeText = typeof badge === "string" ? badge : "";
                    return (
                      <div key={key}>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs font-medium text-slate-600">{label}</span>
                          {badgeText && (
                            <span
                              className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-700"
                              title="Source"
                            >
                              {badgeText.replace("_", " ")}
                            </span>
                          )}
                        </div>
                        <pre className="p-2 bg-gray-100 rounded overflow-x-auto text-xs max-h-32 overflow-y-auto">
                          {JSON.stringify(actuals?.[dataKey] ?? {}, null, 2)}
                        </pre>
                      </div>
                    );
                })}
                {(() => {
                  const ep = (response as { responseBody?: { actuals?: { endpoint?: { url?: string; method?: string; source?: string; flowDirection?: string } } } })
                    .responseBody?.actuals?.endpoint;
                  return ep ? (
                    <div className="sm:col-span-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                      <div className="flex flex-wrap gap-2 items-center">
                        <span className="text-xs font-medium text-slate-600">Endpoint</span>
                        {ep.source && (
                          <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-700">
                            {ep.source}
                          </span>
                        )}
                        {ep.flowDirection && (
                          <span className="text-[10px] text-slate-600">{ep.flowDirection}</span>
                        )}
                        <span className="text-xs text-slate-600 font-mono">
                          {ep.method ?? "POST"} {ep.url ?? ""}
                        </span>
                      </div>
                    </div>
                  ) : null;
                })()}
              </div>
            ) : null}
            <pre className="text-xs text-gray-700 overflow-x-auto bg-gray-50 rounded-lg p-3 border border-gray-200">
              {JSON.stringify(response, null, 2)}
            </pre>
          </div>
        </div>
      ) : null}
      </div>
      <PolicyExplainPanel
        decision={policyPreview ?? null}
        isLoading={policyPreviewLoading}
        errorMessage={
          policyPreviewError
            ? "Unable to preview policy right now."
            : !previewEnabled
              ? "Select operation and target to preview."
              : null
        }
      />
      </div>
    </div>
    </VendorPageLayout>
  );
}
