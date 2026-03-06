import { useState, useEffect } from "react";
import { isDebugPanelEnabled, setDebugPanelEnabled } from "frontend-shared";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function SettingsModal({ isOpen, onClose }: SettingsModalProps) {
  const [debugEnabled, setDebugEnabled] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setDebugEnabled(isDebugPanelEnabled());
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50"
        aria-hidden
      />
      {/* Modal */}
      <div
        className="relative w-full max-w-md bg-white rounded-lg shadow-xl p-5 mx-3"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
      >
        <div className="flex items-center justify-between mb-1">
          <h2 id="settings-title" className="text-xl font-semibold text-gray-900">
            Settings
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 p-1 rounded"
            aria-label="Close settings"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-3">
          {/* Debug Panel */}
          <div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={debugEnabled}
                onChange={(e) => {
                  const v = e.target.checked;
                  setDebugEnabled(v);
                  setDebugPanelEnabled(v);
                }}
                className="rounded border-gray-300"
              />
              <span className="text-sm font-medium text-gray-700">
                Capture console errors (Debug panel)
              </span>
            </label>
            <p className="mt-1 text-xs text-gray-500">
              Press <kbd className="px-1 py-0.5 rounded bg-gray-100 font-mono">Ctrl+Shift+D</kbd> to open debug panel
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
