import type { ReactNode } from "react";

interface FilterableTableShellProps {
  title?: string;
  searchPlaceholder?: string;
  searchValue: string;
  onSearchChange: (value: string) => void;
  /** When false, search input is hidden (use external search bar) */
  searchVisible?: boolean;
  filterSlot?: ReactNode;
  actionSlot?: ReactNode;
  children: ReactNode;
  /** Rendered below the scrollable table area (e.g. pagination) */
  footer?: ReactNode;
  /** When false, hides the header row (use when controls are in parent, e.g. CollapsiblePanel titleActions) */
  showHeader?: boolean;
}

export function FilterableTableShell({
  title = "",
  searchPlaceholder = "Search…",
  searchValue,
  onSearchChange,
  searchVisible = true,
  filterSlot,
  actionSlot,
  children,
  footer,
  showHeader = true,
}: FilterableTableShellProps) {
  const hasHeaderContent = showHeader && (!!title || searchVisible || filterSlot || actionSlot);
  return (
    <div className="space-y-4">
      {hasHeaderContent && (
      <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center sm:justify-between gap-3">
        {title ? <h3 className="text-sm font-semibold text-gray-800 truncate">{title}</h3> : <span />}
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          {searchVisible && (
            <input
              type="search"
              placeholder={searchPlaceholder}
              value={searchValue}
              onChange={(e) => onSearchChange(e.target.value)}
              className="w-full sm:w-auto min-w-0 px-3 py-2 sm:py-1.5 text-sm border border-gray-300 rounded-lg placeholder-gray-400 focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
            />
          )}
          {filterSlot}
          {actionSlot}
        </div>
      </div>
      )}
      <div className="overflow-x-auto max-h-[min(70vh,500px)] overflow-y-auto">
        {children}
      </div>
      {footer}
    </div>
  );
}
