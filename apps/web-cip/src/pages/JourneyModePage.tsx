import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getAdminPlatformFeatures,
  getAdminPlatformPhases,
  updateCurrentPlatformPhase,
  updatePlatformFeatureOverride,
} from "../api/endpoints";

type OverrideOption = "INHERIT" | "ENABLED" | "DISABLED";

function toIsEnabled(value: OverrideOption): boolean | null {
  if (value === "ENABLED") return true;
  if (value === "DISABLED") return false;
  return null;
}

export function JourneyModePage() {
  const queryClient = useQueryClient();
  const [selectedPhase, setSelectedPhase] = useState<string>("");

  const featuresQuery = useQuery({
    queryKey: ["platform-features", "admin"],
    queryFn: getAdminPlatformFeatures,
    staleTime: 60_000,
  });
  const phasesQuery = useQuery({
    queryKey: ["platform-phases", "admin"],
    queryFn: getAdminPlatformPhases,
    staleTime: 60_000,
  });

  const applyPhase = useMutation({
    mutationFn: (phaseCode: string) => updateCurrentPlatformPhase(phaseCode),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["platform-features", "admin"] }),
        queryClient.invalidateQueries({ queryKey: ["platform-phases", "admin"] }),
      ]);
    },
  });

  const updateFeature = useMutation({
    mutationFn: (payload: { featureCode: string; isEnabled: boolean | null }) =>
      updatePlatformFeatureOverride(payload.featureCode, { isEnabled: payload.isEnabled }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["platform-features", "admin"] });
    },
  });

  const currentPhase = featuresQuery.data?.currentPhase ?? "";
  const selected = selectedPhase || currentPhase;
  const rows = featuresQuery.data?.features ?? [];
  const effective = featuresQuery.data?.effectiveFeatures ?? {};
  const isBusy = applyPhase.isPending || updateFeature.isPending;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Journey Mode</h1>
          <p className="text-sm text-slate-600">
            Control product rollout by phase and per-feature overrides.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            void Promise.all([featuresQuery.refetch(), phasesQuery.refetch()]);
          }}
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Refresh flags
        </button>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Current phase
            </label>
            <select
              value={selected}
              onChange={(e) => setSelectedPhase(e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm"
            >
              {(phasesQuery.data ?? []).map((phase) => (
                <option key={phase.phaseCode} value={phase.phaseCode}>
                  {phase.phaseCode} - {phase.phaseName}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            disabled={!selected || selected === currentPhase || isBusy}
            onClick={() => applyPhase.mutate(selected)}
            className="rounded-lg bg-slate-700 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            Apply Phase
          </button>
          <div className="text-xs text-slate-500">
            Active phase: <span className="font-semibold">{currentPhase || "not set"}</span>
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white overflow-hidden">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Feature</th>
              <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Override</th>
              <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Effective</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {rows.map((row) => {
              const state = (row.overrideState ?? "INHERIT") as OverrideOption;
              const enabled = !!effective[row.featureCode];
              return (
                <tr key={row.featureCode}>
                  <td className="px-4 py-3 text-sm">
                    <div className="font-medium text-slate-900">{row.featureCode}</div>
                    {row.description ? (
                      <div className="text-xs text-slate-500">{row.description}</div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 text-sm">
                    <select
                      value={state}
                      disabled={isBusy}
                      onChange={(e) =>
                        updateFeature.mutate({
                          featureCode: row.featureCode,
                          isEnabled: toIsEnabled(e.target.value as OverrideOption),
                        })
                      }
                      className="rounded-md border border-slate-300 px-2 py-1 text-sm"
                    >
                      <option value="INHERIT">Inherit</option>
                      <option value="ENABLED">Enabled</option>
                      <option value="DISABLED">Disabled</option>
                    </select>
                  </td>
                  <td className="px-4 py-3 text-sm">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${
                        enabled
                          ? "bg-emerald-100 text-emerald-800"
                          : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {enabled ? "Enabled" : "Disabled"}
                    </span>
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr>
                <td className="px-4 py-6 text-sm text-slate-500" colSpan={3}>
                  No platform features found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
