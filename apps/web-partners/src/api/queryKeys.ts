/**
 * Canonical React Query keys for vendor portal.
 * Unified shapes enable cache reuse across Home, Transactions, Metrics, etc.
 *
 * Shared keys used by Config tabs (Overview, Auth, Endpoints, Supported, Contracts, Mapping):
 * - ["vendor-contracts"], ["vendor-mappings"], ["vendor-endpoints"], ["vendor-supported-operations"]
 * - ["auth-profiles", activeVendor], ["my-allowlist", activeVendor]
 * Using STALE_CONFIG (2 min) avoids spamming requests when moving between tabs.
 */

/** Metrics overview: ["vendor-metrics-overview", from, to] */
export function vendorMetricsKey(fromStr: string, toStr: string) {
  return ["vendor-metrics-overview", fromStr, toStr] as const;
}

/** Transactions list: ["vendor-transactions", from, to, direction, operation, status, search, cursor] */
export function vendorTransactionsKey(
  fromStr: string,
  toStr: string,
  direction: "all" | "outbound" | "inbound",
  operation: string | null | undefined,
  status: string | null | undefined,
  search: string | null | undefined,
  cursor: string | null
) {
  const op = operation && String(operation).trim();
  const st = status && String(status).trim();
  const sr = search && String(search).trim();
  return [
    "vendor-transactions",
    fromStr,
    toStr,
    direction,
    op || "all",
    st || "all",
    sr || "",
    cursor,
  ] as const;
}

/** Transaction detail: ["vendor-transaction-detail", transactionId] */
export function vendorTransactionDetailKey(transactionId: string) {
  return ["vendor-transaction-detail", transactionId] as const;
}

/** Home top licensees: ["home", "top-licensees", fromStr, toStr] */
export function homeTopLicenseesKey(fromStr: string, toStr: string) {
  return ["home", "top-licensees", fromStr, toStr] as const;
}

/** Canonical contracts: ["vendor-canonical-contracts", operationCode?, canonicalVersion?] */
export function vendorCanonicalContractsKey(operationCode?: string | null, canonicalVersion?: string | null) {
  if (operationCode && canonicalVersion) {
    return ["vendor-canonical-contracts", operationCode, canonicalVersion] as const;
  }
  if (operationCode) {
    return ["vendor-canonical-contracts", operationCode] as const;
  }
  return ["vendor-canonical-contracts"] as const;
}

/** Canonical vendors list (listVendors from vendor API): ["canonical-vendors"] */
export const canonicalVendorsKey = ["canonical-vendors"] as const;

/** My Operations flow readiness: ["vendor-my-operations"] */
export const vendorMyOperationsKey = ["vendor-my-operations"] as const;

/** Operations mapping status (Contracts overview): ["operations-mapping-status"] */
export const operationsMappingStatusKey = ["operations-mapping-status"] as const;

/** Visual Flow Builder: ["vendor-flow", operationCode, canonicalVersion] */
export function vendorFlowKey(operationCode: string, canonicalVersion: string) {
  return ["vendor-flow", operationCode, canonicalVersion] as const;
}

/** staleTime constants */
export const STALE_CONFIG = 2 * 60 * 1000; // 2 min
export const STALE_TRANSACTIONS = 1 * 60 * 1000; // 1 min
export const STALE_HIGH_CHURN = 90 * 1000; // 90 s (legacy)

/**
 * Vendor-scoped query key prefixes. Used to invalidate all vendor data when
 * active licensee changes (Settings → Registration), so the portal refreshes
 * for the new licensee and no UI shows stale data from the previous one.
 */
const VENDOR_QUERY_KEY_PREFIXES = [
  "vendor-metrics-overview",
  "vendor-transactions",
  "vendor-transaction-detail",
  "vendor-canonical-contracts",
  "vendor-my-operations",
  "vendor-flow",
  "vendor-flow-skip",
  "vendor-operations-catalog",
  "vendor-supported-operations",
  "vendor-endpoints",
  "vendor-contracts",
  "vendor-mappings",
  "vendor-canonical-operations",
  "canonical-vendors",
  "operations-mapping-status",
  "operation-mappings",
  "auth-profiles",
  "my-allowlist",
  "home",
  "vendor",
] as const;

function isVendorScopedQuery(queryKey: unknown): boolean {
  if (!Array.isArray(queryKey) || queryKey.length === 0) return false;
  const first = String(queryKey[0]);
  return VENDOR_QUERY_KEY_PREFIXES.some(
    (p) => first === p || first.startsWith(p + "-")
  );
}

/**
 * Invalidates all vendor-scoped queries so the portal refreshes for the
 * newly selected licensee. Call this whenever setActiveVendorCode() is used.
 */
export function invalidateVendorQueries(
  queryClient: import("@tanstack/react-query").QueryClient
): void {
  queryClient.invalidateQueries({
    predicate: (query) => isVendorScopedQuery(query.queryKey),
  });
}
