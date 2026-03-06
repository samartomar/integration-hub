import { useState, useEffect, useRef } from "react";
import type { VendorEndpoint } from "../../types";
import type { AuthProfile } from "../../api/endpoints";

interface VendorEndpointModalProps {
  open: boolean;
  onClose: () => void;
  initialValues: VendorEndpoint | null;
  supportedOperationCodes?: string[];
  authProfiles?: AuthProfile[];
  onSave: (payload: {
    operationCode: string;
    url: string;
    httpMethod?: string;
    payloadFormat?: string;
    timeoutMs?: number;
    isActive?: boolean;
    authProfileId?: string | null;
    verificationRequest?: Record<string, unknown> | null;
  }) => Promise<void>;
}

export function VendorEndpointModal({
  open,
  onClose,
  initialValues,
  supportedOperationCodes = [],
  authProfiles = [],
  onSave,
}: VendorEndpointModalProps) {
  const [operationCode, setOperationCode] = useState("");
  const [url, setUrl] = useState("");
  const [httpMethod, setHttpMethod] = useState("POST");
  const [payloadFormat, setPayloadFormat] = useState("json");
  const [timeoutMs, setTimeoutMs] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [authProfileId, setAuthProfileId] = useState<string>("");
  const [verificationRequestJson, setVerificationRequestJson] = useState("{}");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isEdit = !!initialValues;
  const lastSeededKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (open) {
      const key = initialValues?.operationCode ?? "__add__";
      if (lastSeededKeyRef.current !== key) {
        lastSeededKeyRef.current = key;
        setOperationCode(initialValues?.operationCode ?? "");
        setUrl(initialValues?.url ?? "");
        setHttpMethod(initialValues?.httpMethod ?? "POST");
        setPayloadFormat(initialValues?.payloadFormat ?? "json");
        setTimeoutMs(initialValues?.timeoutMs != null ? String(initialValues.timeoutMs) : "");
        setIsActive(initialValues?.isActive !== false);
        setAuthProfileId(initialValues?.authProfileId ?? "");
        setVerificationRequestJson(
          initialValues?.verificationRequest != null
            ? JSON.stringify(initialValues.verificationRequest, null, 2)
            : "{}"
        );
        setError(null);
      }
    } else {
      lastSeededKeyRef.current = null;
    }
  }, [open, initialValues]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const opCode = operationCode.trim().toUpperCase();
    const urlTrimmed = url.trim();
    if (!opCode || !urlTrimmed) {
      setError("Operation code and URL are required.");
      return;
    }
    let verificationRequest: Record<string, unknown> | null = null;
    const jsonTrimmed = verificationRequestJson.trim();
    if (jsonTrimmed && jsonTrimmed !== "{}") {
      try {
        const parsed = JSON.parse(jsonTrimmed);
        verificationRequest = typeof parsed === "object" && parsed !== null ? parsed : null;
      } catch {
        setError("Verification payload must be valid JSON.");
        return;
      }
    }
    setIsLoading(true);
    try {
      await onSave({
        operationCode: opCode,
        url: urlTrimmed,
        httpMethod: httpMethod.trim() || undefined,
        payloadFormat: payloadFormat.trim() || undefined,
        timeoutMs: timeoutMs ? parseInt(timeoutMs, 10) : undefined,
        isActive,
        authProfileId: authProfileId?.trim() || null,
        verificationRequest: verificationRequest ?? undefined,
      });
      onClose();
    } catch (err) {
      const axiosErr = err as { response?: { data?: { error?: { message?: string } } }; message?: string };
      const msg =
        axiosErr?.response?.data?.error?.message ?? (axiosErr as Error)?.message ?? "Failed to save.";
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center ${open ? "" : "hidden"}`}
    >
      <div className="absolute inset-0 bg-black/50" aria-hidden />
      <div
        className="relative w-full max-w-md bg-white rounded-lg shadow-xl p-6 mx-4 max-h-[90vh] overflow-y-auto"
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">
            {isEdit ? "Edit Endpoint" : "Add Endpoint"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 p-1 rounded"
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Operation</label>
            {isEdit ? (
              <input
                type="text"
                value={operationCode}
                readOnly
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-gray-100 text-gray-600"
              />
            ) : (
              <select
                value={operationCode}
                onChange={(e) => setOperationCode(e.target.value)}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
              >
                <option value="">Select operation…</option>
                {supportedOperationCodes.map((code) => (
                  <option key={code} value={code}>
                    {code}
                  </option>
                ))}
              </select>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Auth profile (optional)</label>
            <select
              value={authProfileId}
              onChange={(e) => setAuthProfileId(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
            >
              <option value="">No auth (public API)</option>
              {authProfiles.map((ap) => (
                <option key={ap.id ?? ap.name} value={ap.id ?? ""}>
                  {ap.name} ({ap.authType})
                </option>
              ))}
            </select>
            {authProfileId && (
              <p className="mt-1 text-xs text-gray-500">
                {authProfiles.find((ap) => ap.id === authProfileId)?.authType ?? ""} will be applied to requests.
              </p>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">URL</label>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://..."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">HTTP method</label>
            <select
              value={httpMethod}
              onChange={(e) => setHttpMethod(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
            >
              <option value="GET">GET</option>
              <option value="POST">POST</option>
              <option value="PUT">PUT</option>
              <option value="PATCH">PATCH</option>
              <option value="DELETE">DELETE</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1" title="How the request body is serialized (JSON, XML, or raw bytes).">
              Payload format
              <span className="ml-1 text-gray-400" aria-hidden>ⓘ</span>
            </label>
            <select
              value={payloadFormat || "json"}
              onChange={(e) => setPayloadFormat(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
            >
              <option value="json">JSON (default)</option>
              <option value="xml">XML</option>
              <option value="binary">Binary file (PDF, image, document) – base64, up to 5 MB</option>
              <option value="form">Form (x-www-form-urlencoded)</option>
              <option value="raw">Raw / text</option>
            </select>
            <p className="text-xs text-gray-500 mt-1">
              {(payloadFormat || "json") === "xml" && "Mapping outputs XML or a JSON-like object."}
              {(payloadFormat || "json") === "binary" && "Mapping outputs base64. Paste a sample in the field below."}
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Timeout (ms)</label>
            <input
              type="number"
              value={timeoutMs}
              onChange={(e) => setTimeoutMs(e.target.value)}
              placeholder="30000"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {(() => {
                const fmt = payloadFormat || "json";
                if (fmt === "binary") return "Verification payload (base64)";
                if (fmt === "xml") return "Verification payload (XML or JSON)";
                return "Verification payload (JSON)";
              })()}
            </label>
            <textarea
              value={verificationRequestJson}
              onChange={(e) => setVerificationRequestJson(e.target.value)}
              placeholder={
                (payloadFormat || "json") === "binary"
                  ? "Paste base64 string here (e.g. SGVsbG8=)..."
                  : (payloadFormat || "json") === "xml"
                    ? "<root><field>value</field></root> or {\"field\": \"value\"}"
                    : '{"healthCheck": true}'
              }
              rows={4}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
            />
            <p className="text-xs text-gray-500 mt-1">
              {(payloadFormat || "json") === "binary" ? (
                "Paste a base64-encoded sample of the file here. Max 5 MB decoded at runtime."
              ) : (payloadFormat || "json") === "xml" ? (
                "Paste raw XML or a JSON-like object here. JSON is converted to XML if needed."
              ) : (
                "Payload sent when verifying endpoint. Use {} for GET or empty POST."
              )}
            </p>
          </div>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="rounded border-gray-300 text-slate-600 focus:ring-slate-500"
            />
            <span className="text-sm text-gray-700">Active</span>
          </label>
          {error && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
              {error}
            </div>
          )}
          <div className="flex gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 disabled:opacity-50 rounded-lg"
            >
              {isLoading ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
