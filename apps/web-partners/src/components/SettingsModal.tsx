import { useState, useEffect, useRef } from "react";
import {
  isDebugPanelEnabled,
  setDebugPanelEnabled,
  setActiveVendorCode,
} from "frontend-shared";
import { isDevToolsEnabled } from "../config/env";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function SettingsModal({ isOpen, onClose }: SettingsModalProps) {
  const [debugEnabled, setDebugEnabled] = useState(false);
  const [licenseeCode, setLicenseeCode] = useState("");
  const [switchError, setSwitchError] = useState<string | null>(null);

  const didInitForOpen = useRef(false);
  useEffect(() => {
    if (isOpen) {
      if (!didInitForOpen.current) {
        didInitForOpen.current = true;
        setDebugEnabled(isDebugPanelEnabled());
        setLicenseeCode("");
        setSwitchError(null);
      }
    } else {
      didInitForOpen.current = false;
    }
  }, [isOpen]);

  const handleSwitchLicensee = (e: React.FormEvent) => {
    e.preventDefault();
    const code = licenseeCode.trim().toUpperCase();
    if (!code) {
      setSwitchError("Licensee code is required.");
      return;
    }
    setSwitchError(null);
    setActiveVendorCode(code);
    window.dispatchEvent(new CustomEvent("activeVendorChanged"));
    window.location.reload();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/50"
        aria-hidden
      />
      <div
        className="relative w-full max-w-md max-h-[90vh] overflow-y-auto bg-white rounded-lg shadow-xl p-5 mx-3"
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
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
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
              Press <kbd className="px-1 py-0.5 rounded bg-gray-100 font-mono">Ctrl+Shift+D</kbd> to open
            </p>
          </div>

          {isDevToolsEnabled() && (
            <div className="border-t border-gray-200 pt-4">
              <h3 className="text-sm font-semibold text-gray-800 mb-2">Switch licensee (dev)</h3>
              <p className="text-xs text-gray-500 mb-3">
                Set active licensee code for local/dev testing.
              </p>
              <form onSubmit={handleSwitchLicensee} className="space-y-3">
                <input
                  type="text"
                  value={licenseeCode}
                  onChange={(e) => setLicenseeCode(e.target.value)}
                  placeholder="LH001, LH002, LH003..."
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
                />
                {switchError && <p className="text-xs text-red-600">{switchError}</p>}
                <div className="flex justify-end">
                  <button
                    type="submit"
                    className="rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white"
                  >
                    Apply & reload
                  </button>
                </div>
              </form>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
