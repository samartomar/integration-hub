import { Link, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  getActiveVendorCode,
} from "frontend-shared";
import {
  listAuthProfiles,
  getVendorEndpoints,
  getVendorSupportedOperations,
  getMyAllowlist,
} from "../api/endpoints";
import { STALE_CONFIG } from "../api/queryKeys";
import { useFeature } from "../features/FeatureFlagContext";

/** Tab icon variant: neutral when no ops, success/warning/error when ops exist. */
type Status = "ok" | "partial" | "missing" | "error";

interface NavCard {
  path: string;
  label: string;
  isActiveWhen?: (pathname: string, search: string) => boolean;
  getCount?: () => number;
  getStatus?: () => Status;
}

function NavCardLink({
  path,
  label,
  count,
  status,
  isActive,
}: {
  path: string;
  label: string;
  count?: number;
  status: Status;
  isActive: boolean;
}) {
  const icon =
    status === "ok" ? (
      <span className={isActive ? "text-teal-100" : "text-emerald-600"} aria-label="OK">✓</span>
    ) : status === "partial" ? (
      <span className={isActive ? "text-teal-100" : "text-amber-600"} aria-label="Partial">⚠</span>
    ) : status === "error" ? (
      <span className={isActive ? "text-teal-100" : "text-red-600"} aria-label="Error">✗</span>
    ) : (
      <span className={isActive ? "text-teal-100" : "text-gray-400"} aria-label="Not configured">○</span>
    );

  const countLabel = count !== undefined ? `${count}` : status === "ok" ? "Ready" : "—";

  return (
    <Link
      to={path}
      className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-colors shrink-0 ${
        isActive
          ? "bg-teal-600 text-white shadow-sm"
          : "bg-white text-slate-700 border border-slate-200 hover:bg-slate-50 hover:border-slate-300"
      }`}
    >
      {icon}
      <span>{label}</span>
      <span className={isActive ? "text-teal-200 text-xs font-normal" : "text-slate-500 text-xs font-normal"}>
        ({countLabel})
      </span>
    </Link>
  );
}

export function ConfigNavCards() {
  const location = useLocation();
  const activeVendor = getActiveVendorCode();
  const hasKey = !!activeVendor;
  const featureRegistryBasic = useFeature("registry_basic");
  const featureGovernanceAllowlist = useFeature("governance_allowlist");

  const { data: authData } = useQuery({
    queryKey: ["auth-profiles", activeVendor ?? ""],
    queryFn: () => listAuthProfiles(activeVendor!),
    enabled: !!activeVendor && hasKey,
    retry: false,
    staleTime: STALE_CONFIG,
  });
  const { data: endpointsData } = useQuery({
    queryKey: ["vendor-endpoints"],
    queryFn: () => getVendorEndpoints(),
    enabled: hasKey,
    retry: (_, err) =>
      (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });
  const { data: supportedData } = useQuery({
    queryKey: ["vendor-supported-operations"],
    queryFn: () => getVendorSupportedOperations(),
    enabled: hasKey,
    retry: (_, err) =>
      (err as { response?: { status?: number } })?.response?.status !== 404,
    staleTime: STALE_CONFIG,
  });

  const { data: allowlistData } = useQuery({
    queryKey: ["my-allowlist", activeVendor ?? ""],
    queryFn: getMyAllowlist,
    enabled: !!activeVendor && hasKey,
    retry: false,
    staleTime: STALE_CONFIG,
  });

  const authProfiles = authData?.items?.filter((a) => a.isActive !== false) ?? [];
  const endpoints = endpointsData?.items ?? [];
  const supportedOps = supportedData?.items ?? [];
  const outboundAllowlist = allowlistData?.outbound ?? [];
  const inboundAllowlist = allowlistData?.inbound ?? [];
  const eligibleOperations = allowlistData?.eligibleOperations ?? [];

  const totalOps = supportedOps.length;

  // Endpoint readiness: count ops with verified endpoint. Endpoints have operationCode + verificationStatus.
  const verifiedEndpoints = endpoints.filter(
    (e) =>
      (e.verificationStatus ?? "").toUpperCase() === "VERIFIED" ||
      (e.verificationStatus ?? "").toUpperCase() === "OK",
  );
  const opsWithVerifiedEndpoint = new Set(
    verifiedEndpoints.map((e) => (e.operationCode ?? "").toUpperCase()).filter(Boolean),
  );
  const endpointVerifiedCount = supportedOps.filter((op) =>
    opsWithVerifiedEndpoint.has((op.operationCode ?? "").toUpperCase()),
  ).length;

  // Access control: blocked = ops where config would be complete but admin blocks. We use eligibleOperations
  // (accessStatusOutbound/Inbound) as a proxy when admin has blocked.
  const blockedCount = eligibleOperations.filter(
    (e) =>
      e.accessStatusOutbound === "BLOCKED" || e.accessStatusInbound === "BLOCKED",
  ).length;
  const allowedCount = eligibleOperations.filter(
    (e) =>
      e.accessStatusOutbound === "ALLOWED" ||
      e.accessStatusInbound === "ALLOWED" ||
      e.canCallOutbound ||
      e.canReceiveInbound,
  ).length;
  const allowlistEntryCount = outboundAllowlist.length + inboundAllowlist.length;

  // --- Overview: count = totalOps. When 0 → neutral; all ready → success; else warning.
  const overviewStatus: Status = (() => {
    if (totalOps === 0) return "missing";
    // Full "all ready" would need readiness rows; we use supported-ops presence as success for Overview tab.
    return "ok";
  })();

  // --- Endpoints: count = totalOps. When 0 → neutral; all verified → success; else warning.
  // No-auth endpoints (e.g. public APIs) can verify successfully; do not require auth profiles for tab icon.
  const authEndpointsStatus: Status = (() => {
    if (totalOps === 0) return "missing";
    if (endpointVerifiedCount === totalOps) return "ok";
    if (endpointVerifiedCount === 0) return "missing";
    return "partial";
  })();

  // --- Access control: count = totalOps.
  // Important: when totalOps === 0, keep tab neutral. We don't show warnings/errors until the vendor actually has operations.
  // Prioritize "has allowed access" over "has blocked": if vendor has rules with allowed access (or any allowlist rules),
  // show ok. Only show error when they have rules but all access is blocked (no allowed ops in any direction).
  const accessControlStatus: Status = (() => {
    if (totalOps === 0) return "missing";
    if (allowedCount > 0 || allowlistEntryCount > 0) return "ok";
    if (blockedCount > 0) return "error";
    return "partial";
  })();

  // Auth profiles: count = profiles. Status based on profiles presence.
  const authProfilesStatus: Status = authProfiles.length > 0 ? "ok" : "missing";
  const authProfilesCount = authProfiles.length;

  const cards: NavCard[] = [
    {
      path: "/configuration",
      label: "Overview",
      isActiveWhen: (p) => p === "/configuration" || p.startsWith("/builder"),
      getCount: () => totalOps,
      getStatus: () => overviewStatus,
    },
    {
      path: "/configuration/auth-profiles",
      label: "Authentication profile",
      isActiveWhen: (p) => p === "/configuration/auth-profiles",
      getCount: () => authProfilesCount,
      getStatus: () => authProfilesStatus,
    },
    {
      path: "/configuration/endpoints",
      label: "Endpoints",
      isActiveWhen: (p) => p === "/configuration/endpoints" || p === "/auth-endpoints",
      getCount: () => totalOps,
      getStatus: () => authEndpointsStatus,
    },
    {
      path: "/configuration/access",
      label: "Access control",
      isActiveWhen: (p) => p === "/configuration/access" || p === "/configuration/allowlist",
      getCount: () => totalOps,
      getStatus: () => accessControlStatus,
    },
  ].filter((card) => {
    if (!featureRegistryBasic) return false;
    if (card.path === "/configuration/access") return featureGovernanceAllowlist;
    return true;
  });

  return (
    <div className="mb-3 sm:mb-4">
      <div className="flex flex-wrap items-center gap-2">
        {cards.map((card) => {
          const isActive = card.isActiveWhen
            ? card.isActiveWhen(location.pathname, location.search)
            : location.pathname === card.path;
          const count = card.getCount?.();
          const status = card.getStatus?.() ?? "missing";

          return (
            <NavCardLink
              key={card.path}
              path={card.path}
              label={card.label}
              count={count}
              status={status}
              isActive={isActive}
            />
          );
        })}
      </div>
    </div>
  );
}
