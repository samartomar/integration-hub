import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { listFeatureGates, updateFeatureGate } from "../api/endpoints";

interface FeaturesModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const FEATURE_GATE_LABELS: Record<string, string> = {
  GATE_ALLOWLIST_RULE: "Allowlist rules",
  GATE_ENDPOINT_CONFIG: "Endpoint configuration",
  GATE_MAPPING_CONFIG: "Mappings (request/response)",
  GATE_VENDOR_CONTRACT_CHANGE: "Vendor contract overrides",
  ai_formatter_enabled: "AI formatter",
};

export function FeaturesModal({ isOpen, onClose }: FeaturesModalProps) {
  const queryClient = useQueryClient();
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const { data: gates, isLoading, error } = useQuery({
    queryKey: ["registry-feature-gates"],
    queryFn: listFeatureGates,
    enabled: isOpen,
  });

  const updateMutation = useMutation({
    mutationFn: ({ gateKey, enabled }: { gateKey: string; enabled: boolean }) =>
      updateFeatureGate(gateKey, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["registry-feature-gates"] });
      setToastMsg(
        "Changes apply to new vendor updates immediately. Existing PENDING change-requests are unaffected."
      );
      setTimeout(() => setToastMsg(null), 5000);
    },
  });

  const sortedItems = [...(gates ?? [])].sort((a, b) =>
    (FEATURE_GATE_LABELS[a.gateKey] ?? a.gateKey).localeCompare(
      FEATURE_GATE_LABELS[b.gateKey] ?? b.gateKey
    )
  );

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/50"
        aria-hidden
      />
      <div
        className="relative w-full max-w-2xl bg-white rounded-lg shadow-xl p-6 mx-4"
        role="dialog"
        aria-modal="true"
        aria-labelledby="features-title"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 id="features-title" className="text-xl font-semibold text-gray-900">
            Features
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 p-1 rounded"
            aria-label="Close features"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        {toastMsg && (
          <div
            role="alert"
            className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-800"
          >
            {toastMsg}
          </div>
        )}
        {isLoading && (
          <div className="py-8 text-center text-sm text-gray-500">Loading…</div>
        )}
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
            {(error as Error).message}
          </div>
        )}
        {!isLoading && !error && (
          <div className="overflow-x-auto rounded-lg border border-slate-200">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b bg-gray-50">
                  <th className="py-2 px-4">Feature</th>
                  <th className="py-2 px-4">Gate key</th>
                  <th className="py-2 px-4">Requires approval?</th>
                </tr>
              </thead>
              <tbody>
                {sortedItems.map((gate) => {
                  const label = FEATURE_GATE_LABELS[gate.gateKey] ?? gate.gateKey;
                  return (
                    <tr key={gate.gateKey} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="py-2 px-4 font-medium text-gray-900">{label}</td>
                      <td className="py-2 px-4 font-mono text-gray-600">{gate.gateKey}</td>
                      <td className="py-2 px-4">
                        <button
                          type="button"
                          role="switch"
                          aria-checked={gate.enabled}
                          aria-label={`${label}: ${gate.enabled ? "requires approval" : "applies immediately"}`}
                          onClick={() => updateMutation.mutate({ gateKey: gate.gateKey, enabled: !gate.enabled })}
                          disabled={updateMutation.isPending}
                          className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 disabled:opacity-50 ${
                            gate.enabled ? "bg-emerald-600" : "bg-gray-200"
                          }`}
                        >
                          <span
                            className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition ${
                              gate.enabled ? "translate-x-5" : "translate-x-1"
                            }`}
                          />
                        </button>
                        <span className="ml-2 text-gray-500">
                          {gate.enabled ? "ON" : "OFF"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {!isLoading && !error && sortedItems.length > 0 && (
          <p className="mt-4 text-xs text-gray-500">
            {sortedItems.map((g) => (
              <span key={g.gateKey} title={g.description} className="block mt-1">
                <strong>{FEATURE_GATE_LABELS[g.gateKey] ?? g.gateKey}:</strong> {g.description}
              </span>
            ))}
          </p>
        )}
      </div>
    </div>
  );
}
