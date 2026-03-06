import { useState, useEffect, useRef } from "react";
import { formatApiErrorForDisplay, type VendorEndpoint } from "frontend-shared";
import type { AuthProfile } from "../../api/endpoints";

interface EndpointVerifyResult {
  verified: boolean;
  httpStatus?: number | null;
  message?: string;
  responseSnippet?: string | null;
}

interface VendorEndpointModalProps {
  open: boolean;
  onClose: () => void;
  initialValues: VendorEndpoint | null;
  /** When true, show "Add Endpoint" title even if initialValues has operationCode (for create-from-context flow). */
  isAddMode?: boolean;
  /** When true, uses full modal pattern (Access Rules style) instead of right drawer. */
  useModalPattern?: boolean;
  /** Optional verify action; when provided, verify is shown in edit mode. */
  onVerify?: (payload: {
    operationCode: string;
    flowDirection?: string;
  }) => Promise<EndpointVerifyResult>;
  /** If true, runs verify once when modal opens in edit mode. */
  autoVerifyOnOpen?: boolean;
  supportedOperationCodes?: string[];
  authProfiles?: AuthProfile[];
  onSave: (payload: {
    id?: string;
    operationCode: string;
    url: string;
    flowDirection?: string;
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
  isAddMode = false,
  useModalPattern = false,
  onVerify,
  autoVerifyOnOpen = false,
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
  const [showDeactivateConfirm, setShowDeactivateConfirm] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<EndpointVerifyResult | null>(null);
  const isEdit = !!initialValues;
  const lastSeededKeyRef = useRef<string | null>(null);
  const autoVerifyDoneRef = useRef<string | null>(null);

  useEffect(() => {
    if (open) {
      const key = initialValues
        ? (initialValues.id
            ? String(initialValues.id)
            : `${initialValues.operationCode ?? ""}::${initialValues.flowDirection ?? ""}`)
        : "__add__";
      if (lastSeededKeyRef.current !== key) {
        lastSeededKeyRef.current = key;
        setOperationCode(initialValues?.operationCode ?? "");
        setUrl(initialValues?.url ?? "");
        setHttpMethod(initialValues?.httpMethod ?? "POST");
        setPayloadFormat(initialValues?.payloadFormat ?? "json");
        setTimeoutMs(initialValues?.timeoutMs != null ? String(initialValues.timeoutMs) : "");
        setIsActive(initialValues?.isActive !== false);
        setAuthProfileId(initialValues?.authProfileId ?? "");
        const vr = initialValues?.verificationRequest;
        const bodyForForm =
          vr != null && typeof vr === "object" && "request" in vr && "responseSnippet" in vr
            ? (vr as { request?: { body?: unknown } }).request?.body ?? {}
            : vr ?? {};
        setVerificationRequestJson(
          typeof bodyForForm === "object" && bodyForForm !== null && Object.keys(bodyForForm).length > 0
            ? JSON.stringify(bodyForForm, null, 2)
            : "{}"
        );
        setVerifyResult(null);
        setError(null);
      }
    } else {
      lastSeededKeyRef.current = null;
      autoVerifyDoneRef.current = null;
      setVerifyResult(null);
    }
  }, [open, initialValues]);

  const handleVerify = async () => {
    if (!onVerify || !isEdit) return;
    const opCode = operationCode.trim().toUpperCase();
    if (!opCode) return;
    setIsVerifying(true);
    setVerifyResult(null);
    try {
      const res = await onVerify({
        operationCode: opCode,
        flowDirection: initialValues?.flowDirection ?? undefined,
      });
      setVerifyResult(res);
    } catch (err) {
      setVerifyResult({
        verified: false,
        message: formatApiErrorForDisplay(err, "Verification failed."),
      });
    } finally {
      setIsVerifying(false);
    }
  };

  useEffect(() => {
    if (!open || !autoVerifyOnOpen || !onVerify || !isEdit) return;
    const key = `${operationCode}::${initialValues?.flowDirection ?? ""}`;
    if (!operationCode || autoVerifyDoneRef.current === key) return;
    autoVerifyDoneRef.current = key;
    void handleVerify();
  }, [open, autoVerifyOnOpen, onVerify, isEdit, operationCode, initialValues?.flowDirection]);

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
      const flowDirection = initialValues?.flowDirection;
      await onSave({
        id: initialValues?.id ? String(initialValues.id) : undefined,
        operationCode: opCode,
        url: urlTrimmed,
        flowDirection: flowDirection || undefined,
        httpMethod: httpMethod.trim() || undefined,
        payloadFormat: payloadFormat.trim() || undefined,
        timeoutMs: timeoutMs ? parseInt(timeoutMs, 10) : undefined,
        isActive,
        authProfileId: authProfileId?.trim() || null,
        verificationRequest: verificationRequest ?? undefined,
      });
      onClose();
    } catch (err) {
      const msg = formatApiErrorForDisplay(err, "Failed to save endpoint.");
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggleActive = async () => {
    setShowDeactivateConfirm(false);
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
      const flowDirection = initialValues?.flowDirection;
      await onSave({
        id: initialValues?.id ? String(initialValues.id) : undefined,
        operationCode: opCode,
        url: urlTrimmed,
        flowDirection: flowDirection || undefined,
        httpMethod: httpMethod.trim() || undefined,
        payloadFormat: payloadFormat.trim() || undefined,
        timeoutMs: timeoutMs ? parseInt(timeoutMs, 10) : undefined,
        isActive: !isActive,
        authProfileId: authProfileId?.trim() || null,
        verificationRequest: verificationRequest ?? undefined,
      });
      setIsActive(!isActive);
    } catch (err) {
      setError(formatApiErrorForDisplay(err, "Failed to save endpoint."));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      className={`fixed inset-0 z-50 ${open ? "flex" : "hidden"} ${
        useModalPattern ? "items-stretch justify-center p-2 sm:p-3 md:p-4" : "items-stretch justify-end"
      }`}
    >
      <div className="absolute inset-0 bg-black/30" aria-hidden />
      <div
        className={`relative w-full bg-white shadow-xl overflow-y-auto ${
          useModalPattern
            ? "max-w-5xl rounded-xl flex flex-col overflow-hidden"
            : "max-w-lg p-3 sm:p-4"
        }`}
        role="dialog"
        aria-modal="true"
        style={{ maxHeight: useModalPattern ? "100%" : "100vh" }}
      >
        <div className={useModalPattern ? "flex items-center justify-between px-3 py-2 border-b border-gray-200 bg-gray-50" : "flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-3"}>
          <div className="flex items-center gap-4 min-w-0">
            <h2 className={`${useModalPattern ? "font-semibold text-gray-900" : "text-lg font-semibold text-gray-900 min-w-0"}`}>
              {isAddMode ? "Add Endpoint" : "Edit Endpoint"}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className={`${useModalPattern ? "p-2 text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-200" : "text-gray-400 hover:text-gray-600 p-1 rounded"}`}
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <form
          onSubmit={handleSubmit}
          className={
            useModalPattern
              ? "px-3 sm:px-4 pt-1.5 sm:pt-2 pb-3 sm:pb-4 flex-1 overflow-y-auto space-y-2"
              : "space-y-4"
          }
        >
          {useModalPattern ? (
            <>
              <div className={`grid grid-cols-1 ${isEdit && onVerify ? "lg:grid-cols-2" : ""} gap-2.5 items-start`}>
                <div className="space-y-2.5">
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
                    <label className="block text-sm font-medium text-gray-700 mb-1" title="Optional. Assign an authentication profile to automatically send headers or API keys with every request to this endpoint.">
                      Auth profile (optional)
                      <span className="ml-1 text-gray-400" aria-hidden>ⓘ</span>
                    </label>
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
                    {authProfileId ? (
                      <p className="mt-0.5 text-xs leading-4 text-gray-500">
                        {authProfiles.find((ap) => ap.id === authProfileId)?.authType ?? ""} will be applied to requests.
                      </p>
                    ) : (
                      <p className="mt-0.5 text-xs leading-4 text-gray-500">
                        Leave auth blank for public APIs. For private APIs, attach an auth profile.
                      </p>
                    )}
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1" title="Used only when verifying the endpoint configuration. Does not affect live traffic.">
                      {(() => {
                        const fmt = payloadFormat || "json";
                        if (fmt === "binary") return "Verification payload (base64)";
                        if (fmt === "xml") return "Verification payload (XML or JSON)";
                        return "Verification payload (JSON)";
                      })()}
                      <span className="ml-1 text-gray-400" aria-hidden>ⓘ</span>
                    </label>
                    <textarea
                      value={verificationRequestJson}
                      onChange={(e) => setVerificationRequestJson(e.target.value)}
                      placeholder={
                        (payloadFormat || "json") === "binary"
                          ? "Paste base64 string here (e.g. SGVsbG8=)..."
                          : (payloadFormat || "json") === "xml"
                            ? "<root><field>value</field></root> or {\"field\": \"value\"}"
                            : '{"exampleField": "test-value"}'
                      }
                      rows={3}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
                    />
                    <p className="text-xs leading-4 text-gray-500 mt-0.5">
                      {(payloadFormat || "json") === "binary" ? (
                        "Paste a base64-encoded sample of the file here. Max 5 MB decoded at runtime."
                      ) : (payloadFormat || "json") === "xml" ? (
                        "Paste raw XML or a JSON-like object here. Platform converts JSON to XML if needed."
                      ) : (
                        "Payload sent when verifying this endpoint. Use {} for GET or empty POST."
                      )}
                    </p>
                  </div>
                </div>
                {isEdit && onVerify && (
                  <div className="space-y-2.5">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">URL</label>
                      <input
                        type="url"
                        value={url}
                        onChange={(e) => setUrl(e.target.value)}
                        placeholder="https://api.vendor.com/v1/receipt"
                        required
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
                      <p className="text-xs leading-4 text-gray-500 mt-0.5">
                        {(payloadFormat || "json") === "xml" && "Mapping outputs XML or a JSON-like object."}
                        {(payloadFormat || "json") === "binary" && "Mapping outputs base64. Paste a sample in the field below."}
                      </p>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1" title="Maximum time allowed for the vendor API to respond before the request is considered failed.">
                        Timeout (ms)
                        <span className="ml-1 text-gray-400" aria-hidden>ⓘ</span>
                      </label>
                      <input
                        type="number"
                        value={timeoutMs}
                        onChange={(e) => setTimeoutMs(e.target.value)}
                        placeholder="30000"
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
                      />
                    </div>
                  </div>
                )}
              </div>
              {isEdit && onVerify && (
                <div className="grid grid-cols-1 lg:grid-cols-10 gap-3 items-start">
                  <div className="lg:col-span-7 rounded-lg border border-slate-200 bg-slate-50 p-2.5 space-y-2.5">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 text-left">
                        <p className="text-sm font-medium text-slate-800">Verify endpoint</p>
                        <p className="text-xs text-slate-600">
                          Runs connectivity check using saved endpoint configuration.
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => void handleVerify()}
                        disabled={isVerifying || isLoading}
                        className="px-3 py-1.5 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 rounded-lg whitespace-nowrap disabled:opacity-50"
                      >
                        {isVerifying ? "Verifying..." : "Verify endpoint"}
                      </button>
                    </div>
                    {verifyResult && (
                      <div className={`rounded-lg border p-3 text-sm ${
                        verifyResult.verified
                          ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                          : "bg-red-50 border-red-200 text-red-800"
                      }`}>
                        <div className="font-medium">
                          {verifyResult.verified ? "Verified" : "Failed"}
                          {verifyResult.httpStatus != null ? ` (HTTP ${verifyResult.httpStatus})` : ""}
                        </div>
                        {verifyResult.message && <div className="mt-1">{verifyResult.message}</div>}
                        {verifyResult.responseSnippet && (
                          <details className="mt-2">
                            <summary className="cursor-pointer text-xs font-medium">Response snippet</summary>
                            <pre className="mt-1 rounded bg-slate-900 text-slate-100 p-2 text-xs whitespace-pre-wrap break-words">
                              {verifyResult.responseSnippet}
                            </pre>
                          </details>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="lg:col-span-3 flex items-start lg:justify-end gap-2 flex-wrap lg:flex-nowrap">
                    <button
                      type="button"
                      onClick={() => (isActive ? setShowDeactivateConfirm(true) : handleToggleActive())}
                      disabled={isLoading}
                      className={`px-2.5 py-1.5 text-sm font-medium rounded-lg border whitespace-nowrap ${
                        isActive
                          ? "text-red-600 border-red-200 hover:bg-red-50"
                          : "text-emerald-600 border-emerald-200 hover:bg-emerald-50"
                      } disabled:opacity-50`}
                    >
                      {isActive ? "Deactivate endpoint" : "Activate endpoint"}
                    </button>
                    <button
                      type="button"
                      onClick={onClose}
                      className="px-2.5 py-1.5 text-sm font-medium text-gray-700 border border-gray-300 hover:bg-gray-50 rounded-lg whitespace-nowrap"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isLoading}
                      className="px-2.5 py-1.5 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 disabled:opacity-50 rounded-lg whitespace-nowrap"
                    >
                      {isLoading ? "Saving…" : "Save"}
                    </button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="space-y-3">
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
                <label className="block text-sm font-medium text-gray-700 mb-1">URL</label>
                <input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://api.vendor.com/v1/receipt"
                  required
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
                <label className="block text-sm font-medium text-gray-700 mb-1" title="Maximum time allowed for the vendor API to respond before the request is considered failed.">
                  Timeout (ms)
                  <span className="ml-1 text-gray-400" aria-hidden>ⓘ</span>
                </label>
                <input
                  type="number"
                  value={timeoutMs}
                  onChange={(e) => setTimeoutMs(e.target.value)}
                  placeholder="30000"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1" title="Used only when verifying the endpoint configuration. Does not affect live traffic.">
                  {(() => {
                    const fmt = payloadFormat || "json";
                    if (fmt === "binary") return "Verification payload (base64)";
                    if (fmt === "xml") return "Verification payload (XML or JSON)";
                    return "Verification payload (JSON)";
                  })()}
                  <span className="ml-1 text-gray-400" aria-hidden>ⓘ</span>
                </label>
                <textarea
                  value={verificationRequestJson}
                  onChange={(e) => setVerificationRequestJson(e.target.value)}
                  placeholder={
                    (payloadFormat || "json") === "binary"
                      ? "Paste base64 string here (e.g. SGVsbG8=)..."
                      : (payloadFormat || "json") === "xml"
                        ? "<root><field>value</field></root> or {\"field\": \"value\"}"
                        : '{"exampleField": "test-value"}'
                  }
                  rows={4}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
                />
                <p className="text-xs text-gray-500 mt-1">
                  {(payloadFormat || "json") === "binary" ? (
                    "Paste a base64-encoded sample of the file here. Max 5 MB decoded at runtime."
                  ) : (payloadFormat || "json") === "xml" ? (
                    "Paste raw XML or a JSON-like object here. Platform converts JSON to XML if needed."
                  ) : (
                    "Payload sent when verifying this endpoint. Use {} for GET or empty POST."
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
            </div>
          )}
          {error && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
              {error}
            </div>
          )}
          {!useModalPattern && (
            <div className="flex justify-end flex-wrap gap-2 pt-2">
            {isEdit && initialValues?.operationCode && (
              <button
                type="button"
                onClick={() => (isActive ? setShowDeactivateConfirm(true) : handleToggleActive())}
                disabled={isLoading}
                className={`px-4 py-2 text-sm font-medium rounded-lg border ${
                  isActive
                    ? "text-red-600 border-red-200 hover:bg-red-50"
                    : "text-emerald-600 border-emerald-200 hover:bg-emerald-50"
                } disabled:opacity-50`}
              >
                {isActive ? "Deactivate endpoint" : "Activate endpoint"}
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 hover:bg-gray-50 rounded-lg"
            >
              Cancel
            </button>
            {!useModalPattern && isEdit && onVerify && (
              <button
                type="button"
                onClick={() => void handleVerify()}
                disabled={isVerifying || isLoading}
                className="px-4 py-2 text-sm font-medium text-white bg-slate-500 hover:bg-slate-600 rounded-lg disabled:opacity-50"
              >
                {isVerifying ? "Verifying..." : "Verify endpoint"}
              </button>
            )}
            <button
              type="submit"
              disabled={isLoading}
              className="px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 disabled:opacity-50 rounded-lg"
            >
              {isLoading ? "Saving…" : "Save"}
            </button>
            </div>
          )}
        </form>

        {showDeactivateConfirm && (
          <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40">
            <div className="bg-white rounded-lg shadow-xl p-4 max-w-md mx-4">
              <p className="text-sm text-gray-700 mb-4">
                Deactivate this endpoint? Live traffic for this operation may fail until another endpoint is configured.
              </p>
              <div className="flex gap-3 justify-end">
                <button
                  type="button"
                  onClick={() => setShowDeactivateConfirm(false)}
                  className="px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => handleToggleActive()}
                  disabled={isLoading}
                  className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg disabled:opacity-50"
                >
                  {isLoading ? "Deactivating…" : "Deactivate"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
