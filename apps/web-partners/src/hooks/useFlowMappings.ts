/**
 * Hook to fetch operation mappings for Visual Flow Builder.
 * Returns prettified JSON strings for request and response mappings.
 */

import { useQuery } from "@tanstack/react-query";
import {
  getOperationMappings,
  type OperationMappingsResponse,
} from "../api/endpoints";
import { STALE_CONFIG } from "../api/queryKeys";

export interface FlowMappings {
  requestJson: string;
  responseJson: string;
}

const DEFAULT_JSON = "{}";

function toPrettifiedJson(obj: Record<string, unknown> | null | undefined): string {
  if (obj == null || typeof obj !== "object") return DEFAULT_JSON;
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return DEFAULT_JSON;
  }
}

export function flowMappingsFromResponse(data: OperationMappingsResponse | undefined): FlowMappings {
  if (!data) {
    return { requestJson: DEFAULT_JSON, responseJson: DEFAULT_JSON };
  }
  const requestJson = data.request?.mapping
    ? toPrettifiedJson(data.request.mapping)
    : DEFAULT_JSON;
  const responseJson = data.response?.mapping
    ? toPrettifiedJson(data.response.mapping)
    : DEFAULT_JSON;
  return { requestJson, responseJson };
}

export function useFlowMappings(operationCode: string | undefined, canonicalVersion: string | undefined) {
  const enabled = !!operationCode && !!canonicalVersion;
  const query = useQuery({
    queryKey: ["operation-mappings", operationCode ?? "", canonicalVersion ?? ""],
    queryFn: () => getOperationMappings(operationCode!, canonicalVersion!),
    enabled,
    staleTime: STALE_CONFIG,
  });
  const flowMappings = flowMappingsFromResponse(query.data);
  return {
    ...query,
    flowMappings,
    requestMapping: query.data?.request?.mapping ?? null,
    responseMapping: query.data?.response?.mapping ?? null,
    usesCanonicalRequest: query.data?.usesCanonicalRequest ?? false,
    usesCanonicalResponse: query.data?.usesCanonicalResponse ?? false,
  };
}
