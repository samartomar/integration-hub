import { StatusPill } from "frontend-shared";

export interface CanonicalOperationsBannerProps {
  hasAvailableOperations: boolean;
  selectControl: React.ReactNode;
  directionControl?: React.ReactNode;
  /** Shown when operation is selected but neither direction is allowed (replaces direction row) */
  addBlockedMessage?: string;
  onAdd?: () => void;
  isAdding?: boolean;
  canAdd?: boolean;
  /** When true, catalog from backend is empty (no admin-approved operations). Shows "no operations available" message. */
  noAdminApprovedOperations?: boolean;
}

export function CanonicalOperationsBanner({
  hasAvailableOperations,
  selectControl,
  directionControl,
  addBlockedMessage,
  onAdd,
  isAdding = false,
  canAdd = true,
  noAdminApprovedOperations = false,
}: CanonicalOperationsBannerProps) {
  if (!hasAvailableOperations) {
    return (
      <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 md:px-6 md:py-4">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-sky-900">
            Canonical operations available to add
          </p>
          {noAdminApprovedOperations ? null : (
            <StatusPill label="Up to date" variant="configured" />
          )}
        </div>
        <p className="mt-1 text-xs text-sky-900/80">
          {noAdminApprovedOperations
            ? "No operations are available for configuration. This vendor does not have any admin-approved operations yet."
            : "All canonical operations have been added. New ones will appear here automatically."}
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 md:px-6 md:py-4">
      <div className="flex flex-col gap-4">
        {/* Row 1: Label + description */}
        <div>
          <p className="text-sm font-medium text-sky-900">
            Canonical operations available to add
          </p>
          <p className="text-xs text-sky-900/80 mt-0.5">
            When a new canonical contract is published, it becomes available here for you to add and wire up to your APIs.
          </p>
        </div>

        {/* Row 2: Dropdown + Add button */}
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-nowrap sm:items-center min-w-0">
          <div className="flex-1 min-w-0">
            {selectControl}
          </div>
          <button
            type="button"
            onClick={onAdd}
            disabled={!canAdd || isAdding}
            className="inline-flex items-center justify-center shrink-0 rounded-lg border border-sky-600 bg-sky-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-sky-700 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isAdding ? "Adding…" : "Add"}
          </button>
        </div>

        {/* Row 3: Direction section or blocked message */}
        {addBlockedMessage ? (
          <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2">
            <p className="text-sm text-amber-800">{addBlockedMessage}</p>
          </div>
        ) : directionControl ? (
          <div className="space-y-2">
            <p className="text-xs font-medium text-sky-900/70">Direction</p>
            <div className="flex flex-col gap-2">
              {directionControl}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
