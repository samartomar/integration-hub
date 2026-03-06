import { useOktaAuth } from "@okta/okta-react";
import type { ReactNode } from "react";
import { getOktaConfig, isOktaEnabled } from "../config/oktaConfig";

interface AuthGateProps {
  children: ReactNode;
}

/**
 * Always requires authentication before rendering children.
 * When Okta is not configured, blocks access with setup guidance.
 */
export function AuthGate({ children }: AuthGateProps) {
  const oktaEnabled = isOktaEnabled();
  if (!oktaEnabled) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50 p-8">
        <div className="max-w-md w-full text-center">
          <h1 className="text-2xl font-bold text-slate-900 mb-2">Authentication required</h1>
          <p className="text-slate-600 mb-3">
            The Licensee Portal requires Okta sign-in before any UI can load.
          </p>
          <p className="text-sm text-slate-500">
            Start the UI with AWS settings, for example `make dev-ui-aws`, or configure `.env.aws`
            so the login screen can be shown.
          </p>
        </div>
      </div>
    );
  }

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
            Click to login
          </button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
