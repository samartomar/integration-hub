import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getTransaction, redrive } from "../api/endpoints";
import type { Transaction, AuditEvent, AuthSummary, ContractMappingSummary } from "../types";
import { Skeleton } from "./Skeleton";

type DrawerTab = "summary" | "debug";

interface TransactionDetailDrawerProps {
  transactionId: string | null;
  vendorCode?: string;
  expandSensitive?: boolean;
  sensitiveReason?: string;
  onClose: () => void;
}

export function TransactionDetailDrawer({
  transactionId,
  vendorCode,
  expandSensitive,
  sensitiveReason,
  onClose,
}: TransactionDetailDrawerProps) {
  const queryClient = useQueryClient();
  const isOpen = !!transactionId;

  const { data: detailData, isLoading: txLoading } = useQuery({
    queryKey: ["transaction", transactionId, vendorCode, !!expandSensitive, sensitiveReason ?? ""],
    queryFn: () =>
      getTransaction(transactionId!, {
        vendorCode,
        expandSensitive: !!expandSensitive,
        reason: sensitiveReason,
      }),
    enabled: !!transactionId,
  });

  const transaction =
    detailData && "transaction" in detailData
      ? detailData.transaction
      : (detailData as Transaction | undefined);
  const events = detailData && "auditEvents" in detailData ? detailData.auditEvents : undefined;
  const authSummary = detailData && "authSummary" in detailData ? detailData.authSummary : undefined;
  const contractMappingSummary =
    detailData && "contractMappingSummary" in detailData ? detailData.contractMappingSummary : undefined;

  const redriveMutation = useMutation({
    mutationFn: (id: string) => redrive(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-transactions"] });
      queryClient.invalidateQueries({ queryKey: ["transaction"] });
    },
  });

  const [activeTab, setActiveTab] = useState<DrawerTab>("summary");
  const handleRedrive = () => {
    if (!transactionId) return;
    redriveMutation.mutate(transactionId);
  };

  if (!isOpen) return null;

  const hasAuditTimeline = Array.isArray(events) && events.length > 0;
  const newTxId = redriveMutation.data?.transactionId;

  return (
    <>
      <div
        className="fixed inset-0 bg-black/30 z-40"
        aria-hidden
      />
      <div
        className="fixed right-0 top-0 bottom-0 w-full max-w-2xl bg-white shadow-xl z-50 flex flex-col overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50 shrink-0">
          <h2 id="drawer-title" className="font-semibold text-gray-900">
            Transaction details
          </h2>
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

        {/* Tab list */}
        {transaction && (
          <div className="flex gap-1 px-4 pt-2 border-b border-gray-200 shrink-0">
            <button
              type="button"
              onClick={() => setActiveTab("summary")}
              className={`px-3 py-2 text-sm font-medium rounded-t-lg -mb-px ${
                activeTab === "summary"
                  ? "bg-white border border-b-0 border-gray-200 text-slate-800"
                  : "text-slate-600 hover:text-slate-800 hover:bg-slate-100"
              }`}
            >
              Summary
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("debug")}
              className={`px-3 py-2 text-sm font-medium rounded-t-lg -mb-px ${
                activeTab === "debug"
                  ? "bg-white border border-b-0 border-gray-200 text-slate-800"
                  : "text-slate-600 hover:text-slate-800 hover:bg-slate-100"
              }`}
            >
              Debug
            </button>
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {txLoading ? (
            <DrawerSkeleton />
          ) : transaction ? (
            activeTab === "summary" ? (
              <>
                <TransactionMetaSection
                  transaction={transaction}
                  authDebug={deriveAuthDebug(events)}
                />
                <JsonSection title="Request body" data={transaction.request_body} />
                <JsonSection title="Response body" data={transaction.response_body} />
                {hasAuditTimeline && (
                  <AuditTimelineSection events={events!} />
                )}
                <RedriveSection
                  transactionId={transactionId!}
                  onRedrive={handleRedrive}
                  isLoading={redriveMutation.isPending}
                  error={redriveMutation.error}
                  newTransactionId={newTxId}
                />
              </>
            ) : (
              <DebugTabContent
                transaction={transaction}
                authSummary={authSummary}
                contractMappingSummary={contractMappingSummary}
                events={events}
              />
            )
          ) : (
            <p className="text-gray-500 text-sm">Transaction not found.</p>
          )}
        </div>
      </div>
    </>
  );
}

function DrawerSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <Skeleton className="h-4 w-48" />
      <div className="space-y-2">
        {[...Array(6)].map((_, i) => (
          <Skeleton key={i} className="h-4 w-full" />
        ))}
      </div>
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-32 w-full" />
    </div>
  );
}

