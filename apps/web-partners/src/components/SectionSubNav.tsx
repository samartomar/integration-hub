import { Link, useLocation } from "react-router-dom";
import { vendorTheme } from "frontend-shared/styles/tokens";

export interface SubNavItem {
  path: string;
  label: string;
  /** Optional: custom active check for paths with query params */
  isActiveWhen?: (pathname: string, search: string) => boolean;
}

export function SectionSubNav({ items }: { title?: string; items: SubNavItem[] }) {
  const location = useLocation();

  return (
    <div className="mb-4 sm:mb-6">
      <div className="flex flex-wrap gap-2 p-2 sm:p-3 bg-gray-100 rounded-lg border border-gray-200">
        {items.map(({ path, label, isActiveWhen }) => {
          const isActive = isActiveWhen
            ? isActiveWhen(location.pathname, location.search)
            : location.pathname === path || location.pathname + (location.search || "") === path;

          return (
            <Link
              key={path}
              to={path}
              className={`px-3 py-2 text-sm font-medium rounded-md transition-colors ${
                isActive
                  ? "text-slate-800 shadow-sm border"
                  : "text-gray-600 hover:text-slate-800 hover:bg-slate-50"
              }`}
              style={{
                background: isActive ? vendorTheme.sidebarActiveBg : undefined,
                borderColor: isActive ? vendorTheme.topbarBorder : "transparent",
              }}
            >
              {label}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
