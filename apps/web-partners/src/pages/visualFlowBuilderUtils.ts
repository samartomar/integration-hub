/**
 * Helpers for Visual Flow Builder – flow stage model and status derivation.
 */

import { getUsingCanonicalFormatLabel } from "../utils/readinessModel";

/** Mapping JSON shape: target field → JSONPath. Same format as legacy Contracts/Mapping modal. */
export type VisualMappingJson = Record<string, unknown>;

export type FlowStageId =
  | "canonical-request"
  | "request-mapping"
  | "vendor-request"
  | "endpoint"
  | "vendor-response"
  | "response-mapping"
  | "canonical-response";

export type FlowStageStatus = "ok" | "warning" | "missing";

export interface FlowStage {
  id: FlowStageId;
  label: string;
  subtitle?: string;
  status: FlowStageStatus;
}

export type MappingStatusDetail =
  | "ok"
  | "warning_optional_missing"
  | "error_required_missing";

export interface BuildFlowStagesContext {
  canonicalRequestHasSchema: boolean;
  canonicalResponseHasSchema: boolean;
  vendorRequestHasSchema: boolean;
  vendorResponseHasSchema: boolean;
  hasRequestMapping: boolean;
  hasResponseMapping: boolean;
  requestMappingStatus?: MappingStatusDetail;
  responseMappingStatus?: MappingStatusDetail;
  /** When true, request-mapping chip shows "Using canonical format". */
  useCanonicalRequestFormat?: boolean;
  /** When true, response-mapping chip shows "Canonical Response" (green) - explicit passthrough. */
  useCanonicalResponseFormat?: boolean;
  hasEndpoint: boolean;
  /** When true and hasEndpoint, endpoint stage shows "ok". When false and hasEndpoint, shows "warning" (partial). */
  endpointVerified?: boolean;
}

function mappingDetailToStageStatus(s: MappingStatusDetail | undefined): FlowStageStatus {
  if (!s || s === "ok") return "ok";
  if (s === "warning_optional_missing") return "warning";
  return "missing";
}

export function buildFlowStages(ctx: BuildFlowStagesContext): FlowStage[] {
  const s = (id: FlowStageId, label: string, hasData: boolean): FlowStage => ({
    id,
    label,
    status: hasData ? "ok" : "missing",
  });
  const sMapping = (
    id: FlowStageId,
    label: string,
    mappingStatus: MappingStatusDetail | undefined
  ): FlowStage => ({
    id,
    label,
    status: mappingDetailToStageStatus(mappingStatus),
  });

  const requestUseCanonicalFormat =
    ctx.useCanonicalRequestFormat === true ||
    ctx.requestMappingStatus === "warning_optional_missing" ||
    (ctx.requestMappingStatus === undefined && !ctx.hasRequestMapping && ctx.canonicalRequestHasSchema);

  const requestMappingStage =
    ctx.requestMappingStatus !== undefined && requestUseCanonicalFormat
      ? { id: "request-mapping" as FlowStageId, label: "Request Mapping", subtitle: getUsingCanonicalFormatLabel(), status: "ok" as FlowStageStatus }
      : ctx.requestMappingStatus !== undefined
        ? sMapping("request-mapping", "Request Mapping", ctx.requestMappingStatus)
        : s("request-mapping", "Request Mapping", ctx.hasRequestMapping);

  const responseUseCanonicalFormat =
    ctx.useCanonicalResponseFormat === true ||
    ctx.responseMappingStatus === "warning_optional_missing" ||
    (ctx.responseMappingStatus === undefined && !ctx.hasResponseMapping && ctx.canonicalResponseHasSchema);

  const responseMappingStage =
    ctx.responseMappingStatus !== undefined && responseUseCanonicalFormat
      ? { id: "response-mapping" as FlowStageId, label: "Response Mapping", subtitle: getUsingCanonicalFormatLabel(), status: "ok" as FlowStageStatus }
      : ctx.responseMappingStatus !== undefined
        ? sMapping("response-mapping", "Response Mapping", ctx.responseMappingStatus)
        : s("response-mapping", "Response Mapping", ctx.hasResponseMapping);

  const endpointStatus: FlowStageStatus =
    !ctx.hasEndpoint ? "missing" : ctx.endpointVerified !== false ? "ok" : "warning";

  return [
    s("canonical-request", "Canonical Request", ctx.canonicalRequestHasSchema),
    requestMappingStage,
    s("vendor-request", "Vendor Request", ctx.vendorRequestHasSchema),
    { id: "endpoint" as FlowStageId, label: "Endpoint", status: endpointStatus },
    s("vendor-response", "Vendor Response", ctx.vendorResponseHasSchema),
    responseMappingStage,
    s("canonical-response", "Canonical Response", ctx.canonicalResponseHasSchema),
  ];
}