function deriveAuthDebug(events: AuditEvent[] | undefined): string | null {
  if (!Array.isArray(events)) return null;
  const ev = events.find((e) => e.action === "DOWNSTREAM_HEADERS_BUILT");
  if (!ev?.details) return null;
  const d = ev.details as Record<string, unknown>;
  const authType = (d.authType as string) || "—";
  const vendorCode = (d.vendorCode as string) || "";
  const authProfileName = (d.authProfileName as string) || "";
  if ((d.authType as string)?.toUpperCase() === "NONE" || !authType) {
    return vendorCode ? `${vendorCode} (no auth)` : null;
  }
  if (vendorCode && authProfileName) {
    return `${vendorCode} / ${authProfileName}, authType=${authType}`;
  }
  if (vendorCode) {
    return `${vendorCode}, authType=${authType}`;
  }
  return `authType=${authType}`;
}

function TransactionMetaSection({
  transaction,
  authDebug,
}: {
  transaction: Transaction;
  authDebug?: string | null;
}) {
  const rows = [
    { label: "Transaction ID", value: transaction.transaction_id },
    { label: "Correlation ID", value: transaction.correlation_id ?? "—" },
    { label: "Status", value: transaction.status ?? "—" },
    { label: "Source", value: transaction.source_vendor ?? "—" },
    { label: "Target", value: transaction.target_vendor ?? "—" },
    { label: "Operation", value: transaction.operation ?? "—" },
    { label: "Redrive count", value: String(transaction.redrive_count ?? 0) },
    { label: "Created", value: transaction.created_at ?? "—" },
    ...(authDebug ? [{ label: "Auth debug", value: authDebug }] : []),
  ];

  const hasStatusDebug =
    transaction.errorCode != null ||
    transaction.httpStatus != null ||
    transaction.failureStage != null;

  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 mb-2">Details</h3>
      <dl className="space-y-1.5">
        {rows.map(({ label, value }) => (
          <div key={label} className="flex gap-2 text-sm">
            <dt className="text-gray-500 w-28 shrink-0">{label}</dt>
            <dd className="text-gray-900 font-mono break-all">{value}</dd>
          </div>
        ))}
      </dl>
      {hasStatusDebug && (
        <div className="mt-3 pt-3 border-t border-gray-200">
          <h3 className="text-sm font-semibold text-slate-700 mb-2">Status</h3>
          <dl className="space-y-1.5">
            {transaction.errorCode != null && (
              <div className="flex gap-2 text-sm">
                <dt className="text-gray-500 w-28 shrink-0">Error code</dt>
                <dd className="text-gray-900 font-mono">{transaction.errorCode}</dd>
              </div>
            )}
            {transaction.httpStatus != null && (
              <div className="flex gap-2 text-sm">
                <dt className="text-gray-500 w-28 shrink-0">HTTP status</dt>
                <dd className="text-gray-900 font-mono">{transaction.httpStatus}</dd>
              </div>
            )}
            {transaction.failureStage != null && (
              <div className="flex gap-2 text-sm">
                <dt className="text-gray-500 w-28 shrink-0">Failure stage</dt>
                <dd className="text-gray-900 font-mono">{transaction.failureStage}</dd>
              </div>
            )}
          </dl>
        </div>
      )}
    </div>
  );
}

