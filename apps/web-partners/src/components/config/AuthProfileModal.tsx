import { useState, useEffect, useRef } from "react";
import { AuthHelpPanel, type AuthHelpType } from "../auth/AuthHelpPanel";
import {
  testAuthProfileConnection,
  previewAuthProfileToken,
  validateAuthProfileMtls,
  type TestConnectionResponse,
  type JwtTokenPreviewResponse,
  type MtlsValidateResponse,
} from "../../api/endpoints";

const LEGACY_STATIC_BEARER = "STATIC_BEARER";
const SUPPORTED_AUTH_TYPES = [
  { value: "API_KEY_HEADER", label: "API key header" },
  { value: "API_KEY_QUERY", label: "API key query" },
  { value: "BASIC", label: "Basic auth" },
  { value: "BEARER", label: "Bearer token" },
  { value: "JWT", label: "JWT bearer token" },
  { value: "MTLS", label: "mTLS (client certificate)" },
] as const;
type SupportedAuthType = (typeof SUPPORTED_AUTH_TYPES)[number]["value"];

function normalizeAuthType(value: string | undefined | null): SupportedAuthType {
  const t = (value ?? "").trim().toUpperCase();
  if (t === LEGACY_STATIC_BEARER) return "BEARER";
  if (SUPPORTED_AUTH_TYPES.some((x) => x.value === t)) return t as SupportedAuthType;
  return "API_KEY_HEADER";
}

interface AuthProfileModalProps {
  open: boolean;
  onClose: () => void;
  vendorCode: string;
  initialValues?: {
    id?: string;
    name: string;
    authType: string;
    config?: Record<string, unknown>;
    isActive?: boolean;
  } | null;
  onSave: (payload: {
    id?: string;
    vendorCode: string;
    name: string;
    authType: string;
    config?: Record<string, unknown>;
    isActive?: boolean;
  }) => Promise<void>;
  /** When provided and editing, shows Deactivate/Activate profile link. Uses onSave to toggle isActive. */
  onDeactivate?: (profileId: string) => Promise<void>;
}

