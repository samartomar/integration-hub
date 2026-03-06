import React from "react";
import { useSessionStore } from "../session/useSessionStore";

export interface ConnectionBannerProps {
  /** Callback when Retry is clicked. Typically invalidates queries. If not provided, Retry is hidden. */
  onRetry?: () => void | Promise<void>;
}

export const ConnectionBanner: React.FC<ConnectionBannerProps> = ({ onRetry }) => {
  const { sessionExpired, lastError } = useSessionStore();

  if (!sessionExpired) return null;

  const message = lastError ?? "We lost connection to the backend.";

  const handleRetry = async () => {
    const { sessionStore } = await import("../session/sessionStore");
    sessionStore.clear();
    if (onRetry) {
      await onRetry();
    }
  };

  const handleReload = () => {
    window.location.reload();
  };

  return (
    <div className="bg-amber-50 border-b border-amber-200 px-3 py-2 flex items-center justify-between gap-3 text-sm shrink-0">
      <span className="font-medium text-amber-900">{message}</span>
      <div className="flex gap-2">
        {onRetry != null && (
          <button
            type="button"
            onClick={handleRetry}
            className="px-2 py-1 rounded border border-amber-400 text-amber-900 text-xs hover:bg-amber-100"
          >
            Retry
          </button>
        )}
        <button
          type="button"
          onClick={handleReload}
          className="px-2 py-1 rounded border border-slate-300 text-slate-700 text-xs hover:bg-slate-50"
        >
          Reload app
        </button>
      </div>
    </div>
  );
};
