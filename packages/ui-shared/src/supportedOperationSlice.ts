/**
 * Supported canonical operation slice – explicit product cutover scope.
 *
 * Mirrors backend shared/supported_operation_slice.py. Drives UI/product routing.
 * Supported slice: GET_VERIFY_MEMBER_ELIGIBILITY, GET_MEMBER_ACCUMULATORS, LH001→LH002.
 */

export const SUPPORTED_OPERATIONS = [
  "GET_VERIFY_MEMBER_ELIGIBILITY",
  "GET_MEMBER_ACCUMULATORS",
] as const;

export const SUPPORTED_SOURCE_VENDOR = "LH001";
export const SUPPORTED_TARGET_VENDOR = "LH002";

export type SupportedOperationCode = (typeof SUPPORTED_OPERATIONS)[number];

export function isSupportedCanonicalSlice(
  operationCode: string,
  sourceVendor?: string | null,
  targetVendor?: string | null
): boolean {
  const op = (operationCode || "").trim().toUpperCase();
  if (!SUPPORTED_OPERATIONS.includes(op as SupportedOperationCode)) {
    return false;
  }
  if (sourceVendor == null && targetVendor == null) {
    return true;
  }
  const src = (sourceVendor || "").trim().toUpperCase();
  const tgt = (targetVendor || "").trim().toUpperCase();
  return src === SUPPORTED_SOURCE_VENDOR && tgt === SUPPORTED_TARGET_VENDOR;
}

export function listSupportedCanonicalOperations(): readonly string[] {
  return SUPPORTED_OPERATIONS;
}
