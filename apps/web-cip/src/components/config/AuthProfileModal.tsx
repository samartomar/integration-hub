import { useState, useEffect, useRef } from "react";

const TIER1_AUTH_TYPES = [
  { value: "API_KEY_HEADER", label: "API key header" },
  { value: "API_KEY_QUERY", label: "API key query" },
  { value: "STATIC_BEARER", label: "Static bearer" },
] as const;

const AUTH_TYPE_HINTS: Record<string, string> = {
  API_KEY_HEADER: "Sends a static value in a header, e.g. Api-Key.",
  API_KEY_QUERY: "Appends a static query param, e.g. ?api_key=...",
  STATIC_BEARER: "Sends a static bearer token in the Authorization header.",
};

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
}

export function AuthProfileModal({
  open,
  onClose,
  vendorCode,
  initialValues,
  onSave,
}: AuthProfileModalProps) {
  const [name, setName] = useState("");
  const [authType, setAuthType] = useState<string>("API_KEY_HEADER");
  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [isActive, setIsActive] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastSeededKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (open) {
      const key = initialValues?.id ?? initialValues?.name ?? "__add__";
      if (lastSeededKeyRef.current !== key) {
        lastSeededKeyRef.current = key;
        setName(initialValues?.name ?? "");
        setAuthType(initialValues?.authType ?? "API_KEY_HEADER");
        setConfig((initialValues?.config as Record<string, unknown>) ?? {});
        setIsActive(initialValues?.isActive ?? true);
        setError(null);
      }
    } else {
      lastSeededKeyRef.current = null;
    }
  }, [open, initialValues]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const nameTrimmed = name.trim();
    if (!nameTrimmed) {
      setError("Name is required");
      return;
    }
    const t = authType.toUpperCase();
    let finalConfig: Record<string, unknown> = {};
    if (t === "API_KEY_HEADER") {
      const headerName = (config.headerName as string)?.trim() || "Api-Key";
      const value = (config.value as string)?.trim();
      if (!value) {
        setError("Value is required for API key header");
        return;
      }
      finalConfig = { headerName, value };
    } else if (t === "API_KEY_QUERY") {
      const paramName = (config.paramName as string)?.trim() || "api_key";
      const value = (config.value as string)?.trim();
      if (!value) {
        setError("Value is required for API key query");
        return;
      }
      finalConfig = { paramName, value };
    } else if (t === "STATIC_BEARER") {
      const token = (config.token as string)?.trim();
      if (!token) {
        setError("Token is required for static bearer");
        return;
      }
      finalConfig = { token };
    }
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
          "Failed to save."
      );
    } finally {
      setIsLoading(false);
    }
  };

  const hint = AUTH_TYPE_HINTS[authType];

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center ${open ? "" : "hidden"}`}
    >
      <div className="absolute inset-0 bg-black/50" aria-hidden />
      <div
        className="relative w-full max-w-md bg-white rounded-lg shadow-xl p-4 sm:p-6 mx-3 sm:mx-4 max-h-[90dvh] overflow-y-auto"
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">
            {initialValues?.id ? "Edit auth profile" : "New auth profile"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 p-1 rounded"
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
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. API key for Acme"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Auth Type
            </label>
            <select
              value={authType}
              onChange={(e) => setAuthType(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
            >
              {TIER1_AUTH_TYPES.map(({ value, label }) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            {hint && <p className="mt-1 text-xs text-gray-500">{hint}</p>}
          </div>

          {authType.toUpperCase() === "API_KEY_HEADER" && (
            <div className="space-y-3 rounded-lg border border-gray-200 p-3 bg-gray-50">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Header name
                </label>
                <input
                  type="text"
                  value={(config.headerName as string) ?? "Api-Key"}
                  onChange={(e) =>
                    setConfig((c) => ({ ...c, headerName: e.target.value }))
                  }
                  placeholder="Api-Key"
                  className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Value
                </label>
                <input
                  type="password"
                  value={(config.value as string) ?? ""}
                  onChange={(e) =>
                    setConfig((c) => ({ ...c, value: e.target.value }))
                  }
                  placeholder="Your API key"
                  className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                />
              </div>
            </div>
          )}

          {authType.toUpperCase() === "API_KEY_QUERY" && (
            <div className="space-y-3 rounded-lg border border-gray-200 p-3 bg-gray-50">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Param name
                </label>
                <input
                  type="text"
                  value={(config.paramName as string) ?? "api_key"}
                  onChange={(e) =>
                    setConfig((c) => ({ ...c, paramName: e.target.value }))
                  }
                  placeholder="api_key"
                  className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Value
                </label>
                <input
                  type="password"
                  value={(config.value as string) ?? ""}
                  onChange={(e) =>
                    setConfig((c) => ({ ...c, value: e.target.value }))
                  }
                  placeholder="Your API key"
                  className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                />
              </div>
            </div>
          )}

          {authType.toUpperCase() === "STATIC_BEARER" && (
            <div className="space-y-3 rounded-lg border border-gray-200 p-3 bg-gray-50">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Token
                </label>
                <input
                  type="password"
                  value={(config.token as string) ?? ""}
                  onChange={(e) =>
                    setConfig((c) => ({ ...c, token: e.target.value }))
                  }
                  placeholder="Bearer token"
                  className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                />
              </div>
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
