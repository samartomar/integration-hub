import { useOktaAuth } from "@okta/okta-react";
import type { ReactNode } from "react";
import { getOktaConfig, isOktaEnabled } from "../config/oktaConfig";

interface AuthGateProps {
  children: ReactNode;
}

/**
 * When Okta is enabled, requires authentication before rendering children.
 * Shows a login screen when not authenticated.
 * When Okta is disabled, renders children immediately.
 */
export function AuthGate({ children }: AuthGateProps) {
  const oktaEnabled = isOktaEnabled();
  if (!oktaEnabled) return <>{children}</>;

  return <AuthGateInner>{children}</AuthGateInner>;
}

function AuthGateInner({ children }: AuthGateProps) {
  const { oktaAuth, authState } = useOktaAuth();
  const config = getOktaConfig();
  const isAuthenticated = !!authState?.isAuthenticated;
  const isLoading = !authState;
  const isCallbackRoute = typeof window !== "undefined" && window.location.pathname === "/callback";

  if (isCallbackRoute) return <>{children}</>;

  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50 p-8">
        <div className="animate-pulse text-slate-600">Loading authentication...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50 p-8">
        <div className="max-w-md w-full text-center">
          <h1 className="text-2xl font-bold text-slate-900 mb-2">Sign in</h1>
          <p className="text-slate-600 mb-6">
            Sign in to access the Licensee Portal.
          </p>
          <button
            type="button"
            onClick={() => {
              void oktaAuth.signInWithRedirect({
                originalUri: `${window.location.pathname}${window.location.search}`,
                ...(config?.connection ? { idp: config.connection } : {}),
              });
            }}
            className="px-6 py-3 text-sm font-medium text-white bg-teal-600 hover:bg-teal-700 rounded-lg transition-colors"
          >
            Log in
          </button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
