/**
 * Endpoint summary panel for Visual Flow Builder.
 * Shown when the user selects the Endpoint step in the flow pipeline.
 * Reuses the same data source as Auth & Endpoints page (getVendorEndpoints).
 * Supports inline editing via VendorEndpointModal (same drawer as Auth & Endpoints).
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getVendorEndpoints, listAuthProfiles, upsertVendorEndpoint } from "../api/endpoints";
import { getActiveVendorCode, Skeleton } from "frontend-shared";
import type { VendorEndpoint } from "frontend-shared";
import { STALE_CONFIG } from "../api/queryKeys";
import { EndpointEditDrawer } from "./config/EndpointEditDrawer";
import { getEndpointVerificationDisplay } from "../utils/readinessModel";

function truncateUrl(url: string, maxLen = 50): string {
  if (!url || url.length <= maxLen) return url;
  return `${url.slice(0, maxLen - 3)}…`;
}

function getAuthStatusFromEndpoint(ep: VendorEndpoint): { label: string; variant: "green" | "red" | "amber" } {
  const d = getEndpointVerificationDisplay(
    ep.verificationStatus,
    ep.isActive,
    (ep as { endpointHealth?: import("../utils/readinessModel").EndpointHealth }).endpointHealth
  );
  const variant =
    d.variant === "configured" ? "green" : d.variant === "error" ? "red" : "amber";
  return { label: d.label, variant };
}

function formatDate(s: string | undefined): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString();
  } catch {
    return s;
  }
}

export type EndpointDirection = "inbound" | "outbound";

export interface EndpointSummaryPanelProps {
  operationCode: string;
  version: string;
  /** Inbound: Platform calls your API. Outbound: Platform routes your request to target licensee. */
  direction?: EndpointDirection;
}

/** Inbound: Other licensees call your API. Outbound: Routes to target licensee. */
const ENDPOINT_EMPTY_COPY: Record<EndpointDirection, string> = {
  inbound:
    "No endpoint configured yet. Configure where the platform calls your API for this operation.",
  outbound:
    "No endpoint configured yet. Configure where the platform routes your request to the target licensee’s API.",
};

