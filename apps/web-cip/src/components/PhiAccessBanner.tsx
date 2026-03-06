import { useState } from "react";
import { usePhiAccess } from "../security/PhiAccessContext";

export function PhiAccessBanner() {
  const { phiApproved, phiModeEnabled, reason, setPhiMode } = usePhiAccess();
  const [draftReason, setDraftReason] = useState(reason || '');

  if (!phiApproved) {
    return (
      <div className="mx-3 mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 sm:mx-6 lg:mx-8">
        PHI view is restricted. Sensitive payloads remain redacted.
      </div>
    );
  }

  return (
    <div className="mx-3 mt-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 sm:mx-6 lg:mx-8">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          {phiModeEnabled
            ? 'PHI view is enabled for this session (audited access).'
            : 'PHI-approved account detected. Sensitive payloads are currently redacted.'}
        </div>
        <div className="flex items-center gap-2">
          <input
            className="min-w-[220px] rounded border border-amber-300 bg-white px-2 py-1 text-xs"
            value={draftReason}
            onChange={(e) => setDraftReason(e.target.value)}
            placeholder="Reason for PHI access"
          />
          {!phiModeEnabled ? (
            <button
              type="button"
              className="rounded bg-amber-600 px-3 py-1 text-xs font-semibold text-white disabled:opacity-60"
              disabled={!draftReason.trim()}
              onClick={() => setPhiMode(true, draftReason.trim())}
            >
              Enable PHI View
            </button>
          ) : (
            <button
              type="button"
              className="rounded border border-amber-600 px-3 py-1 text-xs font-semibold text-amber-800"
              onClick={() => setPhiMode(false)}
            >
              Disable PHI View
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
