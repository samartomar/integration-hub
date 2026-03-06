/**
 * Add/Edit Access rule drawer (Admin portal).
 * Direction is operation-owned: PROVIDER_RECEIVES_ONLY or TWO_WAY.
 * No user-selectable direction; derived from operation and shown as static text.
 */

import { useState, useEffect, useMemo } from "react";
import type { AllowlistEntry, Vendor, Operation } from "../../types";

export type OperationDirectionPolicyUI = "PROVIDER_RECEIVES_ONLY" | "TWO_WAY";

function formatLicenseeLabel(
  vendorCode: string | undefined | null,
  vendors: Vendor[]
): string {
  if (!vendorCode) return "—";
  const v = vendors.find((x) => x.vendorCode === vendorCode);
  if (v) return `${v.vendorCode} – ${v.vendorName}`;
  return vendorCode;
}

function buildRulePreview(
  sourceLabel: string,
  targetLabel: string,
  operationCode: string,
  directionPolicy: OperationDirectionPolicyUI
): string {
  const arrow = directionPolicy === "PROVIDER_RECEIVES_ONLY" ? "→" : "↔";
  const directionLabel =
    directionPolicy === "PROVIDER_RECEIVES_ONLY" ? "Send requests" : "Two-way";
  return `${sourceLabel} ${arrow} ${targetLabel} · ${operationCode} · ${directionLabel}`;
}

function mapPolicyToDirectionPolicy(
  policy: string | undefined
): OperationDirectionPolicyUI {
  const v = (policy || "").toUpperCase().trim();
  if (v === "PROVIDER_RECEIVES_ONLY") return "PROVIDER_RECEIVES_ONLY";
  if (v === "SERVICE_OUTBOUND_ONLY") return "PROVIDER_RECEIVES_ONLY";
  return "TWO_WAY";
}

export interface AllowlistDrawerProps {
  open: boolean;
  onClose: () => void;
  initialValues?: AllowlistEntry | null;
  vendors: Vendor[];
  operations: Operation[];
  existingOperationCodes?: string[];
  /** Map of operationCode -> vendor codes that have endpoints (providers) */
  providerVendorCodesByOperation?: Record<string, string[]>;
  onSave: (payload: {
    source_vendor_code?: string;
    target_vendor_code?: string;
    source_vendor_codes?: string[];
    target_vendor_codes?: string[];
    operation_code: string;
    flow_direction?: string;
  }) => Promise<void>;
  onDelete?: (entry: AllowlistEntry) => void;
}

