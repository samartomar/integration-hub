import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listContracts,
  upsertContract,
  setOperationCanonicalVersion,
} from "../api/endpoints";
import type { Operation } from "../types";

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

const MINIMAL_SCHEMA: Record<string, unknown> = {
  type: "object",
  properties: {},
};

/** Suggest next version (v2, v3, v4, …) from existing version strings */
function suggestNextVersion(versions: string[]): string {
  const nums = versions
    .map((v) => {
      const m = v.match(/^v(\d+)$/i);
      return m ? parseInt(m[1], 10) : 0;
    })
    .filter((n) => n > 0);
  const max = nums.length > 0 ? Math.max(...nums) : 0;
  return `v${max + 1}`;
}

export interface CanonicalContractEditorProps {
  operation: Operation;
  onOperationUpdated?: (newDefaultVersion: string) => void;
  onSelectedVersionChange?: (version: string) => void;
}

type ContractVersionData = {
  requestSchema: Record<string, unknown>;
  responseSchema: Record<string, unknown>;
  isActive: boolean;
};

export function CanonicalContractEditor({
  operation,
  onOperationUpdated,
  onSelectedVersionChange,
}: CanonicalContractEditorProps) {
  const queryClient = useQueryClient();
  const opCode = operation.operationCode;
  const operationDefaultVersion = operation.canonicalVersion ?? "v1";

  const [selectedVersion, setSelectedVersion] = useState<string>("");
  const [contractsByVersion, setContractsByVersion] = useState<
    Record<string, ContractVersionData>
  >({});
  const [draftRequestJson, setDraftRequestJson] = useState("{}");
  const [draftResponseJson, setDraftResponseJson] = useState("{}");
  const [schemaError, setSchemaError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedToast, setSavedToast] = useState<string | null>(null);
  const [showNewVersionModal, setShowNewVersionModal] = useState(false);
  const autoCreateAttempted = useRef(false);

  const { data, isLoading, error: fetchError, refetch } = useQuery({
    queryKey: ["registry-contracts", opCode],
    queryFn: () =>
      listContracts({
        operationCode: opCode,
        isActive: true,
      }),
    enabled: !!opCode,
  });

  const contracts = data?.items ?? [];
  const versionList = useMemo(() => {
    const fromApi = contracts.map((c) => c.canonicalVersion ?? "v1");
    const fromLocal = Object.keys(contractsByVersion);
    const combined = [...new Set([...fromApi, ...fromLocal])].sort((a, b) => {
      const na = parseInt((a.match(/^v(\d+)$/i) ?? [])[1] ?? "0", 10);
      const nb = parseInt((b.match(/^v(\d+)$/i) ?? [])[1] ?? "0", 10);
      return na - nb;
    });
    return combined;
  }, [contracts, contractsByVersion]);

  /** Auto-create default canonical version v1 when none exist */
  useEffect(() => {
    autoCreateAttempted.current = false;
  }, [opCode]);

  useEffect(() => {
    if (!opCode || isLoading || fetchError || contracts.length > 0 || autoCreateAttempted.current) return;
    autoCreateAttempted.current = true;
    upsertContract({
      operation_code: opCode,
      canonical_version: "v1",
      request_schema: { ...MINIMAL_SCHEMA },
      response_schema: {},
      is_active: true,
    })
      .then(() => refetch())
      .catch(() => {
        autoCreateAttempted.current = false;
      });
  }, [opCode, isLoading, fetchError, contracts.length, refetch]);

  /** Initial load: populate contractsByVersion from API */
  useEffect(() => {
    if (contracts.length === 0 && Object.keys(contractsByVersion).length === 0)
      return;

    const next: Record<string, ContractVersionData> = {};
    for (const c of contracts) {
      const v = c.canonicalVersion ?? "v1";
      next[v] = {
        requestSchema:
          c.requestSchema && typeof c.requestSchema === "object"
            ? c.requestSchema
            : {},
        responseSchema:
          c.responseSchema != null &&
          typeof c.responseSchema === "object" &&
          Object.keys(c.responseSchema).length > 0
            ? c.responseSchema
            : {},
        isActive: c.isActive !== false,
      };
    }
    setContractsByVersion((prev) => {
      const merged = { ...prev };
      for (const v of Object.keys(next)) {
        merged[v] = next[v];
      }
      return merged;
    });

    if (!selectedVersion || !versionList.includes(selectedVersion)) {
      const nextSel =
        versionList.length > 0 && versionList.includes(operationDefaultVersion)
          ? operationDefaultVersion
          : versionList[0] ?? "";
      if (nextSel) {
        setSelectedVersion(nextSel);
        onSelectedVersionChange?.(nextSel);
      }
    }
  }, [contracts]);

  useEffect(() => {
    onSelectedVersionChange?.(selectedVersion);
  }, [selectedVersion, onSelectedVersionChange]);

  /** When selectedVersion changes, reload drafts from contractsByVersion */
  useEffect(() => {
    if (!selectedVersion) return;
    const data = contractsByVersion[selectedVersion];
    if (data) {
      setDraftRequestJson(
        Object.keys(data.requestSchema).length > 0
          ? JSON.stringify(data.requestSchema, null, 2)
          : "{}"
      );
      setDraftResponseJson(
        Object.keys(data.responseSchema).length > 0
          ? JSON.stringify(data.responseSchema, null, 2)
          : "{}"
      );
    } else {
      setDraftRequestJson("{}");
      setDraftResponseJson("{}");
    }
  }, [selectedVersion, contractsByVersion]);

  const upsert = useMutation({
    mutationFn: upsertContract,
    onSuccess: async (_, variables) => {
      setError(null);
      const ver = variables.canonical_version;
      const reqSchema = variables.request_schema;
      const respSchema = variables.response_schema;

      setContractsByVersion((prev) => ({
        ...prev,
        [ver]: {
          requestSchema: reqSchema,
          responseSchema:
            respSchema && Object.keys(respSchema).length > 0 ? respSchema : {},
          isActive: true,
        },
      }));

      setSavedToast(`Contract ${ver} saved.`);
      setTimeout(() => setSavedToast(null), 2500);

      queryClient.invalidateQueries({ queryKey: ["registry-contracts"] });
      queryClient.invalidateQueries({ queryKey: ["registry-operations"] });
      await refetch();
    },
  });

  const setDefaultVersion = useMutation({
    mutationFn: ({ operationCode, canonicalVersion }: { operationCode: string; canonicalVersion: string }) =>
      setOperationCanonicalVersion(operationCode, canonicalVersion),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["registry-operations"] });
      queryClient.invalidateQueries({ queryKey: ["registry-contracts"] });
      onOperationUpdated?.(variables.canonicalVersion);
      setSavedToast(`Default version updated to ${variables.canonicalVersion}.`);
      setTimeout(() => setSavedToast(null), 2500);
    },
  });

  /** Changing version: persist current drafts to contractsByVersion, then switch */
  const handleVersionChange = useCallback(
    (newVersion: string) => {
      if (selectedVersion) {
        const reqRes = parseJsonSafe(draftRequestJson);
        const resRes = parseJsonSafe(draftResponseJson);
        const reqSchema = reqRes.ok ? reqRes.data : {};
        const resSchema = resRes.ok && resRes.data ? resRes.data : {};
        setContractsByVersion((prev) => ({
          ...prev,
          [selectedVersion]: {
            requestSchema: reqSchema,
            responseSchema: resSchema,
            isActive: true,
          },
        }));
      }
      setSelectedVersion(newVersion);
      onSelectedVersionChange?.(newVersion);
    },
    [selectedVersion, draftRequestJson, draftResponseJson, onSelectedVersionChange]
  );

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSchemaError(null);

    const versionToSave = selectedVersion;
    if (!versionToSave) {
      setError("No version selected.");
      return;
    }

    const requestResult = parseJsonSafe(draftRequestJson);
    const responseResult = parseJsonSafe(draftResponseJson);
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

    const body = {
      operation_code: opCode,
      canonical_version: versionToSave,
      request_schema: reqSchema,
      response_schema:
        responseResult.data && Object.keys(responseResult.data).length > 0
          ? responseResult.data
          : undefined,
      is_active: true,
    };

    console.debug("Saving canonical contract", {
      operationCode: opCode,
      selectedVersion: versionToSave,
      bodySentToApi: body,
    });

    try {
      await upsert.mutateAsync(body);
    } catch (err) {
      setError((err as Error)?.message ?? "Failed to save.");
    }
  };

  const handleSetAsDefault = async () => {
    setError(null);
    try {
      await setDefaultVersion.mutateAsync({
        operationCode: opCode,
        canonicalVersion: selectedVersion,
      });
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { error?: { code?: string; message?: string } } }; message?: string };
      const apiMsg = ax.response?.data?.error?.message;
      const code = ax.response?.data?.error?.code;
      const msg =
        apiMsg ||
        (err as Error)?.message ||
        "Failed to set default version.";
      setError(
        code === "NO_ACTIVE_CONTRACT_FOR_VERSION"
          ? "Save the contract first, then set as default."
          : msg
      );
    }
  };

  const isDefaultVersion = selectedVersion === operationDefaultVersion;

  if (isLoading) {
    return (
      <div className="animate-pulse space-y-3">
        <div className="h-6 bg-gray-100 rounded w-1/2" />
        <div className="h-24 bg-gray-100 rounded" />
        <div className="h-24 bg-gray-100 rounded" />
      </div>
    );
  }

  if (fetchError) {
    return (
      <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-sm text-amber-800">
        Unable to load contracts: {(fetchError as Error)?.message ?? "Unknown error"}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-mono font-medium text-slate-800">{opCode}</span>
          <span className="text-slate-500">·</span>
          <span className="text-slate-600">Version: {selectedVersion}</span>
          <span className="text-slate-500">
            (Default: {operationDefaultVersion})
          </span>
          {isDefaultVersion && (
            <span className="inline-flex items-center rounded px-2 py-0.5 text-xs font-medium bg-sky-100 text-sky-800">
              Default
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <label className="text-xs font-medium text-gray-500">Canonical version</label>
        <select
          value={
            versionList.includes(selectedVersion) ? selectedVersion : versionList[0] ?? selectedVersion
          }
          onChange={(e) => handleVersionChange(e.target.value)}
          disabled={versionList.length === 0}
          className="px-2.5 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-slate-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
        >
          {versionList.length === 0 && (
            <option value={selectedVersion}>No versions yet</option>
          )}
          {versionList.map((v) => (
            <option key={v} value={v}>
              {v}
              {v === operationDefaultVersion ? " (default)" : ""}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => setShowNewVersionModal(true)}
          className="px-2.5 py-1.5 text-sm font-medium text-slate-700 border border-slate-300 rounded-lg hover:bg-slate-50"
        >
          New version
        </button>
      </div>

      {!isDefaultVersion && (
        <div>
          <button
            type="button"
            onClick={handleSetAsDefault}
            disabled={setDefaultVersion.isPending}
            className="text-xs font-medium text-sky-600 hover:text-sky-800 disabled:opacity-50"
          >
            {setDefaultVersion.isPending ? "Updating…" : "Set as default version"}
          </button>
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">
            Operation · Version (read-only)
          </label>
          <div className="px-3 py-2 text-sm font-mono bg-gray-50 rounded-lg border border-gray-200 text-gray-600">
            {opCode} · {selectedVersion}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Request schema (JSON)
          </label>
          <textarea
            value={draftRequestJson}
            onChange={(e) => setDraftRequestJson(e.target.value)}
            rows={8}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
            placeholder='{"type": "object", "properties": {}}'
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Response schema (JSON)
          </label>
          <textarea
            value={draftResponseJson}
            onChange={(e) => setDraftResponseJson(e.target.value)}
            rows={8}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
            placeholder='{"type": "object", "properties": {}}'
          />
        </div>

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

        {savedToast && (
          <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2 text-sm text-emerald-800">
            {savedToast}
          </div>
        )}
        <button
          type="submit"
          disabled={upsert.isPending}
          className="px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 disabled:opacity-50 rounded-lg"
        >
          {upsert.isPending ? "Saving…" : "Save"}
        </button>
      </form>

      <NewVersionModal
        open={showNewVersionModal}
        onClose={() => setShowNewVersionModal(false)}
        operation={operation}
        versionList={versionList}
        currentVersion={selectedVersion}
        currentRequestSchema={draftRequestJson}
        currentResponseSchema={draftResponseJson}
        onCreated={(newVersion, initialData) => {
          setContractsByVersion((prev) => ({
            ...prev,
            [newVersion]: initialData,
          }));
          setSelectedVersion(newVersion);
          onSelectedVersionChange?.(newVersion);
          setShowNewVersionModal(false);
        }}
      />
    </div>
  );
}

interface NewVersionModalProps {
  open: boolean;
  onClose: () => void;
  operation: Operation;
  versionList: string[];
  currentVersion: string;
  currentRequestSchema: string;
  currentResponseSchema: string;
  onCreated: (
    newVersion: string,
    initialData: ContractVersionData
  ) => void;
}

function NewVersionModal({
  open,
  onClose,
  operation: _operation,
  versionList,
  currentVersion,
  currentRequestSchema,
  currentResponseSchema,
  onCreated,
}: NewVersionModalProps) {
  const [versionInput, setVersionInput] = useState("");
  const [seedFrom, setSeedFrom] = useState<"copy" | "skeleton">("copy");
  const [error, setError] = useState<string | null>(null);

  const suggestedVersion = suggestNextVersion(versionList);

  useEffect(() => {
    if (open) {
      setVersionInput(suggestedVersion);
      setSeedFrom("copy");
      setError(null);
    }
  }, [open, suggestedVersion]);

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const ver = versionInput.trim();
    if (!ver) {
      setError("Version is required.");
      return;
    }
    if (versionList.includes(ver)) {
      setError(`Version "${ver}" already exists.`);
      return;
    }

    let reqSchema: Record<string, unknown>;
    let respSchema: Record<string, unknown>;

    if (seedFrom === "copy") {
      const reqRes = parseJsonSafe(currentRequestSchema);
      const resRes = parseJsonSafe(currentResponseSchema);
      if (!reqRes.ok) {
        setError(`Request schema: ${reqRes.error}`);
        return;
      }
      reqSchema =
        reqRes.data && Object.keys(reqRes.data).length > 0
          ? reqRes.data
          : { ...MINIMAL_SCHEMA };
      respSchema =
        resRes.ok && resRes.data && Object.keys(resRes.data).length > 0
          ? resRes.data
          : { ...MINIMAL_SCHEMA };
    } else {
      reqSchema = { ...MINIMAL_SCHEMA };
      respSchema = { ...MINIMAL_SCHEMA };
    }

    onCreated(ver, {
      requestSchema: reqSchema,
      responseSchema: respSchema,
      isActive: true,
    });
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40">
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6"
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-version-modal-title"
      >
        <h3 id="new-version-modal-title" className="text-lg font-semibold text-gray-900 mb-4">
          Create new canonical version
        </h3>
        <p className="text-sm text-slate-600 mb-4">
          The new version will be saved when you click Save. It is not persisted until then.
        </p>
        <form onSubmit={handleCreate} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Version</label>
            <input
              type="text"
              value={versionInput}
              onChange={(e) => setVersionInput(e.target.value)}
              placeholder="v2"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500"
            />
            <p className="mt-1 text-xs text-gray-500">
              Suggestion: {suggestedVersion}
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Seed from</label>
            <div className="space-y-2">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="seedFrom"
                  checked={seedFrom === "copy"}
                  onChange={() => setSeedFrom("copy")}
                  className="rounded"
                />
                <span className="text-sm">Copy from current version ({currentVersion})</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="seedFrom"
                  checked={seedFrom === "skeleton"}
                  onChange={() => setSeedFrom("skeleton")}
                  className="rounded"
                />
                <span className="text-sm">Minimal skeleton</span>
              </label>
            </div>
          </div>

          {error && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-3 py-1.5 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 rounded-lg"
            >
              Create
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
