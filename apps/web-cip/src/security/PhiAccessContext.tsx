import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useOktaAuth } from "@okta/okta-react";
import { isOktaEnabled } from "../config/oktaConfig";

type PhiAccessContextValue = {
  phiApproved: boolean;
  phiModeEnabled: boolean;
  reason: string;
  setPhiMode: (enabled: boolean, reason?: string) => void;
};

const DEFAULT_CONTEXT_VALUE: PhiAccessContextValue = {
  phiApproved: false,
  phiModeEnabled: false,
  reason: "",
  setPhiMode: () => undefined,
};

const PhiAccessContext = createContext<PhiAccessContextValue>(DEFAULT_CONTEXT_VALUE);

const DEFAULT_GROUP = "integrationhub-phi-approved";
const AUTO_DISABLE_MS = 15 * 60 * 1000;

function extractGroups(claims: Record<string, unknown>): string[] {
  const raw = claims.groups ?? claims.group;
  if (Array.isArray(raw)) return raw.map((v) => String(v).trim()).filter(Boolean);
  if (typeof raw === "string") return raw.split(/[\s,]+/).map((v) => v.trim()).filter(Boolean);
  return [];
}

function PhiAccessProviderInner({ children }: { children: ReactNode }) {
  const { authState } = useOktaAuth();
  const claims = ((authState?.accessToken?.claims ?? authState?.idToken?.claims ?? {}) as Record<string, unknown>);
  const requiredGroup = (import.meta.env.VITE_PHI_APPROVED_GROUP as string | undefined)?.trim() || DEFAULT_GROUP;
  const groups = extractGroups(claims);
  const phiApproved = groups.some((g) => g.toLowerCase() === requiredGroup.toLowerCase());

  const [phiModeEnabled, setPhiModeEnabled] = useState(false);
  const [reason, setReason] = useState('');

  useEffect(() => {
    if (!phiApproved && phiModeEnabled) {
      setPhiModeEnabled(false);
      setReason('');
    }
  }, [phiApproved, phiModeEnabled]);

  useEffect(() => {
    if (!phiModeEnabled) return;
    const timer = window.setTimeout(() => {
      setPhiModeEnabled(false);
      setReason('');
    }, AUTO_DISABLE_MS);
    return () => window.clearTimeout(timer);
  }, [phiModeEnabled]);

  const value = useMemo<PhiAccessContextValue>(() => ({
    phiApproved,
    phiModeEnabled: phiApproved && phiModeEnabled,
    reason,
    setPhiMode: (enabled, nextReason) => {
      if (!phiApproved) return;
      setPhiModeEnabled(enabled);
      if (enabled) setReason((nextReason || '').trim());
      else setReason('');
    },
  }), [phiApproved, phiModeEnabled, reason]);

  return <PhiAccessContext.Provider value={value}>{children}</PhiAccessContext.Provider>;
}

export function PhiAccessProvider({ children }: { children: ReactNode }) {
  if (!isOktaEnabled()) {
    return <PhiAccessContext.Provider value={DEFAULT_CONTEXT_VALUE}>{children}</PhiAccessContext.Provider>;
  }
  return <PhiAccessProviderInner>{children}</PhiAccessProviderInner>;
}

export function usePhiAccess(): PhiAccessContextValue {
  return useContext(PhiAccessContext);
}
