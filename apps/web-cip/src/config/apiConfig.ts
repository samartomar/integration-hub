/** Centralized API base URL helpers. Use .env.local for local overrides. */

export function getAdminApiBaseUrl(): string {
  return (
    import.meta.env.VITE_ADMIN_API_BASE_URL ||
    "http://localhost:8080"
  );
}

/** Runtime API base URL: /v1/execute, /v1/ai/execute. Single source for execute.
 * Defaults to AWS dev (api.dev.aws.gosam.info) - local mock cannot mimic Bedrock/AI. */
export function getRuntimeApiBaseUrl(): string {
  return (
    import.meta.env.VITE_RUNTIME_API_BASE_URL ||
    import.meta.env.VITE_AI_EXECUTE_BASE_URL ||
    "https://api.dev.aws.gosam.info"
  );
}

export function getVendorApiBaseUrl(): string {
  return (
    import.meta.env.VITE_VENDOR_API_BASE_URL ||
    import.meta.env.VITE_ADMIN_API_BASE_URL ||
    "http://localhost:8080"
  );
}
