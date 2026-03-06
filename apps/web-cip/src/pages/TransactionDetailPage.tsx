import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getTransaction } from "../api/endpoints";
import type { Transaction, TransactionDetailResponse } from "../types";
import { usePhiAccess } from "../security/PhiAccessContext";

export function TransactionDetailPage() {
  const { phiModeEnabled, reason } = usePhiAccess();
  const { transactionId } = useParams<{ transactionId: string }>();
  const navigate = useNavigate();
  const { data, isLoading, error } = useQuery({
    queryKey: ["transaction", transactionId, !!phiModeEnabled, reason ?? ""],
    queryFn: () =>
      getTransaction(transactionId!, {
        expandSensitive: phiModeEnabled,
        reason,
      }),
    enabled: !!transactionId,
  });

  if (!transactionId) {
    return (
      <div className="p-6">
        <p className="text-gray-500">Transaction ID is required.</p>
        <button
          onClick={() => navigate("/admin/transactions")}
          className="mt-4 text-slate-600 hover:text-slate-800 underline"
        >
          Back to Transactions
        </button>
      </div>
    );
  }

  if (isLoading) {
    return <TransactionDetailSkeleton />;
  }

  if (error || !data) {
    return (
      <div className="p-6">
        <div className="rounded-lg bg-red-50 border border-red-200 p-4">
          <p className="text-red-800">
            {(error as Error)?.message ?? "Failed to load transaction"}
          </p>
          <button
            onClick={() => navigate("/admin/transactions")}
            className="mt-3 text-sm text-red-600 hover:text-red-800 underline"
          >
            Back to Transactions
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-4xl">
      <button
        onClick={() => navigate(-1)}
        className="mb-4 text-sm text-slate-600 hover:text-slate-800 flex items-center gap-1"
      >
        ← Back
      </button>
      <TransactionDetailContent
        transaction={
          (data && "transaction" in data
            ? (data as TransactionDetailResponse).transaction
            : data) as Transaction
        }
      />
    </div>
  );
}

function TransactionDetailSkeleton() {
  return (
    <div className="p-6 max-w-4xl space-y-4 animate-pulse">
      <div className="h-4 w-24 bg-gray-200 rounded" />
      <div className="h-8 w-64 bg-gray-200 rounded" />
      <div className="grid grid-cols-2 gap-4 mt-6">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="h-16 bg-gray-100 rounded-lg" />
        ))}
      </div>
    </div>
  );
}

function TransactionDetailContent({ transaction }: { transaction: Transaction }) {
  const rows = [
    { label: "Transaction ID", value: transaction.transaction_id },
    { label: "Correlation ID", value: transaction.correlation_id ?? "—" },
    { label: "Source Vendor", value: transaction.source_vendor ?? "—" },
    { label: "Target Vendor", value: transaction.target_vendor ?? "—" },
    { label: "Operation", value: transaction.operation ?? "—" },
    { label: "Status", value: transaction.status ?? "—" },
    { label: "Redrive Count", value: String(transaction.redrive_count ?? 0) },
    { label: "Created", value: transaction.created_at ?? "—" },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">
        Transaction {transaction.transaction_id}
      </h1>
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
          <h2 className="font-semibold text-gray-800">Details</h2>
        </div>
        <dl className="divide-y divide-gray-200">
          {rows.map(({ label, value }) => (
            <div
              key={label}
              className="px-4 py-3 sm:grid sm:grid-cols-3 sm:gap-4"
            >
              <dt className="text-sm font-medium text-gray-500">{label}</dt>
              <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2 font-mono">
                {value}
              </dd>
            </div>
          ))}
        </dl>
      </div>
      {transaction.request_body && Object.keys(transaction.request_body).length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <h2 className="font-semibold text-gray-800">Request Body</h2>
          </div>
          <pre className="p-4 text-xs text-gray-700 overflow-x-auto">
            {JSON.stringify(transaction.request_body, null, 2)}
          </pre>
        </div>
      )}
      {transaction.response_body && Object.keys(transaction.response_body).length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <h2 className="font-semibold text-gray-800">Response Body</h2>
          </div>
          <pre className="p-4 text-xs text-gray-700 overflow-x-auto">
            {JSON.stringify(transaction.response_body, null, 2)}
          </pre>
        </div>
      )}
      {((transaction.canonicalRequestBody ?? transaction.canonical_request_body) != null &&
        Object.keys(transaction.canonicalRequestBody ?? transaction.canonical_request_body ?? {}).length > 0) && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <h2 className="font-semibold text-gray-800">Canonical Request Body</h2>
          </div>
          <pre className="p-4 text-xs text-gray-700 overflow-x-auto">
            {JSON.stringify(transaction.canonicalRequestBody ?? transaction.canonical_request_body, null, 2)}
          </pre>
        </div>
      )}
      {((transaction.targetRequestBody ?? transaction.target_request_body) != null &&
        Object.keys(transaction.targetRequestBody ?? transaction.target_request_body ?? {}).length > 0) && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <h2 className="font-semibold text-gray-800">Target Request Body</h2>
          </div>
          <pre className="p-4 text-xs text-gray-700 overflow-x-auto">
            {JSON.stringify(transaction.targetRequestBody ?? transaction.target_request_body, null, 2)}
          </pre>
        </div>
      )}
      {((transaction.targetResponseBody ?? transaction.target_response_body) != null &&
        Object.keys(transaction.targetResponseBody ?? transaction.target_response_body ?? {}).length > 0) && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <h2 className="font-semibold text-gray-800">Target Response Body</h2>
          </div>
          <pre className="p-4 text-xs text-gray-700 overflow-x-auto">
            {JSON.stringify(transaction.targetResponseBody ?? transaction.target_response_body, null, 2)}
          </pre>
        </div>
      )}
      {((transaction.canonicalResponseBody ?? transaction.canonical_response_body) != null &&
        Object.keys(transaction.canonicalResponseBody ?? transaction.canonical_response_body ?? {}).length > 0) && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <h2 className="font-semibold text-gray-800">Canonical Response Body</h2>
          </div>
          <pre className="p-4 text-xs text-gray-700 overflow-x-auto">
            {JSON.stringify(transaction.canonicalResponseBody ?? transaction.canonical_response_body, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
