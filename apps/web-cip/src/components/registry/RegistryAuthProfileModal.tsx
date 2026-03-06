import { useEffect, useState } from "react";
import type { Vendor } from "../../types";
import type { AuthProfile } from "../../api/endpoints";
import { AuthTestConnectionModal } from "../auth/AuthTestConnectionModal";
import { JwtTokenPreviewPanel } from "../auth/JwtTokenPreviewPanel";
import { MtlsValidatePanel } from "../auth/MtlsValidatePanel";

const AUTH_TYPES = [
  { value: "API_KEY_HEADER", label: "API key header" },
  { value: "API_KEY_QUERY", label: "API key query" },
  { value: "BASIC", label: "Basic auth" },
  { value: "BEARER", label: "Bearer token" },
  { value: "JWT_BEARER_TOKEN", label: "JWT bearer token" },
  { value: "MTLS", label: "mTLS (client certificate)" },
] as const;

interface RegistryAuthProfileModalProps {
  open: boolean;
  onClose: () => void;
  initialValues: AuthProfile | null;
  vendors: Vendor[];
  onSave: (payload: {
    id?: string;
    vendorCode: string;
    name: string;
    authType: string;
    config?: Record<string, unknown>;
    isActive?: boolean;
  }) => Promise<void>;
  authTypeHints?: Record<string, string>;
}

