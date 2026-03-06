import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getVendorMappings,
  upsertVendorMapping,
  getVendorOperationsCatalog,
} from "../../api/endpoints";
import type { VendorMapping, VendorOperationCatalogItem, MappingDirection } from "../../types";

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

const DIRECTION_OPTIONS: { value: MappingDirection; label: string; help: string }[] = [
  { value: "TO_CANONICAL", label: "Source -> Canonical Request", help: "Maps source payload → canonical request format" },
  { value: "FROM_CANONICAL", label: "Canonical -> Target Request", help: "Maps canonical request → target endpoint payload" },
  { value: "TO_CANONICAL_RESPONSE", label: "Target -> Canonical (Response)", help: "Maps target response → canonical response format" },
  { value: "FROM_CANONICAL_RESPONSE", label: "Canonical -> Source (Response)", help: "Maps canonical response → source response format" },
];

function getDirectionLabel(value: MappingDirection): string {
  return DIRECTION_OPTIONS.find((o) => o.value === value)?.label ?? value;
}

interface VendorMappingModalProps {
  open: boolean;
  onClose: () => void;
  initialValues: VendorMapping | null;
  catalogItems: VendorOperationCatalogItem[];
  onSave: (payload: {
    operationCode: string;
    canonicalVersion: string;
    direction: MappingDirection;
    mapping: Record<string, unknown>;
    isActive?: boolean;
  }) => Promise<void>;
}

