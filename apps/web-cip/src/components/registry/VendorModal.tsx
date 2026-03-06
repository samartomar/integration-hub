import { useState, useEffect } from "react";
import { ModalShell } from "./ModalShell";
import type { Vendor } from "../../types";

interface VendorModalProps {
  open: boolean;
  onClose: () => void;
  initialValues?: Vendor | null;
  onSave: (payload: {
    vendor_code: string;
    vendor_name: string;
    is_active?: boolean;
  }) => Promise<void>;
}

export function VendorModal({
  open,
  onClose,
  initialValues,
  onSave,
}: VendorModalProps) {
  const [vendorCode, setVendorCode] = useState("");
  const [vendorName, setVendorName] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isEdit = !!initialValues;

  useEffect(() => {
    if (open) {
      setVendorCode(initialValues?.vendorCode ?? "");
      setVendorName(initialValues?.vendorName ?? "");
      setIsActive(initialValues?.isActive !== false);
      setError(null);
    }
  }, [open, initialValues]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const code = vendorCode.trim().toUpperCase();
    const name = vendorName.trim();
    if (!code || !name) {
      setError("Licensee code and name are required.");
      return;
    }
    setIsLoading(true);
    try {
      await onSave({
        vendor_code: code,
        vendor_name: name,
        is_active: isActive,
      });
      onClose();
    } catch (err) {
      setError((err as Error)?.message ?? "Failed to save licensee.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <ModalShell open={open} onClose={onClose} title={isEdit ? "Edit Licensee" : "Create Licensee"}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Licensee code</label>
          <input
            type="text"
            value={vendorCode}
            onChange={(e) => setVendorCode(e.target.value)}
            placeholder="LH001"
            disabled={isEdit}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500 disabled:bg-gray-100 disabled:text-gray-600"
          />
          {isEdit && <p className="text-xs text-gray-500 mt-1">Code cannot be changed when editing.</p>}
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Licensee name</label>
          <input
            type="text"
            value={vendorName}
            onChange={(e) => setVendorName(e.target.value)}
            placeholder="Acme Corp"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
          />
        </div>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(e) => setIsActive(e.target.checked)}
            className="rounded border-gray-300 text-slate-600 focus:ring-slate-500"
          />
          <span className="text-sm text-gray-700">Active</span>
        </label>
        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
            {error}
          </div>
        )}
        <div className="flex gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isLoading}
            className="px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 disabled:opacity-50 rounded-lg"
          >
            {isLoading ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}
