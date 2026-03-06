import type { HTMLAttributes } from "react";

/**
 * Base skeleton primitive – pulse animation, gray background.
 * Matches Admin dashboard styling (gray-200, animate-pulse, rounded).
 */
export function Skeleton({
  className = "",
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`animate-pulse rounded bg-gray-200 ${className}`}
      {...props}
    />
  );
}
