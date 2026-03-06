export function Skeleton({
  className = "",
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`animate-pulse rounded bg-gray-200 ${className}`}
      {...props}
    />
  );
}

export function CardSkeleton() {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <Skeleton className="h-4 w-24 mb-3" />
      <Skeleton className="h-8 w-16" />
    </div>
  );
}

export function TableRowSkeleton() {
  return (
    <tr>
      {[...Array(7)].map((_, i) => (
        <td key={i} className="px-4 py-3">
          <Skeleton className="h-4 w-full" />
        </td>
      ))}
    </tr>
  );
}

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

export function ChartSkeleton() {
  return (
    <div className="rounded-xl border border-gray-200 p-5 h-64">
      <Skeleton className="h-4 w-32 mb-4" />
      <div className="flex items-end gap-1 h-48 mt-4">
        {CHART_BAR_HEIGHTS.map((heightClass, i) => (
          <Skeleton
            key={i}
            className={`flex-1 min-w-[20px] ${heightClass}`}
          />
        ))}
      </div>
    </div>
  );
}