export function AllowlistDrawer({
  open,
  onClose,
  initialValues,
  vendors,
  operations,
  existingOperationCodes = [],
  providerVendorCodesByOperation = {},
  onSave,
  onDelete,
}: AllowlistDrawerProps) {
  const [operationCode, setOperationCode] = useState("");
  const [operationSearch, setOperationSearch] = useState("");
  const [operationDropdownOpen, setOperationDropdownOpen] = useState(false);
  const [showAllOperations, setShowAllOperations] = useState(false);
  const [sourceVendorCodes, setSourceVendorCodes] = useState<string[]>([]);
  const [targetVendorCodes, setTargetVendorCodes] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isEdit = !!initialValues;

  const selectedOp = useMemo(
    () =>
      operations.find(
        (o) =>
          (o.operationCode || "").toUpperCase() ===
          (operationCode || "").toUpperCase()
      ),
    [operations, operationCode]
  );

  const policyValue =
    (selectedOp as Operation & { directionPolicy?: string })?.directionPolicy ??
    (selectedOp as Operation & { directionPolicy?: string })?.directionPolicy;
  const directionPolicy = mapPolicyToDirectionPolicy(policyValue);

  const providerCodes = operationCode
    ? providerVendorCodesByOperation[(operationCode || "").toUpperCase()] ?? []
    : [];

  const vendorOptions = vendors.filter((v) => v.isActive !== false);
  const activeOperations = operations.filter((o) => o.isActive !== false);
  const existingOperationSet = useMemo(
    () => new Set(existingOperationCodes.map((v) => String(v || "").trim().toUpperCase()).filter(Boolean)),
    [existingOperationCodes]
  );
  const operationOptions = useMemo(() => {
    const q = operationSearch.trim().toUpperCase();
    const base = activeOperations.filter((o) => {
      const op = (o.operationCode || "").toUpperCase();
      if (!showAllOperations && existingOperationSet.has(op) && op !== (operationCode || "").toUpperCase()) {
        return false;
      }
      if (!q) return true;
      const desc = (o.description || "").toUpperCase();
      return op.includes(q) || desc.includes(q);
    });
    return base;
  }, [activeOperations, showAllOperations, existingOperationSet, operationCode, operationSearch]);

  const selectedOperation = useMemo(
    () =>
      activeOperations.find(
        (o) => (o.operationCode || "").toUpperCase() === (operationCode || "").toUpperCase()
      ),
    [activeOperations, operationCode]
  );

  useEffect(() => {
    if (open) {
      setOperationCode(initialValues?.operationCode ?? "");
      setOperationSearch("");
      setOperationDropdownOpen(false);
      setShowAllOperations(false);
      setSourceVendorCodes(initialValues?.sourceVendorCode ? [initialValues.sourceVendorCode] : []);
      setTargetVendorCodes(initialValues?.targetVendorCode ? [initialValues.targetVendorCode] : []);
      setError(null);
    }
  }, [open, initialValues]);

  useEffect(() => {
    if (!open || isEdit || !operationCode || directionPolicy !== "PROVIDER_RECEIVES_ONLY") return;
    if (targetVendorCodes.length > 1) {
      setTargetVendorCodes(targetVendorCodes.slice(0, 1));
    }
  }, [open, isEdit, operationCode, directionPolicy, targetVendorCodes]);

  const targetOptions = useMemo(() => {
    if (directionPolicy !== "PROVIDER_RECEIVES_ONLY") return vendorOptions;
    if (providerCodes.length === 0) return vendorOptions;
    const set = new Set(providerCodes.map((v) => v.toUpperCase()));
    return vendorOptions.filter((v) => set.has((v.vendorCode || "").toUpperCase()));
  }, [directionPolicy, providerCodes, vendorOptions]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!operationCode) {
      setError("Operation is required.");
      return;
    }
    if (sourceVendorCodes.length === 0) {
      setError("At least one source licensee is required.");
      return;
    }
    const effectiveTargets =
      directionPolicy === "PROVIDER_RECEIVES_ONLY"
        ? targetVendorCodes.slice(0, 1)
        : targetVendorCodes;
    if (effectiveTargets.length === 0) {
      setError("At least one target licensee is required.");
      return;
    }
    setIsLoading(true);
    try {
      await onSave({
        source_vendor_codes: sourceVendorCodes,
        target_vendor_codes: effectiveTargets,
        operation_code: operationCode,
      });
      onClose();
    } catch (err) {
      const axiosErr = err as {
        response?: { data?: { error?: { message?: string } } };
        message?: string;
      };
      const msg =
        axiosErr?.response?.data?.error?.message ??
        (axiosErr as Error)?.message ??
        "Failed to save rule.";
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const sourceLabel = sourceVendorCodes.length === 1
    ? formatLicenseeLabel(sourceVendorCodes[0], vendors)
    : `${sourceVendorCodes.length} licensees`;
  const effectiveTargetsForPreview =
    directionPolicy === "PROVIDER_RECEIVES_ONLY"
      ? targetVendorCodes.slice(0, 1)
      : targetVendorCodes;
  const targetLabel = effectiveTargetsForPreview.length === 1
    ? formatLicenseeLabel(effectiveTargetsForPreview[0], vendors)
    : `${effectiveTargetsForPreview.length} licensees`;
  const rulePreview =
    sourceVendorCodes.length > 0 && effectiveTargetsForPreview.length > 0 && operationCode
      ? buildRulePreview(
          sourceLabel,
          targetLabel,
          operationCode,
          directionPolicy
        )
      : null;

  if (!open) return null;

  return (
    <>
      <div
        className="fixed inset-0 bg-black/30 z-40"
        aria-hidden
      />
      <div
        className="fixed inset-4 md:inset-6 lg:inset-8 w-auto bg-white shadow-xl z-50 flex flex-col overflow-hidden rounded-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="allowlist-drawer-title"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50 shrink-0">
          <h2
            id="allowlist-drawer-title"
            className="font-semibold text-gray-900"
          >
            {isEdit ? "Edit rule" : "Add rule"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-2 text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-200"
            aria-label="Close drawer"
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

        <form
          onSubmit={handleSubmit}
          className="flex-1 overflow-y-auto p-4 space-y-4"
        >
          <div>
            <div className="relative">
              <button
                type="button"
                onClick={() => setShowAllOperations((v) => !v)}
                className="absolute -top-2 right-8 text-xs text-slate-600 hover:text-slate-800 bg-white px-1"
              >
                {showAllOperations ? "Show default operations" : "Show all operations"}
              </button>
              <label className="sr-only">
                Operation
              </label>
              <button
                type="button"
                onClick={() => {
                  if (isEdit) return;
                  setOperationDropdownOpen((v) => !v);
                }}
                disabled={isEdit}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-left focus:ring-2 focus:ring-slate-500 focus:border-slate-500 disabled:bg-gray-100 disabled:text-gray-600"
              >
                {selectedOperation
                  ? (selectedOperation.description
                      ? `${selectedOperation.operationCode} - ${selectedOperation.description}`
                      : selectedOperation.operationCode)
                  : "Select operation"}
              </button>
              {operationDropdownOpen && !isEdit && (
                <div className="absolute mt-1 w-full bg-white border border-gray-300 rounded-lg shadow-lg z-20">
                  <input
                    type="search"
                    value={operationSearch}
                    onChange={(e) => setOperationSearch(e.target.value)}
                    placeholder="Search operations..."
                    className="w-full px-3 py-2 text-sm border-b border-gray-200 focus:outline-none focus:ring-2 focus:ring-slate-500"
                    autoFocus
                  />
                  <div className="max-h-56 overflow-y-auto py-1">
                    {operationOptions.length === 0 ? (
                      <div className="px-3 py-2 text-xs text-slate-500">No operations found</div>
                    ) : (
                      operationOptions.map((o) => (
                        <button
                          key={o.operationCode}
                          type="button"
                          onClick={() => {
                            setOperationCode(o.operationCode);
                            setOperationDropdownOpen(false);
                          }}
                          className="w-full text-left px-3 py-2 text-sm hover:bg-slate-50"
                        >
                          {o.description
                            ? `${o.operationCode} - ${o.description}`
                            : o.operationCode}
                        </button>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Direction section - no radios, static text from operation */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Direction
            </label>

            {directionPolicy === "PROVIDER_RECEIVES_ONLY" && (
              <div className="text-sm">
                <strong>INBOUND</strong>
                <p className="text-xs text-gray-500 mt-0.5">
                  Source sends to target (provider receives).
                </p>
              </div>
            )}

            {directionPolicy === "TWO_WAY" && (
              <div className="text-sm">
                <strong>BOTH</strong>
                <p className="text-xs text-gray-500 mt-0.5">
                  Either direction allowed.
                </p>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Source licensee */}
            <div>
              <div className="flex items-center justify-between gap-2 mb-1">
                <label className="block text-sm font-medium text-gray-700">
                  Source licensee
                </label>
                {!isEdit && (
                  <button
                    type="button"
                    onClick={() => setSourceVendorCodes(vendorOptions.map((v) => v.vendorCode))}
                    className="text-xs text-slate-600 hover:text-slate-800"
                  >
                    Select all
                  </button>
                )}
              </div>
              <select
                value={sourceVendorCodes}
                onChange={(e) => setSourceVendorCodes(Array.from(e.target.selectedOptions).map((o) => o.value))}
                multiple
                size={8}
                disabled={isEdit}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500 disabled:bg-gray-100 disabled:text-gray-600"
              >
                {vendorOptions.map((v) => (
                  <option key={v.vendorCode} value={v.vendorCode}>
                    {v.vendorCode} – {v.vendorName}
                  </option>
                ))}
              </select>
              {directionPolicy === "PROVIDER_RECEIVES_ONLY" &&
                targetVendorCodes[0] &&
                sourceVendorCodes.includes(targetVendorCodes[0]) &&
                !isEdit && (
                  <p className="text-xs text-amber-700 mt-1">
                    The provider usually doesn&apos;t call itself on this operation.
                    Only use this if you really need self-calls.
                  </p>
                )}
              <p className="text-xs text-slate-500 mt-1">
                Select one or more source licensees.
              </p>
            </div>

            {/* Target licensee */}
            <div>
              <div className="flex items-center justify-between gap-2 mb-1">
                <label className="block text-sm font-medium text-gray-700">
                  Target licensee
                </label>
                {!isEdit && directionPolicy !== "PROVIDER_RECEIVES_ONLY" && (
                  <button
                    type="button"
                    onClick={() => setTargetVendorCodes(vendorOptions.map((v) => v.vendorCode))}
                    className="text-xs text-slate-600 hover:text-slate-800"
                  >
                    Select all
                  </button>
                )}
              </div>
              <select
                value={directionPolicy === "PROVIDER_RECEIVES_ONLY" ? (targetVendorCodes[0] ?? "") : targetVendorCodes}
                onChange={(e) =>
                  directionPolicy === "PROVIDER_RECEIVES_ONLY"
                    ? setTargetVendorCodes(e.target.value ? [e.target.value] : [])
                    : setTargetVendorCodes(Array.from(e.target.selectedOptions).map((o) => o.value))
                }
                multiple={directionPolicy !== "PROVIDER_RECEIVES_ONLY"}
                size={directionPolicy !== "PROVIDER_RECEIVES_ONLY" ? 8 : undefined}
                disabled={isEdit}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500 disabled:bg-gray-100 disabled:text-gray-600"
              >
                {directionPolicy === "PROVIDER_RECEIVES_ONLY" && (
                  <option value="">Select target provider</option>
                )}
                {targetOptions.map((v) => (
                  <option key={v.vendorCode} value={v.vendorCode}>
                    {v.vendorCode} – {v.vendorName}
                  </option>
                ))}
              </select>
              {directionPolicy === "PROVIDER_RECEIVES_ONLY" && (
                <p className="text-xs text-slate-600 mt-1">
                  Select one target provider for this operation.
                </p>
              )}
              {directionPolicy !== "PROVIDER_RECEIVES_ONLY" && (
                <p className="text-xs text-slate-500 mt-1">
                  Select one or more target licensees.
                </p>
              )}
            </div>
          </div>

          {rulePreview && (
            <div className="rounded-lg bg-slate-50 border border-slate-200 px-3 py-2">
              <p className="text-xs font-medium text-slate-600 mb-0.5">
                Rule preview
              </p>
              <p className="text-sm text-slate-800">{rulePreview}</p>
            </div>
          )}

          {error && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
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
              {isLoading ? "Saving…" : "Save rule"}
            </button>
            {isEdit && initialValues?.id && onDelete && (
              <button
                type="button"
                onClick={() => onDelete(initialValues)}
                className="px-4 py-2 text-sm font-medium text-rose-600 hover:text-rose-700 hover:bg-rose-50 rounded-lg"
              >
                Delete
              </button>
            )}
          </div>
        </form>
      </div>
    </>
  );
}
