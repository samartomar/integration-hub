import type { ReactNode } from "react";
import { pageLayoutTokens, typographyTokens } from "../styles/tokens";

type PageLayoutProps = {
  title: string;
  description?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  /** When true, omit outer wrapper (bg, max-width, padding) for use inside an existing container */
  embedded?: boolean;
};

export function PageLayout({
  title,
  description,
  right,
  children,
  className,
  embedded = false,
}: PageLayoutProps) {
  const content = (
    <>
      <header className="flex flex-col sm:flex-row sm:flex-wrap sm:items-start sm:justify-between gap-3 sm:gap-4">
        <div className="min-w-0 flex-1">
          <h1 className={`${typographyTokens.pageTitle} mb-1`.trim()}>{title}</h1>
          {description ? (
            <p className={typographyTokens.pageSubtitle}>{description}</p>
          ) : null}
        </div>
        {right ? <div className="w-full sm:w-auto flex flex-wrap items-center gap-2">{right}</div> : null}
      </header>
      {children}
    </>
  );
  if (embedded) {
    return (
      <div className={`space-y-6 ${className ?? ""}`.trim()}>
        {content}
      </div>
    );
  }
  const containerClass = [
    "mx-auto",
    pageLayoutTokens.maxWidth,
    pageLayoutTokens.pagePadding,
    "space-y-6",
    className ?? "",
  ].join(" ");
  return (
    <div className={pageLayoutTokens.pageBg}>
      <div className={containerClass}>
        {content}
      </div>
    </div>
  );
}
