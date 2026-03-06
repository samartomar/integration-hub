/**
 * Centralized flow readiness helpers for Contracts & Mapping table and Visual Flow Builder.
 * Both consume backend status (getOperationsMappingStatus / getFlow) and use these utils
 * for consistent pill display.
 */

import type { OperationMappingStatusItem } from "../api/endpoints";
import type { FlowData } from "../api/flows";
import { toChipStatus } from "../components/MappingStatusChip";
import type { MappingStatusChipStatus } from "../components/MappingStatusChip";

export type FlowReadinessStatus = {
  request: MappingStatusChipStatus;
  response: MappingStatusChipStatus;
};

/**
 * Derives chip-ready status from OperationMappingStatusItem (Contracts table)
 * or FlowData (Visual Flow Builder Operation info panel).
 */
export function computeFlowReadiness(
  item: OperationMappingStatusItem | FlowData | null | undefined
): FlowReadinessStatus {
  if (!item) {
    return { request: "not_configured", response: "not_configured" };
  }
  const req = "requestMappingStatus" in item ? item.requestMappingStatus : undefined;
  const resp = "responseMappingStatus" in item ? item.responseMappingStatus : undefined;
  return {
    request: toChipStatus(req),
    response: toChipStatus(resp),
  };
}

/** Stage query param values for deep-linking to a specific Flow Builder step. */
export type FlowBuilderStageParam =
  | "contract"        // canonical-request / Operation info
  | "request-mapping"
  | "endpoint";

export const STAGE_PARAM = "stage";

/**
 * Returns the Visual Flow Builder path for an operation/version.
 * Used for row click and "Open flow" navigation.
 */
export function getFlowBuilderPath(operationCode: string, version: string): string {
  return `/builder/${encodeURIComponent(operationCode)}/${encodeURIComponent(version)}`;
}

/** Parse ?stage= from URL. Returns undefined if not set or invalid. */
export function parseFlowBuilderStage(search: string): FlowBuilderStageParam | undefined {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const s = params.get(STAGE_PARAM)?.toLowerCase();
  if (s === "contract" || s === "request-mapping" || s === "endpoint") return s;
  return undefined;
}

/** Map stage param to FlowStageId for Contract/Operation info. */
export function flowBuilderStageToFlowStageId(
  stage: FlowBuilderStageParam
): "canonical-request" | "request-mapping" | "endpoint" {
  if (stage === "contract") return "canonical-request";
  if (stage === "request-mapping") return "request-mapping";
  return "endpoint";
}

/**
 * Format version for display (breadcrumbs, headers, chips).
 * Ensures a single "v" prefix – e.g. "v1" stays "v1", "1" becomes "v1", "vv1" becomes "v1".
 */
export function formatVersionLabel(version: string | undefined | null): string {
  const v = (version ?? "v1").trim();
  if (!v) return "v1";
  const withoutV = v.replace(/^v+/i, "");
  return withoutV ? `v${withoutV}` : "v1";
}
