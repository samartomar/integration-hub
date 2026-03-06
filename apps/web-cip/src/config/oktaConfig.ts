/** Okta configuration. When issuer and clientId are set, Okta login is enabled. */

const DEFAULT_SCOPES = ["openid", "profile", "email"];

export function getOktaConfig(): {
  issuer: string;
  clientId: string;
  audience?: string;
  scopes: string[];
  redirectUri: string;
} | null {
  const issuer = (import.meta.env.VITE_OKTA_ISSUER as string)?.trim();
  const clientId = (import.meta.env.VITE_OKTA_CLIENT_ID as string)?.trim();
  if (!issuer || !clientId) return null;

  const audience = (import.meta.env.VITE_OKTA_AUDIENCE as string)?.trim() || undefined;
  const scopesRaw = (import.meta.env.VITE_OKTA_SCOPES as string)?.trim();
  const redirectUriRaw = (import.meta.env.VITE_OKTA_REDIRECT_URI as string)?.trim();
  const redirectPathRaw = (import.meta.env.VITE_OKTA_REDIRECT_PATH as string)?.trim();
  const redirectPath = redirectPathRaw
    ? (redirectPathRaw.startsWith("/") ? redirectPathRaw : `/${redirectPathRaw}`)
    : "/callback";
  const scopes = scopesRaw
    ? scopesRaw.split(/[,\s]+/).map((s) => s.trim()).filter(Boolean)
    : DEFAULT_SCOPES;
  const redirectUri =
    redirectUriRaw ||
    (typeof window !== "undefined"
      ? `${window.location.origin}${redirectPath}`
      : "/callback");

  return { issuer, clientId, audience, scopes, redirectUri };
}

export function isOktaEnabled(): boolean {
  return getOktaConfig() !== null;
}
