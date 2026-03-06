import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getActiveVendorCode } from "frontend-shared";
import { getMyAllowlist } from "../api/endpoints";
import { STALE_CONFIG } from "../api/queryKeys";
import { buildOperationDirectionMap, type OperationDirectionMap } from "../utils/directionCapabilities";

/**
 * Exposes direction capabilities per operation from the vendor allowlist.
 * Reuses the same my-allowlist query as elsewhere; compatible with existing invalidateVendorQueries.
 */
export function useOperationDirectionCapabilities() {
  const activeVendor = getActiveVendorCode();
  const hasKey = !!activeVendor;

  const { data: allowlist, ...rest } = useQuery({
    queryKey: ["my-allowlist", activeVendor ?? ""],
    queryFn: getMyAllowlist,
    enabled: !!activeVendor && hasKey,
    retry: false,
    staleTime: STALE_CONFIG,
  });

  const directionMap: OperationDirectionMap = useMemo(
    () => (allowlist ? buildOperationDirectionMap(allowlist) : {}),
    [allowlist]
  );

  return { directionMap, ...rest };
}
