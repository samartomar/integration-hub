import { useState, useMemo, useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { OpenSettingsLink } from "../components/OpenSettingsLink";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getMyAllowlist,
  getEligibleAccess,
  getProviderNarrowing,
  postProviderNarrowingCandidates,
  listVendors,
  listOperations,
  getVendorSupportedOperations,
  getVendorContracts,
  getVendorEndpoints,
  getVendorMappings,
  getVendorOperationsCatalog,
  getMyOperations,
  deleteAllowlist,
} from "../api/endpoints";
import {
  createAllowlistChangeRequest,
  listMyAllowlistChangeRequests,
  listMyAccessRequestsAllStatuses,
} from "../api/changeRequests";
import { canonicalVendorsKey, STALE_CONFIG } from "../api/queryKeys";
import {
  getActiveVendorCode,
  getVendorDirectionLabel,
} from "frontend-shared";
import {
  getDirectionPolicyConstraintTooltip,
} from "../utils/vendorDirectionLabels";
import { ModalShell } from "frontend-shared";
import { VendorPageLayout } from "../components/layout/VendorPageLayout";
import { VendorTableSkeleton } from "../components/vendor/skeleton";
import type { AllowlistEntry, Vendor, Operation } from "frontend-shared";
import {
  buildReadinessRowsForLicensee,
  getAccessOutcomeDisplay,
  mapReadinessToDisplay,
} from "../utils/readinessModel";
import { StatusPill } from "frontend-shared";
import type { MyAllowlistEntry } from "../api/endpoints";
import { useVendorConfigBundle } from "../hooks/useVendorConfigBundle";

function vendorDisplay(code: string | null | undefined, vendors: Vendor[]): string {
  if (!code) return "";
  const v = vendors.find((x) => x.vendorCode === code);
  return v ? `${code} – ${v.vendorName}` : code;
}

type AddStep = 1 | 2;

type EligibleOperationItem = {
  operationCode: string;
  canCallOutbound: boolean;
  canReceiveInbound: boolean;
};

