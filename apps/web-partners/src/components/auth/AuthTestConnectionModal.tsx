import { useMemo, useState } from "react";
import { testAuthProfileConnection, type TestConnectionResponse } from "../../api/endpoints";

interface AuthTestConnectionModalProps {
  open: boolean;
  onClose: () => void;
  authProfileId?: string;
  authType: string;
  authConfig: Record<string, unknown>;
}

const METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"] as const;

export function AuthTestConnectionModal({
  open,
  onClose,
  authProfileId,
  authType,
  authConfig,
}: AuthTestConnectionModalProps) {
  const [url, setUrl] = useState("");
  const [method, setMethod] = useState<(typeof METHODS)[number]>("GET");
  const [headersText, setHeadersText] = useState("{}");
  const [bodyText, setBodyText] = useState("");
  const [timeoutMs, setTimeoutMs] = useState(5000);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TestConnectionResponse | null>(null);

  const canSendBody = useMemo(
    () => method === "POST" || method === "PUT" || method === "PATCH" || method === "DELETE",
    [method]
  );

  const runTest = async () => {
    setError(null);
    setResult(null);
    if (!url.trim()) {
      setError("Target URL is required.");
      return;
    }
    let parsedHeaders: Record<string, string> = {};
    try {
      const parsed = JSON.parse(headersText || "{}");
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        parsedHeaders = Object.fromEntries(
          Object.entries(parsed).map(([k, v]) => [String(k), String(v)])
        );
      } else {
        throw new Error("headers object");
      }
    } catch {
      setError("Headers must be valid JSON object.");
      return;
    }

    let body: Record<string, unknown> | string | null = null;
    if (canSendBody && bodyText.trim()) {
      try {
        body = JSON.parse(bodyText);
      } catch {
        body = bodyText;
      }
    }

    setRunning(true);
    try {
      const data = await testAuthProfileConnection({
        authProfileId: authProfileId ?? null,
        authType,
        authConfig,
        url: url.trim(),
        method,
        headers: parsedHeaders,
        body,
        timeoutMs: Math.min(10000, Math.max(1, timeoutMs)),
      });
      setResult(data);
    } catch (e) {
      setError((e as Error)?.message ?? "Failed to run connection test.");
    } finally {
      setRunning(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-2xl bg-white rounded-lg border border-gray-200 shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 bg-gray-50 px-4 py-3">
          <h3 className="text-sm font-semibold text-gray-900">Test connection</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 p-1 rounded"
            aria-label="Close"
          >
            x
          </button>
        </div>
        <div className="p-4 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2">
              <label className="block text-xs font-medium text-gray-600 mb-1">Target URL</label>
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://api.vendor.com/health"
                className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Method</label>
              <select
                value={method}
                onChange={(e) => setMethod(e.target.value as (typeof METHODS)[number])}
                className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
              >
                {METHODS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Optional headers (JSON, non-secret only)
            </label>
            <textarea
              rows={3}
              value={headersText}
              onChange={(e) => setHeadersText(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded text-xs font-mono"
            />
          </div>

          {canSendBody && (
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Optional body</label>
              <textarea
                rows={4}
                value={bodyText}
                onChange={(e) => setBodyText(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded text-xs font-mono"
              />
            </div>
          )}

          <div className="w-40">
            <label className="block text-xs font-medium text-gray-600 mb-1">Timeout (ms)</label>
            <input
              type="number"
              min={1}
              max={10000}
              value={timeoutMs}
              onChange={(e) => setTimeoutMs(Number(e.target.value || 5000))}
              className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
            />
          </div>

          <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
            Secrets are redacted in diagnostics. Response preview is limited to 2 KB.
          </div>

          {error && <div className="text-xs text-red-600">{error}</div>}

          {result && (
            <div className="rounded-md border border-gray-200 bg-gray-50 p-3 space-y-2">
              <div className="flex flex-wrap gap-3 text-xs">
                <span className={`font-semibold ${result.ok ? "text-emerald-700" : "text-red-700"}`}>
                  {result.ok ? "SUCCESS" : "FAILURE"}
                </span>
                <span>HTTP: {result.httpStatus ?? "-"}</span>
                <span>Latency: {result.latencyMs} ms</span>
              </div>
              {result.error && (
                <p className="text-xs text-red-700">
                  {result.error.category}: {result.error.message}
                </p>
              )}
              <div>
                <p className="text-xs font-medium text-gray-700 mb-1">Response preview</p>
                <pre className="text-[11px] bg-white border border-gray-200 rounded p-2 overflow-x-auto">
                  {result.responsePreview || "(empty)"}
                </pre>
              </div>
              {result.debug?.resolvedAuth && (
                <div>
                  <p className="text-xs font-medium text-gray-700 mb-1">Resolved auth (redacted)</p>
                  <pre className="text-[11px] bg-white border border-gray-200 rounded p-2 overflow-x-auto">
                    {JSON.stringify(result.debug.resolvedAuth, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
        <div className="px-4 py-3 border-t border-gray-200 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg text-gray-700"
          >
            Close
          </button>
          <button
            type="button"
            onClick={runTest}
            disabled={running}
            className="px-3 py-1.5 text-sm text-white bg-slate-600 hover:bg-slate-700 disabled:opacity-50 rounded-lg"
          >
            {running ? "Running..." : "Run test"}
          </button>
        </div>
      </div>
    </div>
  );
}
