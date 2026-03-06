import type { AuthProfile } from "../api/endpoints";
import type { VendorEndpoint } from "frontend-shared";
import { deriveHealthFromLegacyFields } from "./readinessModel";

function getEndpointHealth(ep: VendorEndpoint): "healthy" | "error" | "inactive" | "not_verified" {
  const epAny = ep as { endpointHealth?: string };
  if (epAny.endpointHealth) return epAny.endpointHealth as "healthy" | "error" | "inactive" | "not_verified";
  return deriveHealthFromLegacyFields(ep.verificationStatus, ep.isActive);
}

/** Single-pass stats: profile counts, endpoint health. Do NOT use authProfileId for health. */
export function computeStats(
  authProfiles: AuthProfile[],
  allEndpoints: VendorEndpoint[]
) {
  const endpointCountByProfile: Record<string, number> = {};
  let healthyEndpoints = 0;
  let endpointsWithIssues = 0;
  for (const ap of authProfiles) {
    if (ap.id) endpointCountByProfile[ap.id] = 0;
  }
  for (const ep of allEndpoints) {
    if (ep.authProfileId) {
      endpointCountByProfile[ep.authProfileId] =
        (endpointCountByProfile[ep.authProfileId] ?? 0) + 1;
    }
    const health = getEndpointHealth(ep);
    if (health === "healthy") {
      healthyEndpoints++;
    } else if (health === "error" || health === "not_verified") {
      endpointsWithIssues++;
    }
    // inactive excluded from both counts
  }
  const profilesInUse = authProfiles.filter(
    (ap) => ap.id && (endpointCountByProfile[ap.id] ?? 0) > 0
  ).length;
  return {
    endpointCountByProfile,
    profilesInUse,
    healthyEndpoints,
    endpointsWithIssues,
  };
}

export function formatConfigDate(s: string | undefined): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString();
  } catch {
    return s;
  }
}
