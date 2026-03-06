import { useState, useEffect, useRef } from "react";
import { ModalShell } from "./ModalShell";
import type { Endpoint } from "../../types";
import type { AuthProfile } from "../../api/endpoints";

interface EndpointModalProps {
  open: boolean;
  onClose: () => void;
  initialValues?: Endpoint | null;
  /** When creating, prefill vendor code (e.g. from Vendor Detail page) */
  defaultVendorCode?: string;
  /** Optional: when provided, show auth profile dropdown */
  authProfiles?: AuthProfile[];
  onSave: (payload: {
    vendor_code: string;
    operation_code: string;
    url: string;
    http_method?: string;
    payload_format?: string;
    timeout_ms?: number;
    is_active?: boolean;
    auth_profile_id?: string | null;
  }) => Promise<void>;
}

export function EndpointModal({
  open,
  onClose,
  initialValues,
  defaultVendorCode,
  authProfiles = [],
  onSave,
}: EndpointModalProps) {
  const [vendorCode, setVendorCode] = useState("");
  const [operationCode, setOperationCode] = useState("");
  const [url, setUrl] = useState("");
  const [httpMethod, setHttpMethod] = useState("POST");
  const [payloadFormat, setPayloadFormat] = useState("json");
  const [timeoutMs, setTimeoutMs] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [authProfileId, setAuthProfileId] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isEdit = !!(initialValues?.url);
  const lastSeededKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (open) {
      const key = initialValues?.operationCode ? `${initialValues.vendorCode}:${initialValues.operationCode}` : "__add__";
      if (lastSeededKeyRef.current !== key) {
        lastSeededKeyRef.current = key;
        setVendorCode(initialValues?.vendorCode ?? defaultVendorCode ?? "");
        setOperationCode(initialValues?.operationCode ?? "");
        setUrl(initialValues?.url ?? "");
        setHttpMethod(initialValues?.httpMethod ?? "POST");
        setPayloadFormat(initialValues?.payloadFormat ?? "json");
        setTimeoutMs(initialValues?.timeoutMs != null ? String(initialValues.timeoutMs) : "");
        setIsActive(initialValues?.isActive !== false);
        setAuthProfileId(initialValues?.authProfileId ?? "");
        setError(null);
      }
    } else {
      lastSeededKeyRef.current = null;
    }
  }, [open, initialValues, defaultVendorCode]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const vCode = vendorCode.trim().toUpperCase();
    const opCode = operationCode.trim().toUpperCase();
    const urlTrimmed = url.trim();
    if (!vCode || !opCode || !urlTrimmed) {
      setError("Licensee code, operation code, and URL are required.");
      return;
    }
    setIsLoading(true);
    try {
      await onSave({
        vendor_code: vCode,
        operation_code: opCode,
        url: urlTrimmed,
        http_method: httpMethod.trim() || undefined,
        payload_format: payloadFormat.trim() || undefined,
        timeout_ms: timeoutMs ? parseInt(timeoutMs, 10) : undefined,
        is_active: isActive,
        auth_profile_id: authProfiles.length ? (authProfileId.trim() || null) : null,
      });
      onClose();
    } catch (err) {
      setError((err as Error)?.message ?? "Failed to save endpoint.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <ModalShell open={open} onClose={onClose} title={isEdit ? "Edit Endpoint" : "Create Endpoint"}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Licensee code</label>
          <input
            type="text"
            value={vendorCode}
            onChange={(e) => setVendorCode(e.target.value)}
            placeholder="LH002"
            disabled={isEdit}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500 disabled:bg-gray-100 disabled:text-gray-600"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Operation code</label>
          <input
            type="text"
            value={operationCode}
            onChange={(e) => setOperationCode(e.target.value)}
            placeholder="GET_RECEIPT"
            disabled={isEdit}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500 disabled:bg-gray-100 disabled:text-gray-600"
          />
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
          <input
            type="text"
            value={httpMethod}
            onChange={(e) => setHttpMethod(e.target.value)}
            placeholder="POST"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Payload format</label>
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
        {authProfiles.length > 0 && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Auth profile</label>
            <select
              value={authProfileId}
              onChange={(e) => setAuthProfileId(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
            >
              <option value="">No auth (public API)</option>
              {authProfiles.filter((ap) => ap.isActive !== false).map((ap) => (
                <option key={ap.id ?? ap.name} value={ap.id ?? ""}>
                  {ap.name} ({ap.authType})
                </option>
              ))}
            </select>
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
    </ModalShell>
  );
}
