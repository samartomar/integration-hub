import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { ModalShell } from "./ModalShell";
import { listOperations, listContracts } from "../../api/endpoints";
import type { RegistryContract } from "../../types";

function parseJsonSafe(
  value: string
): { ok: true; data: Record<string, unknown> } | { ok: false; error: string } {
  const trimmed = value.trim();
  if (!trimmed) return { ok: true, data: {} };
  try {
    const parsed = JSON.parse(trimmed);
    if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
      return { ok: true, data: parsed };
    }
    return { ok: false, error: "Must be a JSON object" };
  } catch (e) {
    const msg = e instanceof SyntaxError ? e.message : "Invalid JSON";
    return { ok: false, error: msg };
  }
}

interface ContractModalProps {
  open: boolean;
  onClose: () => void;
  initialValues: RegistryContract | null;
  onSave: (payload: {
    operation_code: string;
    canonical_version: string;
    request_schema: Record<string, unknown>;
    response_schema?: Record<string, unknown> | null;
    is_active?: boolean;
  }) => Promise<void>;
}

export function ContractModal({
  open,
  onClose,
  initialValues,
  onSave,
}: ContractModalProps) {
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
    refetch: refetchOperations,
  } = useQuery({
    queryKey: ["registry-operations"],
    queryFn: () => listOperations(),
    enabled: open,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
  });

  const handleCloneCanonical = async () => {
    const op = operationCode.trim().toUpperCase();
    const ver = canonicalVersion.trim();
    if (!op || !ver) {
      setError("Select operation and canonical version first.");
      return;
    }
    setError(null);
    try {
      const { items } = await listContracts({ operationCode: op, canonicalVersion: ver });
      const canon = items.find(
        (c) => c.operationCode === op && (c.canonicalVersion ?? "v1") === ver
      ) ?? items[0];
      if (canon?.requestSchema) {
        setRequestSchemaText(JSON.stringify(canon.requestSchema, null, 2));
      }
      if (canon?.responseSchema && typeof canon.responseSchema === "object") {
        setResponseSchemaText(JSON.stringify(canon.responseSchema, null, 2));
      } else {
        setResponseSchemaText("{}");
      }
      setSchemaError(null);
    } catch (e) {
      setError((e as Error)?.message ?? "Failed to load canonical contract.");
    }
  };

  const allOperations = operationsData?.items ?? [];
  const activeOperations = allOperations.filter((o) => o.isActive !== false);
  const noOperations = !operationsLoading && !operationsError && activeOperations.length === 0;
  const canCreate = !isEdit && activeOperations.length > 0 && !operationsError;
  const createDisabledByNoOps = !isEdit && noOperations;

  const handleOperationChange = (code: string) => {
    setOperationCode(code);
    const op = activeOperations.find((o) => o.operationCode === code);
    setCanonicalVersion(op?.canonicalVersion ?? "v1");
  };

  // In edit mode, ensure current operation appears in options (may be deactivated)
  const operationOptions =
    isEdit && operationCode && !activeOperations.some((o) => o.operationCode === operationCode)
      ? [{ operationCode, canonicalVersion: canonicalVersion || "v1" }, ...activeOperations]
      : activeOperations;

  useEffect(() => {
    if (open) {
      setOperationCode(initialValues?.operationCode ?? "");
      setCanonicalVersion(initialValues?.canonicalVersion ?? "v1");
      setRequestSchemaText(
        initialValues?.requestSchema
          ? JSON.stringify(initialValues.requestSchema, null, 2)
          : "{}"
      );
      setResponseSchemaText(
        initialValues?.responseSchema != null &&
        typeof initialValues.responseSchema === "object" &&
        Object.keys(initialValues.responseSchema).length > 0
          ? JSON.stringify(initialValues.responseSchema, null, 2)
          : "{}"
      );
      setIsActive(initialValues?.isActive !== false);
      setError(null);
      setSchemaError(null);
    }
  }, [open, initialValues]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSchemaError(null);

    const opCode = operationCode.trim().toUpperCase();
    if (!opCode) {
      setError("Operation code is required.");
      return;
    }
    const version = canonicalVersion.trim();
    if (!version) {
      setError("Canonical version is required.");
      return;
    }

    const requestResult = parseJsonSafe(requestSchemaText);
    const responseResult = parseJsonSafe(responseSchemaText);
    if (!requestResult.ok) {
      setSchemaError(`Request schema: ${requestResult.error}`);
      return;
    }
    if (!responseResult.ok) {
      setSchemaError(`Response schema: ${responseResult.error}`);
      return;
    }
    const reqSchema = requestResult.data;
    if (!reqSchema || typeof reqSchema !== "object" || Object.keys(reqSchema).length === 0) {
      setError("Request schema cannot be empty.");
      return;
    }
    if (!("type" in reqSchema) && !("properties" in reqSchema)) {
      setError("Request schema must include type or properties.");
      return;
    }

    setIsLoading(true);
    try {
      await onSave({
        operation_code: opCode,
        canonical_version: version,
        request_schema: requestResult.data,
        response_schema: responseResult.data && Object.keys(responseResult.data).length > 0 ? responseResult.data : undefined,
        is_active: isActive,
      });
      onClose();
    } catch (err) {
      setError((err as Error)?.message ?? "Failed to save.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <ModalShell open={open} onClose={onClose} title={isEdit ? "Edit Contract" : "Create Contract"}>
      <form onSubmit={handleSubmit} className="space-y-4">
        {noOperations && !isEdit && (
          <div className="rounded-lg bg-gray-50 border border-gray-200 p-4 text-sm text-gray-700">
            No operations found. Create an operation in the Operations tab before adding a contract.
          </div>
        )}
        {operationsError && (
          <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-sm text-amber-800 flex items-center justify-between gap-2">
            <span>Unable to load operations. Please try again.</span>
            <button
              type="button"
              onClick={() => refetchOperations()}
              className="px-2 py-1 text-xs font-medium text-amber-800 bg-amber-100 hover:bg-amber-200 rounded"
            >
              Retry
            </button>
          </div>
        )}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Operation</label>
          <select
            value={operationCode}
            onChange={(e) => handleOperationChange(e.target.value)}
            disabled={isEdit || operationsLoading || createDisabledByNoOps}
            required
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500 disabled:bg-gray-100 disabled:text-gray-600"
          >
            <option value="">
              {operationsLoading ? "Loading operations…" : "Select operation…"}
            </option>
            {operationOptions.map((o) => (
              <option key={o.operationCode} value={o.operationCode}>
                {o.operationCode}
                {o.canonicalVersion ? ` (${o.canonicalVersion})` : ""}
              </option>
            ))}
          </select>
          {isEdit && (
            <p className="text-xs text-gray-500 mt-1">Operation cannot be changed when editing.</p>
          )}
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Canonical version</label>
          <input
            type="text"
            value={canonicalVersion}
            onChange={(e) => setCanonicalVersion(e.target.value)}
            placeholder="v1"
            disabled={isEdit}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500 disabled:bg-gray-100 disabled:text-gray-600"
          />
          {isEdit && (
            <p className="text-xs text-gray-500 mt-1">Canonical version cannot be changed when editing.</p>
          )}
        </div>
        {!isEdit && operationCode && canonicalVersion && (
          <div>
            <button
              type="button"
              onClick={handleCloneCanonical}
              className="px-3 py-1.5 text-sm font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-lg"
            >
              Clone canonical contract
            </button>
          </div>
        )}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Request schema (JSON)</label>
          <textarea
            value={requestSchemaText}
            onChange={(e) => setRequestSchemaText(e.target.value)}
            rows={6}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
            placeholder='{"type": "object", "properties": {}}'
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Response schema (JSON)</label>
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
            disabled={isLoading || (!isEdit && !canCreate)}
            className="px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 disabled:opacity-50 rounded-lg"
          >
            {isLoading ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}
