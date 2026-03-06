import { useState } from "react";
import {
  validateAuthProfileMtls,
  type MtlsValidateResponse,
} from "../../api/endpoints";

interface MtlsValidatePanelProps {
  authType: string;
  certificatePem: string;
  privateKeyPem: string;
  caBundlePem?: string;
}

export function MtlsValidatePanel({
  authType,
  certificatePem,
  privateKeyPem,
  caBundlePem,
}: MtlsValidatePanelProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MtlsValidateResponse | null>(null);

  if (authType !== "MTLS") return null;

  const validate = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await validateAuthProfileMtls({
        certificatePem,
        privateKeyPem,
        caBundlePem: caBundlePem || null,
      });
      setResult(data);
    } catch (e) {
      setError((e as Error)?.message ?? "Validation failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold text-gray-800 uppercase tracking-wide">
          Validate Certificate
        </h4>
        <button
          type="button"
          onClick={validate}
          disabled={loading}
          className="px-2.5 py-1 text-xs font-medium rounded border border-slate-300 text-slate-700 hover:bg-slate-100 disabled:opacity-50"
        >
          {loading ? "Validating..." : "Validate certificate"}
        </button>
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}

      {result && (
        <div className="space-y-1 text-xs text-gray-700">
          <p>
            Status:{" "}
            <span className={result.ok ? "text-emerald-700 font-semibold" : "text-red-700 font-semibold"}>
              {result.ok ? "Valid" : "Invalid"}
            </span>
          </p>
          <p>Expiry: {result.expiresAt ?? "-"}</p>
          <p>Days remaining: {result.daysRemaining ?? "-"}</p>
          <p>Subject: {result.subject ?? "-"}</p>
          <p>Issuer: {result.issuer ?? "-"}</p>
          <p>SANs: {result.sans?.length ? result.sans.join(", ") : "-"}</p>
          {result.warnings && result.warnings.length > 0 && (
            <div>
              <p className="font-medium text-amber-700">Warnings:</p>
              <ul className="list-disc list-inside">
                {result.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
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
