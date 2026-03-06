/**
 * TransactionDetailsDrawer – slide-in drawer for transaction details.
 * Matches vendor portal UX spec: Summary, Audit timeline, Request & response,
 * Contracts & mappings, Redrive.
 *
 * TODO: replace with masked payload once masking utility is implemented.
 * TODO: ensure redrive continues to use real payload even after masking is introduced.
 */

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { postVendorRedrive } from "../api/endpoints";
import { vendorTransactionDetailKey } from "../api/queryKeys";
import { StatusPill, type StatusPillVariant } from "frontend-shared";

export interface AuditEvent {
  id: string;
  timestamp: string;
  stage: string;
  message: string;
  snippet?: Record<string, unknown>;
}

export interface TransactionDetails {
  id: string;
  correlationId?: string;
  createdAt: string;
  sourceVendor: string;
  targetVendor: string;
  operationCode: string;
  operationVersion: string;
  status: string;
  errorCode?: string;
  httpStatus?: number;
  redriveCount: number;

  canonicalRequestBody?: Record<string, unknown>;
  targetRequestBody?: Record<string, unknown>;
  targetResponseBody?: Record<string, unknown>;
  canonicalResponseBody?: Record<string, unknown>;

  auditEvents: AuditEvent[];

  contractInfo?: {
    canonicalRequestSchema?: string;
    canonicalResponseSchema?: string;
    vendorRequestSchema?: string;
    vendorResponseSchema?: string;
    requestMapping?: string;
    responseMapping?: string;
  };

  /** Internal: required for redrive API call */
  _transactionId?: string;
  _canRedrive?: boolean;
}

function formatDate(s: string | undefined): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return s;
  }
}

function statusToPill(status: string | undefined): { label: string; variant: StatusPillVariant } {
  const s = (status ?? "").toLowerCase();
  if (s === "completed") return { label: "Success", variant: "configured" };
  if (s === "validation_failed") return { label: "Validation error", variant: "error" };
  if (["downstream_error", "downstream_timeout", "mapping_failed"].includes(s)) return { label: "Integration error", variant: "error" };
  if (["received", "in_progress", "pending"].includes(s)) return { label: "Pending", variant: "warning" };
  if (s === "replayed") return { label: "Replayed", variant: "info" };
  return { label: status ?? "Unknown", variant: "neutral" };
}

function CopyButton({ value }: { value: string }) {
  return (
    <button
      type="button"
      onClick={() => navigator.clipboard.writeText(value)}
      className="p-1 text-gray-500 hover:text-gray-700 rounded"
      title="Copy to clipboard"
      aria-label="Copy"
    >
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
      </svg>
    </button>
  );
}

