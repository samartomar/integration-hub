import { createContext, useContext, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { getAdminPlatformFeatures } from "../api/endpoints";
import { isFeatureEnabled } from "./featureFlags";

type FeatureFlagsContextValue = {
  currentPhase: string | null;
  effectiveFeatures: Record<string, boolean>;
  isLoading: boolean;
  refresh: () => Promise<unknown>;
};

const FeatureFlagsContext = createContext<FeatureFlagsContextValue | null>(null);

export function FeatureFlagProvider({ children }: { children: ReactNode }) {
  const isCallbackRoute =
    typeof window !== "undefined" && window.location.pathname === "/callback";
  const query = useQuery({
    queryKey: ["platform-features", "admin"],
    queryFn: getAdminPlatformFeatures,
    enabled: !isCallbackRoute,
    staleTime: 60_000,
  });

  const value: FeatureFlagsContextValue = {
    currentPhase: query.data?.currentPhase ?? null,
    effectiveFeatures: query.data?.effectiveFeatures ?? {},
    isLoading: query.isLoading,
    refresh: async () => query.refetch(),
  };

  return (
    <FeatureFlagsContext.Provider value={value}>
      {children}
    </FeatureFlagsContext.Provider>
  );
}

export function useFeature(featureCode: string): boolean {
  const ctx = useContext(FeatureFlagsContext);
  if (!ctx) return false;
  return isFeatureEnabled(ctx.effectiveFeatures, featureCode);
}

export function useFeatureFlags() {
  const ctx = useContext(FeatureFlagsContext);
  if (!ctx) {
    throw new Error("useFeatureFlags must be used inside FeatureFlagProvider");
  }
  return ctx;
}

export function FeatureUnavailablePage({ title }: { title?: string }) {
  return (
    <div className="min-h-[50vh] flex items-center justify-center p-6">
      <div className="max-w-xl rounded-lg border border-amber-200 bg-amber-50 p-6 text-center">
        <h2 className="text-xl font-semibold text-amber-900">
          {title ?? "Feature not enabled"}
        </h2>
        <p className="mt-2 text-sm text-amber-800">
          This feature is not enabled in the current rollout phase.
        </p>
      </div>
    </div>
  );
}

export function FeatureRoute({
  featureCode,
  children,
}: {
  featureCode: string;
  children: ReactNode;
}) {
  const { isLoading } = useFeatureFlags();
  const enabled = useFeature(featureCode);
  if (isLoading) {
    return <div className="p-6 text-sm text-slate-600">Loading rollout settings...</div>;
  }
  if (!enabled) {
    return <FeatureUnavailablePage />;
  }
  return <>{children}</>;
}
