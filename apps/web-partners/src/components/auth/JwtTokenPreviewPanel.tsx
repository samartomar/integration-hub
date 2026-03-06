import { useState } from "react";
import {
  previewAuthProfileToken,
  type JwtTokenPreviewResponse,
} from "../../api/endpoints";

interface JwtTokenPreviewPanelProps {
  authType: string;
  authConfig: Record<string, unknown>;
}

export function JwtTokenPreviewPanel({ authType, authConfig }: JwtTokenPreviewPanelProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<JwtTokenPreviewResponse | null>(null);

  if (authType !== "JWT" && authType !== "JWT_BEARER_TOKEN") return null;

  const fetchPreview = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await previewAuthProfileToken({
        authType: "JWT_BEARER_TOKEN",
        authConfig,
        timeoutMs: 5000,
      });
      setResult(data);
    } catch (e) {
      setError((e as Error)?.message ?? "Failed to preview token.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold text-gray-800 uppercase tracking-wide">Token Preview</h4>
        <button
          type="button"
          onClick={fetchPreview}
          disabled={loading}
          className="px-2.5 py-1 text-xs font-medium rounded border border-slate-300 text-slate-700 hover:bg-slate-100 disabled:opacity-50"
        >
          {loading ? "Fetching..." : "Fetch token (preview)"}
        </button>
      </div>
      <p className="text-xs text-gray-600">
        Runtime caches tokens for (ttl-30s) and refreshes automatically.
      </p>
      {error && <p className="text-xs text-red-600">{error}</p>}
      {result && (
        <div className="space-y-1 text-xs text-gray-700">
          <p>
            Result:{" "}
            <span className={result.ok ? "text-emerald-700 font-medium" : "text-red-700 font-medium"}>
              {result.ok ? "Success" : "Failure"}
            </span>
          </p>
          {result.tokenRedacted && <p>Token (redacted): {result.tokenRedacted}</p>}
          {result.tokenLength != null && <p>Token length: {result.tokenLength}</p>}
          {result.expiresIn != null && <p>expires_in: {result.expiresIn}s</p>}
          {result.jwtClaims && (
            <>
              <p>iss: {String(result.jwtClaims.iss ?? "-")}</p>
              <p>aud: {Array.isArray(result.jwtClaims.aud) ? result.jwtClaims.aud.join(", ") : String(result.jwtClaims.aud ?? "-")}</p>
              <p>exp: {String(result.jwtClaims.exp ?? "-")}</p>
              <p>iat: {String(result.jwtClaims.iat ?? "-")}</p>
            </>
          )}
          {result.cacheDiagnostics && (
            <>
              <p>cacheKey hash: {result.cacheDiagnostics.cacheKeyHash ?? "-"}</p>
              <p>expiresAt: {result.cacheDiagnostics.expiresAt ?? "-"}</p>
              <p>lastFetchedAt: {result.cacheDiagnostics.lastFetchedAt ?? "-"}</p>
            </>
          )}
          {result.error && (
            <p className="text-red-700">
              {result.error.category}: {result.error.message}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
