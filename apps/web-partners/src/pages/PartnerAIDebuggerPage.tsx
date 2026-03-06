import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getActiveVendorCode } from "frontend-shared";
import {
  listPartnerSyntegrisCanonicalOperations,
  getPartnerSyntegrisCanonicalOperation,
  analyzePartnerDebugRequest,
  analyzePartnerDebugFlowDraft,
  analyzePartnerDebugSandboxResult,
  type CanonicalOperationItem,
  type CanonicalOperationDetail,
  type DebugReport,
} from "../api/endpoints";

type DebugMode = "canonical-request" | "flow-draft" | "sandbox-result";

const MODES: { id: DebugMode; label: string }[] = [
  { id: "canonical-request", label: "Canonical Request" },
  { id: "flow-draft", label: "Flow Draft" },
  { id: "sandbox-result", label: "Sandbox Result" },
];

function getSampleFlowDraft(): Record<string, unknown> {
  const sourceVendor = getActiveVendorCode() ?? "LH001";
  return {
    name: "Eligibility Flow",
    operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
    version: "v1",
    sourceVendor,
    targetVendor: "LH002",
    trigger: { type: "MANUAL" },
    mappingMode: "CANONICAL_FIRST",
    notes: "",
  };
}

const SAMPLE_SANDBOX_RESULT: Record<string, unknown> = {
  operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
  version: "1.0",
  mode: "MOCK",
  valid: true,
  requestPayloadValid: true,
  requestEnvelopeValid: true,
  responseEnvelopeValid: true,
  requestEnvelope: {
    operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
    version: "1.0",
    direction: "REQUEST",
    correlationId: "corr-debug-sample",
    timestamp: "2025-03-06T12:00:00Z",
    payload: { memberIdWithPrefix: "LH001-12345", date: "2025-03-06" },
  },
  responseEnvelope: {
    operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
    version: "1.0",
    direction: "RESPONSE",
    correlationId: "corr-debug-sample",
    timestamp: "2025-03-06T12:00:05Z",
    payload: {
      memberIdWithPrefix: "LH001-12345",
      name: "Jane Doe",
      dob: "1990-01-15",
      status: "ACTIVE",
    },
  },
  notes: ["Mock sandbox execution only. No vendor endpoint was called."],
};

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

