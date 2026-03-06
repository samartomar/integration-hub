import type { PolicyPreviewDecision } from "../api/endpoints";

type PolicyExplainPanelProps = {
  decision?: PolicyPreviewDecision | null;
  isLoading?: boolean;
  errorMessage?: string | null;
};

const CHECK_LABELS: Array<{ key: keyof PolicyPreviewDecision["checks"]; label: string }> = [
  { key: "jwt", label: "JWT" },
  { key: "allowlist", label: "Allowlist" },
  { key: "endpoint", label: "Endpoint" },
  { key: "contracts", label: "Contracts" },
  { key: "usageLimit", label: "Usage Limit" },
  { key: "ai", label: "AI" },
];

export function PolicyExplainPanel({ decision, isLoading, errorMessage }: PolicyExplainPanelProps) {
  return (
    <aside className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-800">Policy Preview</h3>
        {decision ? (
          <span
            className={`rounded px-2 py-0.5 text-xs font-medium ${
              decision.allowed ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"
            }`}
          >
            {decision.allowed ? "Allowed" : "Blocked"}
          </span>
        ) : null}
      </div>

      {isLoading ? <p className="text-xs text-slate-500">Checking policy...</p> : null}
      {errorMessage ? <p className="text-xs text-amber-700">{errorMessage}</p> : null}

      {decision ? (
        <>
          <p className="text-xs text-slate-600">
            Reason: <span className="font-medium">{decision.reason}</span>
          </p>
          <div className="space-y-1">
            {CHECK_LABELS.map(({ key, label }) => {
              const item = decision.checks[key];
              return (
                <div key={key} className="flex items-center justify-between gap-2 text-xs">
                  <span className="text-slate-700">{label}</span>
                  <span className={item.passed ? "text-emerald-700" : "text-red-700"}>
                    {item.passed ? "OK" : "Fail"} - {item.reason}
                  </span>
                </div>
              );
            })}
          </div>

          {!decision.allowed && decision.whatToFix?.length > 0 ? (
            <div className="pt-1">
              <p className="text-xs font-medium text-slate-700 mb-1">What to fix</p>
              <ul className="list-disc list-inside text-xs text-slate-600 space-y-1">
                {decision.whatToFix.map((fix) => (
                  <li key={fix}>{fix}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : (
        !isLoading && !errorMessage ? <p className="text-xs text-slate-500">Select operation and target.</p> : null
      )}
    </aside>
  );
}
