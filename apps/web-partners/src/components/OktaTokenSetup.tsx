import { useEffect } from "react";
import { useOktaAuth } from "@okta/okta-react";
import { getActiveVendorCode, setActiveVendorCode } from "frontend-shared";
import { setAuthTokenProvider } from "../api/authTokenProvider";
import { isOktaEnabled } from "../config/oktaConfig";

/**
 * When Okta is enabled and user is authenticated, registers the token getter
 * so API clients can add Authorization: Bearer <token> to requests.
 * Renders nothing.
 */
export function OktaTokenSetup() {
  const oktaEnabled = isOktaEnabled();
  if (!oktaEnabled) return null;

  return <OktaTokenSetupInner />;
}

function OktaTokenSetupInner() {
  const { oktaAuth, authState } = useOktaAuth();
  const isAuthenticated = !!authState?.isAuthenticated;

  const normalizeCode = (value: unknown): string | null => {
    if (typeof value !== "string") return null;
    const trimmed = value.trim().toUpperCase();
    return trimmed || null;
  };

  const getVendorCodeFromClaims = (): string | null => {
    const accessClaims = (authState?.accessToken as { claims?: Record<string, unknown> } | undefined)?.claims;
    const idClaims = (authState?.idToken as { claims?: Record<string, unknown> } | undefined)?.claims;
    const claims = accessClaims ?? idClaims;
    if (!claims) return null;
    // Prefer canonical claim; keep bcpAuth for current tenant compatibility.
    return normalizeCode(claims.vendor_code) ?? normalizeCode(claims.bcpAuth);
  };

  useEffect(() => {
    if (!isAuthenticated) {
      setAuthTokenProvider(null);
      return;
    }
    setAuthTokenProvider(async () => {
      try {
        return oktaAuth.getAccessToken() ?? null;
      } catch {
        return null;
      }
    });
    return () => setAuthTokenProvider(null);
  }, [isAuthenticated, oktaAuth]);

  useEffect(() => {
    if (!isAuthenticated) return;
    const claimVendorCode = getVendorCodeFromClaims();
    if (!claimVendorCode) return;
    const activeVendor = getActiveVendorCode();
    if (activeVendor === claimVendorCode) return;
    setActiveVendorCode(claimVendorCode);
    window.dispatchEvent(new CustomEvent("activeVendorChanged"));
  }, [isAuthenticated, authState]);

  return null;
}
