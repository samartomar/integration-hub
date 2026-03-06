import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Skeleton } from "../Skeleton";

interface ResultsPanelProps {
  lastResponse: Record<string, unknown> | null;
  isLoading: boolean;
  error: string | { code?: string; message?: string; violations?: unknown[] } | null;
}

function getStatusChipClass(status: string): string {
  switch (status) {
    case "completed":
      return "bg-emerald-100 text-emerald-800";
    case "validation_failed":
      return "bg-amber-100 text-amber-800";
    case "downstream_error":
      return "bg-red-100 text-red-800";
    case "received":
      return "bg-slate-100 text-slate-800";
    case "error":
      return "bg-red-100 text-red-800";
    default:
      return "bg-slate-100 text-slate-800";
  }
}

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  };
  return (
    <button
      type="button"
      onClick={handleCopy}
      className="ml-2 px-2 py-0.5 text-xs font-medium text-slate-600 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 rounded"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

export function ResultsPanel({
  lastResponse,
  isLoading,
  error,
}: ResultsPanelProps) {
  const navigate = useNavigate();

  const transactionId =
    lastResponse && typeof lastResponse.transactionId === "string"
      ? lastResponse.transactionId
      : null;
  const correlationId =
    lastResponse && typeof lastResponse.correlationId === "string"
      ? lastResponse.correlationId
      : null;
  const responseBody =
    lastResponse && typeof lastResponse.responseBody === "object" && lastResponse.responseBody != null
      ? (lastResponse.responseBody as Record<string, unknown>)
      : null;
  const statusFromBody =
    responseBody && typeof responseBody.status === "string"
      ? responseBody.status
      : null;

  const canonicalError =
    error && typeof error === "object" && "message" in error
      ? (error as { code?: string; message?: string; violations?: unknown[] })
      : null;

  const displayStatus: string | null =
    statusFromBody ?? canonicalError?.code ?? (error ? "error" : null);

  const handleOpenInAdmin = () => {
    if (transactionId) navigate(`/admin/transactions/${transactionId}`);
  };

  return (
    <div className="rounded-lg bg-white border border-gray-200 p-4 w-full min-w-0 flex flex-col overflow-hidden lg:max-h-[calc(100vh-6rem)]">
      <h3 className="text-sm font-semibold text-gray-800 mb-4 shrink-0">Results</h3>
      <div className="flex-1 min-h-0 overflow-y-auto">

      {isLoading && (
        <div className="space-y-3">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-32 w-full" />
        </div>
      )}

      {!isLoading && !lastResponse && !error && (
        <p className="text-sm text-gray-500">Run an execution to see results.</p>
      )}

      {!isLoading && (lastResponse || error) && (
        <div className="space-y-4">
          {displayStatus && (
            <div>
              <span className="text-xs font-medium text-gray-500">Status</span>
              <span
                className={`ml-2 inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${getStatusChipClass(displayStatus)}`}
              >
                {displayStatus}
              </span>
            </div>
          )}

          {transactionId && (
            <div>
              <span className="text-xs font-medium text-gray-500 block mb-1">
                Transaction ID
              </span>
              <div className="flex items-center">
                <code className="text-sm font-mono text-gray-800 truncate">
                  {transactionId}
                </code>
                <CopyButton value={transactionId} />
              </div>
            </div>
          )}

          {correlationId && (
            <div>
              <span className="text-xs font-medium text-gray-500 block mb-1">
                Correlation ID
              </span>
              <div className="flex items-center">
                <code className="text-sm font-mono text-gray-800 truncate">
                  {correlationId}
                </code>
                <CopyButton value={correlationId} />
              </div>
            </div>
          )}

          {canonicalError && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3">
              {canonicalError.code && (
                <p className="text-xs font-medium text-red-700">
                  Code: {canonicalError.code}
                </p>
              )}
              {canonicalError.message && (
                <p className="text-sm text-red-800 mt-1">
                  {canonicalError.message}
                </p>
              )}
              {canonicalError.violations &&
                Array.isArray(canonicalError.violations) &&
                canonicalError.violations.length > 0 && (
                  <pre className="text-xs text-red-700 mt-2 overflow-x-auto">
                    {JSON.stringify(canonicalError.violations, null, 2)}
                  </pre>
                )}
            </div>
          )}

          {!canonicalError && error && typeof error === "string" && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
              {error}
            </div>
          )}

          {lastResponse && (
            <div>
              <span className="text-xs font-medium text-gray-500 block mb-1">
                Full response
              </span>
              <pre className="text-xs text-gray-700 overflow-x-auto bg-gray-50 rounded-lg p-3 border border-gray-200 max-h-64 overflow-y-auto">
                {JSON.stringify(lastResponse, null, 2)}
              </pre>
            </div>
          )}

          {transactionId && (
            <button
              type="button"
              onClick={handleOpenInAdmin}
              className="w-full px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 rounded-lg"
            >
              Open in Admin
            </button>
          )}
        </div>
      )}
      </div>
    </div>
  );
}
