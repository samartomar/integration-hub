import { Skeleton } from "frontend-shared";

const CHART_BAR_HEIGHTS = [
  "h-[45%]",
  "h-[65%]",
  "h-[35%]",
  "h-[55%]",
  "h-[75%]",
  "h-[40%]",
  "h-[60%]",
  "h-[50%]",
  "h-[70%]",
  "h-[45%]",
  "h-[55%]",
  "h-[65%]",
] as const;

/**
 * Skeleton for chart placeholders (Home activity, heatmap area).
 * Matches Admin ChartSkeleton styling.
 */
export function VendorChartSkeleton({ className = "" }: { className?: string } = {}) {
  return (
    <div className={`rounded-xl border border-gray-200 p-5 h-64 ${className}`}>
      <Skeleton className="h-4 w-32 mb-4" />
      <div className="flex items-end gap-1 h-48 mt-4">
        {CHART_BAR_HEIGHTS.map((heightClass, i) => (
          <Skeleton key={i} className={`flex-1 min-w-[20px] ${heightClass}`} />
        ))}
      </div>
    </div>
  );
}
