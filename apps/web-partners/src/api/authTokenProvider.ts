/**
 * Module-level access token provider used by API client interceptors.
 * Set by OktaTokenSetup when a user session is authenticated.
 */
let tokenProvider: (() => Promise<string | null>) | null = null;

export function setAuthTokenProvider(fn: (() => Promise<string | null>) | null): void {
  tokenProvider = fn;
}

export function getAuthTokenProvider(): (() => Promise<string | null>) | null {
  return tokenProvider;
}
