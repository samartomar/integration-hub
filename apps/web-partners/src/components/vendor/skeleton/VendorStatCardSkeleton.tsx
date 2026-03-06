import { Skeleton } from "frontend-shared";

/**
 * Skeleton for stat/metric cards on vendor Home/Operations.
 * Matches Admin CardSkeleton styling (gray-200 pulse, white card).
 */
export function VendorStatCardSkeleton({ className = "" }: { className?: string }) {
  return (
    <div className={`bg-white rounded-xl border border-gray-200 p-5 ${className}`}>
      <Skeleton className="h-4 w-24 mb-3" />
      <Skeleton className="h-8 w-16" />
    </div>
  );
}
