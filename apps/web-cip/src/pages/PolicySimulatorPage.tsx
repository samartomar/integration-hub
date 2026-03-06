import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { simulatePolicyDecision } from "../api/endpoints";

const ACTIONS = [
  "EXECUTE",
  "AI_EXECUTE_DATA",
  "AI_EXECUTE_PROMPT",
  "AUDIT_READ",
  "AUDIT_EXPAND_SENSITIVE",
] as const;

export function PolicySimulatorPage() {
  const [vendorCode, setVendorCode] = useState("");
  const [operationCode, setOperationCode] = useState("");
  const [targetVendorCode, setTargetVendorCode] = useState("");
  const [action, setAction] = useState<(typeof ACTIONS)[number]>("EXECUTE");

  const simulate = useMutation({
    mutationFn: () =>
      simulatePolicyDecision({
        vendorCode: vendorCode || undefined,
        operationCode: operationCode || undefined,
        targetVendorCode: targetVendorCode || undefined,
        action,
      }),
  });

  const result = simulate.data;
  const isAllowed = !!result?.allowed;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Policy Simulator</h1>
        <p className="text-sm text-slate-600">
          Admin-only simulation for policy outcomes. This endpoint evaluates policy only and never executes integrations.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <label className="text-sm text-slate-700">
          Vendor Code
          <input
            value={vendorCode}
            onChange={(e) => setVendorCode(e.target.value)}
            placeholder="LH001"
            className="mt-1 w-full border rounded px-2 py-1"
          />
        </label>

        <label className="text-sm text-slate-700">
          Operation Code
          <input
            value={operationCode}
            onChange={(e) => setOperationCode(e.target.value)}
            placeholder="get-verify-member-eligibility"
            className="mt-1 w-full border rounded px-2 py-1"
          />
        </label>

        <label className="text-sm text-slate-700">
          Target Vendor
          <input
            value={targetVendorCode}
            onChange={(e) => setTargetVendorCode(e.target.value)}
            placeholder="VENDOR_B"
            className="mt-1 w-full border rounded px-2 py-1"
          />
        </label>

        <label className="text-sm text-slate-700">
          Action
          <select
            value={action}
            onChange={(e) => setAction(e.target.value as (typeof ACTIONS)[number])}
            className="mt-1 w-full border rounded px-2 py-1"
          >
            {ACTIONS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
      </div>

      <button
        type="button"
        onClick={() => simulate.mutate()}
        disabled={simulate.isPending}
        className="inline-flex items-center rounded bg-slate-700 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
      >
        {simulate.isPending ? "Simulating..." : "Simulate"}
      </button>

      {simulate.isError && (
        <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          Simulation failed. Check inputs and try again.
        </div>
      )}

      {result && (
        <div className="rounded border bg-white p-4 space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-600">Decision:</span>
            <span
              className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${
                isAllowed ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
              }`}
            >
              {isAllowed ? "ALLOW" : "DENY"}
            </span>
          </div>
          <div className="text-sm text-slate-800">HTTP Status: {result.httpStatus}</div>
          <div className="text-sm text-slate-800">Reason Code: {result.decisionCode}</div>
          <div className="text-sm text-slate-700">Message: {result.message}</div>
        </div>
      )}
    </div>
  );
}
