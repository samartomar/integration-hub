import type { ReactNode } from "react";
import { pageLayoutTokens, typographyTokens } from "../styles/tokens";

type SectionCardProps = {
  title?: string;
  description?: string;
  headerExtras?: ReactNode;
  children: ReactNode;
};

export function SectionCard({
  title,
  description,
  headerExtras,
  children,
}: SectionCardProps) {
  const sectionClass = [
    pageLayoutTokens.surfaceBg,
    pageLayoutTokens.surfaceBorder,
    pageLayoutTokens.surfaceRadius,
    pageLayoutTokens.surfaceShadow,
    "p-5",
  ].join(" ");
  const hasHeader = title || description || headerExtras;
  return (
    <section className={sectionClass}>
      {hasHeader && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
          <div>
            {title ? (
              <h2 className={typographyTokens.sectionTitle}>{title}</h2>
            ) : null}
            {description ? (
              <p className={typographyTokens.sectionSubtitle}>{description}</p>
            ) : null}
          </div>
          {headerExtras ? (
            <div className="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-2 w-full sm:w-auto min-w-0">
              {headerExtras}
            </div>
          ) : null}
        </div>
      )}
      {children}
    </section>
  );
}
