import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getActiveVendorCode, isSupportedCanonicalSlice, SUPPORTED_SOURCE_VENDOR } from "frontend-shared";
import {
  listPartnerSyntegrisCanonicalOperations,
  getPartnerSyntegrisCanonicalOperation,
  runPartnerCanonicalBridgeExecution,
  type CanonicalOperationItem,
  type CanonicalBridgeResponse,
} from "../api/endpoints";

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
      {label && (
        <span className="text-xs font-medium text-gray-600 block mb-1">{label}</span>
      )}
      <pre className="text-xs text-gray-700 bg-gray-50 rounded-lg p-4 overflow-x-auto border border-gray-200 font-mono">
        {text}
      </pre>
    </div>
  );
}

function CheckStatusBadge({ status }: { status: string }) {
  const cls =
    status === "PASS"
      ? "bg-green-100 text-green-800"
      : status === "WARN"
        ? "bg-amber-100 text-amber-800"
        : "bg-red-100 text-red-800";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}

function ResultPanel({ result }: { result: CanonicalBridgeResponse }) {
  const statusCls =
    result.status === "READY" || result.status === "EXECUTED"
      ? "bg-green-100 text-green-800"
      : result.status === "WARN"
        ? "bg-amber-100 text-amber-800"
        : "bg-red-100 text-red-800";

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span className={`inline-flex px-2.5 py-1 rounded text-sm font-medium ${statusCls}`}>
          {result.status}
        </span>
        <span className="text-sm text-gray-600">{result.mode}</span>
        {result.operationCode && (
          <span className="text-sm text-gray-600">
            {result.operationCode} @ {result.canonicalVersion}
          </span>
        )}
        {result.sourceVendor && result.targetVendor && (
          <span className="text-sm text-gray-500">
            {result.sourceVendor} → {result.targetVendor}
          </span>
        )}
      </div>

      {result.preflight?.checks && result.preflight.checks.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-gray-700 mb-2">Preflight checks</h3>
          <ul className="space-y-2">
            {result.preflight.checks.map((c, i) => (
              <li
                key={i}
                className="flex items-center gap-2 p-3 rounded-lg border border-gray-200 bg-white"
              >
                <CheckStatusBadge status={c.status} />
                <span className="text-xs font-mono text-gray-500">{c.code}</span>
                <span className="text-sm text-gray-700">{c.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {result.errors && result.errors.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-red-700 mb-2">Errors</h3>
          <ul className="space-y-1">
            {result.errors.map((e, i) => (
              <li key={i} className="text-sm text-red-600">
                {e.field}: {e.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {(result.mappingSummary ?? result.preflight?.mappingSummary) && (
        <div>
          <h3 className="text-sm font-medium text-gray-700 mb-2">Mapping summary</h3>
          <div className="p-3 rounded-lg border border-gray-200 bg-slate-50 text-sm space-y-1">
            <p>
              <span className="font-medium">Available:</span>{" "}
              {String(
                (result.mappingSummary ?? result.preflight?.mappingSummary)?.available ?? false
              )}
            </p>
            {(result.mappingSummary ?? result.preflight?.mappingSummary)?.direction && (
              <p>
                <span className="font-medium">Direction:</span>{" "}
                {(result.mappingSummary ?? result.preflight?.mappingSummary)?.direction}
              </p>
            )}
            {(result.mappingSummary ?? result.preflight?.mappingSummary)?.fieldMappings !=
              null && (
              <p>
                <span className="font-medium">Field mappings:</span>{" "}
                {(result.mappingSummary ?? result.preflight?.mappingSummary)?.fieldMappings}
              </p>
            )}
            {(result.mappingSummary ?? result.preflight?.mappingSummary)?.warnings &&
              (result.mappingSummary ?? result.preflight?.mappingSummary)!.warnings!.length >
                0 && (
              <p className="text-amber-700">
                <span className="font-medium">Warnings:</span>{" "}
                {(result.mappingSummary ?? result.preflight?.mappingSummary)!.warnings!.join(
                  "; "
                )}
              </p>
            )}
          </div>
        </div>
      )}

      {(result.vendorRequestPreview ?? result.preflight?.vendorRequestPreview) &&
        Object.keys(
          result.vendorRequestPreview ?? result.preflight?.vendorRequestPreview ?? {}
        ).length > 0 && (
          <JsonBlock
            data={
              (result.vendorRequestPreview ?? result.preflight?.vendorRequestPreview) as Record<
                string,
                unknown
              >
            }
            label="Vendor request preview"
          />
        )}

      {result.executeRequestPreview && Object.keys(result.executeRequestPreview).length > 0 && (
        <JsonBlock data={result.executeRequestPreview} label="Execute request preview" />
      )}

      {result.canonicalResponseEnvelope &&
        Object.keys(result.canonicalResponseEnvelope).length > 0 && (
          <JsonBlock
            data={result.canonicalResponseEnvelope}
            label="Canonical response envelope"
          />
        )}

      {result.executionPlan && (
        <div>
          <h3 className="text-sm font-medium text-gray-700 mb-1">Execution plan</h3>
          <div className="p-3 rounded-lg border border-gray-200 bg-gray-50 text-sm">
            <p>
              <span className="font-medium">Can execute:</span>{" "}
              {String(result.executionPlan.canExecute)}
            </p>
            {result.executionPlan.reason && (
              <p>
                <span className="font-medium">Reason:</span> {result.executionPlan.reason}
              </p>
            )}
          </div>
        </div>
      )}

      {result.executeResult && (
        <div>
          <h3 className="text-sm font-medium text-gray-700 mb-1">Execute result</h3>
          <div className="p-3 rounded-lg border border-gray-200 bg-gray-50">
            {result.executeResult.error ? (
              <p className="text-sm text-red-600">{result.executeResult.error}</p>
            ) : (
              <JsonBlock data={result.executeResult.body as Record<string, unknown>} />
            )}
          </div>
        </div>
      )}

      {result.notes && result.notes.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-gray-700 mb-1">Notes</h3>
          <ul className="list-disc list-inside text-sm text-gray-600 space-y-0.5">
            {result.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function PartnerCanonicalExecutePage() {
  const activeVendor = getActiveVendorCode();
  const hasVendor = !!activeVendor;

  const [selectedOp, setSelectedOp] = useState<CanonicalOperationItem | null>(null);
  const [targetVendor, setTargetVendor] = useState("LH002");
  const [mode, setMode] = useState<"DRY_RUN" | "EXECUTE">("DRY_RUN");
  const [envelopeJson, setEnvelopeJson] = useState("{}");
  const [result, setResult] = useState<CanonicalBridgeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  const { data: opsData, isLoading: opsLoading, error: opsError } = useQuery({
    queryKey: ["partner-syntegris-canonical-operations"],
    queryFn: listPartnerSyntegrisCanonicalOperations,
  });

  const { data: opDetail } = useQuery({
    queryKey: ["partner-syntegris-canonical-operation", selectedOp?.operationCode, selectedOp?.latestVersion],
    queryFn: () =>
      getPartnerSyntegrisCanonicalOperation(selectedOp!.operationCode, selectedOp!.latestVersion),
    enabled: !!selectedOp,
  });

  const allItems = opsData?.items ?? [];
  const items = useMemo(() => {
    if (activeVendor !== SUPPORTED_SOURCE_VENDOR) return allItems;
    return allItems.filter((op) =>
      isSupportedCanonicalSlice(op.operationCode ?? "", activeVendor, "LH002")
    );
  }, [allItems, activeVendor]);

  useEffect(() => {
    if (opDetail?.examples?.requestEnvelope) {
      setEnvelopeJson(JSON.stringify(opDetail.examples.requestEnvelope, null, 2));
    } else if (opDetail?.examples?.request && selectedOp) {
      const envelope = {
        operationCode: selectedOp.operationCode,
        version: selectedOp.latestVersion,
        direction: "REQUEST",
        correlationId: "corr-execute-" + Date.now(),
        timestamp: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
        context: {},
        payload: opDetail.examples.request,
      };
      setEnvelopeJson(JSON.stringify(envelope, null, 2));
    }
  }, [opDetail?.operationCode, opDetail?.examples?.request, opDetail?.examples?.requestEnvelope, selectedOp]);

  const handleRun = useCallback(async () => {
    if (!hasVendor || !activeVendor) return;
    setIsRunning(true);
    setError(null);
    setResult(null);
    try {
      let envelope: Record<string, unknown>;
      try {
        envelope = JSON.parse(envelopeJson);
      } catch {
        setError("Invalid JSON in envelope");
        return;
      }
      const report = await runPartnerCanonicalBridgeExecution({
        targetVendor: targetVendor.trim(),
        mode,
        envelope,
      });
      setResult(report);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { error?: { message?: string } } } }).response?.data
              ?.error?.message ?? "Bridge execution failed"
          : String(err);
      setError(msg);
    } finally {
      setIsRunning(false);
    }
  }, [activeVendor, hasVendor, targetVendor, mode, envelopeJson]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h1 className="text-xl font-semibold text-gray-900">Canonical Execute</h1>
        {hasVendor && (
          <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium bg-teal-100 text-teal-800">
            {activeVendor}
          </span>
        )}
      </div>
      <p className="text-sm text-gray-600">
        Bridge canonical request to runtime execute. DRY_RUN previews; EXECUTE calls the runtime.
      </p>

      {!hasVendor && (
        <div className="p-4 rounded-lg border border-amber-200 bg-amber-50 text-amber-800 text-sm">
          Select active licensee first. Run is disabled until a licensee is selected.
        </div>
      )}

      <div className="flex flex-col lg:flex-row gap-4">
        <div className="w-full lg:w-64 shrink-0">
          <h2 className="text-sm font-medium text-gray-700 mb-2">Operations</h2>
          {opsLoading && <p className="text-sm text-gray-500">Loading…</p>}
          {opsError && (
            <p className="text-sm text-red-600">Failed to load operations.</p>
          )}
          {!opsLoading && !opsError && items.length === 0 && (
            <p className="text-sm text-gray-500">No canonical operations registered.</p>
          )}
          {!opsLoading && items.length > 0 && (
            <ul className="border border-gray-200 rounded-lg divide-y divide-gray-200 bg-white">
              {items.map((op) => (
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
                    {op.operationCode}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex-1 min-w-0 space-y-4">
          {selectedOp && (
            <>
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1">
                  Source Vendor (from active licensee)
                </label>
                <div className="px-3 py-2 text-sm bg-gray-100 rounded-lg border border-gray-200">
                  {hasVendor ? activeVendor : "—"}
                </div>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1">
                  Target Vendor
                </label>
                <input
                  type="text"
                  value={targetVendor}
                  onChange={(e) => setTargetVendor(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-slate-500"
                  placeholder="LH002"
                />
              </div>

              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1">Mode</label>
                <select
                  value={mode}
                  onChange={(e) => setMode(e.target.value as "DRY_RUN" | "EXECUTE")}
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-slate-500"
                >
                  <option value="DRY_RUN">DRY_RUN (preview only)</option>
                  <option value="EXECUTE">EXECUTE (run via runtime)</option>
                </select>
              </div>

              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1">
                  Canonical request envelope (JSON)
                </label>
                <textarea
                  value={envelopeJson}
                  onChange={(e) => setEnvelopeJson(e.target.value)}
                  rows={16}
                  className="w-full px-3 py-2 text-sm font-mono border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-slate-500"
                  spellCheck={false}
                />
              </div>

              <button
                type="button"
                onClick={handleRun}
                disabled={isRunning || !hasVendor}
                className="px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg"
              >
                {isRunning ? "Running…" : "Run"}
              </button>
            </>
          )}
          {!selectedOp && (
            <p className="text-sm text-gray-500 italic">Select an operation to run.</p>
          )}
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-lg border border-red-200 bg-red-50 text-red-700 text-sm">
          {error}
        </div>
      )}

      {result && (
        <div className="mt-6 p-4 rounded-lg border border-gray-200 bg-white">
          <h2 className="text-sm font-semibold text-gray-900 mb-3">Result</h2>
          <ResultPanel result={result} />
        </div>
      )}
    </div>
  );
}
