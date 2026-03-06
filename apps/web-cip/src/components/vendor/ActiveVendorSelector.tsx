import { useCallback, useEffect, useState } from "react";
import {
  getActiveVendorCode,
  setActiveVendorCode,
} from "../../utils/vendorStorage";

const PRESET_VENDORS = ["LH001", "LH002", "LH003"];

interface ActiveVendorSelectorProps {
  onVendorChange?: () => void;
  /** "card" for light styling in main content; "sidebar" for dark sidebar (default) */
  variant?: "sidebar" | "card";
}

export function ActiveVendorSelector({ onVendorChange, variant = "sidebar" }: ActiveVendorSelectorProps) {
  const [activeCode, setActiveCode] = useState<string>(() => getActiveVendorCode() ?? "");
  const [, setKeysVersion] = useState(0);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement | HTMLInputElement>) => {
      const value = e.target.value.trim().toUpperCase();
      setActiveCode(value);
      setActiveVendorCode(value);
      onVendorChange?.();
      window.dispatchEvent(new CustomEvent("activeVendorChanged"));
    },
    [onVendorChange]
  );

  useEffect(() => {
    setActiveCode(getActiveVendorCode() ?? "");
  }, []);

  useEffect(() => {
    const sync = () => setActiveCode(getActiveVendorCode() ?? "");
    const onKeysChanged = () => setKeysVersion((v) => v + 1);
    window.addEventListener("storage", sync);
    window.addEventListener("vendorKeysChanged" as keyof WindowEventMap, onKeysChanged);
    window.addEventListener("activeVendorChanged" as keyof WindowEventMap, sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener("vendorKeysChanged" as keyof WindowEventMap, onKeysChanged);
      window.removeEventListener("activeVendorChanged" as keyof WindowEventMap, sync);
    };
  }, []);

  const displayCode = activeCode || (getActiveVendorCode() ?? "");

  const isCard = variant === "card";
  return (
    <div className="space-y-3">
      <label className={`block text-xs font-medium uppercase tracking-wide ${isCard ? "text-gray-600" : "text-slate-400"}`}>
        Active Licensee
      </label>
      <div className="flex gap-2">
        <input
          list="active-vendor-list"
          value={displayCode}
          onChange={handleChange}
          placeholder="e.g. LH001"
          className={`flex-1 px-3 py-2 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500 placeholder-slate-500 ${
            isCard
              ? "bg-white border border-gray-300 text-gray-900"
              : "bg-slate-700 border border-slate-600 text-white placeholder-slate-500"
          }`}
        />
        <datalist id="active-vendor-list">
          {PRESET_VENDORS.map((code) => (
            <option key={code} value={code} />
          ))}
        </datalist>
      </div>
      {displayCode && (
        <div className="space-y-1">
          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${isCard ? "bg-slate-100 text-slate-700" : "bg-slate-600 text-slate-200"}`}>
            {displayCode}
          </span>
        </div>
      )}
    </div>
  );
}
