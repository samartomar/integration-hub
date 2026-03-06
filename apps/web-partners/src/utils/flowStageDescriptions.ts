/**
 * Centralized tooltip copy for Visual Flow Builder pipeline stages.
 * Single source of truth so all pills show consistent descriptions.
 */

export type FlowStageId =
  | "canonical-request"
  | "request-mapping"
  | "vendor-request"
  | "endpoint"
  | "vendor-response"
  | "response-mapping"
  | "canonical-response";

export type FlowStageStatus = "ok" | "warning" | "missing";

/** Tooltip for a pipeline stage, optionally vary by status when relevant. */
export function getStageTooltip(
  stageId: FlowStageId,
  status?: FlowStageStatus
): string {
  if (stageId === "request-mapping") {
    return (
      {
        ok: "Transforms canonical request into vendor endpoint request payload.",
        warning: "Using identity mapping (canonical → vendor request).",
        missing: "Mapping required before this operation can be called.",
      }[status ?? "ok"] ?? "How the canonical request is transformed to your vendor request."
    );
  }
  if (stageId === "response-mapping") {
    return (
      {
        ok: "Transforms vendor response into canonical response format.",
        warning: "Using identity mapping (vendor → canonical response).",
        missing: "Mapping required before this operation can be used.",
      }[status ?? "ok"] ?? "How the vendor response is transformed to canonical format."
    );
  }
  const descriptions: Record<FlowStageId, string> = {
    "canonical-request":
      "Canonical request payload shape for this operation.",
    "vendor-request": "Payload sent to your endpoint.",
    endpoint: "The URL and auth profile used when the platform calls your API.",
    "vendor-response": "Raw response from your API (before mapping).",
    "canonical-response":
      "Normalized response returned back to callers.",
    "request-mapping": "How the canonical request is transformed to your vendor request.",
    "response-mapping": "How the vendor response is transformed to canonical format.",
  };
  return descriptions[stageId] ?? "";
}
