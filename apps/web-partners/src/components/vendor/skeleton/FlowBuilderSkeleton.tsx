import { Skeleton } from "frontend-shared";

/**
 * Skeleton for Visual Flow Builder page.
 * Matches layout: header, stage tabs, main content grid.
 */
export function FlowBuilderSkeleton() {
  return (
    <div className="space-y-6 pb-20">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <Skeleton className="h-4 w-32 mb-2 rounded" />
          <Skeleton className="h-8 w-48 mb-1 rounded" />
          <Skeleton className="h-4 w-24 rounded" />
        </div>
      </div>
      <div className="flex gap-4 overflow-x-auto pb-2">
        {["canonical-request", "request-mapping", "vendor-request", "response-mapping", "canonical-response"].map(
          (id) => (
            <div
              key={id}
              className="flex-shrink-0 rounded-xl border border-gray-200 bg-white p-4 min-w-[140px]"
            >
              <Skeleton className="h-4 w-20 rounded mb-2" />
              <Skeleton className="h-3 w-16 rounded" />
            </div>
          )
        )}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 rounded-xl border border-gray-200 bg-white p-4">
          <Skeleton className="h-4 w-32 rounded mb-4" />
          <div className="space-y-2">
            {[...Array(4)].map((_, i) => (
              <Skeleton key={i} className="h-6 w-full rounded" />
            ))}
          </div>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <Skeleton className="h-4 w-24 rounded mb-4" />
          <div className="space-y-2">
            {[...Array(3)].map((_, i) => (
              <Skeleton key={i} className="h-4 w-full rounded" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