export function EndpointSummaryPanel({
  operationCode,
  version: _version,
  direction = "inbound",
}: EndpointSummaryPanelProps) {
  const [endpointModalOpen, setEndpointModalOpen] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [toastType, setToastType] = useState<"success" | "error">("success");
  const activeVendor = getActiveVendorCode();
  const hasKey = !!activeVendor;
  const queryClient = useQueryClient();

  const { data: endpointsData, isLoading } = useQuery({
    queryKey: ["vendor-endpoints"],
    queryFn: getVendorEndpoints,
    enabled: hasKey,
    staleTime: STALE_CONFIG,
  });

  const { data: authData } = useQuery({
    queryKey: ["auth-profiles", activeVendor ?? ""],
    queryFn: () => listAuthProfiles(activeVendor!),
    enabled: !!activeVendor && hasKey,
    staleTime: STALE_CONFIG,
  });

  const upsertEndpoint = useMutation({
    mutationFn: upsertVendorEndpoint,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vendor-endpoints"] });
      queryClient.invalidateQueries({ queryKey: ["vendor", "config-bundle"] });
      setEndpointModalOpen(false);
      setToastType("success");
      setToastMessage("Endpoint saved");
      setTimeout(() => setToastMessage(null), 3000);
    },
    onError: (err) => {
      const msg =
        (err as { response?: { data?: { error?: { message?: string } } } })?.response?.data?.error
          ?.message ??
        (err as Error)?.message ??
        "Failed to save endpoint.";
      setToastType("error");
      setToastMessage(msg);
      setTimeout(() => setToastMessage(null), 6000);
    },
  });

  const authProfiles = authData?.items ?? [];
  const activeAuthProfiles = authProfiles.filter((ap) => ap.isActive !== false);
  const allEndpoints = endpointsData?.items ?? [];
  const flowDirection = direction.toUpperCase();
  const endpoint = allEndpoints.find(
    (e) =>
      (e.operationCode ?? "").toUpperCase() === operationCode.toUpperCase() &&
      (e.flowDirection ?? "").toUpperCase() === flowDirection
  );

  const authProfileName = (id: string | undefined | null): string => {
    if (id == null || id === "") return "—";
    const ap = authProfiles.find((a) => a.id === id);
    return ap?.name ?? id;
  };

  const authToAuthEndpointPath = () => {
    const params = new URLSearchParams();
    params.set("tab", "endpoints");
    params.set("operation", operationCode);
    params.set("direction", flowDirection);
    return `/configuration/endpoints?${params.toString()}`;
  };

  const handleSaveEndpoint = async (payload: {
    operationCode: string;
    url: string;
    flowDirection?: string;
    httpMethod?: string;
    payloadFormat?: string;
    timeoutMs?: number;
    isActive?: boolean;
    authProfileId?: string | null;
    verificationRequest?: Record<string, unknown> | null;
  }) => {
    await upsertEndpoint.mutateAsync({
      ...payload,
      flowDirection: payload.flowDirection ?? flowDirection,
    });
  };

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-20 w-full rounded-lg" />
        <Skeleton className="h-10 w-32 rounded" />
      </div>
    );
  }

  if (!endpoint || !endpoint.url?.trim()) {
    const emptyEndpoint: VendorEndpoint = {
      operationCode,
      url: "",
      flowDirection,
    };
    return (
      <div className="space-y-4">
        {toastMessage && (
          <p
            className={`text-sm font-medium ${toastType === "error" ? "text-red-600" : "text-emerald-600"}`}
          >
            {toastMessage}
          </p>
        )}
        <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-6">
          <p className="text-sm text-gray-600 mb-4">
            {ENDPOINT_EMPTY_COPY[direction]}
          </p>
          <div className="flex flex-col sm:flex-row gap-2">
            <button
              type="button"
              onClick={() => setEndpointModalOpen(true)}
              disabled={upsertEndpoint.isPending}
              className="inline-flex items-center justify-center px-4 py-2 text-sm font-medium text-white bg-slate-700 hover:bg-slate-800 rounded-lg disabled:opacity-50 shrink-0"
            >
              Add endpoint
            </button>
            <Link
              to={authToAuthEndpointPath()}
              className="inline-flex items-center justify-center text-sm font-medium text-slate-500 hover:text-slate-700"
            >
              Manage in Auth & Endpoints →
            </Link>
          </div>
        </div>
        <EndpointEditDrawer
          open={endpointModalOpen}
          onClose={() => setEndpointModalOpen(false)}
          initialValues={emptyEndpoint}
          isAddMode
          supportedOperationCodes={[operationCode]}
          authProfiles={activeAuthProfiles}
          onSave={handleSaveEndpoint}
        />
      </div>
    );
  }

  const { label: statusLabel, variant: statusVariant } = getAuthStatusFromEndpoint(endpoint);
  const statusColors = {
    green: "bg-emerald-100 text-emerald-800 border-emerald-200",
    red: "bg-red-100 text-red-800 border-red-200",
    amber: "bg-amber-100 text-amber-800 border-amber-200",
  };

  return (
    <div className="space-y-4">
      {toastMessage && (
        <p
          className={`text-sm font-medium ${toastType === "error" ? "text-red-600" : "text-emerald-600"}`}
        >
          {toastMessage}
        </p>
      )}
      <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className="inline-block px-2 py-0.5 text-xs font-medium rounded border bg-gray-100 text-gray-700 border-gray-200"
            title="HTTP method"
          >
            {(endpoint.httpMethod ?? "POST").toUpperCase()}
          </span>
          <span
            className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded border ${statusColors[statusVariant]}`}
            title={statusLabel}
          >
            {authProfileName(endpoint.authProfileId)} · {statusLabel}
          </span>
        </div>
        <p
          className="text-sm font-mono text-gray-700 truncate"
          title={endpoint.url ?? undefined}
        >
          {truncateUrl(endpoint.url ?? "")}
        </p>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
          <span>Timeout: {endpoint.timeoutMs ?? 8000}ms</span>
          <span>Last verified: {formatDate(endpoint.lastVerifiedAt ?? undefined)}</span>
        </div>
        <div className="flex flex-col sm:flex-row gap-2 pt-2">
          <button
            type="button"
            onClick={() => setEndpointModalOpen(true)}
            disabled={upsertEndpoint.isPending}
            className="inline-flex items-center justify-center px-4 py-2 text-sm font-medium text-white bg-slate-700 hover:bg-slate-800 rounded-lg disabled:opacity-50 shrink-0"
          >
            Edit endpoint
          </button>
          <Link
            to={authToAuthEndpointPath()}
            className="inline-flex items-center text-sm font-medium text-slate-500 hover:text-slate-700"
          >
            Manage in Auth & Endpoints →
          </Link>
        </div>
      </div>

      <EndpointEditDrawer
        open={endpointModalOpen}
        onClose={() => setEndpointModalOpen(false)}
        initialValues={endpoint ?? null}
        supportedOperationCodes={[operationCode]}
        authProfiles={activeAuthProfiles}
        onSave={handleSaveEndpoint}
      />
    </div>
  );
}
