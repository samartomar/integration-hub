import { useEffect } from "react";
import { useOktaAuth } from "@okta/okta-react";
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

  return null;
}