function AddAllowlistWizard({
  open,
  onClose,
  activeVendor,
  vendors,
  operations,
  catalog,
  eligibleOperations,
  initialOperation,
  initialDirection,
  onSuccess,
  onPendingApproval,
  hasPendingForOperationDirection,
}: {
  open: boolean;
  onClose: () => void;
  activeVendor: string;
  vendors: Vendor[];
  operations: Operation[];
  catalog: { operationCode?: string; directionPolicy?: string }[];
  eligibleOperations?: EligibleOperationItem[];
  initialOperation?: string;
  initialDirection?: "outbound" | "inbound";
  onSuccess: () => void;
  onPendingApproval?: () => void;
  hasPendingForOperationDirection?: (op: string, dir: "outbound" | "inbound") => boolean;
}) {
  const [step, setStep] = useState<AddStep>(1);
  const [direction, setDirection] = useState<"outbound" | "inbound">(initialDirection ?? "outbound");
  const [otherVendorCode, setOtherVendorCode] = useState("");
  const [operationCode, setOperationCode] = useState(initialOperation ?? "");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [eligibleAccess, setEligibleAccess] = useState<{
    outboundTargets: string[];
    inboundSources: string[];
    canUseWildcardOutbound: boolean;
    canUseWildcardInbound: boolean;
    isBlockedByAdmin?: boolean;
  } | null>(null);
  const [loadingEligible, setLoadingEligible] = useState(false);
  const [providerNarrowingData, setProviderNarrowingData] = useState<{
    adminEnvelope: string[];
    vendorWhitelist: string[];
  } | null>(null);
  const [providerCandidatesData, setProviderCandidatesData] = useState<{
    candidates: { vendorCode: string; vendorName: string; hasVendorRule: boolean }[];
  } | null>(null);
  const [selectedCallers, setSelectedCallers] = useState<string[]>([]);
  const [selectedProviders, setSelectedProviders] = useState<string[]>([]);
  const [loadingProviderNarrowing, setLoadingProviderNarrowing] = useState(false);
  const [loadingProviderCandidates, setLoadingProviderCandidates] = useState(false);

  const allActiveOps = operations.filter((o) => o.isActive !== false);

  const activeOps = useMemo(() => {
    if (!eligibleOperations || eligibleOperations.length === 0) return allActiveOps;
    const eligibleByOp = new Map(
      eligibleOperations.map((e) => [
        (e.operationCode ?? "").toUpperCase(),
        { canCallOutbound: e.canCallOutbound === true, canReceiveInbound: e.canReceiveInbound === true },
      ])
    );
    let ops = allActiveOps.filter((o) => {
      const op = (o.operationCode ?? "").toUpperCase();
      const cap = eligibleByOp.get(op);
      if (!cap) return false;
      return direction === "outbound" ? cap.canCallOutbound : cap.canReceiveInbound;
    });
    // Include pre-selected op if not in filtered list (e.g. from URL params)
    if (operationCode) {
      const inList = ops.some((o) => (o.operationCode ?? "").toUpperCase() === operationCode.toUpperCase());
      if (!inList) {
        const sel = allActiveOps.find((o) => (o.operationCode ?? "").toUpperCase() === operationCode.toUpperCase());
        if (sel) ops = [sel, ...ops];
      }
    }
    return ops;
  }, [allActiveOps, eligibleOperations, direction, operationCode]);

  const partnerOptions = useMemo(() => {
    if (direction === "outbound") {
      const targets = eligibleAccess?.outboundTargets ?? [];
      return targets
        .filter((c) => c !== activeVendor)
        .map((c) => vendors.find((v) => v.vendorCode === c))
        .filter(Boolean) as Vendor[];
    }
    const sources = eligibleAccess?.inboundSources ?? [];
    return sources
      .filter((c) => c !== activeVendor)
      .map((c) => vendors.find((v) => v.vendorCode === c))
      .filter(Boolean) as Vendor[];
  }, [direction, eligibleAccess, vendors, activeVendor]);

  const catalogOpForPolicy = catalog.find(
    (c) => (c.operationCode ?? "").toUpperCase() === (operationCode ?? "").toUpperCase()
  );
  const directionPolicy = catalogOpForPolicy?.directionPolicy;
  const isProviderReceivesOnly =
    directionPolicy === "PROVIDER_RECEIVES_ONLY" || directionPolicy === "service_outbound_only";

  const reset = () => {
    setStep(1);
    setDirection("outbound");
    setOtherVendorCode("");
    setOperationCode("");
    setEligibleAccess(null);
    setProviderNarrowingData(null);
    setProviderCandidatesData(null);
    setSelectedCallers([]);
    setSelectedProviders([]);
    setError(null);
  };

  const loadEligibleAccess = async (op: string) => {
    setLoadingEligible(true);
    setLoadingProviderNarrowing(false);
    setError(null);
    try {
      const data = await getEligibleAccess(op, direction);
      setEligibleAccess(data);
      setProviderNarrowingData(null);
    } catch (e) {
      setEligibleAccess(null);
      setError((e as Error)?.message ?? "Could not load eligible partners.");
    } finally {
      setLoadingEligible(false);
    }
  };

  const loadProviderNarrowing = async (op: string) => {
    setLoadingProviderNarrowing(true);
    setLoadingEligible(false);
    setLoadingProviderCandidates(false);
    setError(null);
    try {
      const data = await getProviderNarrowing(op);
      setProviderNarrowingData({ adminEnvelope: data.adminEnvelope ?? [], vendorWhitelist: data.vendorWhitelist ?? [] });
      const whitelist = data.vendorWhitelist ?? [];
      const envelope = data.adminEnvelope ?? [];
      setSelectedCallers(whitelist.length === 0 ? [...envelope] : whitelist);
      setEligibleAccess(null);
      setProviderCandidatesData(null);
    } catch (e) {
      setProviderNarrowingData(null);
      setSelectedCallers([]);
      setError((e as Error)?.message ?? "Could not load provider narrowing options.");
    } finally {
      setLoadingProviderNarrowing(false);
    }
  };

  const loadProviderCandidates = async (op: string) => {
    setLoadingProviderCandidates(true);
    setLoadingProviderNarrowing(false);
    setLoadingEligible(false);
    setError(null);
    try {
      const data = await postProviderNarrowingCandidates(op, [activeVendor]);
      const candidates = data.candidates ?? [];
      setProviderCandidatesData({ candidates });
      setSelectedProviders(candidates.map((c) => c.vendorCode));
      setEligibleAccess(null);
      setProviderNarrowingData(null);
    } catch (e) {
      setProviderCandidatesData(null);
      setSelectedProviders([]);
      setError((e as Error)?.message ?? "Could not load candidate providers.");
    } finally {
      setLoadingProviderCandidates(false);
    }
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleSave = async () => {
    setError(null);
    setIsLoading(true);
    try {
      // Outbound provider narrowing: selectedProviders is set only when we loaded provider candidates
      const isOutboundProviderNarrowing =
        direction === "outbound" && selectedProviders.length > 0 && operationCode;
      if (providerNarrowingData && direction === "inbound") {
        if (!operationCode) return;
        const envelope = providerNarrowingData.adminEnvelope ?? [];
        if (selectedCallers.length === envelope.length) {
          onSuccess();
          handleClose();
          return;
        }
        await createAllowlistChangeRequest({
          direction: "INBOUND",
          operationCode: operationCode.toUpperCase(),
          targetVendorCodes: selectedCallers.map((c) => c.toUpperCase()),
          useWildcardTarget: false,
          ruleScope: "vendor",
          requestType: "CALLER_NARROWING",
        });
        onPendingApproval?.();
      } else if (isOutboundProviderNarrowing) {
        await createAllowlistChangeRequest({
          direction: "OUTBOUND",
          operationCode: operationCode!.toUpperCase(),
          targetVendorCodes: selectedProviders.map((c) => c.toUpperCase()),
          useWildcardTarget: false,
          ruleScope: "vendor",
          requestType: "PROVIDER_NARROWING",
        });
        onPendingApproval?.();
      } else {
        if (!otherVendorCode || !operationCode) return;
        await createAllowlistChangeRequest({
          direction: direction === "outbound" ? "OUTBOUND" : "INBOUND",
          operationCode: operationCode.toUpperCase(),
          targetVendorCodes: [otherVendorCode.toUpperCase()],
          useWildcardTarget: false,
          ruleScope: "vendor",
          requestType: "ALLOWLIST_RULE",
        });
        onPendingApproval?.();
      }
      onSuccess();
      handleClose();
    } catch (err) {
      setError((err as Error)?.message ?? "Failed to add access rule.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      setOperationCode(initialOperation ?? "");
      setDirection(initialDirection ?? "outbound");
      setOtherVendorCode("");
      setEligibleAccess(null);
      setProviderNarrowingData(null);
      setProviderCandidatesData(null);
      setSelectedCallers([]);
      setSelectedProviders([]);
    }
  }, [open, initialOperation, initialDirection]);

  // No longer force inbound for PROVIDER_RECEIVES_ONLY - allow outbound (request flow)

  if (!open) return null;

  const selectedOp = operations.find((o) => (o.operationCode ?? "").toUpperCase() === (operationCode ?? "").toUpperCase());
  const opVersion = selectedOp?.canonicalVersion ?? "v1";
  const vendorObj = vendors.find((v) => v.vendorCode === activeVendor);
  const vendorDisplayName = vendorObj ? `${activeVendor} – ${vendorObj.vendorName}` : activeVendor;
  const modalTitle =
    step === 1
      ? operationCode
        ? `Add access rule – ${(operationCode ?? "").toUpperCase()} ${opVersion}`
        : "Add access rule"
      : "Choose licensees for this rule";

  return (
    <ModalShell open={open} onClose={handleClose} title={modalTitle}>
      <div className="space-y-4">
        {step === 1 && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Operation</label>
              {activeOps.length === 0 ? (
                <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800">
                  No operations are enabled for your organization. Contact the integration administrator to enable access.
                </div>
              ) : (
                <select
                  value={operationCode}
                  onChange={(e) => {
                    const val = e.target.value;
                    setOperationCode(val);
                    setOtherVendorCode("");
                    setEligibleAccess(null);
                  }}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
                >
                  <option value="">Select operation</option>
                  {activeOps.map((o) => (
                    <option key={o.operationCode} value={o.operationCode}>
                      {o.operationCode} · {o.canonicalVersion ?? "v1"}
                    </option>
                  ))}
                </select>
              )}
            </div>

            {operationCode && (
              <div>
                <p className="block text-sm font-medium text-gray-700 mb-2">
                  Choose how calls flow on this operation
                </p>
                {directionPolicy && getDirectionPolicyConstraintTooltip(directionPolicy) && (
                  <p
                    className={`text-xs rounded-lg px-3 py-2 mb-2 border ${
                      isProviderReceivesOnly
                        ? "text-amber-700 bg-amber-50 border-amber-200"
                        : "text-slate-600 bg-slate-50 border-slate-200"
                    }`}
                    title={getDirectionPolicyConstraintTooltip(directionPolicy)}
                  >
                    {getDirectionPolicyConstraintTooltip(directionPolicy)}
                  </p>
                )}
                <div className="space-y-2">
                  <label className="flex items-start gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="direction"
                      checked={direction === "outbound"}
                      onChange={() => {
                        setDirection("outbound");
                        setOtherVendorCode("");
                        setEligibleAccess(null);
                        setProviderCandidatesData(null);
                      }}
                      className="mt-1 text-slate-600"
                    />
                    <span className="text-sm">
                      <strong>OUTBOUND</strong>
                      <span className="block text-xs text-gray-500 mt-0.5 font-normal">
                        I call other licensees on this operation.
                      </span>
                    </span>
                  </label>
                  <label className="flex items-start gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="direction"
                      checked={direction === "inbound"}
                      onChange={() => {
                        setDirection("inbound");
                        setOtherVendorCode("");
                        setEligibleAccess(null);
                      }}
                      className="mt-1 text-slate-600"
                    />
                    <span className="text-sm">
                      <strong>INBOUND</strong>
                      <span className="block text-xs text-gray-500 mt-0.5 font-normal">
                        Other licensees call me on this operation.
                      </span>
                    </span>
                  </label>
                  {isProviderReceivesOnly && (
                    <p className="text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 mt-2">
                      INBOUND: other licensees call you on this operation.
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            {(hasPendingForOperationDirection?.(operationCode, direction) ?? false) && (
              <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800">
                You already have a pending access request for this operation and direction. You can submit another
                request after the current one is approved or rejected.
              </div>
            )}
            <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3 text-sm text-slate-700">
              {direction === "outbound" ? (
                <>
                  <p><strong>Direction:</strong> {getVendorDirectionLabel("OUTBOUND")}</p>
                  <p><strong>Caller:</strong> {vendorDisplayName}</p>
                  <p><strong>Receiver:</strong> Select one or more licensees</p>
                </>
              ) : (
                <>
                  <p><strong>Direction:</strong> {getVendorDirectionLabel("INBOUND")}</p>
                  <p><strong>Caller:</strong> Select one or more licensees</p>
                  <p><strong>Receiver:</strong> {vendorDisplayName}</p>
                </>
              )}
            </div>

            {isProviderReceivesOnly && direction === "outbound" ? (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Which licensees do you want to request access to call?
                </label>
                {loadingProviderCandidates ? (
                  <p className="text-sm text-gray-500">Loading candidate providers…</p>
                ) : !providerCandidatesData ? (
                  <p className="text-sm text-amber-600">Could not load candidate providers.</p>
                ) : providerCandidatesData.candidates.length === 0 ? (
                  <div className="rounded-lg bg-sky-50 border border-sky-200 px-4 py-3 text-sm text-sky-800">
                    No licensees are admin-allowed for you to call on this operation. Contact the integration administrator.
                  </div>
                ) : (
                  <>
                    <p className="text-xs text-slate-600 mb-2">
                      Select which licensees you want to request. Admin approval required.
                    </p>
                    <div className="max-h-60 overflow-y-auto border border-gray-200 rounded-lg p-2 space-y-1">
                      {providerCandidatesData.candidates.map((c) => {
                        const checked = selectedProviders.includes(c.vendorCode);
                        const v = vendors.find((x) => x.vendorCode === c.vendorCode);
                        const label = v ? `${v.vendorName} (${c.vendorCode})` : `${c.vendorName} (${c.vendorCode})`;
                        return (
                          <label key={c.vendorCode} className="flex items-center gap-2 cursor-pointer hover:bg-slate-50 rounded px-2 py-1">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => {
                                setSelectedProviders((prev) =>
                                  prev.includes(c.vendorCode)
                                    ? prev.filter((x) => x !== c.vendorCode)
                                    : [...prev, c.vendorCode]
                                );
                              }}
                              className="text-slate-600"
                            />
                            <span className="text-sm">{label}</span>
                            {c.hasVendorRule && (
                              <span className="text-xs text-emerald-600">(rule exists)</span>
                            )}
                          </label>
                        );
                      })}
                    </div>
                  </>
                )}
              </div>
            ) : isProviderReceivesOnly && direction === "inbound" ? (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Who can call you on this operation?
                </label>
                {loadingProviderNarrowing ? (
                  <p className="text-sm text-gray-500">Loading…</p>
                ) : !providerNarrowingData ? (
                  <p className="text-sm text-amber-600">Could not load options.</p>
                ) : providerNarrowingData.adminEnvelope.length === 0 ? (
                  <div className="rounded-lg bg-sky-50 border border-sky-200 px-4 py-3 text-sm text-sky-800">
                    No licensees are admin-allowed to call you on this operation. Contact the integration administrator to enable access.
                  </div>
                ) : (
                  <>
                    {providerNarrowingData.vendorWhitelist.length === 0 && (
                      <p className="text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 mb-3">
                        No custom restrictions yet. All admin-allowed licensees can call you.
                      </p>
                    )}
                    <div className="max-h-60 overflow-y-auto border border-gray-200 rounded-lg p-2 space-y-1">
                      {providerNarrowingData.adminEnvelope.map((code) => {
                        const checked = selectedCallers.includes(code);
                        const v = vendors.find((x) => x.vendorCode === code);
                        const label = v ? `${v.vendorName} (${code})` : code;
                        return (
                          <label key={code} className="flex items-center gap-2 cursor-pointer hover:bg-slate-50 rounded px-2 py-1">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => {
                                setSelectedCallers((prev) =>
                                  prev.includes(code)
                                    ? prev.filter((c) => c !== code)
                                    : [...prev, code]
                                );
                              }}
                              className="text-slate-600"
                            />
                            <span className="text-sm">{label}</span>
                          </label>
                        );
                      })}
                    </div>
                    <p className="mt-2 text-xs text-gray-500">
                      Uncheck licensees to restrict who can call you. All checked = no restrictions (all admin-allowed can call).
                    </p>
                  </>
                )}
              </div>
            ) : (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  {direction === "outbound"
                    ? "Who is receiving the request?"
                    : "Who is allowed to send requests to me?"}
                </label>
                {operationCode && (
                  <p className="text-xs text-gray-500 mb-1.5">
                    {direction === "outbound"
                      ? `Who is allowed to receive ${operationCode} requests from you?`
                      : `Who is allowed to send ${operationCode} requests to you?`}
                  </p>
                )}
                {loadingEligible ? (
                  <p className="text-sm text-gray-500">Loading eligible partners…</p>
                ) : eligibleAccess?.isBlockedByAdmin ? (
                  <div className="rounded-lg bg-sky-50 border border-sky-200 px-4 py-3 text-sm text-sky-800">
                    This operation is blocked by admin rules in this direction. Contact the integration administrator to enable access before
                    you add rules.
                  </div>
                ) : partnerOptions.length === 0 ? (
                  <p className="text-sm text-amber-600">
                    No eligible partners for this operation. Admin rules may restrict access.
                  </p>
                ) : (
                  <>
                    <select
                      value={otherVendorCode}
                      onChange={(e) => setOtherVendorCode(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
                    >
                      <option value="">Select licensee</option>
                      {partnerOptions.map((v) => (
                        <option key={v.vendorCode} value={v.vendorCode}>
                          {v.vendorCode === "*" ? "Any licensee (*) – global rule" : `${v.vendorName} (${v.vendorCode})`}
                        </option>
                      ))}
                    </select>
                    {otherVendorCode === "*" ? (
                      <p className="mt-1.5 text-xs text-gray-500">
                        Using <strong>Any licensee (*)</strong> creates a <strong>global rule</strong> that applies to
                        all licensees for this operation and direction.
                      </p>
                    ) : otherVendorCode ? (
                      <p className="mt-1.5 text-xs text-gray-500">
                        This rule applies only between <strong>{vendorDisplayName}</strong> and{" "}
                        <strong>{vendorDisplay(otherVendorCode, vendors)}</strong> for this operation and direction.
                      </p>
                    ) : (
                      (eligibleAccess?.canUseWildcardOutbound || eligibleAccess?.canUseWildcardInbound) && (
                        <p className="mt-1.5 text-xs text-gray-500">
                          Using <strong>Any licensee (*)</strong> creates a <strong>global rule</strong> that applies
                          to all licensees for this operation and direction.
                        </p>
                      )
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
            {error.includes("DIRECTION_POLICY_VIOLATION") || error.toLowerCase().includes("direction") || error.toLowerCase().includes("policy") ? (
              <>
                This combination of direction and licensees isn&apos;t allowed for{" "}
                <strong className="font-mono">{operationCode || "this operation"}</strong>. Contact the integration administrator if you think this should be enabled.
              </>
            ) : (
              error
            )}
          </div>
        )}

        <div className="flex justify-between pt-2">
          <div className="flex gap-2">
            {step > 1 ? (
              <button
                type="button"
                onClick={() => setStep(1)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
              >
                Back
              </button>
            ) : (
              <button
                type="button"
                onClick={handleClose}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
              >
                Cancel
              </button>
            )}
          </div>
          {step < 2 ? (
            <button
              type="button"
              onClick={async () => {
                if (operationCode) {
                  if (isProviderReceivesOnly && direction === "inbound") {
                    await loadProviderNarrowing(operationCode);
                  } else if (isProviderReceivesOnly && direction === "outbound") {
                    await loadProviderCandidates(operationCode);
                  } else {
                    await loadEligibleAccess(operationCode);
                  }
                  setOtherVendorCode("");
                  setStep(2);
                }
              }}
              disabled={
                !operationCode ||
                activeOps.length === 0 ||
                loadingEligible ||
                loadingProviderNarrowing ||
                loadingProviderCandidates
              }
              className="px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 disabled:opacity-50 rounded-lg"
            >
              Next
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSave}
              disabled={
                (hasPendingForOperationDirection?.(operationCode, direction) ?? false) ||
                isLoading ||
                !operationCode ||
                (providerNarrowingData && direction === "inbound"
                  ? false
                  : direction === "outbound" && selectedProviders.length > 0
                    ? false
                    : !otherVendorCode)
              }
              className="px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 disabled:opacity-50 rounded-lg"
            >
              {isLoading ? "Saving…" : "Save rule"}
            </button>
          )}
        </div>
      </div>
    </ModalShell>
  );
}

export function VendorAllowlistPage() {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const operationParam = searchParams.get("operation") ?? undefined;
  const directionParam = searchParams.get("direction") ?? undefined;
  const activeVendor = getActiveVendorCode();
  const hasKey = !!activeVendor;
  const [wizardOpen, setWizardOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<AllowlistEntry | null>(null);
  const [pendingToast, setPendingToast] = useState(false);
  const outboundSectionRef = useRef<HTMLDivElement>(null);
  const inboundSectionRef = useRef<HTMLDivElement>(null);
  const accessRequestsSectionRef = useRef<HTMLDivElement>(null);

  const { data: bundleData, isLoading: bundleLoading, isError: bundleError } = useVendorConfigBundle(!!hasKey);
  const useIndividualConfig = hasKey && (bundleError || !bundleData);

  const { data: myAllowlistData, isLoading: allowlistLoading } = useQuery({
    queryKey: ["my-allowlist", activeVendor ?? ""],
    queryFn: getMyAllowlist,
    enabled: !!activeVendor && useIndividualConfig,
    retry: false,
    staleTime: STALE_CONFIG,
  });
  const { data: vendorsData } = useQuery({
    queryKey: canonicalVendorsKey,
    queryFn: () => listVendors(),
    enabled: !!activeVendor && hasKey,
    retry: false,
    staleTime: STALE_CONFIG,
  });
  const { data: opsData } = useQuery({
    queryKey: ["vendor-canonical-operations"],
    queryFn: () => listOperations(),
    enabled: hasKey,
    retry: false,
    staleTime: STALE_CONFIG,
  });
  const { data: supportedData } = useQuery({
    queryKey: ["vendor-supported-operations"],
    queryFn: getVendorSupportedOperations,
    enabled: useIndividualConfig,
    staleTime: STALE_CONFIG,
  });
  const { data: catalogData, isLoading: catalogLoading } = useQuery({
    queryKey: ["vendor-operations-catalog"],
    queryFn: getVendorOperationsCatalog,
    enabled: useIndividualConfig,
    staleTime: STALE_CONFIG,
  });
  const { data: contractsData } = useQuery({
    queryKey: ["vendor-contracts"],
    queryFn: () => getVendorContracts(),
    enabled: useIndividualConfig,
    staleTime: STALE_CONFIG,
  });
  const { data: endpointsData } = useQuery({
    queryKey: ["vendor-endpoints"],
    queryFn: () => getVendorEndpoints(),
    enabled: useIndividualConfig,
    staleTime: STALE_CONFIG,
  });
  const { data: mappingsData } = useQuery({
    queryKey: ["vendor-mappings"],
    queryFn: () => getVendorMappings(),
    enabled: useIndividualConfig,
    staleTime: STALE_CONFIG,
  });
  const { data: myOpsData } = useQuery({
    queryKey: ["vendor-my-operations"],
    queryFn: getMyOperations,
    enabled: !!activeVendor && useIndividualConfig,
    staleTime: STALE_CONFIG,
  });
  const { data: myChangeRequestsData } = useQuery({
    queryKey: ["my-allowlist-change-requests", activeVendor ?? ""],
    queryFn: () => listMyAllowlistChangeRequests("PENDING"),
    enabled: !!activeVendor && hasKey,
    staleTime: 30_000,
  });
  const { data: myAccessRequestsAll } = useQuery({
    queryKey: ["my-access-requests-all", activeVendor ?? ""],
    queryFn: listMyAccessRequestsAllStatuses,
    enabled: !!activeVendor && hasKey,
    staleTime: 60_000,
    refetchOnWindowFocus: true,
  });

  const catalog = bundleData?.operationsCatalog ?? catalogData?.items ?? [];
  const supportedOps = bundleData?.supportedOperations ?? supportedData?.items ?? [];
  const vendorContracts = bundleData?.contracts ?? contractsData?.items ?? [];
  const endpoints = bundleData?.endpoints ?? endpointsData?.items ?? [];
  const mappings = bundleData?.mappings ?? mappingsData?.mappings ?? [];
  const allowlistForPage = bundleData?.myAllowlist ?? myAllowlistData;
  const outboundAllowlist = allowlistForPage?.outbound ?? [];
  const inboundAllowlist = allowlistForPage?.inbound ?? [];

  const deleteMutation = useMutation({
    mutationFn: deleteAllowlist,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["my-allowlist", activeVendor ?? ""] });
      queryClient.invalidateQueries({ queryKey: ["vendor", "config-bundle"] });
      setDeleteConfirm(null);
    },
  });

  const vendors = vendorsData?.items ?? [];

  const configLoading =
    (bundleLoading && !bundleData) || (useIndividualConfig && (allowlistLoading || catalogLoading));

  const flowReadinessRows = useMemo(
    () =>
      buildReadinessRowsForLicensee({
        supported: supportedOps,
        catalog,
        vendorContracts,
        endpoints,
        mappings,
        outboundAllowlist,
        inboundAllowlist,
        eligibleOperations: allowlistForPage?.eligibleOperations,
        accessOutcomes: allowlistForPage?.accessOutcomes,
        vendorCode: activeVendor ?? "",
        myOperationsOutbound: myOpsData?.outbound,
        myOperationsInbound: myOpsData?.inbound,
      }),
    [
      supportedOps,
      catalog,
      vendorContracts,
      endpoints,
      mappings,
      outboundAllowlist,
      inboundAllowlist,
      allowlistForPage?.eligibleOperations,
      allowlistForPage?.accessOutcomes,
      activeVendor,
      myOpsData?.outbound,
      myOpsData?.inbound,
    ]
  );

  /** Summary counts: operations with admin-allowed access per direction (perspective-aware). */
  const stats = useMemo(() => {
    const outboundAllowed = flowReadinessRows.filter(
      (r) =>
        r.direction === "Outbound" &&
        r.isActive &&
        (r.accessOutcome === "ALLOWED_BY_ADMIN" || r.accessOutcome === "ALLOWED_NARROWED_BY_VENDOR")
    ).length;
    const inboundAllowed = flowReadinessRows.filter(
      (r) =>
        r.direction === "Inbound" &&
        r.isActive &&
        (r.accessOutcome === "ALLOWED_BY_ADMIN" || r.accessOutcome === "ALLOWED_NARROWED_BY_VENDOR")
    ).length;
    const blocked = flowReadinessRows.filter(
      (r) => r.isActive && r.accessOutcome === "BLOCKED_BY_ADMIN"
    ).length;
    return { outboundAllowed, inboundAllowed, blocked };
  }, [flowReadinessRows]);

  const pendingByOpDirection = useMemo(() => {
    const m = new Map<string, boolean>();
    for (const r of myChangeRequestsData ?? []) {
      const key = `${(r.operationCode ?? "").toUpperCase()}:${(r.direction ?? "OUTBOUND").toUpperCase()}`;
      m.set(key, true);
    }
    return m;
  }, [myChangeRequestsData]);

  /** Outbound rows: driven by flowReadinessRows, enriched with allowlist targets. */
  const outboundRows = useMemo(() => {
    const outboundByOp = new Map<string, MyAllowlistEntry[]>();
    for (const a of outboundAllowlist) {
      const op = (a.operation ?? "").toUpperCase();
      if (!op) continue;
      if (!outboundByOp.has(op)) outboundByOp.set(op, []);
      outboundByOp.get(op)!.push(a);
    }
    return flowReadinessRows
      .filter((r) => r.direction === "Outbound" && r.isActive)
      .map((row) => {
        const entries = outboundByOp.get(row.operationCode) ?? [];
        const entry = entries[0];
        return {
          operationCode: row.operationCode,
          operationVersion: row.operationVersion,
          row,
          entry,
          entries,
        };
      })
      .sort((a, b) => a.operationCode.localeCompare(b.operationCode));
  }, [flowReadinessRows, outboundAllowlist]);

  /** Inbound rows: driven by flowReadinessRows, enriched with allowlist callers. */
  const inboundRows = useMemo(() => {
    const inboundByOp = new Map<string, MyAllowlistEntry[]>();
    for (const a of inboundAllowlist) {
      const op = (a.operation ?? "").toUpperCase();
      if (!op) continue;
      if (!inboundByOp.has(op)) inboundByOp.set(op, []);
      inboundByOp.get(op)!.push(a);
    }
    return flowReadinessRows
      .filter((r) => r.direction === "Inbound" && r.isActive)
      .map((row) => ({
        operation: row.operationCode,
        operationVersion: row.operationVersion,
        row,
        entries: inboundByOp.get(row.operationCode) ?? [],
      }))
      .sort((a, b) => a.operation.localeCompare(b.operation));
  }, [flowReadinessRows, inboundAllowlist]);

  useEffect(() => {
    if (!operationParam || !directionParam) return;
    const d = directionParam.toLowerCase();
    if (d === "outbound" && outboundSectionRef.current) {
      outboundSectionRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (d === "inbound" && inboundSectionRef.current) {
      inboundSectionRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [operationParam, directionParam]);

  if (!activeVendor) {
    return (
      <VendorPageLayout title="Access control" subtitle="Manage outbound and inbound access rules.">
        <div className="rounded-lg bg-gray-50 border border-gray-200 p-4">
          <p className="text-sm font-medium text-gray-700">Select an active licensee above.</p>
        </div>
      </VendorPageLayout>
    );
  }

  if (!hasKey) {
    return (
      <VendorPageLayout title="Access control" subtitle="Manage outbound and inbound access rules.">
        <div className="rounded-lg bg-amber-50 border border-amber-200 p-4">
          <p className="text-sm font-medium text-amber-800">Active licensee not selected.</p>
          <OpenSettingsLink>Open Settings →</OpenSettingsLink>
        </div>
      </VendorPageLayout>
    );
  }

  return (
    <VendorPageLayout
      title="Access control"
      subtitle="Who you can call (outbound) and who can call you (inbound). Controlled by admin access rules."
      rightContent={
        <button
          type="button"
          onClick={() => setWizardOpen(true)}
          className="px-3 py-1.5 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 rounded-lg"
        >
          Add rule
        </button>
      }
    >
    <div className="space-y-6">

      {stats.blocked > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800">
          {stats.blocked} operation{stats.blocked !== 1 ? "s" : ""} blocked by admin access rules.
        </div>
      )}

      {(operationParam || directionParam) && (
        <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-2 text-sm text-slate-700">
          {operationParam && (
            <>
              Viewing operation: <strong className="font-mono">{operationParam}</strong>
              {directionParam && (
                <span className="ml-1">
                  · <strong>{directionParam === "outbound" ? "Outbound" : "Inbound"}</strong>
                </span>
              )}
            </>
          )}
          {!operationParam && directionParam && (
            <>Viewing direction: <strong>{directionParam === "outbound" ? "Outbound" : "Inbound"}</strong></>
          )}
          <Link to="/configuration/access" className="ml-2 text-slate-600 hover:text-slate-800 hover:underline">
            Clear filter
          </Link>
        </div>
      )}

      <div ref={outboundSectionRef} className="space-y-3">
        <h2 className="text-base font-semibold text-gray-800">
          {getVendorDirectionLabel("OUTBOUND")} ({configLoading ? "—" : stats.outboundAllowed})
        </h2>
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {configLoading ? (
            <VendorTableSkeleton rowCount={5} columnCount={4} />
          ) : outboundRows.length === 0 ? (
            <div className="p-6 text-center text-sm text-gray-500">
              No outbound access rules. Add a rule to enable calling another licensee.
            </div>
          ) : (
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b bg-gray-50">
                  <th className="py-2 px-4">Operation</th>
                  <th className="py-2 px-4">Target licensee</th>
                  <th className="py-2 px-4">Access</th>
                  <th className="py-2 px-4">Status</th>
                </tr>
              </thead>
              <tbody>
                {outboundRows.map(({ operationCode, row, entries }) => {
                  const op = operationCode;
                  const target = entries.length > 0
                    ? entries.some((e) => (e.targetVendor ?? "").trim() === "*")
                      ? "Any licensee"
                      : vendorDisplay(entries[0].targetVendor ?? "", vendors)
                    : "—";
                  const catalogOp = catalog.find(
                    (c) => (c.operationCode ?? "").toUpperCase() === op
                  );
                  const policyVal = catalogOp?.directionPolicy;
                  const policyTip = policyVal
                    ? getDirectionPolicyConstraintTooltip(policyVal)
                    : undefined;
                  const accessDisplay =
                    row.accessOutcome != null
                      ? getAccessOutcomeDisplay(row.accessOutcome, row.direction, {
                          narrowCount: row.vendorNarrowedCount,
                          envelopeCount: row.adminEnvelopeCount,
                        })
                      : row.hasAllowedOutboundTarget
                        ? getAccessOutcomeDisplay("ALLOWED_NARROWED_BY_VENDOR", row.direction)
                        : { label: "—", variant: "neutral" as const, tooltip: "" };
                  const statusDisplay = mapReadinessToDisplay(row);
                  return (
                    <tr key={`out-${op}`} className="border-b border-gray-100 hover:bg-gray-50">
                      <td
                        className="py-2 px-4 font-mono"
                        title={policyTip}
                      >
                        OUTBOUND {op} to…
                      </td>
                      <td className="py-2 px-4">{target}</td>
                      <td className="py-2 px-4" title={accessDisplay.tooltip || undefined}>
                        <div className="flex flex-col items-start gap-1.5">
                          {accessDisplay.label === "—" ? (
                            <span className="text-sm text-gray-500">—</span>
                          ) : (
                            <StatusPill
                              label={accessDisplay.label}
                              variant={accessDisplay.variant}
                              title={accessDisplay.tooltip || undefined}
                            />
                          )}
                          {pendingByOpDirection.get(`${op}:OUTBOUND`) && (
                            <button
                              type="button"
                              onClick={() => accessRequestsSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
                              className="inline-flex"
                              title="View in My access requests"
                            >
                              <StatusPill
                                label="Pending admin approval"
                                variant="warning"
                                title="View in My access requests"
                              />
                            </button>
                          )}
                        </div>
                      </td>
                      <td className="py-2 px-4">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <StatusPill
                            label={statusDisplay.label}
                            variant={statusDisplay.variant}
                            title={statusDisplay.tooltip}
                          />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div ref={inboundSectionRef} className="space-y-3">
        <h2 className="text-base font-semibold text-gray-800">
          {getVendorDirectionLabel("INBOUND")} ({configLoading ? "—" : stats.inboundAllowed})
        </h2>
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {configLoading ? (
            <VendorTableSkeleton rowCount={5} columnCount={4} />
          ) : inboundRows.length === 0 ? (
            <div className="p-6 text-center text-sm text-gray-500">
              No inbound access rules. Add a rule to enable other licensees to call you.
            </div>
          ) : (
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b bg-gray-50">
                  <th className="py-2 px-4">Operation</th>
                  <th className="py-2 px-4">Allowed callers</th>
                  <th className="py-2 px-4">Access</th>
                  <th className="py-2 px-4">Status</th>
                </tr>
              </thead>
              <tbody>
                {inboundRows.map(({ operation, row, entries }) => {
                  const catalogOp = catalog.find(
                    (c) => (c.operationCode ?? "").toUpperCase() === (operation ?? "").toUpperCase()
                  );
                  const policyVal = catalogOp?.directionPolicy;
                  const policyTip = policyVal
                    ? getDirectionPolicyConstraintTooltip(policyVal)
                    : undefined;
                  const hasWildcard = entries.some((e) => (e.sourceVendor ?? "").trim() === "*");
                  const callers = hasWildcard
                    ? "Any licensee"
                    : entries.length > 0
                      ? entries.map((e) => vendorDisplay(e.sourceVendor ?? "", vendors)).filter(Boolean).join(", ")
                      : "—";
                  const accessDisplay =
                    row.accessOutcome != null
                      ? getAccessOutcomeDisplay(row.accessOutcome, row.direction, {
                          narrowCount: row.vendorNarrowedCount,
                          envelopeCount: row.adminEnvelopeCount,
                        })
                      : row.hasAllowedInboundAccess
                        ? getAccessOutcomeDisplay("ALLOWED_NARROWED_BY_VENDOR", row.direction)
                        : { label: "—", variant: "neutral" as const, tooltip: "" };
                  const statusDisplay = mapReadinessToDisplay(row);
                  return (
                    <tr key={`in-${operation}`} className="border-b border-gray-100 hover:bg-gray-50">
                      <td
                        className="py-2 px-4 font-mono"
                        title={policyTip}
                      >
                        INBOUND {operation} from…
                      </td>
                      <td className="py-2 px-4">{callers}</td>
                      <td className="py-2 px-4" title={accessDisplay.tooltip || undefined}>
                        <div className="flex flex-col items-start gap-1.5">
                          {accessDisplay.label === "—" ? (
                            <span className="text-sm text-gray-500">—</span>
                          ) : (
                            <StatusPill
                              label={accessDisplay.label}
                              variant={accessDisplay.variant}
                              title={accessDisplay.tooltip || undefined}
                            />
                          )}
                          {pendingByOpDirection.get(`${operation}:INBOUND`) && (
                            <button
                              type="button"
                              onClick={() => accessRequestsSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
                              className="inline-flex"
                              title="View in My access requests"
                            >
                              <StatusPill
                                label="Pending admin approval"
                                variant="warning"
                                title="View in My access requests"
                              />
                            </button>
                          )}
                        </div>
                      </td>
                      <td className="py-2 px-4">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <StatusPill
                            label={statusDisplay.label}
                            variant={statusDisplay.variant}
                            title={statusDisplay.tooltip}
                          />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div ref={accessRequestsSectionRef} className="space-y-3">
        <h2 className="text-base font-semibold text-gray-800">My access requests</h2>
        <p className="text-sm text-gray-500">
          Shows your recent access change requests and their status.
        </p>
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {myAccessRequestsAll === undefined ? (
            <div className="p-6 text-center text-sm text-gray-500">Loading…</div>
          ) : (myAccessRequestsAll ?? []).length === 0 ? (
            <div className="p-6 text-center text-sm text-gray-500">
              No access requests yet. Add a rule above to submit a request for admin approval.
            </div>
          ) : (
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b bg-gray-50">
                  <th className="py-2 px-4">Requested at</th>
                  <th className="py-2 px-4">Operation</th>
                  <th className="py-2 px-4">Direction</th>
                  <th className="py-2 px-4">Targets</th>
                  <th className="py-2 px-4">Status</th>
                  <th className="py-2 px-4">Reason</th>
                </tr>
              </thead>
              <tbody>
                {(myAccessRequestsAll ?? []).map((r) => {
                  const reqAt = r.requestedAt ?? r.createdAt;
                  const dateStr = reqAt
                    ? new Date(reqAt).toLocaleString(undefined, {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                        hour: "numeric",
                        minute: "2-digit",
                      })
                    : "—";
                  const targets =
                    r.useWildcardTarget
                      ? "Any (*)"
                      : (r.targetVendorCodes ?? []).length === 0
                        ? "—"
                        : (r.targetVendorCodes ?? []).join(", ");
                  return (
                    <tr key={r.id} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="py-2 px-4 text-gray-700">{dateStr}</td>
                      <td className="py-2 px-4 font-mono">{r.operationCode ?? "—"}</td>
                      <td className="py-2 px-4">{r.direction ?? "—"}</td>
                      <td className="py-2 px-4">{targets}</td>
                      <td className="py-2 px-4">
                        <StatusPill
                          label={r.status ?? "—"}
                          variant={
                            r.status === "PENDING"
                              ? "warning"
                              : r.status === "APPROVED"
                                ? "configured"
                                : r.status === "REJECTED"
                                  ? "error"
                                  : "neutral"
                          }
                        />
                      </td>
                      <td className="py-2 px-4 text-gray-600 max-w-xs truncate" title={r.decisionReason ?? undefined}>
                        {r.status === "REJECTED" && r.decisionReason ? r.decisionReason : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <AddAllowlistWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        activeVendor={activeVendor ?? ""}
        vendors={vendors}
        operations={opsData?.items ?? []}
        catalog={catalog}
        eligibleOperations={allowlistForPage?.eligibleOperations}
        initialOperation={operationParam}
        initialDirection={directionParam === "outbound" ? "outbound" : directionParam === "inbound" ? "inbound" : undefined}
        hasPendingForOperationDirection={(op, dir) =>
          pendingByOpDirection.get(`${(op ?? "").toUpperCase()}:${(dir ?? "outbound").toUpperCase()}`) ?? false
        }
        onSuccess={() => {
          queryClient.invalidateQueries({ queryKey: ["my-allowlist", activeVendor ?? ""] });
          queryClient.invalidateQueries({ queryKey: ["my-allowlist-change-requests", activeVendor ?? ""] });
          queryClient.invalidateQueries({ queryKey: ["my-access-requests-all", activeVendor ?? ""] });
          queryClient.invalidateQueries({ queryKey: ["vendor", "config-bundle"] });
        }}
        onPendingApproval={() => {
          queryClient.invalidateQueries({ queryKey: ["my-allowlist-change-requests", activeVendor ?? ""] });
          queryClient.invalidateQueries({ queryKey: ["my-access-requests-all", activeVendor ?? ""] });
          setPendingToast(true);
          setTimeout(() => setPendingToast(false), 4000);
        }}
      />

      {deleteConfirm && (
        <ModalShell open onClose={() => setDeleteConfirm(null)} title="Remove access rule?">
          <p className="text-sm text-gray-600 mb-4">
            This will remove the rule: {vendorDisplay(deleteConfirm.sourceVendorCode, vendors)} →{" "}
            {vendorDisplay(deleteConfirm.targetVendorCode, vendors)} • {deleteConfirm.operationCode}
          </p>
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={() => setDeleteConfirm(null)}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => deleteConfirm.id && deleteMutation.mutate(deleteConfirm.id)}
              disabled={deleteMutation.isPending}
              className="px-4 py-2 text-sm font-medium text-white bg-rose-600 hover:bg-rose-700 rounded-lg disabled:opacity-50"
            >
              {deleteMutation.isPending ? "Removing…" : "Remove"}
            </button>
          </div>
        </ModalShell>
      )}

      {pendingToast && (
        <div
          className="fixed bottom-4 right-4 px-4 py-2 bg-emerald-600 text-white rounded-lg shadow-lg text-sm"
          role="status"
        >
          Access rule submitted for approval. Status: pending admin review.
        </div>
      )}
    </div>
    </VendorPageLayout>
  );
}
