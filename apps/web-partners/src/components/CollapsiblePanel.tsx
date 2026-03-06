import { useState } from "react";

interface CollapsiblePanelProps {
  title: string;
  /** Muted helper text below the title when expanded */
  subtitle?: string;
  defaultExpanded?: boolean;
  children: React.ReactNode;
  /** When true, forces expanded state (e.g. when there are issues) */
  forceExpanded?: boolean;
  /** Optional badge count or status */
  badge?: React.ReactNode;
  /** Controls rendered right-aligned in the header (e.g. filter dropdown, Add button) */
  titleActions?: React.ReactNode;
}

export function CollapsiblePanel({
  title,
  subtitle,
  defaultExpanded = true,
  children,
  forceExpanded = false,
  badge,
  titleActions,
}: CollapsiblePanelProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const isExpanded = forceExpanded || expanded;
  const canToggle = !forceExpanded;

  return (
    <div className="border border-gray-200 rounded-xl bg-white overflow-hidden">
      <div
        className={`flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 px-4 py-2.5 transition-colors ${
          isExpanded ? "bg-gray-50 border-b border-gray-200" : "hover:bg-gray-50"
        }`}
      >
        <button
          type="button"
          onClick={() => canToggle && setExpanded((e) => !e)}
          className={`flex-1 flex items-center justify-between text-left min-w-0 py-2 sm:py-0 min-h-[44px] sm:min-h-0 ${
            canToggle ? "cursor-pointer hover:opacity-80 active:opacity-70" : "cursor-default"
          }`}
        >
          <div className="flex items-center gap-2 min-w-0">
            {canToggle && (
              <span className="text-gray-500 text-xs shrink-0" aria-hidden>
                {isExpanded ? "▼" : "▶"}
              </span>
            )}
            <span className="text-sm font-semibold text-gray-800 truncate">{title}</span>
            {badge && <span className="text-xs text-gray-500 shrink-0">{badge}</span>}
          </div>
          {canToggle && (
            <span className="text-xs text-gray-500 shrink-0 ml-2">
              {isExpanded ? "Collapse" : "Expand"}
            </span>
          )}
        </button>
        {titleActions && (
          <div
            className="flex flex-wrap items-center gap-2 shrink-0 w-full sm:w-auto"
            onClick={(e) => e.stopPropagation()}
          >
            {titleActions}
          </div>
        )}
      </div>
      {isExpanded && (
        <div className="p-3">
          {subtitle && (
            <p className="text-xs text-gray-500 mb-2">{subtitle}</p>
          )}
          {children}
        </div>
      )}
    </div>
  );
}