export function AuthProfileModal({
  open,
  onClose,
  vendorCode,
  initialValues,
  onSave,
  onDeactivate: _onDeactivate,
}: AuthProfileModalProps) {
  const [name, setName] = useState("");
  const [authType, setAuthType] = useState<string>("API_KEY_HEADER");
  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [isActive, setIsActive] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{
    name?: string;
    headerName?: string;
    paramName?: string;
    key?: string;
    token?: string;
    username?: string;
    password?: string;
    tokenUrl?: string;
    clientId?: string;
    clientSecret?: string;
    certPem?: string;
    keyPem?: string;
    caPem?: string;
  }>({});
  const [toggleLoading, setToggleLoading] = useState(false);
  const [showDeactivateConfirm, setShowDeactivateConfirm] = useState(false);
  const [testUrl, setTestUrl] = useState("");
  const [testMethod, setTestMethod] = useState<"GET" | "POST" | "PUT" | "PATCH" | "DELETE">("GET");
  const [testHeadersText, setTestHeadersText] = useState("{}");
  const [testBodyText, setTestBodyText] = useState("");
  const [testTimeoutMs, setTestTimeoutMs] = useState(5000);
  const [testLoading, setTestLoading] = useState(false);
  const [testError, setTestError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<TestConnectionResponse | null>(null);
  const [tokenPreviewLoading, setTokenPreviewLoading] = useState(false);
  const [tokenPreviewResult, setTokenPreviewResult] = useState<JwtTokenPreviewResponse | null>(null);
  const [tokenPreviewError, setTokenPreviewError] = useState<string | null>(null);
  const [mtlsValidateLoading, setMtlsValidateLoading] = useState(false);
  const [mtlsValidateResult, setMtlsValidateResult] = useState<MtlsValidateResponse | null>(null);
  const [mtlsValidateError, setMtlsValidateError] = useState<string | null>(null);
  const [showAuthGuidePanel, setShowAuthGuidePanel] = useState(true);
  const [diagnosticsRefreshCount, setDiagnosticsRefreshCount] = useState(0);
  const lastSeededKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (open) {
      const key = initialValues?.id ?? initialValues?.name ?? "__add__";
      if (lastSeededKeyRef.current !== key) {
        lastSeededKeyRef.current = key;
        setName(initialValues?.name ?? "");
        setAuthType(normalizeAuthType(initialValues?.authType ?? "API_KEY_HEADER"));
        setConfig((initialValues?.config as Record<string, unknown>) ?? {});
        setIsActive(initialValues?.isActive ?? true);
        setError(null);
        setFieldErrors({});
        setTestResult(null);
        setTokenPreviewResult(null);
        setMtlsValidateResult(null);
        setTestError(null);
        setTokenPreviewError(null);
        setMtlsValidateError(null);
        setShowAuthGuidePanel(true);
        setDiagnosticsRefreshCount(0);
      }
    } else {
      lastSeededKeyRef.current = null;
    }
  }, [open, initialValues]);

  useEffect(() => {
    setTestResult(null);
    setTokenPreviewResult(null);
    setMtlsValidateResult(null);
    setTestError(null);
    setTokenPreviewError(null);
    setMtlsValidateError(null);
    setShowAuthGuidePanel(true);
    setDiagnosticsRefreshCount(0);
  }, [authType]);

  const runValidation = (): boolean => {
    const errs: typeof fieldErrors = {};
    const nameTrimmed = name.trim();
    if (!nameTrimmed) errs.name = "Name is required.";
    const t = normalizeAuthType(authType);
    if (t === "API_KEY_HEADER") {
      const headerName = (config.headerName as string)?.trim();
      const key = ((config.key as string) ?? (config.value as string))?.trim();
      if (!headerName) errs.headerName = "Header name is required.";
      if (!key) errs.key = "API key value is required.";
    }
    if (t === "API_KEY_QUERY") {
      const paramName = (config.paramName as string)?.trim();
      const key = ((config.key as string) ?? (config.value as string))?.trim();
      if (!paramName) errs.paramName = "Parameter name is required.";
      if (!key) errs.key = "API key value is required.";
    }
    if (t === "BEARER") {
      const token = (config.token as string)?.trim();
      if (!token) errs.token = "Token is required.";
    }
    if (t === "BASIC") {
      const username = (config.username as string)?.trim();
      const password = (config.password as string)?.trim();
      if (!username) errs.username = "Username is required.";
      if (!password) errs.password = "Password is required.";
    }
    if (t === "JWT") {
      const tokenUrl = (config.tokenUrl as string)?.trim();
      const clientId = (config.clientId as string)?.trim();
      const clientSecret = (config.clientSecret as string)?.trim();
      if (!tokenUrl) errs.tokenUrl = "Token URL is required.";
      if (!clientId) errs.clientId = "Client ID is required.";
      if (!clientSecret) errs.clientSecret = "Client secret is required.";
    }
    if (t === "MTLS") {
      const certPem = (config.certPem as string)?.trim();
      const keyPem = (config.keyPem as string)?.trim();
      const caPem = (config.caPem as string)?.trim();
      if (!certPem) errs.certPem = "Certificate PEM is required.";
      if (!keyPem) errs.keyPem = "Private key PEM is required.";
      if (!caPem) errs.caPem = "Certificate authority PEM is required.";
    }
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const buildFinalConfig = (type: SupportedAuthType): Record<string, unknown> => {
    if (type === "API_KEY_HEADER") {
      const keyValue = ((config.key as string) ?? (config.value as string))?.trim();
      return {
        headerName: (config.headerName as string)?.trim() || "Api-Key",
        value: keyValue,
      };
    }
    if (type === "API_KEY_QUERY") {
      const keyValue = ((config.key as string) ?? (config.value as string))?.trim();
      return {
        paramName: (config.paramName as string)?.trim() || "api_key",
        value: keyValue,
      };
    }
    if (type === "BEARER") {
      return {
        headerName: (config.headerName as string)?.trim() || "Authorization",
        prefix: "Bearer",
        token: (config.token as string)?.trim(),
      };
    }
    if (type === "JWT") {
      return {
        headerName: "Authorization",
        prefix: "Bearer",
        tokenUrl: (config.tokenUrl as string)?.trim(),
        clientId: (config.clientId as string)?.trim(),
        clientSecret: (config.clientSecret as string)?.trim(),
        scope: (config.scope as string)?.trim() || undefined,
      };
    }
    if (type === "BASIC") {
      return {
        username: (config.username as string)?.trim(),
        password: (config.password as string)?.trim(),
      };
    }
    if (type === "MTLS") {
      return {
        certPem: (config.certPem as string)?.trim(),
        keyPem: (config.keyPem as string)?.trim(),
        caPem: (config.caPem as string)?.trim(),
        passphrase: (config.passphrase as string)?.trim() || undefined,
      };
    }
    return {};
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!runValidation()) return;
    const nameTrimmed = name.trim();
    const t = normalizeAuthType(authType);
    const finalConfig = buildFinalConfig(t);
    setIsLoading(true);
    try {
      await onSave({
        id: initialValues?.id,
        vendorCode,
        name: nameTrimmed,
        authType: t,
        config: finalConfig,
        isActive,
      });
      onClose();
    } catch (err) {
      const axiosErr = err as {
        response?: { data?: { error?: { message?: string } } };
        message?: string;
      };
      setError(
        axiosErr?.response?.data?.error?.message ??
          (err as Error)?.message ??
          "Failed to save.",
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggleActiveClick = () => {
    if (isActive) {
      setShowDeactivateConfirm(true);
    } else {
      handleToggleActive();
    }
  };

  const handleToggleActive = async () => {
    setShowDeactivateConfirm(false);
    if (!initialValues?.id) return;
    if (!runValidation()) return;
    const nameTrimmed = name.trim();
    const t = normalizeAuthType(authType);
    const finalConfig = buildFinalConfig(t);
    setToggleLoading(true);
    try {
      await onSave({
        id: initialValues.id,
        vendorCode,
        name: nameTrimmed,
        authType: t,
        config: finalConfig,
        isActive: !isActive,
      });
      setIsActive(!isActive);
    } catch (err) {
      const axiosErr = err as {
        response?: { data?: { error?: { message?: string } } };
        message?: string;
      };
      setError(
        axiosErr?.response?.data?.error?.message ??
          (err as Error)?.message ??
          "Failed to update.",
      );
    } finally {
      setToggleLoading(false);
    }
  };

  const normalizedAuthType = normalizeAuthType(authType);
  const testReadyByAuthType =
    normalizedAuthType === "API_KEY_HEADER"
      ? !!((config.headerName as string)?.trim() && ((config.key as string) ?? (config.value as string))?.trim())
      : normalizedAuthType === "API_KEY_QUERY"
        ? !!((config.paramName as string)?.trim() && ((config.key as string) ?? (config.value as string))?.trim())
        : normalizedAuthType === "BASIC"
          ? !!((config.username as string)?.trim() && (config.password as string)?.trim())
          : normalizedAuthType === "BEARER"
            ? !!(config.token as string)?.trim()
            : normalizedAuthType === "JWT"
              ? !!((config.tokenUrl as string)?.trim() && (config.clientId as string)?.trim() && (config.clientSecret as string)?.trim())
              : !!((config.certPem as string)?.trim() && (config.keyPem as string)?.trim() && (config.caPem as string)?.trim());
  const canRunConnectionTest = !!name.trim() && !!testUrl.trim() && testReadyByAuthType;

  const runConnectionTest = async () => {
    if (!canRunConnectionTest || testLoading) return;
    setTestLoading(true);
    setTestError(null);
    setShowAuthGuidePanel(false);
    try {
      let parsedHeaders: Record<string, string> = {};
      try {
        const parsed = JSON.parse(testHeadersText || "{}");
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          parsedHeaders = Object.fromEntries(
            Object.entries(parsed as Record<string, unknown>).map(([k, v]) => [String(k), String(v)])
          );
        } else {
          throw new Error("Headers JSON must be an object.");
        }
      } catch {
        setTestError("Headers must be a valid JSON object.");
        setTestLoading(false);
        return;
      }

      let body: Record<string, unknown> | string | null = null;
      if (testBodyText.trim()) {
        try {
          body = JSON.parse(testBodyText);
        } catch {
          body = testBodyText;
        }
      }

      const result = await testAuthProfileConnection({
        authProfileId: initialValues?.id ?? null,
        authType: normalizedAuthType,
        authConfig: buildFinalConfig(normalizedAuthType),
        url: testUrl.trim(),
        method: testMethod,
        headers: parsedHeaders,
        body,
        timeoutMs: Math.min(10000, Math.max(1, testTimeoutMs)),
      });
      setTestResult(result);
      setDiagnosticsRefreshCount((c) => c + 1);
    } catch (err) {
      setTestError((err as Error)?.message ?? "Failed to run test connection.");
      setDiagnosticsRefreshCount((c) => c + 1);
    } finally {
      setTestLoading(false);
    }
  };

  const runTokenPreview = async () => {
    if (normalizedAuthType !== "JWT" || tokenPreviewLoading) return;
    setTokenPreviewLoading(true);
    setTokenPreviewError(null);
    setShowAuthGuidePanel(false);
    try {
      const result = await previewAuthProfileToken({
        authType: "JWT_BEARER_TOKEN",
        authConfig: buildFinalConfig(normalizedAuthType),
        timeoutMs: 5000,
      });
      setTokenPreviewResult(result);
      setDiagnosticsRefreshCount((c) => c + 1);
    } catch (err) {
      setTokenPreviewError((err as Error)?.message ?? "Failed to fetch token preview.");
      setDiagnosticsRefreshCount((c) => c + 1);
    } finally {
      setTokenPreviewLoading(false);
    }
  };

  const runMtlsValidate = async () => {
    if (normalizedAuthType !== "MTLS" || mtlsValidateLoading) return;
    setMtlsValidateLoading(true);
    setMtlsValidateError(null);
    setShowAuthGuidePanel(false);
    try {
      const result = await validateAuthProfileMtls({
        certificatePem: String(config.certPem ?? ""),
        privateKeyPem: String(config.keyPem ?? ""),
        caBundlePem: String(config.caPem ?? "") || null,
      });
      setMtlsValidateResult(result);
      setDiagnosticsRefreshCount((c) => c + 1);
    } catch (err) {
      setMtlsValidateError((err as Error)?.message ?? "Failed to validate certificate.");
      setDiagnosticsRefreshCount((c) => c + 1);
    } finally {
      setMtlsValidateLoading(false);
    }
  };

  const renderDiagnosticsControls = () => (
    <div className="mt-2 rounded-md border border-slate-200 bg-white p-3 space-y-3">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        <input
          type="url"
          value={testUrl}
          onChange={(e) => setTestUrl(e.target.value)}
          placeholder="https://api.vendor.com/health"
          className="md:col-span-2 px-3 py-2 border border-gray-300 rounded text-xs"
        />
        <div className="grid grid-cols-2 gap-2">
          <select
            value={testMethod}
            onChange={(e) => setTestMethod(e.target.value as "GET" | "POST" | "PUT" | "PATCH" | "DELETE")}
            className="px-2 py-2 border border-gray-300 rounded text-xs"
          >
            <option value="GET">GET</option>
            <option value="POST">POST</option>
            <option value="PUT">PUT</option>
            <option value="PATCH">PATCH</option>
            <option value="DELETE">DELETE</option>
          </select>
          <input
            type="number"
            min={1}
            max={10000}
            value={testTimeoutMs}
            onChange={(e) => setTestTimeoutMs(Number(e.target.value || 5000))}
            className="px-2 py-2 border border-gray-300 rounded text-xs"
            title="Timeout in milliseconds"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <textarea
          rows={2}
          value={testHeadersText}
          onChange={(e) => setTestHeadersText(e.target.value)}
          className="w-full px-2 py-2 border border-gray-300 rounded text-xs font-mono"
          placeholder='Headers JSON (non-secret), e.g. {"X-Trace":"demo"}'
        />
        {(testMethod === "POST" || testMethod === "PUT" || testMethod === "PATCH" || testMethod === "DELETE") ? (
          <textarea
            rows={2}
            value={testBodyText}
            onChange={(e) => setTestBodyText(e.target.value)}
            className="w-full px-2 py-2 border border-gray-300 rounded text-xs font-mono"
            placeholder="Optional body (JSON or text)"
          />
        ) : (
          <div className="hidden md:block" />
        )}
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2">
        <button
          type="button"
          onClick={runConnectionTest}
          disabled={!canRunConnectionTest || testLoading}
          className="px-3 py-1.5 text-xs font-medium text-slate-700 border border-slate-300 rounded-lg hover:bg-slate-50 disabled:opacity-50"
        >
          {testLoading ? "Testing..." : "Test connection"}
        </button>
        {normalizedAuthType === "JWT" && (
          <button
            type="button"
            onClick={runTokenPreview}
            disabled={!testReadyByAuthType || tokenPreviewLoading}
            className="px-3 py-1.5 text-xs font-medium text-slate-700 border border-slate-300 rounded-lg hover:bg-slate-50 disabled:opacity-50"
          >
            {tokenPreviewLoading ? "Fetching..." : "Fetch token (preview)"}
          </button>
        )}
        {normalizedAuthType === "MTLS" && (
          <button
            type="button"
            onClick={runMtlsValidate}
            disabled={!testReadyByAuthType || mtlsValidateLoading}
            className="px-3 py-1.5 text-xs font-medium text-slate-700 border border-slate-300 rounded-lg hover:bg-slate-50 disabled:opacity-50"
          >
            {mtlsValidateLoading ? "Validating..." : "Validate certificate"}
          </button>
        )}
      </div>

      {(testResult || tokenPreviewResult || mtlsValidateResult || testError || tokenPreviewError || mtlsValidateError) && (
        <div className="rounded-md border border-gray-200 bg-gray-50 p-3 space-y-2">
          <p className="text-xs font-semibold text-gray-800">
            Diagnostics Result (refresh #{diagnosticsRefreshCount})
          </p>
          {testError && <p className="text-xs text-red-600">{testError}</p>}
          {testResult && (
            <div className="text-xs text-gray-700 space-y-1">
              <p>
                Test connection:{" "}
                <span className={testResult.ok ? "text-emerald-700 font-medium" : "text-red-700 font-medium"}>
                  {testResult.ok ? "Success" : "Failure"}
                </span>
              </p>
              <p>HTTP: {testResult.httpStatus ?? "-"} | Latency: {testResult.latencyMs} ms</p>
              {testResult.error && <p>{testResult.error.category}: {testResult.error.message}</p>}
              <pre className="rounded border border-gray-200 bg-white p-2 text-[11px] overflow-x-auto">
                {testResult.responsePreview || "(empty)"}
              </pre>
            </div>
          )}
          {tokenPreviewError && <p className="text-xs text-red-600">{tokenPreviewError}</p>}
          {tokenPreviewResult && (
            <div className="text-xs text-gray-700 space-y-1">
              <p>
                Token preview:{" "}
                <span className={tokenPreviewResult.ok ? "text-emerald-700 font-medium" : "text-red-700 font-medium"}>
                  {tokenPreviewResult.ok ? "Success" : "Failure"}
                </span>
              </p>
              {tokenPreviewResult.tokenRedacted && <p>Token: {tokenPreviewResult.tokenRedacted}</p>}
              {tokenPreviewResult.expiresIn != null && <p>expires_in: {tokenPreviewResult.expiresIn}s</p>}
              {tokenPreviewResult.jwtClaims && (
                <p>
                  iss: {String(tokenPreviewResult.jwtClaims.iss ?? "-")} | aud:{" "}
                  {Array.isArray(tokenPreviewResult.jwtClaims.aud)
                    ? tokenPreviewResult.jwtClaims.aud.join(", ")
                    : String(tokenPreviewResult.jwtClaims.aud ?? "-")}
                </p>
              )}
              {tokenPreviewResult.error && (
                <p>{tokenPreviewResult.error.category}: {tokenPreviewResult.error.message}</p>
              )}
            </div>
          )}
          {mtlsValidateError && <p className="text-xs text-red-600">{mtlsValidateError}</p>}
          {mtlsValidateResult && (
            <div className="text-xs text-gray-700 space-y-1">
              <p>
                Certificate validation:{" "}
                <span className={mtlsValidateResult.ok ? "text-emerald-700 font-medium" : "text-red-700 font-medium"}>
                  {mtlsValidateResult.ok ? "Valid" : "Invalid"}
                </span>
              </p>
              <p>Expiry: {mtlsValidateResult.expiresAt ?? "-"} | Days remaining: {mtlsValidateResult.daysRemaining ?? "-"}</p>
              {mtlsValidateResult.warnings && mtlsValidateResult.warnings.length > 0 && (
                <p>Warnings: {mtlsValidateResult.warnings.join(", ")}</p>
              )}
              {mtlsValidateResult.error && (
                <p>{mtlsValidateResult.error.category}: {mtlsValidateResult.error.message}</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );

  return (
    <div
      className={`fixed inset-0 z-50 ${open ? "flex items-center justify-center p-2 sm:p-3" : "hidden"}`}
    >
      <div className="absolute inset-0 bg-black/30" aria-hidden />
      <div
        className="relative w-full max-w-5xl bg-white rounded-lg shadow-xl overflow-y-auto max-h-[90vh]"
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-gray-200 bg-gray-50">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-gray-900">
              {initialValues?.id ? "Edit auth profile" : "New auth profile"}
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Applies to all endpoints that reference this profile.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="p-2 text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-200"
              aria-label="Close"
            >
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3 p-3 sm:p-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="space-y-3 lg:col-span-2">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Name
                  </label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => {
                      setName(e.target.value);
                      if (fieldErrors.name) setFieldErrors((prev) => ({ ...prev, name: undefined }));
                    }}
                    placeholder="e.g. API key for Acme"
                    className={`w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500 ${
                      fieldErrors.name ? "border-red-300" : "border-gray-300"
                    }`}
                  />
                  {fieldErrors.name && (
                    <p className="mt-1 text-xs text-red-600">{fieldErrors.name}</p>
                  )}
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Auth Type
                  </label>
                  <select
                    value={normalizedAuthType}
                    onChange={(e) => {
                      setAuthType(normalizeAuthType(e.target.value));
                      setFieldErrors({});
                    }}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
                  >
                    {SUPPORTED_AUTH_TYPES.map(({ value, label }) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {normalizedAuthType === "API_KEY_HEADER" && (
                <div className="space-y-3 rounded-lg border border-gray-200 p-3 bg-gray-50">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Header Name
                    </label>
                    <input
                      type="text"
                      value={(config.headerName as string) ?? "Api-Key"}
                      onChange={(e) => {
                        setConfig((c) => ({ ...c, headerName: e.target.value }));
                        if (fieldErrors.headerName) setFieldErrors((f) => ({ ...f, headerName: undefined }));
                      }}
                      placeholder="Api-Key"
                      className={`w-full px-3 py-2 border rounded text-sm ${
                        fieldErrors.headerName ? "border-red-300" : "border-gray-300"
                      }`}
                    />
                    {fieldErrors.headerName && (
                      <p className="mt-1 text-xs text-red-600">{fieldErrors.headerName}</p>
                    )}
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      API Key Value
                    </label>
                    <input
                      type="password"
                      value={((config.key as string) ?? (config.value as string)) ?? ""}
                      onChange={(e) => {
                        setConfig((c) => ({ ...c, key: e.target.value, value: e.target.value }));
                        if (fieldErrors.key) setFieldErrors((f) => ({ ...f, key: undefined }));
                      }}
                      placeholder="Your API key"
                      className={`w-full px-3 py-2 border rounded text-sm ${
                        fieldErrors.key ? "border-red-300" : "border-gray-300"
                      }`}
                    />
                    {fieldErrors.key && (
                      <p className="mt-1 text-xs text-red-600">{fieldErrors.key}</p>
                    )}
                  </div>
                  {renderDiagnosticsControls()}
                </div>
              )}

              {normalizedAuthType === "API_KEY_QUERY" && (
                <div className="space-y-3 rounded-lg border border-gray-200 p-3 bg-gray-50">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Parameter Name
                    </label>
                    <input
                      type="text"
                      value={(config.paramName as string) ?? "api_key"}
                      onChange={(e) => {
                        setConfig((c) => ({ ...c, paramName: e.target.value }));
                        if (fieldErrors.paramName) setFieldErrors((f) => ({ ...f, paramName: undefined }));
                      }}
                      placeholder="api_key"
                      className={`w-full px-3 py-2 border rounded text-sm ${
                        fieldErrors.paramName ? "border-red-300" : "border-gray-300"
                      }`}
                    />
                    {fieldErrors.paramName && (
                      <p className="mt-1 text-xs text-red-600">{fieldErrors.paramName}</p>
                    )}
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      API Key Value
                    </label>
                    <input
                      type="password"
                      value={((config.key as string) ?? (config.value as string)) ?? ""}
                      onChange={(e) => {
                        setConfig((c) => ({ ...c, key: e.target.value, value: e.target.value }));
                        if (fieldErrors.key) setFieldErrors((f) => ({ ...f, key: undefined }));
                      }}
                      placeholder="Your API key"
                      className={`w-full px-3 py-2 border rounded text-sm ${
                        fieldErrors.key ? "border-red-300" : "border-gray-300"
                      }`}
                    />
                    {fieldErrors.key && (
                      <p className="mt-1 text-xs text-red-600">{fieldErrors.key}</p>
                    )}
                  </div>
                  {renderDiagnosticsControls()}
                </div>
              )}

              {normalizedAuthType === "BEARER" && (
                <div className="space-y-3 rounded-lg border border-gray-200 p-3 bg-gray-50">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Token
                    </label>
                    <input
                      type="password"
                      value={(config.token as string) ?? ""}
                      onChange={(e) => {
                        setConfig((c) => ({ ...c, token: e.target.value }));
                        if (fieldErrors.token) setFieldErrors((f) => ({ ...f, token: undefined }));
                      }}
                      placeholder="Paste token here..."
                      className={`w-full px-3 py-2 border rounded text-sm ${
                        fieldErrors.token ? "border-red-300" : "border-gray-300"
                      }`}
                    />
                    {fieldErrors.token && (
                      <p className="mt-1 text-xs text-red-600">{fieldErrors.token}</p>
                    )}
                  </div>
                  {renderDiagnosticsControls()}
                </div>
              )}

              {normalizedAuthType === "JWT" && (
                <div className="space-y-3 rounded-lg border border-gray-200 p-3 bg-gray-50">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Token URL
                    </label>
                    <input
                      type="url"
                      value={(config.tokenUrl as string) ?? ""}
                      onChange={(e) => {
                        setConfig((c) => ({ ...c, tokenUrl: e.target.value }));
                        if (fieldErrors.tokenUrl) setFieldErrors((f) => ({ ...f, tokenUrl: undefined }));
                      }}
                      placeholder="https://idp.vendor.com/oauth/token"
                      className={`w-full px-3 py-2 border rounded text-sm ${
                        fieldErrors.tokenUrl ? "border-red-300" : "border-gray-300"
                      }`}
                    />
                    {fieldErrors.tokenUrl && (
                      <p className="mt-1 text-xs text-red-600">{fieldErrors.tokenUrl}</p>
                    )}
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Client ID
                    </label>
                    <input
                      type="text"
                      value={(config.clientId as string) ?? ""}
                      onChange={(e) => {
                        setConfig((c) => ({ ...c, clientId: e.target.value }));
                        if (fieldErrors.clientId) setFieldErrors((f) => ({ ...f, clientId: undefined }));
                      }}
                      placeholder="integration-hub-client"
                      className={`w-full px-3 py-2 border rounded text-sm ${
                        fieldErrors.clientId ? "border-red-300" : "border-gray-300"
                      }`}
                    />
                    {fieldErrors.clientId && (
                      <p className="mt-1 text-xs text-red-600">{fieldErrors.clientId}</p>
                    )}
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Client Secret
                    </label>
                    <input
                      type="password"
                      value={(config.clientSecret as string) ?? ""}
                      onChange={(e) => {
                        setConfig((c) => ({ ...c, clientSecret: e.target.value }));
                        if (fieldErrors.clientSecret) setFieldErrors((f) => ({ ...f, clientSecret: undefined }));
                      }}
                      placeholder="Client secret"
                      className={`w-full px-3 py-2 border rounded text-sm ${
                        fieldErrors.clientSecret ? "border-red-300" : "border-gray-300"
                      }`}
                    />
                    {fieldErrors.clientSecret && (
                      <p className="mt-1 text-xs text-red-600">{fieldErrors.clientSecret}</p>
                    )}
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Scope (optional)
                    </label>
                    <input
                      type="text"
                      value={(config.scope as string) ?? ""}
                      onChange={(e) => setConfig((c) => ({ ...c, scope: e.target.value }))}
                      placeholder="read:claims write:claims"
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    />
                  </div>
                  {renderDiagnosticsControls()}
                </div>
              )}

              {normalizedAuthType === "BASIC" && (
                <div className="space-y-3 rounded-lg border border-gray-200 p-3 bg-gray-50">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Username
                    </label>
                    <input
                      type="text"
                      value={(config.username as string) ?? ""}
                      onChange={(e) => {
                        setConfig((c) => ({ ...c, username: e.target.value }));
                        if (fieldErrors.username) setFieldErrors((f) => ({ ...f, username: undefined }));
                      }}
                      placeholder="api-user"
                      className={`w-full px-3 py-2 border rounded text-sm ${
                        fieldErrors.username ? "border-red-300" : "border-gray-300"
                      }`}
                    />
                    {fieldErrors.username && (
                      <p className="mt-1 text-xs text-red-600">{fieldErrors.username}</p>
                    )}
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Password
                    </label>
                    <input
                      type="password"
                      value={(config.password as string) ?? ""}
                      onChange={(e) => {
                        setConfig((c) => ({ ...c, password: e.target.value }));
                        if (fieldErrors.password) setFieldErrors((f) => ({ ...f, password: undefined }));
                      }}
                      placeholder="********"
                      className={`w-full px-3 py-2 border rounded text-sm ${
                        fieldErrors.password ? "border-red-300" : "border-gray-300"
                      }`}
                    />
                    {fieldErrors.password && (
                      <p className="mt-1 text-xs text-red-600">{fieldErrors.password}</p>
                    )}
                  </div>
                  {renderDiagnosticsControls()}
                </div>
              )}

              {normalizedAuthType === "MTLS" && (
                <div className="space-y-3 rounded-lg border border-gray-200 p-3 bg-gray-50">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Client certificate (PEM)
                    </label>
                    <textarea
                      value={(config.certPem as string) ?? ""}
                      onChange={(e) => {
                        setConfig((c) => ({ ...c, certPem: e.target.value }));
                        if (fieldErrors.certPem) setFieldErrors((f) => ({ ...f, certPem: undefined }));
                      }}
                      rows={4}
                      placeholder="-----BEGIN CERTIFICATE-----"
                      className={`w-full px-3 py-2 border rounded text-sm font-mono ${
                        fieldErrors.certPem ? "border-red-300" : "border-gray-300"
                      }`}
                    />
                    {fieldErrors.certPem && (
                      <p className="mt-1 text-xs text-red-600">{fieldErrors.certPem}</p>
                    )}
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Client private key (PEM)
                    </label>
                    <textarea
                      value={(config.keyPem as string) ?? ""}
                      onChange={(e) => {
                        setConfig((c) => ({ ...c, keyPem: e.target.value }));
                        if (fieldErrors.keyPem) setFieldErrors((f) => ({ ...f, keyPem: undefined }));
                      }}
                      rows={4}
                      placeholder="-----BEGIN PRIVATE KEY-----"
                      className={`w-full px-3 py-2 border rounded text-sm font-mono ${
                        fieldErrors.keyPem ? "border-red-300" : "border-gray-300"
                      }`}
                    />
                    {fieldErrors.keyPem && (
                      <p className="mt-1 text-xs text-red-600">{fieldErrors.keyPem}</p>
                    )}
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Certificate authority (PEM)
                    </label>
                    <textarea
                      value={(config.caPem as string) ?? ""}
                      onChange={(e) => {
                        setConfig((c) => ({ ...c, caPem: e.target.value }));
                        if (fieldErrors.caPem) setFieldErrors((f) => ({ ...f, caPem: undefined }));
                      }}
                      rows={3}
                      placeholder="-----BEGIN CERTIFICATE-----"
                      className={`w-full px-3 py-2 border rounded text-sm font-mono ${
                        fieldErrors.caPem ? "border-red-300" : "border-gray-300"
                      }`}
                    />
                    {fieldErrors.caPem && (
                      <p className="mt-1 text-xs text-red-600">{fieldErrors.caPem}</p>
                    )}
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Key passphrase (optional)
                    </label>
                    <input
                      type="password"
                      value={(config.passphrase as string) ?? ""}
                      onChange={(e) => setConfig((c) => ({ ...c, passphrase: e.target.value }))}
                      placeholder="Optional passphrase"
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    />
                  </div>
                  {renderDiagnosticsControls()}
                </div>
              )}

              <div className="flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"
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

              <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                Sensitive credentials are stored using encrypted storage and must never be logged.
              </div>

            </div>

            <div className="lg:col-span-1">
              {showAuthGuidePanel ? (
                <AuthHelpPanel authType={normalizedAuthType as AuthHelpType} />
              ) : (
                <aside className="rounded-lg border border-gray-200 bg-gray-50 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-gray-900">Diagnostics Panel</h3>
                    <button
                      type="button"
                      onClick={() => setShowAuthGuidePanel(true)}
                      className="text-xs text-slate-700 underline"
                    >
                      X Close
                    </button>
                  </div>
                  <p className="text-xs text-gray-700">
                    Authentication guide is temporarily replaced while running diagnostics.
                  </p>
                  <div className="rounded border border-gray-200 bg-white p-3 text-xs text-gray-700 space-y-1">
                    <p>Refresh count: {diagnosticsRefreshCount}</p>
                    <p>Auth type: {normalizedAuthType}</p>
                    {testResult && (
                      <p>
                        Last connection test:{" "}
                        <span className={testResult.ok ? "text-emerald-700 font-medium" : "text-red-700 font-medium"}>
                          {testResult.ok ? "Success" : "Failure"}
                        </span>
                      </p>
                    )}
                    {tokenPreviewResult && (
                      <p>
                        Last token preview:{" "}
                        <span className={tokenPreviewResult.ok ? "text-emerald-700 font-medium" : "text-red-700 font-medium"}>
                          {tokenPreviewResult.ok ? "Success" : "Failure"}
                        </span>
                      </p>
                    )}
                    {mtlsValidateResult && (
                      <p>
                        Last certificate validation:{" "}
                        <span className={mtlsValidateResult.ok ? "text-emerald-700 font-medium" : "text-red-700 font-medium"}>
                          {mtlsValidateResult.ok ? "Valid" : "Invalid"}
                        </span>
                      </p>
                    )}
                  </div>
                </aside>
              )}
            </div>
          </div>

          {error && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
              {error}
            </div>
          )}
          <div className="pt-1.5 space-y-1">
            {initialValues?.id && (
              <p className="text-xs text-gray-500 text-right">
                Inactive profiles remain saved but cannot be selected by endpoints.
              </p>
            )}
            <div className="flex items-center justify-end gap-3">
              {initialValues?.id && (
                <button
                  type="button"
                  onClick={handleToggleActiveClick}
                  disabled={toggleLoading}
                  className={`px-4 py-2 text-sm font-medium rounded-lg border ${
                    isActive
                      ? "text-red-600 border-red-200 hover:bg-red-50"
                      : "text-emerald-600 border-emerald-200 hover:bg-emerald-50"
                  } disabled:opacity-50`}
                >
                  {toggleLoading
                    ? (isActive ? "Deactivating…" : "Activating…")
                    : isActive
                      ? "Deactivate profile"
                      : "Activate profile"}
                </button>
              )}
            </div>
          </div>
        </form>

        {showDeactivateConfirm && (
          <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40">
            <div className="bg-white rounded-lg shadow-xl p-4 max-w-md mx-4">
              <p className="text-sm text-gray-700 mb-4">
                Deactivate this profile? Live endpoints using it may start failing until they&apos;re updated.
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
                  disabled={toggleLoading}
                  className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg disabled:opacity-50"
                >
                  {toggleLoading ? "Deactivating…" : "Deactivate"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