/** Collapsible payload panel. Only render if data exists. TODO: replace with masked payload once masking utility is implemented. */
function CollapsiblePayloadPanel({
  title,
  data,
  defaultOpen = false,
}: {
  title: string;
  data?: Record<string, unknown> | null;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  // TODO: const payloadToDisplay = maskPayload(data);
  const payload = data;
  const hasData = payload != null && typeof payload === "object" && Object.keys(payload).length > 0;

  if (!hasData) return null;

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 text-sm font-semibold text-gray-700 bg-gray-50 hover:bg-gray-100"
      >
        {title}
        <span className="text-gray-500">{open ? "▼" : "▶"}</span>
      </button>
      {open && (
        <div className="p-3 bg-white border-t border-gray-200">
          <pre className="text-xs text-gray-700 bg-gray-50 rounded p-3 overflow-x-auto border border-gray-100 max-h-64 overflow-y-auto font-mono">
            {JSON.stringify(payload, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

function AuditTimelineItem({
  stage,
  timestamp,
  message,
  snippet,
}: {
  stage: string;
  timestamp: string;
  message: string;
  snippet?: Record<string, unknown>;
}) {
  const [showSnippet, setShowSnippet] = useState(false);
  return (
    <div className="relative pl-5 pb-3 last:pb-0 border-l-2 border-slate-200 ml-2">
      <span className="absolute left-0 top-0.5 -translate-x-1/2 w-2 h-2 rounded-full bg-slate-400" />
      <div className="text-xs">
        <div className="flex flex-wrap items-baseline gap-1.5">
          <span className="font-medium text-gray-800">{stage}</span>
          <span className="text-gray-400">·</span>
          <span className="text-gray-500">{formatDate(timestamp)}</span>
        </div>
        {message && <p className="text-gray-600 mt-0.5">{message}</p>}
        {snippet && Object.keys(snippet).length > 0 && (
          <div className="mt-1">
            <button
              type="button"
              onClick={() => setShowSnippet(!showSnippet)}
              className="text-slate-600 hover:text-slate-800 text-xs font-medium"
            >
              {showSnippet ? "Hide snippet" : "View snippet"}
            </button>
            {showSnippet && (
              <pre className="text-xs text-gray-500 mt-1 overflow-x-auto rounded bg-gray-50 p-2 border border-gray-100">
                {JSON.stringify(snippet, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/** Map VendorTransactionDetail (API) to TransactionDetails (drawer). */
export function vendorDetailToTransactionDetails(
  d: import("../api/endpoints").VendorTransactionDetail | null
): TransactionDetails | null {
  if (!d) return null;
  const id = d.transactionId ?? "";
  const op = d.operation ?? "";
  const parts = op.split(/\s+/);
  const operationCode = parts[0] ?? op;
  const operationVersion = parts[1] ?? "";
  const events: AuditEvent[] = (d.auditEvents ?? []).map((e, idx) => {
    const details = e.details as Record<string, unknown> | undefined;
    const msg =
      (details?.message != null && String(details.message)) ||
      (details?.error != null && String(details.error)) ||
      (details?.reason != null && String(details.reason)) ||
      "";
    return {
      id: e.id ?? `evt-${idx}`,
      timestamp: e.createdAt ?? "",
      stage: e.action,
      message: typeof msg === "string" ? msg : "",
      snippet: details && Object.keys(details).length > 0 ? details : undefined,
    };
  });
  const hasRequestBody =
    (d.requestBody && Object.keys(d.requestBody).length > 0) ||
    (d.canonicalRequestBody && Object.keys(d.canonicalRequestBody ?? {}).length > 0);
  const s = (d.status ?? "").toLowerCase();
  const eligible = ["downstream_error", "validation_failed", "downstream_timeout", "mapping_failed"].includes(s);
  const canRedrive =
    d.canRedrive ?? (eligible && (d.redriveCount ?? 0) < 5 && !!hasRequestBody);
  return {
    id,
    _transactionId: id,
    _canRedrive: canRedrive,
    correlationId: d.correlationId,
    createdAt: d.createdAt ?? "",
    sourceVendor: d.sourceVendor ?? "",
    targetVendor: d.targetVendor ?? "",
    operationCode,
    operationVersion,
    status: d.status ?? "",
    errorCode: d.errorCode,
    httpStatus: d.httpStatus,
    redriveCount: d.redriveCount ?? 0,
    canonicalRequestBody: d.canonicalRequestBody ?? d.requestBody,
    targetRequestBody: d.targetRequestBody,
    targetResponseBody: d.targetResponseBody,
    canonicalResponseBody: d.canonicalResponseBody ?? d.responseBody,
    auditEvents: events,
    contractInfo: d.contractInfo,
  };
}

export interface TransactionDetailsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  transaction: TransactionDetails | null;
  /** Called after successful redrive with new transaction ID */
  onRedriveSuccess?: (newTransactionId: string) => void;
}

export function TransactionDetailsDrawer({
  isOpen,
  onClose,
  transaction,
  onRedriveSuccess,
}: TransactionDetailsDrawerProps) {
  const [redriveModalOpen, setRedriveModalOpen] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const txId = transaction?._transactionId ?? transaction?.id;
  const canRedrive = transaction?._canRedrive ?? false;

  const redriveMutation = useMutation({
    mutationFn: (id: string) => postVendorRedrive(id),
    onSuccess: (data, id) => {
      setRedriveModalOpen(false);
      queryClient.invalidateQueries({ queryKey: vendorTransactionDetailKey(id) });
      queryClient.invalidateQueries({ queryKey: ["vendor-transactions"] });
      if (data.transactionId) {
        queryClient.invalidateQueries({ queryKey: vendorTransactionDetailKey(data.transactionId) });
        onRedriveSuccess?.(data.transactionId);
      }
      setToastMessage("Redrive started");
      setTimeout(() => setToastMessage(null), 3000);
    },
  });

  const handleRedriveConfirm = () => {
    if (txId) {
      // TODO: ensure redrive continues to use real payload even after masking is introduced.
      redriveMutation.mutate(txId);
    }
  };

  if (!isOpen) return null;

  const statusPill = transaction ? statusToPill(transaction.status) : { label: "—", variant: "neutral" as StatusPillVariant };
  const operationLabel = transaction?.operationVersion
    ? `${transaction.operationCode} · ${transaction.operationVersion}`
    : transaction?.operationCode ?? "—";

  const hasAnyPayload =
    Object.keys(transaction?.canonicalRequestBody ?? {}).length > 0 ||
    Object.keys(transaction?.targetRequestBody ?? {}).length > 0 ||
    Object.keys(transaction?.targetResponseBody ?? {}).length > 0 ||
    Object.keys(transaction?.canonicalResponseBody ?? {}).length > 0;

  const sortedEvents = [...(transaction?.auditEvents ?? [])].sort((a, b) => {
    const ta = new Date(a.timestamp).getTime();
    const tb = new Date(b.timestamp).getTime();
    return ta - tb;
  });

  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-40" aria-hidden />
      <div
        className="fixed right-0 top-0 bottom-0 w-full max-w-[560px] bg-white shadow-xl z-50 flex flex-col overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-labelledby="tx-drawer-title"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50 shrink-0">
          <div className="min-w-0">
            <h2 id="tx-drawer-title" className="font-semibold text-gray-900">
              Transaction details
            </h2>
            {transaction && (
              <div className="flex items-center gap-2 mt-0.5 text-xs text-gray-500 flex-wrap">
                <StatusPill label={statusPill.label} variant={statusPill.variant} />
                <span aria-hidden>•</span>
                <span>Created {formatDate(transaction.createdAt)}</span>
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-200"
            aria-label="Close drawer"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {!transaction ? (
            <p className="text-gray-500 text-sm">Loading…</p>
          ) : (
            <>
              {toastMessage && (
                <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2 text-sm text-emerald-800">
                  {toastMessage}
                </div>
              )}

              {/* Summary card */}
              <div className="rounded-lg border border-gray-200 bg-white shadow-sm p-4">
                <h3 className="text-sm font-semibold text-gray-700 mb-3">Summary</h3>
                <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-sm">
                  <div>
                    <dt className="text-gray-500">Transaction ID</dt>
                    <dd className="font-mono text-gray-900 break-all flex items-center gap-1">
                      {transaction.id}
                      <CopyButton value={transaction.id} />
                    </dd>
                  </div>
                  <div>
                    <dt className="text-gray-500">Correlation ID</dt>
                    <dd className="font-mono text-gray-900 break-all flex items-center gap-1">
                      {transaction.correlationId ?? "—"}
                      {transaction.correlationId && <CopyButton value={transaction.correlationId} />}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-gray-500">Status</dt>
                    <dd>
                      <StatusPill label={statusPill.label} variant={statusPill.variant} />
                    </dd>
                  </div>
                  <div>
                    <dt className="text-gray-500">Error code</dt>
                    <dd className="font-mono">{transaction.errorCode ?? "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-gray-500">HTTP status</dt>
                    <dd className="font-mono">{transaction.httpStatus ?? "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-gray-500">Redrive count</dt>
                    <dd>{transaction.redriveCount}</dd>
                  </div>
                  <div className="sm:col-span-2 pt-2 border-t border-gray-100 mt-1">
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                      <div>
                        <dt className="text-gray-500">Source</dt>
                        <dd className="font-mono">{transaction.sourceVendor}</dd>
                      </div>
                      <div>
                        <dt className="text-gray-500">Target</dt>
                        <dd className="font-mono">{transaction.targetVendor}</dd>
                      </div>
                      <div>
                        <dt className="text-gray-500">Operation</dt>
                        <dd className="font-mono">{operationLabel}</dd>
                      </div>
                    </div>
                  </div>
                </dl>
              </div>

              {/* Audit timeline */}
              {sortedEvents.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">Audit timeline</h3>
                  <div className="space-y-2">
                    {sortedEvents.map((e) => (
                      <AuditTimelineItem
                        key={e.id}
                        stage={e.stage}
                        timestamp={e.timestamp}
                        message={e.message}
                        snippet={e.snippet}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Request & response – only render panels with data */}
              {hasAnyPayload && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">Request & response</h3>
                  <div className="space-y-2">
                    <CollapsiblePayloadPanel title="Canonical request" data={transaction.canonicalRequestBody} defaultOpen />
                    <CollapsiblePayloadPanel title="Target request" data={transaction.targetRequestBody} />
                    <CollapsiblePayloadPanel title="Target response" data={transaction.targetResponseBody} />
                    <CollapsiblePayloadPanel title="Canonical response" data={transaction.canonicalResponseBody} />
                  </div>
                </div>
              )}

              {/* Contracts & mappings */}
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Contracts & mappings</h3>
                {!transaction.contractInfo ? (
                  <p className="text-xs text-slate-500">
                    Contract and mapping information will appear here for this transaction.
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-xs border border-gray-200 rounded-lg overflow-hidden">
                      <thead>
                        <tr className="bg-gray-50">
                          <th className="px-3 py-2 text-left font-semibold text-gray-700 border-b border-r border-gray-200">Canonical</th>
                          <th className="px-3 py-2 text-left font-semibold text-gray-700 border-b border-gray-200">Vendor</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr className="border-b border-gray-100">
                          <td className="px-3 py-2 font-mono text-gray-700" title="Request schema">{transaction.contractInfo.canonicalRequestSchema ?? "—"}</td>
                          <td className="px-3 py-2 font-mono text-gray-700">{transaction.contractInfo.vendorRequestSchema ?? "—"}</td>
                        </tr>
                        <tr className="border-b border-gray-100">
                          <td className="px-3 py-2 font-mono text-gray-700" title="Response schema">{transaction.contractInfo.canonicalResponseSchema ?? "—"}</td>
                          <td className="px-3 py-2 font-mono text-gray-700">{transaction.contractInfo.vendorResponseSchema ?? "—"}</td>
                        </tr>
                        <tr className="border-b border-gray-100">
                          <td className="px-3 py-2 font-mono text-gray-700" title="Request mapping">{transaction.contractInfo.requestMapping ?? "—"}</td>
                          <td className="px-3 py-2 font-mono text-gray-700">—</td>
                        </tr>
                        <tr>
                          <td className="px-3 py-2 font-mono text-gray-700" title="Response mapping">{transaction.contractInfo.responseMapping ?? "—"}</td>
                          <td className="px-3 py-2 font-mono text-gray-700">—</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Redrive area */}
              {canRedrive && (
                <div className="pt-4 mt-4 border-t border-gray-200">
                  <p className="text-xs text-gray-600 mb-3">
                    Redrive transaction – retry this transaction using the original request payload.
                  </p>
                  <button
                    type="button"
                    onClick={() => setRedriveModalOpen(true)}
                    disabled={redriveMutation.isPending}
                    className="w-full inline-flex items-center justify-center gap-1.5 px-4 py-2.5 text-sm font-medium rounded-lg bg-slate-700 text-white hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {redriveMutation.isPending ? (
                      <>
                        <span className="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        Redriving…
                      </>
                    ) : (
                      <>
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                        Redrive transaction
                      </>
                    )}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Redrive confirmation modal */}
      {redriveModalOpen && transaction && txId && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/40">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-5" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-gray-900 mb-3">Redrive this transaction?</h3>
            <p className="text-sm text-gray-600 mb-4">
              The platform will re-send the original request payload to the downstream API.
            </p>
            <dl className="text-sm space-y-1 mb-4 bg-gray-50 rounded-lg p-3">
              <div>
                <dt className="text-gray-500 inline">Operation: </dt>
                <dd className="inline font-mono">{operationLabel}</dd>
              </div>
              <div>
                <dt className="text-gray-500 inline">Source → Target: </dt>
                <dd className="inline font-mono">{transaction.sourceVendor} → {transaction.targetVendor}</dd>
              </div>
              <div>
                <dt className="text-gray-500 inline">Existing redrives: </dt>
                <dd className="inline">{transaction.redriveCount}</dd>
              </div>
            </dl>
            {redriveMutation.isError && (
              <p className="text-sm text-red-600 mb-3">
                {((redriveMutation.error as { response?: { data?: { error?: { message?: string } } }; message?: string })?.response?.data?.error?.message)
                  ?? (redriveMutation.error as Error)?.message ?? "Redrive failed"}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setRedriveModalOpen(false)}
                disabled={redriveMutation.isPending}
                className="px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleRedriveConfirm}
                disabled={redriveMutation.isPending}
                className="px-3 py-2 text-sm font-medium text-white bg-slate-700 rounded-lg hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {redriveMutation.isPending ? "Redriving…" : "Redrive transaction"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
