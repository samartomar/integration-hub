import type { ReactNode } from "react";

interface OpenSettingsLinkProps {
  children: ReactNode;
  className?: string;
}

export function OpenSettingsLink({ children, className }: OpenSettingsLinkProps) {
  return (
    <button
      type="button"
      onClick={() => window.dispatchEvent(new CustomEvent("openSettings"))}
      className={className ?? "text-amber-600 hover:underline mt-2 inline-block"}
    >
      {children}
    </button>
  );
}
