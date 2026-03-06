import { Skeleton } from "frontend-shared";

const DEFAULT_ROW_COUNT = 6;

/**
 * Skeleton for list/table pages (Operations, Flows, Configuration).
 * Shows header row + skeleton rows. Matches Admin table style.
 */
export function VendorTableSkeleton({
  rowCount = DEFAULT_ROW_COUNT,
  columnCount = 7,
  className = "",
}: { rowCount?: number; columnCount?: number; className?: string } = {}) {
  return (
    <div className={`overflow-x-auto ${className}`}>
      <table className="min-w-full text-sm">
        <thead>
          <tr className="text-left text-gray-500 border-b bg-gray-50">
            {[...Array(columnCount)].map((_, i) => (
              <th key={i} className="py-2 px-3">
                <Skeleton className="h-3 w-16" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {[...Array(rowCount)].map((_, rowIdx) => (
            <tr key={rowIdx}>
              {[...Array(columnCount)].map((_, colIdx) => (
                <td key={colIdx} className="px-4 py-3">
                  <Skeleton className="h-4 w-full" />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
