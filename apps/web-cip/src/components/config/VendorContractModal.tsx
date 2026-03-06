import { useQuery } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import { getVendorOperationsCatalog } from "../../api/endpoints";
import type { VendorContract } from "../../types";

function parseJsonSafe(
  value: string
): Record<string, unknown> | undefined | null {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
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

interface VendorContractModalProps {
  open: boolean;
  onClose: () => void;
  initialValues: VendorContract | null;
  onSave: (payload: {
    operationCode: string;
    canonicalVersion?: string;
    requestSchema?: Record<string, unknown>;
    responseSchema?: Record<string, unknown>;
    isActive?: boolean;
  }) => Promise<void>;
}

export function VendorContractModal({
  open,
  onClose,
  initialValues,
  onSave,
}: VendorContractModalProps) {
  const [operationCode, setOperationCode] = useState("");
  const [canonicalVersion, setCanonicalVersion] = useState("");
  const [requestSchemaText, setRequestSchemaText] = useState("{}");
  const [responseSchemaText, setResponseSchemaText] = useState("{}");
  const [isActive, setIsActive] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [schemaError, setSchemaError] = useState<string | null>(null);
  const isEdit = !!initialValues;

  const {
    data: operationsData,
    isLoading: operationsLoading,
    isError: operationsError,
  } = useQuery({
    queryKey: ["vendor-operations-catalog"],
    queryFn: getVendorOperationsCatalog,
    enabled: open,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
  });

  const operations = operationsData?.items ?? [];
  const useFallbackInput = !!operationsError;

  useEffect(() => {
    if (open && operationsError) {
      console.warn("[VendorContractModal] Operations list failed to load, falling back to manual operation code input.");
    }
  }, [open, operationsError]);

  useEffect(() => {
    if (open) {
      setOperationCode(initialValues?.operationCode ?? "");
      setCanonicalVersion(initialValues?.canonicalVersion ?? "");
      setRequestSchemaText(
        initialValues?.requestSchema
          ? JSON.stringify(initialValues.requestSchema, null, 2)
          : "{}"
      );
      setResponseSchemaText(
        initialValues?.responseSchema
          ? JSON.stringify(initialValues.responseSchema, null, 2)
          : "{}"
      );
      setIsActive(initialValues?.isActive !== false);
      setError(null);
      setSchemaError(null);
    }
  }, [open, initialValues]);

  const handleOperationChange = (code: string) => {
    setOperationCode(code);
    const op = operations.find((o) => o.operationCode === code);
    setCanonicalVersion(op?.canonicalVersion ?? "v1");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSchemaError(null);

    const opCode = operationCode.trim().toUpperCase();
    if (!opCode) {
      setError("Operation code is required.");
      return;
    }

    const requestSchema = parseJsonSafe(requestSchemaText);
    const responseSchema = parseJsonSafe(responseSchemaText);
    if (requestSchema === null) {
      setSchemaError("Request schema must be valid JSON.");
      return;
    }
    if (responseSchema === null) {
      setSchemaError("Response schema must be valid JSON.");
      return;
    }

    setIsLoading(true);
    try {
      await onSave({
        operationCode: opCode,
        canonicalVersion: canonicalVersion.trim() || undefined,
        requestSchema: requestSchema ?? undefined,
        responseSchema: responseSchema ?? undefined,
        isActive,
      });
      onClose();
    } catch (err) {
      setError((err as Error)?.message ?? "Failed to save.");
    } finally {
      setIsLoading(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" aria-hidden />
      <div
        className="relative w-full max-w-lg bg-white rounded-lg shadow-xl p-6 mx-4 max-h-[90vh] overflow-y-auto"
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">
            {isEdit ? "Edit Contract" : "Add Contract"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 p-1 rounded"
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          {useFallbackInput && (
            <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-sm text-amber-800">
              Could not load operations from registry. Using manual entry.
            </div>
          )}
          {useFallbackInput ? (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Operation code</label>
                <input
                  type="text"
                  value={operationCode}
                  onChange={(e) => setOperationCode(e.target.value)}
                  placeholder="GET_RECEIPT"
                  disabled={isEdit}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500 disabled:bg-gray-100 disabled:text-gray-600"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Canonical version</label>
                <input
                  type="text"
                  value={canonicalVersion}
                  onChange={(e) => setCanonicalVersion(e.target.value)}
                  placeholder="1.0"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
                />
              </div>
            </>
          ) : (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Operation</label>
              <select
                value={operationCode}
                onChange={(e) => handleOperationChange(e.target.value)}
                disabled={isEdit || operationsLoading}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500 disabled:bg-gray-100 disabled:text-gray-600"
              >
                <option value="">{operationsLoading ? "Loading operations…" : "Select operation…"}</option>
                {operations.map((op) => (
                  <option key={op.operationCode} value={op.operationCode}>
                    {op.operationCode} – {op.canonicalVersion ?? "v1"}
                  </option>
                ))}
                {isEdit && operationCode && !operations.some((o) => o.operationCode === operationCode) && (
                  <option value={operationCode}>
                    {operationCode} – {canonicalVersion || "v1"}
                  </option>
                )}
              </select>
              {isEdit && (
                <p className="text-xs text-gray-500 mt-1">Operation cannot be changed when editing.</p>
              )}
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Request schema (JSON)
            </label>
            <textarea
              value={requestSchemaText}
              onChange={(e) => setRequestSchemaText(e.target.value)}
              rows={6}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
              placeholder='{"type": "object", "properties": {}}'
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Response schema (JSON)
            </label>
            <textarea
              value={responseSchemaText}
              onChange={(e) => setResponseSchemaText(e.target.value)}
              rows={6}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
              placeholder='{"type": "object", "properties": {}}'
            />
          </div>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="rounded border-gray-300 text-slate-600 focus:ring-slate-500"
            />
            <span className="text-sm text-gray-700">Active</span>
          </label>
          {schemaError && (
            <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-sm text-amber-800">
              {schemaError}
            </div>
          )}
          {error && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
              {error}
            </div>
          )}
          <div className="flex gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 disabled:opacity-50 rounded-lg"
            >
              {isLoading ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
