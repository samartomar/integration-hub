import type { ReactNode } from "react";
import { useMemo } from "react";
import { Security } from "@okta/okta-react";
import { OktaAuth, toRelativeUrl } from "@okta/okta-auth-js";
import { getOktaConfig } from "../config/oktaConfig";

interface OktaProviderWithConfigProps {
  children: ReactNode;
}

/**
 * Wraps children with Okta Security when Okta is configured.
 * When VITE_OKTA_ISSUER and VITE_OKTA_CLIENT_ID are unset, renders children without Okta.
 */
export function OktaProviderWithConfig({ children }: OktaProviderWithConfigProps) {
  const config = getOktaConfig();
  const oktaAuth = useMemo(() => {
    if (!config) return null;
    return new OktaAuth({
      issuer: config.issuer,
      clientId: config.clientId,
      redirectUri: config.redirectUri,
      scopes: config.scopes,
      pkce: true,
      tokenManager: { storage: "localStorage" },
    });
  }, [config?.issuer, config?.clientId, config?.redirectUri, config?.scopes?.join(" ")]);

  if (!config || !oktaAuth) return <>{children}</>;

  return (
    <Security
      oktaAuth={oktaAuth}
      restoreOriginalUri={async (_oktaAuth, originalUri) => {
        const relativeUrl = toRelativeUrl(originalUri || "/", window.location.origin);
        window.location.replace(relativeUrl);
      }}
    >
      {children}
    </Security>
  );
}
