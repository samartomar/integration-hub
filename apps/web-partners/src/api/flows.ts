/**
 * Flow Builder API client - wraps Vendor API endpoints for Visual Flow Builder.
 */

import { vendorApi } from "./client";

export type VisualFieldNodeKind =
  | "canonicalRequest"
  | "canonicalResponse"
  | "vendorRequest"
  | "vendorResponse";

export interface VisualFieldNode {
  id: string;
  kind: VisualFieldNodeKind;
  path: string;
  label: string;
}

export interface VisualMappingEdge {
  id: string;
  fromNodeId: string;
  toNodeId: string;
  transform?: string;
}

export interface VisualModel {
  nodes: VisualFieldNode[];
  edges: VisualMappingEdge[];
}

export type MappingStatusDetail =
  | "ok"
  | "warning_optional_missing"
  | "error_required_missing";

export type MappingMode = "CANONICAL" | "CUSTOM_CONFIGURED" | "CUSTOM_MISSING";

export interface FlowData {
  operationCode: string;
  version: string;
  canonicalVersion?: string;
  flowDirection?: string;
  canonicalRequestSchema: Record<string, unknown>;
  canonicalResponseSchema: Record<string, unknown>;
  vendorRequestSchema?: Record<string, unknown>;
  vendorResponseSchema?: Record<string, unknown>;
  visualModel: VisualModel | null;
  requestMapping: Record<string, unknown> | null;
  responseMapping: Record<string, unknown> | null;
  usesCanonicalRequest?: boolean;
  usesCanonicalResponse?: boolean;
  requiresRequestMapping?: boolean;
  requiresResponseMapping?: boolean;
  requestMappingStatus?: MappingStatusDetail;
  responseMappingStatus?: MappingStatusDetail;
  requestMappingMode?: MappingMode;
  responseMappingMode?: MappingMode;
  endpoint: {
    url: string;
    httpMethod: string;
    timeoutMs: number;
    verificationStatus?: string;
  };
}

export interface FlowTestResult {
  canonicalRequest: Record<string, unknown>;
  vendorRequest: Record<string, unknown>;
  vendorResponse: Record<string, unknown>;
  canonicalResponse: Record<string, unknown>;
  errors?: {
    mappingRequest: string[];
    downstream: string[];
    mappingResponse: string[];
  };
  /** Effective contract source: "vendor" | "canonical" */
  contractSource?: string;
  /** Effective request mapping: "vendor_mapping" | "canonical_pass_through" */
  mappingRequestSource?: string;
  /** Effective response mapping: "vendor_mapping" | "canonical_pass_through" */
  mappingResponseSource?: string;
}

export async function getFlow(
  operationCode: string,
  version: string
): Promise<FlowData> {
  const { data } = await vendorApi.get<FlowData>(
    `/v1/vendor/flows/${encodeURIComponent(operationCode)}/${encodeURIComponent(version)}`
  );
  return data;
}

export interface SaveFlowPayload {
  visualModel?: VisualModel;
  requestMapping?: Record<string, unknown>;
  responseMapping?: Record<string, unknown>;
  useCanonicalRequest?: boolean;
  useCanonicalResponse?: boolean;
}

export async function saveFlow(
  operationCode: string,
  version: string,
  payload: SaveFlowPayload
): Promise<FlowData> {
  const { data } = await vendorApi.put<FlowData>(
    `/v1/vendor/flows/${encodeURIComponent(operationCode)}/${encodeURIComponent(version)}`,
    payload
  );
  return data;
}

export async function testFlow(
  operationCode: string,
  version: string,
  payload: {
    canonicalRequest: Record<string, unknown>;
    visualModel?: VisualModel | null;
    requestMapping?: Record<string, unknown> | null;
    responseMapping?: Record<string, unknown> | null;
    flowDirection?: "OUTBOUND" | "INBOUND";
  }
): Promise<FlowTestResult> {
  const { data } = await vendorApi.post<FlowTestResult>(
    `/v1/vendor/flows/${encodeURIComponent(operationCode)}/${encodeURIComponent(version)}/test`,
    payload
  );
  return data;
}
