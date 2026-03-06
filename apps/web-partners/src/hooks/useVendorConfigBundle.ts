import { useQuery } from "@tanstack/react-query";
import { getVendorConfigBundle } from "../api/endpoints";
import { STALE_CONFIG } from "../api/queryKeys";

export function useVendorConfigBundle(enabled = true) {
  return useQuery({
    queryKey: ["vendor", "config-bundle"],
    queryFn: getVendorConfigBundle,
    staleTime: STALE_CONFIG,
    enabled,
  });
}