export function RegistryAuthProfileModal({
  open,
  onClose,
  initialValues,
  vendors,
  onSave,
  authTypeHints = {},
}: RegistryAuthProfileModalProps) {
  const [vendorCode, setVendorCode] = useState("");
  const [name, setName] = useState("");
  const [authType, setAuthType] = useState<string>("API_KEY_HEADER");
  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [isActive, setIsActive] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testModalOpen, setTestModalOpen] = useState(false);

  useEffect(() => {
    if (open) {
      setVendorCode(initialValues?.vendorCode ?? "");
      setName(initialValues?.name ?? "");
      const normalized = normalizeAuthType(initialValues?.authType ?? "API_KEY_HEADER");
      setAuthType(normalized);
      const c = initialValues?.config;
      setConfig(typeof c === "object" && c ? c : {});
      setIsActive(initialValues?.isActive !== false);
      setError(null);
    }
  }, [open, initialValues]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const vendorTrimmed = vendorCode.trim();
    const nameTrimmed = name.trim();
    if (!vendorTrimmed) {
      setError("Vendor is required");
      return;
    }
    if (!nameTrimmed) {
      setError("Name is required");
      return;
    }
    const type = normalizeAuthType(authType);
    const configObj = buildFinalConfig(type, config);
    const validationError = validateConfig(type, configObj);
    if (validationError) {
      setError(validationError);
      return;
    }

    setIsLoading(true);
    try {
      await onSave({
        id: initialValues?.id,
        vendorCode: vendorTrimmed,
        name: nameTrimmed,
        authType: type,
        config: configObj,
        isActive,
      });
      onClose();
    } catch (err) {
      const axiosErr = err as { response?: { data?: { error?: { message?: string } } }; message?: string };
      setError(axiosErr?.response?.data?.error?.message ?? (err as Error)?.message ?? "Failed to save.");
    } finally {
      setIsLoading(false);
    }
  };

  const hint = authTypeHints[authType];

  return (
    <div className={`fixed inset-0 z-50 flex items-center justify-center ${open ? "" : "hidden"}`}>
      <div className="absolute inset-0 bg-black/50" aria-hidden />
      <div
        className="relative w-full max-w-4xl bg-white rounded-lg shadow-xl p-6 mx-4 max-h-[90vh] overflow-y-auto"
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">
            {initialValues ? "Edit Auth Profile" : "New Auth Profile"}
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
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Vendor</label>
                <select
                  value={vendorCode}
                  onChange={(e) => setVendorCode(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
                >
                  <option value="">Select vendor…</option>
                  {vendors.map((v) => (
                    <option key={v.vendorCode} value={v.vendorCode}>
                      {v.vendorCode} {v.vendorName ? `— ${v.vendorName}` : ""}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. LH001 Claims API Key"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Auth type</label>
                <select
                  value={authType}
                  onChange={(e) => setAuthType(normalizeAuthType(e.target.value))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
                >
                  {AUTH_TYPES.map(({ value, label }) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                {hint && <p className="mt-1 text-xs text-gray-500">{hint}</p>}
              </div>

              {authType === "API_KEY_HEADER" && (
                <div className="space-y-3 rounded-lg border border-gray-200 bg-gray-50 p-3">
                  <input
                    type="text"
                    value={String(config.headerName ?? "Api-Key")}
                    onChange={(e) => setConfig((c) => ({ ...c, headerName: e.target.value }))}
                    placeholder="Header name (Api-Key)"
                    className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                  />
                  <input
                    type="password"
                    value={String(config.key ?? config.value ?? "")}
                    onChange={(e) => setConfig((c) => ({ ...c, key: e.target.value, value: e.target.value }))}
                    placeholder="API key value"
                    className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                  />
                </div>
              )}

              {authType === "API_KEY_QUERY" && (
                <div className="space-y-3 rounded-lg border border-gray-200 bg-gray-50 p-3">
                  <input
                    type="text"
                    value={String(config.paramName ?? "api_key")}
                    onChange={(e) => setConfig((c) => ({ ...c, paramName: e.target.value }))}
                    placeholder="Parameter name (api_key)"
                    className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                  />
                  <input
                    type="password"
                    value={String(config.key ?? config.value ?? "")}
                    onChange={(e) => setConfig((c) => ({ ...c, key: e.target.value, value: e.target.value }))}
                    placeholder="API key value"
                    className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                  />
                </div>
              )}

              {authType === "BASIC" && (
                <div className="space-y-3 rounded-lg border border-gray-200 bg-gray-50 p-3">
                  <input
                    type="text"
                    value={String(config.username ?? "")}
                    onChange={(e) => setConfig((c) => ({ ...c, username: e.target.value }))}
                    placeholder="Username"
                    className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                  />
                  <input
                    type="password"
                    value={String(config.password ?? "")}
                    onChange={(e) => setConfig((c) => ({ ...c, password: e.target.value }))}
                    placeholder="Password"
                    className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                  />
                </div>
              )}

              {authType === "BEARER" && (
                <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                  <input
                    type="password"
                    value={String(config.token ?? "")}
                    onChange={(e) => setConfig((c) => ({ ...c, token: e.target.value }))}
                    placeholder="Bearer token"
                    className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                  />
                </div>
              )}

              {authType === "JWT_BEARER_TOKEN" && (
                <div className="space-y-3 rounded-lg border border-gray-200 bg-gray-50 p-3">
                  <input
                    type="url"
                    value={String(config.tokenUrl ?? "")}
                    onChange={(e) => setConfig((c) => ({ ...c, tokenUrl: e.target.value }))}
                    placeholder="Token URL"
                    className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                  />
                  <input
                    type="text"
                    value={String(config.clientId ?? "")}
                    onChange={(e) => setConfig((c) => ({ ...c, clientId: e.target.value }))}
                    placeholder="Client ID"
                    className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                  />
                  <input
                    type="password"
                    value={String(config.clientSecret ?? "")}
                    onChange={(e) => setConfig((c) => ({ ...c, clientSecret: e.target.value }))}
                    placeholder="Client Secret"
                    className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                  />
                  <input
                    type="text"
                    value={String(config.scope ?? "")}
                    onChange={(e) => setConfig((c) => ({ ...c, scope: e.target.value }))}
                    placeholder="Scope (optional)"
                    className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                  />
                </div>
              )}

              {authType === "MTLS" && (
                <div className="space-y-3 rounded-lg border border-gray-200 bg-gray-50 p-3">
                  <textarea
                    rows={4}
                    value={String(config.certificate ?? config.certPem ?? "")}
                    onChange={(e) => setConfig((c) => ({ ...c, certificate: e.target.value, certPem: e.target.value }))}
                    placeholder="Client certificate PEM"
                    className="w-full px-3 py-2 border border-gray-300 rounded text-xs font-mono"
                  />
                  <textarea
                    rows={4}
                    value={String(config.privateKey ?? config.keyPem ?? "")}
                    onChange={(e) => setConfig((c) => ({ ...c, privateKey: e.target.value, keyPem: e.target.value }))}
                    placeholder="Private key PEM"
                    className="w-full px-3 py-2 border border-gray-300 rounded text-xs font-mono"
                  />
                  <textarea
                    rows={3}
                    value={String(config.certificateAuthority ?? config.caBundlePem ?? "")}
                    onChange={(e) => setConfig((c) => ({ ...c, certificateAuthority: e.target.value, caBundlePem: e.target.value }))}
                    placeholder="Certificate authority PEM (optional)"
                    className="w-full px-3 py-2 border border-gray-300 rounded text-xs font-mono"
                  />
                </div>
              )}

              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={isActive}
                  onChange={(e) => setIsActive(e.target.checked)}
                  className="rounded border-gray-300 text-slate-600 focus:ring-slate-500"
                />
                <span className="text-sm text-gray-700">Active</span>
              </label>
              <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
                Never log API keys, passwords, bearer tokens, client secrets, or private keys.
              </div>
            </div>

            <div className="space-y-3">
              <JwtTokenPreviewPanel authType={authType} authConfig={config} />
              <MtlsValidatePanel
                authType={authType}
                certificatePem={String(config.certificate ?? config.certPem ?? "")}
                privateKeyPem={String(config.privateKey ?? config.keyPem ?? "")}
                caBundlePem={String(config.certificateAuthority ?? config.caBundlePem ?? "")}
              />
            </div>
          </div>

          {error && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
              {error}
            </div>
          )}
          <div className="flex gap-2 pt-2 justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => setTestModalOpen(true)}
              className="px-4 py-2 text-sm font-medium text-slate-700 border border-slate-300 hover:bg-slate-50 rounded-lg"
            >
              Test connection
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

        <AuthTestConnectionModal
          open={testModalOpen}
          onClose={() => setTestModalOpen(false)}
          authProfileId={initialValues?.id}
          authType={authType}
          authConfig={buildFinalConfig(normalizeAuthType(authType), config)}
        />
      </div>
    </div>
  );
}

function normalizeAuthType(value: string): string {
  const t = (value || "").trim().toUpperCase();
  if (t === "STATIC_BEARER" || t === "BEARER_TOKEN") return "BEARER";
  if (t === "BASIC_AUTH") return "BASIC";
  if (t === "JWT") return "JWT_BEARER_TOKEN";
  return t || "API_KEY_HEADER";
}

function buildFinalConfig(authType: string, config: Record<string, unknown>): Record<string, unknown> {
  if (authType === "API_KEY_HEADER") {
    return {
      headerName: String(config.headerName ?? "Api-Key").trim() || "Api-Key",
      key: String(config.key ?? config.value ?? "").trim(),
      value: String(config.key ?? config.value ?? "").trim(),
    };
  }
  if (authType === "API_KEY_QUERY") {
    return {
      paramName: String(config.paramName ?? "api_key").trim() || "api_key",
      key: String(config.key ?? config.value ?? "").trim(),
      value: String(config.key ?? config.value ?? "").trim(),
    };
  }
  if (authType === "BASIC") {
    return {
      username: String(config.username ?? "").trim(),
      password: String(config.password ?? "").trim(),
    };
  }
  if (authType === "BEARER") {
    return { token: String(config.token ?? "").trim() };
  }
  if (authType === "JWT_BEARER_TOKEN") {
    return {
      tokenUrl: String(config.tokenUrl ?? "").trim(),
      clientId: String(config.clientId ?? "").trim(),
      clientSecret: String(config.clientSecret ?? "").trim(),
      scope: String(config.scope ?? "").trim(),
    };
  }
  if (authType === "MTLS") {
    return {
      certificate: String(config.certificate ?? config.certPem ?? "").trim(),
      privateKey: String(config.privateKey ?? config.keyPem ?? "").trim(),
      certificateAuthority: String(config.certificateAuthority ?? config.caBundlePem ?? "").trim(),
    };
  }
  return {};
}

function validateConfig(authType: string, config: Record<string, unknown>): string | null {
  if (authType === "API_KEY_HEADER") {
    if (!String(config.headerName ?? "").trim()) return "Header name is required.";
    if (!String(config.key ?? "").trim()) return "API key value is required.";
  }
  if (authType === "API_KEY_QUERY") {
    if (!String(config.paramName ?? "").trim()) return "Parameter name is required.";
    if (!String(config.key ?? "").trim()) return "API key value is required.";
  }
  if (authType === "BASIC") {
    if (!String(config.username ?? "").trim()) return "Username is required.";
    if (!String(config.password ?? "").trim()) return "Password is required.";
  }
  if (authType === "BEARER") {
    if (!String(config.token ?? "").trim()) return "Token is required.";
  }
  if (authType === "JWT_BEARER_TOKEN") {
    if (!String(config.tokenUrl ?? "").trim()) return "Token URL is required.";
    if (!String(config.clientId ?? "").trim()) return "Client ID is required.";
    if (!String(config.clientSecret ?? "").trim()) return "Client secret is required.";
  }
  if (authType === "MTLS") {
    if (!String(config.certificate ?? "").trim()) return "Client certificate is required.";
    if (!String(config.privateKey ?? "").trim()) return "Private key is required.";
  }
  return null;
}
