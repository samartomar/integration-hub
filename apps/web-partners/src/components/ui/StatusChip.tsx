/**
 * Shared status chip for consistent status badges across the app.
 * Use for: operation info, flow pipeline, mapping status, etc.
 */

export type StatusVariant =
  | "configured"   // green – ready / verified
  | "passThrough"  // amber – canonical pass-through / optional mapping
  | "warning"      // yellow – needs mapping but not blocking
  | "error"        // rose – blocking / missing required config
  | "info"         // slate – informational ("Using canonical format")
  | "neutral";     // grey – unknown / not configured

export interface StatusChipProps {
  label: string;
  variant: StatusVariant;
  className?: string;
  title?: string;
  showDot?: boolean;
}

const VARIANT_STYLES: Record<StatusVariant, string> = {
  configured: "bg-emerald-50 text-emerald-700 border-emerald-100",
  passThrough: "bg-amber-50 text-amber-700 border-amber-100",
  warning: "bg-yellow-50 text-yellow-800 border-yellow-100",
  error: "bg-rose-50 text-rose-700 border-rose-100",
  info: "bg-slate-50 text-slate-600 border-slate-200",
  neutral: "bg-gray-50 text-gray-500 border-gray-200",
};

export function StatusChip({
  label,
  variant,
  className = "",
  title,
  showDot = true,
}: StatusChipProps) {
  const baseStyles =
    "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium border";
  const variantStyles = VARIANT_STYLES[variant];

  return (
    <span
      className={`${baseStyles} ${variantStyles} ${className}`.trim()}
      title={title ?? label}
      role="status"
    >
      {showDot && (
        <span
          className="h-1.5 w-1.5 shrink-0 rounded-full bg-current opacity-80"
          aria-hidden
        />
      )}
      <span>{label}</span>
    </span>
  );
}
