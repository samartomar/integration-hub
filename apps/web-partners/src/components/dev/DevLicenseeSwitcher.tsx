import { useState } from "react";
import {
  setActiveVendorCode,
} from "frontend-shared";
import { isDevToolsEnabled } from "../../config/env";

interface DevLicenseeSwitcherProps {
  className?: string;
}

export function DevLicenseeSwitcher({ className }: DevLicenseeSwitcherProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [licenseeCode, setLicenseeCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (!isDevToolsEnabled()) {
    return null;
  }

  const open = () => {
    setError(null);
    setIsOpen(true);
  };

  const close = () => {
    setIsOpen(false);
  };

  const handleApply = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const code = licenseeCode.trim().toUpperCase();
    if (!code) {
      setError("Licensee code is required.");
      return;
    }

    setActiveVendorCode(code);
    window.dispatchEvent(new CustomEvent("activeVendorChanged"));
    window.location.reload();
  };

  return (
    <div className={className}>
      <button
        type="button"
        className="text-xs text-slate-500 hover:text-slate-800 underline"
        onClick={open}
      >
        Switch licensee (dev)
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-lg mx-4">
            <h2 className="mb-2 text-lg font-semibold">Switch licensee (dev only)</h2>
            <p className="mb-4 text-sm text-slate-600">
              Set the active licensee code for local flow testing.
            </p>

            <form onSubmit={handleApply} className="space-y-4">
              <div>
                <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600">
                  Licensee code
                </label>
                <input
                  type="text"
                  className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
                  placeholder="LH001, LH002, LH003..."
                  value={licenseeCode}
                  onChange={(e) => setLicenseeCode(e.target.value)}
                />
              </div>

              {error && <p className="text-xs text-red-600">{error}</p>}

              <div className="mt-4 flex justify-end gap-2">
                <button
                  type="button"
                  className="rounded-md border border-slate-300 px-3 py-1 text-sm"
                  onClick={close}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded-md bg-slate-900 px-3 py-1 text-sm font-medium text-white"
                >
                  Apply & reload
                </button>
              </div>

              <p className="mt-3 text-[11px] text-slate-500">
                Note: This tool is for local / dev testing only. In production,
                licensees should use the normal registration flow.
              </p>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
