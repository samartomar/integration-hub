/**
 * Shared StatusPill component for Admin and Vendor portals.
 * Used for status chips, badges, and readiness indicators.
 */

export type StatusPillVariant =
  | "configured"
  | "primary"
  | "info"
  | "warning"
  | "error"
  | "neutral";

export interface StatusPillProps {
  label: string;
  variant: StatusPillVariant;
  className?: string;
  title?: string;
  showIcon?: boolean;
  /** When true and configured, show only the check icon (no label text) */
  iconOnlyWhenReady?: boolean;
}

const VARIANT_STYLES: Record<StatusPillVariant, string> = {
  configured: "bg-emerald-100 text-emerald-800 border-emerald-200",
  primary: "bg-blue-100 text-blue-800 border-blue-100",
  info: "bg-sky-100 text-sky-800 border-sky-200",
  warning: "bg-amber-100 text-amber-800 border-amber-200",
  error: "bg-red-100 text-red-800 border-red-200",
  neutral: "bg-gray-100 text-gray-600 border-gray-200",
};

function CheckIcon({ className = "w-3.5 h-3.5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
    </svg>
  );
}

function InfoIcon({ className = "w-3.5 h-3.5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function ExclamationIcon({ className = "w-3.5 h-3.5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
  );
}

function MinusIcon({ className = "w-3.5 h-3.5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
    </svg>
  );
}

function StatusIcon({ variant }: { variant: StatusPillVariant }) {
  switch (variant) {
    case "configured":
    case "primary":
      return <CheckIcon />;
    case "info":
      return <InfoIcon />;
    case "warning":
    case "error":
      return <ExclamationIcon />;
    case "neutral":
      return <MinusIcon />;
    default:
      return null;
  }
}

export function StatusPill({
  label,
  variant,
  className = "",
  title,
  showIcon = true,
  iconOnlyWhenReady = false,
}: StatusPillProps) {
  const baseStyles =
    "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium border whitespace-nowrap";
  const compactStyles = "px-1.5 py-0.5";
  const variantStyles = VARIANT_STYLES[variant];
  const hideLabel = iconOnlyWhenReady && variant === "configured";

  return (
    <span
      className={`${baseStyles} ${hideLabel ? compactStyles : ""} ${variantStyles} ${className}`.trim()}
      title={title ?? label}
      role="status"
    >
      {showIcon && <StatusIcon variant={variant} />}
      {!hideLabel && <span>{label}</span>}
    </span>
  );
}