function VendorMappingModal({
  open,
  onClose,
  initialValues,
  catalogItems,
  onSave,
}: VendorMappingModalProps) {
  const [operationCode, setOperationCode] = useState("");
  const [canonicalVersion, setCanonicalVersion] = useState("");
  const [direction, setDirection] = useState<MappingDirection>("TO_CANONICAL");
  const [mappingText, setMappingText] = useState("{}");
  const [isActive, setIsActive] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mappingError, setMappingError] = useState<string | null>(null);
  const isEdit = !!initialValues;

  useEffect(() => {
    if (open) {
      setOperationCode(initialValues?.operationCode ?? "");
      setCanonicalVersion(initialValues?.canonicalVersion ?? "v1");
      setDirection(initialValues?.direction ?? "TO_CANONICAL");
      setMappingText(
        initialValues?.mapping
          ? JSON.stringify(initialValues.mapping, null, 2)
          : "{}"
      );
      setIsActive(initialValues?.isActive !== false);
      setError(null);
      setMappingError(null);
    }
  }, [open, initialValues]);

  // Auto-fill canonicalVersion when operation changes (for add mode)
  useEffect(() => {
    if (open && !isEdit && operationCode) {
      const item = catalogItems.find(
        (c) => c.operationCode.toUpperCase() === operationCode.toUpperCase()
      );
      if (item?.canonicalVersion) {
        setCanonicalVersion(item.canonicalVersion);
      } else if (!canonicalVersion) {
        setCanonicalVersion("v1");
      }
    }
  }, [open, isEdit, operationCode, catalogItems]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setMappingError(null);

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

    const mapping = parseJsonSafe(mappingText);
    if (mapping === null) {
      setMappingError("Mapping must be valid JSON object.");
      return;
    }

    setIsLoading(true);
    try {
      await onSave({
        operationCode: opCode,
        canonicalVersion: version,
        direction,
        mapping: mapping ?? {},
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
            {isEdit ? "Edit Mapping" : "Add Mapping"}
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
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Operation</label>
            <select
              value={operationCode}
              onChange={(e) => setOperationCode(e.target.value)}
              disabled={isEdit}
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500 disabled:bg-gray-100 disabled:text-gray-600"
            >
              <option value="">Select operation</option>
              {catalogItems.map((op) => (
                <option key={op.operationCode} value={op.operationCode}>
                  {op.operationCode}
                  {op.description ? ` — ${op.description}` : ""}
                </option>
              ))}
            </select>
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
            <p className="text-xs text-gray-500 mt-0.5">
              Auto-filled from selected operation. Edit if needed.
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Direction</label>
            <fieldset disabled={isEdit}>
              <div className="space-y-2">
                {DIRECTION_OPTIONS.map((opt) => (
                  <label
                  key={opt.value}
                  className={`flex items-start gap-2 p-2 rounded-lg border cursor-pointer ${
                    direction === opt.value
                      ? "border-slate-500 bg-slate-50"
                      : "border-gray-200 hover:border-gray-300"
                  }`}
                >
                  <input
                    type="radio"
                    name="direction"
                    value={opt.value}
                    checked={direction === opt.value}
                    onChange={() => setDirection(opt.value)}
                    className="mt-1 border-gray-300 text-slate-600 focus:ring-slate-500"
                  />
                  <div>
                    <span className="text-sm font-medium text-gray-900">{opt.label}</span>
                    <p className="text-xs text-gray-500">{opt.help}</p>
                  </div>
                </label>
              ))}
              </div>
            </fieldset>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Mapping (JSON)</label>
            <textarea
              value={mappingText}
              onChange={(e) => setMappingText(e.target.value)}
              rows={6}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
              placeholder='{"yourField": "canonicalField"}'
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
          {mappingError && (
            <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-sm text-amber-800">
              {mappingError}
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

export function MappingsTab() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<VendorMapping | null>(null);

  const { data: catalogData, isLoading: catalogLoading } = useQuery({
    queryKey: ["vendor-operations-catalog"],
    queryFn: getVendorOperationsCatalog,
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
  });
  const catalogItems = catalogData?.items ?? [];
  const noAdminApprovedOps = !catalogLoading && catalogItems.length === 0;

  const { data: mappingsData, isLoading, error } = useQuery({
    queryKey: ["vendor-mappings"],
    queryFn: () => getVendorMappings(),
    retry: (_, err) => (err as { response?: { status?: number } })?.response?.status !== 404,
  });

  const upsert = useMutation({
    mutationFn: upsertVendorMapping,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vendor-mappings"] });
    },
  });

  const mappings = mappingsData?.mappings ?? [];

  const handleSave = async (payload: {
    operationCode: string;
    canonicalVersion: string;
    direction: MappingDirection;
    mapping: Record<string, unknown>;
    isActive?: boolean;
  }) => {
    await upsert.mutateAsync(payload);
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-800">My Mappings</h3>
        <button
          type="button"
          onClick={() => {
            setEditing(null);
            setModalOpen(true);
          }}
          disabled={noAdminApprovedOps}
          className="px-3 py-1.5 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Add Mapping
        </button>
      </div>
      {noAdminApprovedOps && (
        <p className="text-sm text-amber-700 mb-4">
          No admin-approved operations are available for this vendor. Add operations in Supported Ops first.
        </p>
      )}

      <p className="text-xs text-gray-500 mb-4">
        <strong>Source → Canonical Request:</strong> source payload → canonical format.{" "}
        <strong>Canonical → Target Request:</strong> canonical → target endpoint.{" "}
        <strong>Target → Canonical (Response):</strong> target response → canonical.{" "}
        <strong>Canonical → Source (Response):</strong> canonical → source response.
      </p>

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-10 bg-gray-100 rounded animate-pulse" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-amber-600">Unable to load mappings.</p>
      ) : mappings.length === 0 ? (
        <p className="text-sm text-gray-500 py-4">No mappings yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b">
                <th className="py-2">Operation</th>
                <th className="py-2">Version</th>
                <th className="py-2">Direction</th>
                <th className="py-2">Active</th>
                <th className="py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {mappings.map((m) => (
                <tr key={`${m.operationCode}-${m.canonicalVersion}-${m.direction}`} className="border-b border-gray-100">
                  <td className="py-2 font-mono">{m.operationCode}</td>
                  <td className="py-2 text-gray-700">{m.canonicalVersion ?? "—"}</td>
                  <td className="py-2">
                    <span className="text-gray-700" title={m.direction}>
                      {getDirectionLabel(m.direction)}
                    </span>
                  </td>
                  <td className="py-2">
                    <span
                      className={`px-2 py-0.5 rounded text-xs ${
                        m.isActive !== false ? "bg-emerald-100 text-emerald-800" : "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {m.isActive !== false ? "Yes" : "No"}
                    </span>
                  </td>
                  <td className="py-2 text-right">
                    <button
                      type="button"
                      onClick={() => {
                        setEditing(m);
                        setModalOpen(true);
                      }}
                      className="text-slate-600 hover:text-slate-900 text-sm font-medium"
                    >
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <VendorMappingModal
        open={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        initialValues={editing}
        catalogItems={catalogItems}
        onSave={handleSave}
      />
    </div>
  );
}
