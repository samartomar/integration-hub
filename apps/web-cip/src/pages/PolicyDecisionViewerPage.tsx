import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listPolicyDecisions } from "../api/endpoints";

const DECISION_COLORS: Record<string, string> = {
  ALLOW: "text-green-700 bg-green-100",
  DENY: "text-red-700 bg-red-100",
};

function decisionTone(allowed: boolean): string {
  return allowed ? DECISION_COLORS.ALLOW : DECISION_COLORS.DENY;
}

export function PolicyDecisionViewerPage() {
  const [vendorCode, setVendorCode] = useState("");
  const [operationCode, setOperationCode] = useState("");
  const [decisionCode, setDecisionCode] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const query = useQuery({
    queryKey: [
      "policy-decisions",
      vendorCode,
      operationCode,
      decisionCode,
      dateFrom,
      dateTo,
    ],
    queryFn: () =>
      listPolicyDecisions({
        vendorCode: vendorCode || undefined,
        operationCode: operationCode || undefined,
        decisionCode: decisionCode || undefined,
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
        limit: 100,
      }),
  });

  const items = query.data?.items ?? [];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Policy Decisions</h1>
        <p className="text-sm text-slate-600">
          Diagnostic policy evaluation stream (metadata-only, no payloads).
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
        <input
          value={vendorCode}
          onChange={(e) => setVendorCode(e.target.value)}
          placeholder="Vendor"
          className="border rounded px-2 py-1 text-sm"
        />
        <input
          value={operationCode}
          onChange={(e) => setOperationCode(e.target.value)}
          placeholder="Operation"
          className="border rounded px-2 py-1 text-sm"
        />
        <input
          value={decisionCode}
          onChange={(e) => setDecisionCode(e.target.value)}
          placeholder="Decision Code"
          className="border rounded px-2 py-1 text-sm"
        />
        <input
          type="datetime-local"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          className="border rounded px-2 py-1 text-sm"
        />
        <input
          type="datetime-local"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          className="border rounded px-2 py-1 text-sm"
        />
      </div>

      <div className="border rounded bg-white overflow-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-100 text-slate-700">
            <tr>
              <th className="text-left px-3 py-2">Time</th>
              <th className="text-left px-3 py-2">Vendor</th>
              <th className="text-left px-3 py-2">Operation</th>
              <th className="text-left px-3 py-2">Action</th>
              <th className="text-left px-3 py-2">Decision</th>
              <th className="text-left px-3 py-2">HTTP Status</th>
              <th className="text-left px-3 py-2">Correlation ID</th>
            </tr>
          </thead>
          <tbody>
            {query.isLoading ? (
              <tr><td className="px-3 py-3" colSpan={7}>Loading...</td></tr>
            ) : items.length === 0 ? (
              <tr><td className="px-3 py-3 text-slate-500" colSpan={7}>No policy decisions found.</td></tr>
            ) : (
              items.map((item) => (
                <tr key={`${item.id ?? "row"}-${item.occurredAt ?? ""}`} className="border-t">
                  <td className="px-3 py-2">{item.occurredAt ?? "-"}</td>
                  <td className="px-3 py-2">{item.vendorCode ?? "-"}</td>
                  <td className="px-3 py-2">{item.operationCode ?? "-"}</td>
                  <td className="px-3 py-2">{item.action ?? "-"}</td>
                  <td className="px-3 py-2">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${decisionTone(!!item.allowed)}`}>
                      {item.allowed ? "ALLOW" : "DENY"} {item.decisionCode ? `(${item.decisionCode})` : ""}
                    </span>
                  </td>
                  <td className="px-3 py-2">{item.httpStatus ?? "-"}</td>
                  <td className="px-3 py-2 font-mono text-xs">{item.correlationId ?? "-"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="text-xs text-slate-500">Count: {query.data?.count ?? 0}</div>
    </div>
  );
}