function AuthSummaryCard({ auth }: { auth?: AuthSummary }) {
  if (!auth) return null;

  const modeLabel: Record<AuthSummary["mode"], string> = {
    JWT: "JWT (IDP-issued token)",
    API_KEY: "API key",
    ADMIN_SECRET: "Admin JWT",
    UNKNOWN: "Unknown",
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm space-y-1">
      <div className="flex items-center justify-between">
        <span className="font-semibold text-slate-800">Auth</span>
        <span className="inline-flex items-center rounded-full bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-700">
          {modeLabel[auth.mode]}
        </span>
      </div>
      <div className="text-xs text-slate-600">
        <div>
          <span className="font-semibold">Source vendor:</span>{" "}
          {auth.sourceVendor || "—"}
        </div>
        {auth.authProfile && (
          <div>
            <span className="font-semibold">Outbound profile:</span>{" "}
            {auth.authProfile.name || auth.authProfile.id || "—"}{" "}
            {auth.authProfile.authType && (
              <span className="ml-1 text-[10px] uppercase tracking-wide text-slate-500">
                ({auth.authProfile.authType})
              </span>
            )}
          </div>
        )}
        {auth.mode === "JWT" && (
          <div className="mt-1 space-y-0.5">
            <div>
              <span className="font-semibold">Issuer:</span>{" "}
              {auth.idpIssuer || "—"}
            </div>
            <div>
              <span className="font-semibold">Audience:</span>{" "}
              {auth.idpAudience || "—"}
            </div>
            <div>
              <span className="font-semibold">Vendor claim:</span>{" "}
              {auth.jwtVendorClaim || "vendor_code"}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ContractsMappingsCard({
  summary,
}: {
  summary?: ContractMappingSummary;
}) {
  if (!summary) return null;

  const { canonical, sourceVendor, targetVendor } = summary;

  const pill = (label: string, active: boolean) => (
    <span
      className={
        "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium mr-1 mb-1 " +
        (active
          ? "bg-emerald-100 text-emerald-700"
          : "bg-slate-100 text-slate-400 line-through")
      }
    >
      {label}
    </span>
  );

  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm space-y-2">
      <div className="flex items-center justify-between">
        <span className="font-semibold text-slate-800">
          Contracts & mappings
        </span>
        <span className="text-xs text-slate-500">
          {summary.operationCode || "—"}
          {summary.canonicalVersion && ` · v${summary.canonicalVersion}`}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
        <div>
          <div className="text-xs font-semibold text-slate-700 mb-1">
            Canonical
          </div>
          <div className="text-[11px] text-slate-500 mb-1">
            Canonical contract
          </div>
          <div>
            {pill("Request schema", canonical.hasRequestSchema)}
            {pill("Response schema", canonical.hasResponseSchema)}
          </div>
        </div>

        <div>
          <div className="text-xs font-semibold text-slate-700 mb-1">
            Source ({sourceVendor.vendorCode || "—"})
          </div>
          <div className="text-[11px] text-slate-500 mb-1">
            Caller-side view
          </div>
          <div>
            {pill("Vendor contract", sourceVendor.hasVendorContract)}
            {pill("Req schema", sourceVendor.hasRequestSchema)}
            {pill("Res schema", sourceVendor.hasResponseSchema)}
            {pill(
              "From canonical (request)",
              sourceVendor.hasFromCanonicalRequestMapping
            )}
            {pill(
              "To canonical (response)",
              sourceVendor.hasToCanonicalResponseMapping
            )}
          </div>
        </div>

        <div>
          <div className="text-xs font-semibold text-slate-700 mb-1">
            Target ({targetVendor.vendorCode || "—"})
          </div>
          <div className="text-[11px] text-slate-500 mb-1">
            Downstream API / bot
          </div>
          <div>
            {pill("Vendor contract", targetVendor.hasVendorContract)}
            {pill("Req schema", targetVendor.hasRequestSchema)}
            {pill("Res schema", targetVendor.hasResponseSchema)}
            {pill(
              "From canonical (request)",
              targetVendor.hasFromCanonicalRequestMapping
            )}
            {pill(
              "To canonical (response)",
              targetVendor.hasToCanonicalResponseMapping
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function DebugTabContent({
  transaction,
  authSummary,
  contractMappingSummary,
  events,
}: {
  transaction: Transaction;
  authSummary?: AuthSummary;
  contractMappingSummary?: ContractMappingSummary;
  events?: AuditEvent[];
}) {
  const panels: { title: string; data?: Record<string, unknown> | null }[] = [
    { title: "Canonical request", data: transaction.canonicalRequestBody ?? transaction.canonical_request_body },
    { title: "Target request", data: transaction.targetRequestBody ?? transaction.target_request_body },
    { title: "Target response", data: transaction.targetResponseBody ?? transaction.target_response_body },
    { title: "Canonical response", data: transaction.canonicalResponseBody ?? transaction.canonical_response_body },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <AuthSummaryCard auth={authSummary} />
        <ContractsMappingsCard summary={contractMappingSummary} />
      </div>
      {Array.isArray(events) && events.length > 0 && (
        <AuditTimelineSection events={events} />
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {panels.map(({ title, data }) => (
          <div
            key={title}
            className="rounded-lg border border-gray-200 p-3 bg-white"
          >
            <h3 className="text-sm font-semibold text-slate-700 mb-2">{title}</h3>
            {data != null && typeof data === "object" && Object.keys(data).length > 0 ? (
              <pre className="text-xs text-gray-700 bg-gray-50 rounded p-2 overflow-x-auto border border-gray-100 min-h-[4rem]">
                {JSON.stringify(data, null, 2)}
              </pre>
            ) : (
              <p className="text-gray-400 text-sm py-2">No data recorded</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function JsonSection({
  title,
  data,
}: {
  title: string;
  data?: Record<string, unknown> | null;
}) {
  if (data == null || Object.keys(data).length === 0) {
    return (
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">{title}</h3>
        <p className="text-gray-400 text-sm">Not available</p>
      </div>
    );
  }

  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 mb-2">{title}</h3>
      <pre className="text-xs text-gray-700 bg-gray-50 rounded-lg p-3 overflow-x-auto border border-gray-200">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}

function AuditTimelineSection({ events }: { events: AuditEvent[] }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 mb-2">Audit timeline</h3>
      <div className="space-y-3">
        {events.map((e, i) => (
          <div
            key={i}
            className="flex gap-3 text-sm pl-3 border-l-2 border-slate-200"
          >
            <div className="shrink-0">
              <span className="font-medium text-gray-800">{e.action}</span>
              <span className="text-gray-500 ml-2">{e.vendorCode}</span>
            </div>
            {e.createdAt && (
              <span className="text-gray-400 text-xs">{e.createdAt}</span>
            )}
            {e.details && Object.keys(e.details).length > 0 && (
              <pre className="text-xs text-gray-500 mt-1 overflow-x-auto">
                {JSON.stringify(e.details)}
              </pre>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function RedriveSection({
  transactionId,
  onRedrive,
  isLoading,
  error,
  newTransactionId,
}: {
  transactionId: string;
  onRedrive: () => void;
  isLoading: boolean;
  error: Error | null;
  newTransactionId?: string;
}) {
  return (
    <div className="pt-4 border-t border-gray-200">
      <h3 className="text-sm font-semibold text-gray-700 mb-2">Redrive</h3>
      <p className="text-gray-500 text-sm mb-3">
        Retry this failed transaction via POST /v1/admin/redrive/{transactionId}
      </p>
      {error && (
        <div className="mb-3 rounded-lg bg-red-50 border border-red-200 p-2 text-sm text-red-700">
          {(error as Error).message}
        </div>
      )}
      {newTransactionId && (
        <div className="mb-3 rounded-lg bg-emerald-50 border border-emerald-200 p-3">
          <p className="text-sm font-medium text-emerald-800">Redrive successful</p>
          <Link
            to={`/admin/transactions/${newTransactionId}`}
            className="text-sm text-emerald-600 hover:text-emerald-800 underline font-mono mt-1 block"
          >
            New transaction: {newTransactionId}
          </Link>
        </div>
      )}
      <button
        type="button"
        onClick={onRedrive}
        disabled={isLoading}
        className="px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg"
      >
        {isLoading ? "Redriving…" : "Redrive"}
      </button>
    </div>
  );
}
