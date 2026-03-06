import type { ReactNode } from "react";

type VendorPageLayoutProps = {
  title?: string;
  subtitle?: string;
  rightContent?: ReactNode;
  /** When rightContent is tall (e.g. Canonical banner), use "start" to align top */
  rightContentAlign?: "start" | "center";
  /** Header split: left % for title/subtitle, right % for rightContent (e.g. { left: 30, right: 70 }) */
  headerSplit?: { left: number; right: number };
  children: ReactNode;
  className?: string;
};

/**
 * Vendor page layout – header (title, subtitle, rightContent) and children.
 * The centered max-width container is provided by VendorAppLayout.
 */
export function VendorPageLayout({
  title,
  subtitle,
  rightContent,
  rightContentAlign = "center",
  headerSplit,
  children,
  className = "",
}: VendorPageLayoutProps) {
  const alignClass = rightContentAlign === "start" ? "items-start" : "items-center";
  const hasLeft = !!(title || subtitle);
  const leftClass = !hasLeft
    ? "hidden"
    : headerSplit
      ? "min-w-0 sm:flex-[3]" /* 30% when split 3:7 */
      : "min-w-0 flex-1";
  const rightClass = !hasLeft
    ? `w-full flex ${alignClass} gap-2 min-w-0`
    : headerSplit
      ? `w-full sm:min-w-0 sm:flex-[7] flex ${alignClass} gap-2` /* 70% when split 3:7 */
      : `w-full sm:w-auto flex ${alignClass} gap-2 flex-shrink-0 min-w-0`;
  return (
    <div className={`space-y-6 ${className}`.trim()}>
      {(title || subtitle || rightContent) && (
        <header className="flex flex-col sm:flex-row sm:flex-wrap sm:items-start sm:justify-between gap-3 sm:gap-4">
          <div className={leftClass}>
            {title && (
              <h1 className="text-lg sm:text-2xl font-semibold text-slate-900 tracking-tight mb-1">
                {title}
              </h1>
            )}
            {subtitle && (
              <p className="text-sm text-slate-500">{subtitle}</p>
            )}
          </div>
          {rightContent && (
            <div className={rightClass}>{rightContent}</div>
          )}
        </header>
      )}
      {children}
    </div>
  );
}
