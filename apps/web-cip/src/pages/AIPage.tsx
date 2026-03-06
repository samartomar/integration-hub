import { useState, useMemo } from "react";
import { useMutation } from "@tanstack/react-query";
import { executeAiIntegration } from "../api/endpoints";
import { getActiveVendorCode } from "frontend-shared";
import type { ExecuteIntegrationPayload } from "../types";
import { ResultsPanel } from "../components/ai/ResultsPanel";

const DEFAULT_SOURCE_VENDOR = "LH001";

/**
 * Normalize AI Tool output into canonical ExecuteIntegrationPayload shape.
 * Handles:
 * - Direct shape: { operation, parameters, sourceVendor, targetVendor, idempotencyKey }
 * - Wrapper: { value: { operation, parameters, ... } }
 * - operationCode -> operation mapping
 */
function normalizeToExecutePayload(raw: unknown): ExecuteIntegrationPayload | null {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;

  // Unwrap { value: { ... } }
  let inner = obj;
  if (obj.value != null && typeof obj.value === "object" && !Array.isArray(obj.value)) {
    inner = obj.value as Record<string, unknown>;
  }

  const operation =
    (inner.operation as string) ??
    (inner.operationCode as string) ??
    "";
  const targetVendor = (inner.targetVendor as string) ?? "";
  if (!operation.trim() || !targetVendor.trim()) return null;

  let parameters = inner.parameters;
  if (parameters != null && typeof parameters !== "object") parameters = undefined;
  if (Array.isArray(parameters)) parameters = undefined;
  const params =
    parameters != null && typeof parameters === "object"
      ? (parameters as Record<string, unknown>)
      : undefined;

  return {
    sourceVendor: (inner.sourceVendor as string)?.trim() || getActiveVendorCode() || DEFAULT_SOURCE_VENDOR,
    targetVendor: targetVendor.trim(),
    operation: operation.trim(),
    parameters: params && Object.keys(params).length > 0 ? params : undefined,
    idempotencyKey: (inner.idempotencyKey as string)?.trim() || undefined,
  };
}

/**
 * Deterministic parser for POC:
 * - default sourceVendor LH001
 * - "Vendor B" => targetVendor LH002
 * - "receipt" => operation GET_RECEIPT
 * - extract last number as transactionId
 */
function parsePromptToPayload(prompt: string): {
  sourceVendor: string;
  targetVendor: string;
  operation: string;
  parameters: { transactionId?: string };
  idempotencyKey: string;
} | null {
  const trimmed = prompt.trim();
  if (!trimmed) return null;

  const idempotencyKey = `ai-${Date.now()}`;

  // targetVendor: "Licensee B" => LH002, or explicit LHxxx
  let targetVendor = "";
  if (/\bLicensee\s+B\b/i.test(trimmed) || /\bVendor\s+B\b/i.test(trimmed)) {
    targetVendor = "LH002";
  } else {
    const match = trimmed.match(/\b(LH\d{3})\b/i);
    if (match) targetVendor = match[1].toUpperCase();
  }

  // operation: "receipt" => GET_RECEIPT
  let operation = "";
  if (/\breceipt\b/i.test(trimmed)) {
    operation = "GET_RECEIPT";
  } else {
    const opMatch = trimmed.match(/\b(GET_[A-Z0-9_]+)\b/i);
    if (opMatch) operation = opMatch[1].toUpperCase();
  }

  // parameters: extract last number as transactionId
  const params: { transactionId?: string } = {};
  const numbers = trimmed.match(/\d+/g);
  if (numbers && numbers.length > 0) {
    params.transactionId = numbers[numbers.length - 1];
  }
  // Fallback: "transaction 123", "tx-123"
  if (!params.transactionId) {
    const txMatch =
      trimmed.match(/transaction\s+([^\s,]+)/i) ??
      trimmed.match(/\b(tx-[a-zA-Z0-9_-]+)\b/i);
    if (txMatch) params.transactionId = txMatch[1];
  }

  if (!targetVendor || !operation) return null;

  return {
    sourceVendor: DEFAULT_SOURCE_VENDOR,
    targetVendor,
    operation,
    parameters: Object.keys(params).length > 0 ? params : {},
    idempotencyKey,
  };
}

const EXAMPLE_PROMPTS = [
  "Ask Licensee B for receipt for transaction 123",
  "Get receipt 987 from Licensee B",
] as const;

