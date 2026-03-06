/**
 * Extract structured error from API/axios errors.
 * Use for displaying actionable error messages (code, message, details).
 */

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  retryable?: boolean;
}

export function extractApiError(err: unknown): ApiError {
  const e = err as {
    response?: {
      status?: number;
      data?: {
        error?: { code?: string; message?: string; details?: Record<string, unknown>; retryable?: boolean };
        message?: string;
      };
    };
    message?: string;
  };

  const data = e?.response?.data;
  const errObj = data && typeof data === "object" ? (data as { error?: unknown; message?: string }).error : undefined;
  const errDict = errObj && typeof errObj === "object" ? (errObj as Record<string, unknown>) : undefined;

  const code = (errDict?.code as string) ?? (e?.response?.status === 502 ? "GATEWAY_ERROR" : "UNKNOWN");
  const message =
    (errDict?.message as string) ??
    (data && typeof data === "object" ? (data as { message?: string }).message : undefined) ??
    (e?.message as string) ??
    "An unexpected error occurred.";
  const details = errDict?.details as Record<string, unknown> | undefined;
  const retryable = errDict?.retryable as boolean | undefined;

  return { code, message, details, retryable };
}

/**
 * Format error for display: message plus optional details hint.
 * @param defaultMessage - fallback when no message can be extracted
 */
export function formatApiErrorForDisplay(err: unknown, defaultMessage = "An unexpected error occurred."): string {
  const apiErr = extractApiError(err);
  let out = apiErr.message || defaultMessage;
  if (apiErr.details?.hint) {
    out += ` (${apiErr.details.hint})`;
  } else if (apiErr.details?.type) {
    out += ` [${apiErr.details.type}]`;
  }
  return out;
}
