import { useState, useEffect } from "react";
import { ModalShell } from "./ModalShell";
import type { Operation, OperationDirectionPolicy, OperationAiPresentationMode } from "../../types";

function _normalizeDirectionPolicy(
  v: string | undefined
): OperationDirectionPolicy | "" {
  if (!v || !v.trim()) return "";
  const u = v.toUpperCase().trim();
  if (u === "PROVIDER_RECEIVES_ONLY") return "PROVIDER_RECEIVES_ONLY";
  if (u === "TWO_WAY") return "TWO_WAY";
  if (v.toLowerCase() === "service_outbound_only") return "PROVIDER_RECEIVES_ONLY";
  if (v.toLowerCase() === "exchange_bidirectional") return "TWO_WAY";
  return "";
}

const DIRECTION_POLICY_OPTIONS: {
  value: OperationDirectionPolicy | "";
  label: string;
  description?: string;
}[] = [
  {
    value: "PROVIDER_RECEIVES_ONLY",
    label: "INBOUND (provider receives)",
    description: "Provider receives requests.",
  },
  {
    value: "TWO_WAY",
    label: "BOTH",
    description: "Either direction.",
  },
];

interface OperationModalProps {
  open: boolean;
  onClose: () => void;
  initialValues?: Operation | null;
  aiFormatterEnabled?: boolean;
  onSave: (payload: {
    operation_code: string;
    description?: string;
    canonical_version?: string;
    is_async_capable?: boolean;
    is_active?: boolean;
    direction_policy?: OperationDirectionPolicy;
    ai_presentation_mode?: OperationAiPresentationMode;
    ai_formatter_prompt?: string;
    ai_formatter_model?: string;
  }) => Promise<void>;
}

const AI_MODE_OPTIONS: { value: OperationAiPresentationMode; label: string }[] = [
  { value: "RAW_ONLY", label: "Off (RAW_ONLY)" },
  { value: "RAW_AND_FORMATTED", label: "Raw + AI summary" },
  { value: "FORMAT_ONLY", label: "AI-only answer" },
];

export function OperationModal({
  open,
  onClose,
  initialValues,
  aiFormatterEnabled = true,
  onSave,
}: OperationModalProps) {
  const [operationCode, setOperationCode] = useState("");
  const [description, setDescription] = useState("");
  const [canonicalVersion, setCanonicalVersion] = useState("v1");
  const [directionPolicy, setDirectionPolicy] = useState<OperationDirectionPolicy | "">("TWO_WAY");
  const [isAsyncCapable, setIsAsyncCapable] = useState(false);
  const [isActive, setIsActive] = useState(true);
  const [aiPresentationMode, setAiPresentationMode] = useState<OperationAiPresentationMode>("RAW_ONLY");
  const [aiFormatterPrompt, setAiFormatterPrompt] = useState("");
  const [aiFormatterModel, setAiFormatterModel] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isEdit = !!initialValues;
  const showAiFormatterSection = isEdit || aiFormatterEnabled;

  useEffect(() => {
    if (open) {
      setOperationCode(initialValues?.operationCode ?? "");
      setDescription(initialValues?.description ?? "");
      setCanonicalVersion(initialValues?.canonicalVersion ?? "v1");
      setDirectionPolicy(_normalizeDirectionPolicy(initialValues?.directionPolicy) || "TWO_WAY");
      setIsAsyncCapable(initialValues?.isAsyncCapable ?? false);
      setIsActive(initialValues?.isActive !== false);
      setAiPresentationMode(initialValues?.aiPresentationMode ?? "RAW_ONLY");
      setAiFormatterPrompt(initialValues?.aiFormatterPrompt ?? "");
      setAiFormatterModel(initialValues?.aiFormatterModel ?? "");
      setError(null);
    }
  }, [open, initialValues]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const code = operationCode.trim().toUpperCase();
    if (!code) {
      setError("Operation code is required.");
      return;
    }
    setIsLoading(true);
    try {
      const payload: {
        operation_code: string;
        description?: string;
        canonical_version?: string;
        direction_policy?: OperationDirectionPolicy;
        is_async_capable?: boolean;
        is_active?: boolean;
        ai_presentation_mode?: OperationAiPresentationMode;
        ai_formatter_prompt?: string;
        ai_formatter_model?: string;
      } = {
        operation_code: code,
        description: description.trim() || undefined,
        canonical_version: canonicalVersion.trim() || undefined,
        direction_policy: directionPolicy || "TWO_WAY",
        is_async_capable: isAsyncCapable,
        is_active: isActive,
      };
      if (showAiFormatterSection) {
        payload.ai_presentation_mode = aiPresentationMode;
        payload.ai_formatter_prompt = aiFormatterPrompt.trim() || undefined;
        payload.ai_formatter_model = aiFormatterModel.trim() || undefined;
      }
      await onSave(payload);
      onClose();
    } catch (err) {
      setError((err as Error)?.message ?? "Failed to save operation.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <ModalShell
      open={open}
      onClose={onClose}
      title={isEdit ? "Edit Operation" : "Create Operation"}
      panelClassName="relative w-full max-w-5xl bg-white rounded-lg shadow-xl mx-4 max-h-[90vh] overflow-y-auto"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div
          className={`grid grid-cols-1 gap-4 items-start ${showAiFormatterSection ? "md:grid-cols-2" : ""}`}
        >
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
                {isEdit && (
                  <p className="text-xs text-gray-500 mt-1">Code cannot be changed when editing.</p>
                )}
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                <input
                  type="text"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Optional"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Direction policy</label>
                <select
                  value={directionPolicy}
                  onChange={(e) =>
                    setDirectionPolicy(e.target.value as OperationDirectionPolicy | "")
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
                >
                  {DIRECTION_POLICY_OPTIONS.map((opt) => (
                    <option key={opt.value || "_empty"} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  INBOUND: provider receives. BOTH: either direction.
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Canonical version</label>
                <input
                  type="text"
                  value={canonicalVersion}
                  onChange={(e) => setCanonicalVersion(e.target.value)}
                  placeholder="v1"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
                />
              </div>
            </div>
            <div className="space-y-2">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={isAsyncCapable}
                  onChange={(e) => setIsAsyncCapable(e.target.checked)}
                  className="rounded border-gray-300 text-slate-600 focus:ring-slate-500"
                />
                <span className="text-sm text-gray-700">Async capable</span>
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={isActive}
                  onChange={(e) => setIsActive(e.target.checked)}
                  className="rounded border-gray-300 text-slate-600 focus:ring-slate-500"
                />
                <span className="text-sm text-gray-700">Active</span>
              </label>
            </div>
          </div>
          {showAiFormatterSection && (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 space-y-3">
              <div className="text-sm font-medium text-slate-700">AI Formatter</div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Mode</label>
                <select
                  value={aiPresentationMode}
                  onChange={(e) => setAiPresentationMode(e.target.value as OperationAiPresentationMode)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
                >
                  {AI_MODE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Prompt</label>
                <textarea
                  value={aiFormatterPrompt}
                  onChange={(e) => setAiFormatterPrompt(e.target.value)}
                  rows={3}
                  placeholder="Optional operation-specific formatting prompt"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Model (optional)</label>
                <input
                  type="text"
                  value={aiFormatterModel}
                  onChange={(e) => setAiFormatterModel(e.target.value)}
                  placeholder="anthropic.claude-3-haiku-20240307-v1:0"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
                />
              </div>
            </div>
          )}
        </div>
        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
            {error}
          </div>
        )}
        <div className="flex justify-end gap-2 pt-2">
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
    </ModalShell>
  );
}
