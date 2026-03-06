/**
 * Direction capabilities model – answers which directions are possible for a given
 * licensee and canonical operation based on the admin allowlist.
 *
 * Uses my-allowlist.eligibleOperations (admin rules) so that admin allowlist changes
 * (including deletions) are reflected in the Add panel. eligibleOperations has
 * canCallOutbound / canReceiveInbound per operation from the admin perspective.
 *
 * Direction is operation-owned (PROVIDER_RECEIVES_ONLY | TWO_WAY):
 * - PROVIDER_RECEIVES_ONLY: canConfigureOutbound usually true (as caller), canConfigureInbound false.
 * - TWO_WAY: both can be true depending on rules.
 */

import type { MyAllowlistResponse } from "../api/endpoints";

export type DirectionCapability = {
  canConfigureOutbound: boolean;
  canConfigureInbound: boolean;
};

export type OperationDirectionMap = Record<string, DirectionCapability>;

/**
 * Build a map of operation code → direction capability from the allowlist.
 * Uses eligibleOperations (admin rules) so admin allowlist changes propagate to the UI.
 * canConfigureOutbound = canCallOutbound, canConfigureInbound = canReceiveInbound.
 * Operations not in eligibleOperations get no entry; caller treats missing as both false
 * (not addable) when allowlist is loaded.
 */
export function buildOperationDirectionMap(
  allowlist: MyAllowlistResponse
): OperationDirectionMap {
  const map: OperationDirectionMap = {};
  const eligible = allowlist.eligibleOperations ?? [];

  for (const item of eligible) {
    const op = (item.operationCode ?? "").trim().toUpperCase();
    if (!op) continue;
    map[op] = {
      canConfigureOutbound: item.canCallOutbound === true,
      canConfigureInbound: item.canReceiveInbound === true,
    };
  }

  return map;
}