function SeverityBadge({ severity }: { severity: string }) {
  const cls =
    severity === "ERROR"
      ? "bg-red-100 text-red-800"
      : severity === "WARNING"
        ? "bg-amber-100 text-amber-800"
        : "bg-slate-100 text-slate-700";
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${cls}`}
    >
      {severity}
    </span>
  );
}

function ReportPanel({ report }: { report: DebugReport }) {
  const artifacts = report.normalizedArtifacts;
  const hasPayload = artifacts?.payload && Object.keys(artifacts.payload as object).length > 0;
  const hasDraft = artifacts?.draft && Object.keys(artifacts.draft as object).length > 0;
  const hasSandbox =
    artifacts?.sandboxResult && Object.keys(artifacts.sandboxResult as object).length > 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span
          className={`inline-flex px-2.5 py-1 rounded text-sm font-medium ${
            report.status === "PASS"
              ? "bg-green-100 text-green-800"
              : report.status === "WARN"
                ? "bg-amber-100 text-amber-800"
                : "bg-red-100 text-red-800"
          }`}
        >
          {report.status}
        </span>
        {report.operationCode && (
          <span className="text-sm text-gray-600">
            {report.operationCode} {report.version && `@ ${report.version}`}
          </span>
        )}
      </div>
      <p className="text-sm text-gray-700">{report.summary}</p>
      {report.findings && report.findings.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-gray-700 mb-2">Findings</h3>
          <ul className="space-y-2">
            {report.findings.map((f, i) => (
              <li
                key={i}
                className="flex flex-col gap-1 p-3 rounded-lg border border-gray-200 bg-white"
              >
                <div className="flex items-center gap-2">
                  <SeverityBadge severity={f.severity} />
                  <span className="text-sm font-medium text-gray-900">{f.title}</span>
                  {f.code && (
                    <span className="text-xs text-gray-500 font-mono">{f.code}</span>
                  )}
                </div>
                <p className="text-sm text-gray-600">{f.message}</p>
                {f.field && (
                  <p className="text-xs text-gray-500 font-mono">Field: {f.field}</p>
                )}
                {f.suggestion && (
                  <p className="text-sm text-slate-600 italic">Suggestion: {f.suggestion}</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {(hasPayload || hasDraft || hasSandbox) && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-gray-700">Normalized artifacts</h3>
          {hasPayload && (
            <JsonBlock data={artifacts.payload as Record<string, unknown>} label="Payload" />
          )}
          {hasDraft && (
            <JsonBlock data={artifacts.draft as Record<string, unknown>} label="Draft" />
          )}
          {hasSandbox && (
            <JsonBlock
              data={artifacts.sandboxResult as Record<string, unknown>}
              label="Sandbox result"
            />
          )}
        </div>
      )}
      {report.notes && report.notes.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-gray-700 mb-1">Notes</h3>
          <ul className="list-disc list-inside text-sm text-gray-600 space-y-0.5">
            {report.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function PartnerAIDebuggerPage() {
  const activeVendor = getActiveVendorCode();
  const hasVendor = !!activeVendor;

  const [mode, setMode] = useState<DebugMode>("canonical-request");
  const [selectedOp, setSelectedOp] = useState<CanonicalOperationItem | null>(null);
  const [requestPayload, setRequestPayload] = useState("{}");
  const [flowDraftJson, setFlowDraftJson] = useState(
    () => JSON.stringify(getSampleFlowDraft(), null, 2)
  );
  const [sandboxResultJson, setSandboxResultJson] = useState(
    () => JSON.stringify(SAMPLE_SANDBOX_RESULT, null, 2)
  );
  const [report, setReport] = useState<DebugReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

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
  const items = useMemo(() => allItems, [allItems]);

  useEffect(() => {
    if (opDetail?.examples?.request && mode === "canonical-request") {
      setRequestPayload(JSON.stringify(opDetail.examples.request, null, 2));
    }
  }, [opDetail?.operationCode, opDetail?.examples?.request, mode]);

  useEffect(() => {
    if (hasVendor) {
      setFlowDraftJson(JSON.stringify(getSampleFlowDraft(), null, 2));
    }
  }, [activeVendor, hasVendor]);

  const handleAnalyzeRequest = useCallback(async () => {
    if (!selectedOp) return;
    setIsAnalyzing(true);
    setError(null);
    setReport(null);
    try {
      let payload: Record<string, unknown>;
      try {
        payload = JSON.parse(requestPayload);
      } catch {
        setError("Invalid JSON in request payload");
        return;
      }
      const result = await analyzePartnerDebugRequest({
        operationCode: selectedOp.operationCode,
        version: selectedOp.latestVersion,
        payload,
      });
      setReport(result);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { error?: { message?: string } } } }).response?.data
              ?.error?.message ?? "Analysis failed"
          : String(err);
      setError(msg);
    } finally {
      setIsAnalyzing(false);
    }
  }, [selectedOp, requestPayload]);

  const handleAnalyzeFlowDraft = useCallback(async () => {
    setIsAnalyzing(true);
    setError(null);
    setReport(null);
    try {
      let draft: Record<string, unknown>;
      try {
        draft = JSON.parse(flowDraftJson);
      } catch {
        setError("Invalid JSON in flow draft");
        return;
      }
      const result = await analyzePartnerDebugFlowDraft({ draft });
      setReport(result);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { error?: { message?: string } } } }).response?.data
              ?.error?.message ?? "Analysis failed"
          : String(err);
      setError(msg);
    } finally {
      setIsAnalyzing(false);
    }
  }, [flowDraftJson]);

  const handleAnalyzeSandboxResult = useCallback(async () => {
    setIsAnalyzing(true);
    setError(null);
    setReport(null);
    try {
      let result: Record<string, unknown>;
      try {
        result = JSON.parse(sandboxResultJson);
      } catch {
        setError("Invalid JSON in sandbox result");
        return;
      }
      const reportResult = await analyzePartnerDebugSandboxResult({ result });
      setReport(reportResult);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { error?: { message?: string } } } }).response?.data
              ?.error?.message ?? "Analysis failed"
          : String(err);
      setError(msg);
    } finally {
      setIsAnalyzing(false);
    }
  }, [sandboxResultJson]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h1 className="text-xl font-semibold text-gray-900">AI Debugger</h1>
        {hasVendor && (
          <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium bg-teal-100 text-teal-800">
            {activeVendor}
          </span>
        )}
      </div>
      <p className="text-sm text-gray-600">
        Deterministic integration debugger. Analyze canonical requests, flow drafts, and sandbox
        results. No LLM or vendor calls.
      </p>

      {!hasVendor && (
        <div className="p-4 rounded-lg border border-amber-200 bg-amber-50 text-amber-800 text-sm">
          Select active licensee first to use flow draft samples with your vendor identity.
        </div>
      )}

      <div className="flex gap-2 border-b border-gray-200">
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => {
              setMode(m.id);
              setReport(null);
              setError(null);
            }}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 -mb-px transition-colors ${
              mode === m.id
                ? "border-slate-600 text-slate-900 bg-slate-50"
                : "border-transparent text-gray-600 hover:text-gray-900 hover:bg-gray-50"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {mode === "canonical-request" && (
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
                  <span className="text-xs font-medium text-gray-600 block mb-1">
                    Version: {selectedOp.latestVersion}
                  </span>
                  <label className="text-sm font-medium text-gray-700 block mb-1">
                    Request payload (JSON)
                  </label>
                  <textarea
                    value={requestPayload}
                    onChange={(e) => setRequestPayload(e.target.value)}
                    rows={12}
                    className="w-full px-3 py-2 text-sm font-mono border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-slate-500"
                    spellCheck={false}
                  />
                </div>
                <button
                  type="button"
                  onClick={handleAnalyzeRequest}
                  disabled={isAnalyzing}
                  className="px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 disabled:opacity-50 rounded-lg"
                >
                  {isAnalyzing ? "Analyzing…" : "Analyze Request"}
                </button>
              </>
            )}
            {!selectedOp && (
              <p className="text-sm text-gray-500 italic">Select an operation to analyze.</p>
            )}
          </div>
        </div>
      )}

      {mode === "flow-draft" && (
        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1">
              Flow draft (JSON)
            </label>
            <textarea
              value={flowDraftJson}
              onChange={(e) => setFlowDraftJson(e.target.value)}
              rows={16}
              className="w-full px-3 py-2 text-sm font-mono border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-slate-500"
              spellCheck={false}
            />
          </div>
          <button
            type="button"
            onClick={handleAnalyzeFlowDraft}
            disabled={isAnalyzing}
            className="px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 disabled:opacity-50 rounded-lg"
          >
            {isAnalyzing ? "Analyzing…" : "Analyze Flow Draft"}
          </button>
        </div>
      )}

      {mode === "sandbox-result" && (
        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1">
              Sandbox result (JSON)
            </label>
            <textarea
              value={sandboxResultJson}
              onChange={(e) => setSandboxResultJson(e.target.value)}
              rows={20}
              className="w-full px-3 py-2 text-sm font-mono border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-slate-500"
              spellCheck={false}
            />
          </div>
          <button
            type="button"
            onClick={handleAnalyzeSandboxResult}
            disabled={isAnalyzing}
            className="px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 disabled:opacity-50 rounded-lg"
          >
            {isAnalyzing ? "Analyzing…" : "Analyze Sandbox Result"}
          </button>
        </div>
      )}

      {error && (
        <div className="p-4 rounded-lg border border-red-200 bg-red-50 text-red-700 text-sm">
          {error}
        </div>
      )}

      {report && (
        <div className="mt-6 p-4 rounded-lg border border-gray-200 bg-white">
          <h2 className="text-sm font-semibold text-gray-900 mb-3">Report</h2>
          <ReportPanel report={report} />
        </div>
      )}
    </div>
  );
}