export function AIPage() {
  const [prompt, setPrompt] = useState("");

  const toolPayload = useMemo(() => parsePromptToPayload(prompt), [prompt]);
  const executePayload = useMemo(
    () => (toolPayload ? normalizeToExecutePayload(toolPayload) : null),
    [toolPayload]
  );

  const mutation = useMutation({
    mutationFn: executeAiIntegration,
  });

  const validationError = useMemo(() => {
    if (!executePayload) return null;
    if (!executePayload.operation?.trim()) return "Operation is required.";
    if (executePayload.parameters != null && typeof executePayload.parameters !== "object") {
      return "Parameters must be a JSON object.";
    }
    if (
      executePayload.operation === "GET_RECEIPT" &&
      (!executePayload.parameters?.transactionId || typeof executePayload.parameters.transactionId !== "string")
    ) {
      return "GET_RECEIPT requires parameters.transactionId (canonical schema).";
    }
    return null;
  }, [executePayload]);

  const getReceiptHint =
    executePayload?.operation === "GET_RECEIPT" &&
    (!executePayload.parameters?.transactionId || typeof executePayload.parameters.transactionId !== "string");

  const handleExecute = () => {
    if (!executePayload || validationError) return;
    mutation.mutate(executePayload);
  };

  const response = mutation.data;
  const transactionId = response?.transactionId;
  const canExecute =
    executePayload !== null &&
    !mutation.isPending &&
    !validationError;

  const resultsError = mutation.error
    ? (() => {
        const err = mutation.error as { response?: { data?: unknown } };
        const data = err?.response?.data;
        if (data && typeof data === "object" && (data as object).hasOwnProperty("message")) {
          return data as { code?: string; message?: string; violations?: unknown[] };
        }
        return (mutation.error as Error)?.message ?? "Unknown error";
      })()
    : null;

  return (
    <div className="space-y-6">
      {/* Full-width header */}
      <div>
        <h1 className="text-lg sm:text-2xl font-bold text-gray-900">AI Demo</h1>
        <p className="text-sm text-gray-500 mt-1">
          Describe the integration call in natural language. A deterministic parser builds the tool payload.
        </p>
      </div>

      {/* 2-column: Left cards | Right sticky ResultsPanel (~420px) */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_420px] gap-6 items-start">
        {/* Left: Prompt, Derived payload, Execution, Explainability */}
        <div className="space-y-6 min-w-0 overflow-hidden">
      {/* 1. Prompt input */}
      <div className="rounded-lg bg-white border border-gray-200 p-4">
        <label className="block text-sm font-medium text-gray-700 mb-2">Prompt</label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="e.g. Ask Licensee B for receipt for transaction 123"
          rows={3}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-slate-500 focus:border-slate-500 text-sm"
        />
        <div className="flex flex-wrap gap-2 mt-2">
          {EXAMPLE_PROMPTS.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => setPrompt(ex)}
              className="px-3 py-1.5 text-xs font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-lg"
            >
              {ex}
            </button>
          ))}
        </div>
      </div>

      {/* 2. Derived payload panel */}
      {toolPayload && (
        <div className="rounded-lg bg-white border border-gray-200 p-4">
          <h3 className="text-sm font-semibold text-gray-800 mb-2">Derived payload</h3>
          <pre className="text-xs text-gray-700 overflow-x-auto font-mono bg-gray-50 rounded-lg p-3 border border-gray-200">
            {JSON.stringify(toolPayload, null, 2)}
          </pre>
        </div>
      )}

      {!toolPayload && prompt.trim().length > 0 && (
        <p className="text-sm text-amber-600">
          Could not parse: need "Licensee B" (or LH002) and "receipt" (or GET_RECEIPT) in the prompt.
        </p>
      )}

      {/* 3. Execution panel */}
      <div className="rounded-lg bg-white border border-gray-200 p-4">
        <h3 className="text-sm font-semibold text-gray-800 mb-3">Execution</h3>
        {getReceiptHint && (
          <p className="text-sm text-amber-700 mb-2">
            GET_RECEIPT requires <code className="bg-amber-100 px-1 rounded">parameters.transactionId</code> to match the canonical schema.
          </p>
        )}
        {validationError && (
          <p className="text-sm text-red-600 mb-2">{validationError}</p>
        )}
        <button
          type="button"
          onClick={handleExecute}
          disabled={!canExecute}
          className="px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg"
        >
          {mutation.isPending ? "Executing…" : "Execute"}
        </button>
      </div>

      {/* 4. Explainability panel */}
      <div className="rounded-lg bg-white border border-gray-200 p-4">
        <h3 className="text-sm font-semibold text-gray-800 mb-4">Explainability</h3>
        <div className="space-y-4">
          <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">
              Step 1: Intent detected
            </p>
            <p className="text-sm text-gray-800">
              {toolPayload
                ? `Operation: ${toolPayload.operation}, Target: ${toolPayload.targetVendor}`
                : "—"}
            </p>
          </div>
          <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">
              Step 2: Tool payload built
            </p>
            <pre className="text-xs text-gray-700 font-mono overflow-x-auto">
              {toolPayload
                ? JSON.stringify(toolPayload, null, 2)
                : "—"}
            </pre>
          </div>
          <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">
              Step 3: Platform response
            </p>
            <p className="text-sm text-gray-800">
              {mutation.isPending
                ? "Executing…"
                : mutation.isError
                  ? "Error"
                  : response
                    ? `Status: Success, Transaction: ${transactionId ?? "—"}`
                    : "—"}
            </p>
          </div>
        </div>
      </div>
        </div>

        {/* Right: Sticky Results panel */}
        <div className="lg:sticky lg:top-4 self-start">
        <ResultsPanel
          lastResponse={response ? { ...response } as Record<string, unknown> : null}
          isLoading={mutation.isPending}
          error={resultsError}
        />
        </div>
      </div>
    </div>
  );
}
