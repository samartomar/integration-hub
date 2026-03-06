import { Link } from "react-router-dom";
import { getChecklistStatusLabel } from "../utils/readinessModel";

export type Status = "ok" | "partial" | "missing";

export function ChecklistCard({
  title,
  status,
  count,
  to,
  actionLabel = "Configure",
  disabled = false,
  openSettings = false,
  compact = false,
  statusLabels,
}: {
  title: string;
  status: Status;
  count?: number;
  to: string;
  actionLabel?: string;
  disabled?: boolean;
  openSettings?: boolean;
  compact?: boolean;
  statusLabels?: { ok?: string; partial?: string; missing?: string };
}) {
  const icon =
    disabled ? (
      <span className="text-gray-300 text-lg">○</span>
    ) : status === "ok" ? (
      <span className="text-emerald-600 text-lg">✅</span>
    ) : status === "partial" ? (
      <span className="text-amber-600 text-lg">⚠</span>
    ) : (
      <span className="text-gray-400 text-lg">○</span>
    );

  const statusLabel =
    statusLabels
      ? (status === "ok"
          ? statusLabels.ok ?? getChecklistStatusLabel("ok")
          : status === "partial"
            ? statusLabels.partial ?? getChecklistStatusLabel("partial")
            : statusLabels.missing ?? getChecklistStatusLabel("missing"))
      : getChecklistStatusLabel(status);

  const content = (
    <>
      <div className={`flex items-start justify-between gap-3 ${compact ? "gap-2" : ""}`}>
        <div className={`flex items-start gap-3 min-w-0 ${compact ? "gap-2" : ""}`}>
          <span className={`shrink-0 ${compact ? "mt-0" : "mt-0.5"}`}>{icon}</span>
          <div className="min-w-0">
            <h3 className={`font-medium text-gray-900 ${compact ? "text-sm" : ""}`}>{title}</h3>
            <p className={`text-gray-500 ${compact ? "text-xs mt-0.5" : "text-sm mt-0.5"}`}>
              {count !== undefined ? (
                <>{count} {count === 1 ? "item" : "items"}</>
              ) : (
                statusLabel
              )}
            </p>
          </div>
        </div>
        {!disabled && (
          <span className={`font-medium text-slate-600 shrink-0 ${compact ? "text-xs" : "text-xs"}`}>
            {actionLabel}
          </span>
        )}
      </div>
    </>
  );

  const baseClasses = compact
    ? "block rounded-lg border border-gray-200 bg-white hover:border-slate-300 hover:shadow-sm transition-colors p-3"
    : "block p-4 rounded-xl border border-gray-200 bg-white hover:border-slate-300 hover:shadow-sm transition-colors";

  if (disabled) {
    return (
      <div
        className={`${baseClasses} bg-gray-50 opacity-60 cursor-not-allowed`}
        title="Select a licensee first"
      >
        {content}
      </div>
    );
  }

  if (openSettings) {
    return (
      <button
        type="button"
        onClick={() => window.dispatchEvent(new CustomEvent("openSettings"))}
        className={`w-full text-left ${baseClasses}`}
      >
        {content}
      </button>
    );
  }

  return <Link to={to} className={baseClasses}>{content}</Link>;
}
