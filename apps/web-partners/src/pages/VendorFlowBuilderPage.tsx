import { useState, useMemo, useEffect, useRef } from "react";
import { Link, useParams, useNavigate, useLocation } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getVendorOperationsCatalog,
  getVendorSupportedOperations,
  getVendorContracts,
  getVendorEndpoints,
  getVendorMappings,
  getMyAllowlist,
  putOperationMappings,
} from "../api/endpoints";
import { getFlow, testFlow } from "../api/flows";
import { vendorFlowKey, operationsMappingStatusKey, STALE_CONFIG } from "../api/queryKeys";
import { useFlowMappings } from "../hooks/useFlowMappings";
import { getActiveVendorCode } from "frontend-shared";
import { OpenSettingsLink } from "../components/OpenSettingsLink";
import {
  buildFlowStages,
  type FlowStageId,
  type FlowStage,
} from "./visualFlowBuilderUtils";
import { MappingStatusChip } from "../components/MappingStatusChip";
import { FlowReadinessPill } from "../components/FlowReadinessPill";
import { StatusPill } from "frontend-shared";
import { computeFlowReadiness } from "../utils/flowReadiness";
import {
  buildReadinessRowsForLicensee,
  canRunTest,
  getContractStatusDisplay,
  getEndpointStatusDisplay,
} from "../utils/readinessModel";
import {
  getIdentityMappingTemplate,
  mappingEqualsTemplate,
  templateToPrettifiedJson,
} from "../utils/identityMappingTemplate";
import { generateMockPayloadFromSchema } from "../utils/generateMockPayload";
import {
  parseFilterParamsFromSearch,
  buildContractsPathWithFilters,
  getDirectionFromSearch,
} from "../utils/supportedOperationsFilters";
import {
  parseFlowBuilderStage,
  flowBuilderStageToFlowStageId,
  formatVersionLabel,
} from "../utils/flowReadiness";
import { getDirectionLabelWithPolicy, getDirectionCellTooltip } from "../utils/vendorDirectionLabels";
import { getStageTooltip } from "../utils/flowStageDescriptions";
import { EndpointSummaryPanel } from "../components/EndpointSummaryPanel";
import { FlowBuilderSkeleton } from "../components/vendor/skeleton";
import { VendorPageLayout } from "../components/layout/VendorPageLayout";
import { useVendorConfigBundle } from "../hooks/useVendorConfigBundle";

type PanelTab = "fields" | "mappings" | "test";

/**
 * Mapping between Visual Builder stages and Vendor API directions.
 * Uses putOperationMappings (same underlying storage as legacy Contracts/Mapping screen).
 *
 * request-mapping   -> CANONICAL_TO_TARGET_REQUEST (canonical → vendor request)
 * response-mapping -> TARGET_TO_CANONICAL_RESPONSE (vendor → canonical response)
 *
 * Backend stores as FROM_CANONICAL and TO_CANONICAL_RESPONSE internally.
 */

function schemaFieldList(schema: Record<string, unknown>): string[] {
  const props = (schema?.properties as Record<string, unknown>) ?? {};
  return Object.keys(props);
}

function schemaExists(s: unknown): boolean {
  return s != null && typeof s === "object" && !Array.isArray(s);
}

function parseMappingJson(
  value: string
): { ok: true; data: Record<string, unknown> } | { ok: false; error: string } {
  const trimmed = value.trim();
  if (!trimmed) return { ok: true, data: {} };
  try {
    const parsed = JSON.parse(trimmed) as unknown;
    if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
      return { ok: true, data: parsed as Record<string, unknown> };
    }
    return { ok: false, error: "Must be a JSON object" };
  } catch (e) {
    return { ok: false, error: (e as Error).message ?? "Invalid JSON" };
  }
}

function requestBadgeTooltip(status: string | undefined): string {
  if (status === "ok") return "Request mapping is configured for this operation.";
  if (status === "warning_optional_missing")
    return "Canonical request is used directly. No mapping required unless you need transformations.";
  if (status === "error_required_missing")
    return "Request mapping is required before this operation can be used.";
  return "Request mapping status.";
}

function responseBadgeTooltip(status: string | undefined): string {
  if (status === "ok") return "Response mapping is configured for this operation.";
  if (status === "warning_optional_missing")
    return "Canonical response is used directly. Add mapping only if you need to transform the vendor response.";
  if (status === "error_required_missing")
    return "Response mapping is required before this operation can be used.";
  return "Response mapping status.";
}


export function VendorFlowBuilderPage() {
  const { operationCode: routeOp, canonicalVersion: routeVer } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [panelTab, setPanelTab] = useState<PanelTab>("fields");
  const [activeStageId, setActiveStageId] = useState<FlowStageId>("canonical-request");
  const [testInput, setTestInput] = useState("{}");
  const requestMappingRef = useRef<HTMLTextAreaElement | null>(null);
  const responseMappingRef = useRef<HTMLTextAreaElement | null>(null);
  const [testJsonError, setTestJsonError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [dirty, setDirty] = useState(false);
  const [useCanonicalResponseFormat, setUseCanonicalResponseFormat] = useState(false);
  const [useCanonicalRequestFormat, setUseCanonicalRequestFormat] = useState(false);
  const [requestJson, setRequestJson] = useState("{}");
  const [responseJson, setResponseJson] = useState("{}");
  const [requestError, setRequestError] = useState<string | null>(null);
  const [responseError, setResponseError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{
    canonicalRequest?: Record<string, unknown>;
    vendorRequest?: Record<string, unknown>;
    vendorResponse?: Record<string, unknown>;
    canonicalResponse?: Record<string, unknown>;
    contractSource?: string;
    mappingRequestSource?: string;
    mappingResponseSource?: string;
    errors?: { mappingRequest: string[]; downstream: string[]; mappingResponse: string[] };
  } | null>(null);

  const activeVendor = getActiveVendorCode();
  const hasKey = !!activeVendor;

  const operationCode = (routeOp ?? "").trim().toUpperCase() || undefined;
  const version = (routeVer ?? "v1").trim() || "v1";

  const { data: bundleData, isError: bundleError } = useVendorConfigBundle(!!hasKey);
  const useIndividualConfig = hasKey && (bundleError || !bundleData);

  const { data: catalogData } = useQuery({
    queryKey: ["vendor-operations-catalog"],
    queryFn: () => getVendorOperationsCatalog(),
    enabled: useIndividualConfig,
    staleTime: STALE_CONFIG,
  });
  const { data: supportedData } = useQuery({
    queryKey: ["vendor-supported-operations"],
    queryFn: () => getVendorSupportedOperations(),
    enabled: useIndividualConfig,
    staleTime: STALE_CONFIG,
  });
  const { data: allowlistData } = useQuery({
    queryKey: ["my-allowlist", activeVendor ?? ""],
    queryFn: getMyAllowlist,
    enabled: !!activeVendor && useIndividualConfig && !!operationCode,
    staleTime: STALE_CONFIG,
  });
  const { data: vendorContractsData } = useQuery({
    queryKey: ["vendor-contracts"],
    queryFn: () => getVendorContracts(),
    enabled: useIndividualConfig && !!operationCode,
    staleTime: STALE_CONFIG,
  });
  const { data: endpointsData } = useQuery({
    queryKey: ["vendor-endpoints"],
    queryFn: getVendorEndpoints,
    enabled: useIndividualConfig && !!operationCode,
    staleTime: STALE_CONFIG,
  });
  const { data: readinessMappingsData } = useQuery({
    queryKey: ["vendor-mappings"],
    queryFn: () => getVendorMappings(),
    enabled: useIndividualConfig && !!operationCode,
    staleTime: STALE_CONFIG,
  });

  const catalog = bundleData?.operationsCatalog ?? catalogData?.items ?? [];
  const supported = bundleData?.supportedOperations ?? supportedData?.items ?? [];
  const vendorContracts = bundleData?.contracts ?? vendorContractsData?.items ?? [];
  const endpoints = bundleData?.endpoints ?? endpointsData?.items ?? [];
  const mappings = bundleData?.mappings ?? readinessMappingsData?.mappings ?? [];

  const { data: flowData, isLoading, error, refetch } = useQuery({
    queryKey: operationCode && version ? vendorFlowKey(operationCode, version) : ["vendor-flow-skip"],
    queryFn: () => getFlow(operationCode!, version),
    enabled: !!operationCode && !!version && hasKey,
    staleTime: STALE_CONFIG,
  });

  const { data: mappingsData, flowMappings: initialFlowMappings } =
    useFlowMappings(operationCode, version);

  // Identity template: UI convenience when requiresMapping=false and no saved mapping.
  // We show it so users see what pass-through looks like; we do NOT persist it.
  const identityTemplates = useMemo(() => {
    if (!operationCode || !flowData) return { request: {}, response: {} };
    return getIdentityMappingTemplate(
      operationCode,
      (flowData.canonicalRequestSchema ?? {}) as Record<string, unknown>,
      (flowData.vendorRequestSchema ?? flowData.canonicalRequestSchema ?? {}) as Record<string, unknown>,
      (flowData.canonicalResponseSchema ?? {}) as Record<string, unknown>,
      (flowData.vendorResponseSchema ?? flowData.canonicalResponseSchema ?? {}) as Record<string, unknown>
    );
  }, [operationCode, flowData]);

  useEffect(() => {
    setRequestJson("{}");
    setResponseJson("{}");
    setTestInput("{}");
    setTestResult(null);
    setDirty(false);
    setUseCanonicalResponseFormat(false);
    setUseCanonicalRequestFormat(false);
    setRequestError(null);
    setResponseError(null);
    setTestJsonError(null);
  }, [operationCode, version]);

  // Auto-populate Test tab with mock payload from canonical schema when user hasn't entered anything yet.
  useEffect(() => {
    if (
      flowData?.canonicalRequestSchema &&
      typeof flowData.canonicalRequestSchema === "object" &&
      testInput.trim() === "{}" &&
      testResult === null &&
      Object.keys((flowData.canonicalRequestSchema as Record<string, unknown>)?.properties ?? {}).length > 0
    ) {
      const mock = generateMockPayloadFromSchema(
        flowData.canonicalRequestSchema as Record<string, unknown>
      );
      setTestInput(JSON.stringify(mock, null, 2));
    }
  }, [flowData?.canonicalRequestSchema, testInput, testResult]);

  useEffect(() => {
    const matches =
      mappingsData &&
      mappingsData.operationCode === operationCode &&
      mappingsData.canonicalVersion === version &&
      !dirty;
    if (matches && flowData) {
      const hasReqMapping =
        mappingsData.request?.mapping &&
        typeof mappingsData.request.mapping === "object" &&
        Object.keys(mappingsData.request.mapping).length > 0;
      const hasRespMapping =
        mappingsData.response?.mapping &&
        typeof mappingsData.response.mapping === "object" &&
        Object.keys(mappingsData.response.mapping).length > 0;
      const hasResponseRow = mappingsData.response != null;
      const canPassThrough = schemaFieldList(flowData?.canonicalResponseSchema ?? {}).length > 0;
      const respUseCanonical =
        mappingsData?.usesCanonicalResponse !== undefined
          ? mappingsData.usesCanonicalResponse
          : canPassThrough &&
            !hasRespMapping &&
            (flowData?.responseMappingStatus === "warning_optional_missing" ||
              (flowData?.responseMappingStatus === undefined &&
                flowData?.requiresResponseMapping === false));
      setUseCanonicalResponseFormat(hasRespMapping ? false : respUseCanonical);

      const canPassThroughRequest = schemaFieldList(flowData?.canonicalRequestSchema ?? {}).length > 0;
      const reqUseCanonical =
        mappingsData?.usesCanonicalRequest !== undefined
          ? mappingsData.usesCanonicalRequest
          : canPassThroughRequest &&
            !hasReqMapping &&
            (flowData?.requestMappingStatus === "warning_optional_missing" ||
              (flowData?.requestMappingStatus === undefined &&
                flowData?.requiresRequestMapping === false));
      setUseCanonicalRequestFormat(hasReqMapping ? false : reqUseCanonical);

      const reqDisplay =
        hasReqMapping
          ? initialFlowMappings.requestJson
          : reqUseCanonical
            ? templateToPrettifiedJson(identityTemplates.request)
            : "{}";
      const respDisplay = hasRespMapping
        ? initialFlowMappings.responseJson
        : (canPassThrough || flowData?.requiresResponseMapping === false) && !hasResponseRow
          ? templateToPrettifiedJson(identityTemplates.response)
          : "{}";
      setRequestJson(reqDisplay);
      setResponseJson(respDisplay);
      setRequestError(null);
      setResponseError(null);
    }
  }, [
    mappingsData,
    operationCode,
    version,
    initialFlowMappings.requestJson,
    initialFlowMappings.responseJson,
    dirty,
    flowData,
    identityTemplates,
  ]);

  const derivedMappings = useMemo(() => {
    const req = parseMappingJson(requestJson);
    const resp = parseMappingJson(responseJson);
    return {
      requestMapping: useCanonicalRequestFormat ? null : (req.ok ? req.data : {}),
      responseMapping: useCanonicalResponseFormat ? null : (resp.ok ? resp.data : {}),
      responseValid: useCanonicalResponseFormat || resp.ok,
      requestValid: useCanonicalRequestFormat || req.ok,
    };
  }, [requestJson, responseJson, useCanonicalResponseFormat, useCanonicalRequestFormat]);

  const [pendingChangeRequestId, setPendingChangeRequestId] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const saveMutation = useMutation({
    mutationFn: (payload: {
      requestMapping: Record<string, unknown>;
      responseMapping: Record<string, unknown> | null;
      useCanonicalRequest: boolean;
      useCanonicalResponse: boolean;
    }) =>
      putOperationMappings(operationCode!, version, {
        useCanonicalRequest: payload.useCanonicalRequest,
        useCanonicalResponse: payload.useCanonicalResponse,
        request: {
          direction: "CANONICAL_TO_TARGET_REQUEST",
          mapping: payload.requestMapping,
          usesCanonical: payload.useCanonicalRequest,
        },
        response: {
          direction: "TARGET_TO_CANONICAL_RESPONSE",
          mapping: payload.responseMapping,
          usesCanonical: payload.useCanonicalResponse,
        },
      }),
    onSuccess: (data) => {
      setDirty(false);
      if (data && "changeRequestId" in data) {
        setPendingChangeRequestId(data.changeRequestId);
        setSaveMessage({
          type: "success",
          text: `Your change has been submitted for admin approval (Request ID: ${data.changeRequestId}). It will take effect after approval.`,
        });
      } else {
        setPendingChangeRequestId(null);
        setSaveMessage({ type: "success", text: "Mappings saved. Changes apply to live traffic." });
      }
      if (operationCode && version) {
        queryClient.invalidateQueries({ queryKey: ["operation-mappings", operationCode, version] });
        queryClient.invalidateQueries({ queryKey: vendorFlowKey(operationCode, version) });
        queryClient.invalidateQueries({ queryKey: operationsMappingStatusKey });
        queryClient.invalidateQueries({ queryKey: ["vendor-contracts"] });
        queryClient.invalidateQueries({ queryKey: ["vendor-mappings"] });
        queryClient.invalidateQueries({ queryKey: ["vendor", "config-bundle"] });
      }
      setTimeout(() => setSaveMessage(null), 5000);
    },
    onError: (err) => {
      setSaveMessage({
        type: "error",
        text: (err as Error).message ?? "Failed to save",
      });
    },
  });

  const testMutation = useMutation({
    mutationFn: async () => {
      const parsed = JSON.parse(testInput) as Record<string, unknown>;
      return testFlow(operationCode!, version, {
        canonicalRequest: parsed,
        requestMapping: derivedMappings.requestMapping,
        responseMapping: derivedMappings.responseMapping,
        flowDirection: directionFromUrl === "inbound" ? "INBOUND" : "OUTBOUND",
      });
    },
    onSuccess: (data) => {
      setTestResult(data);
      setTestJsonError(null);
    },
    onError: (err) => {
      setTestResult(null);
      setTestJsonError((err as Error).message ?? "Test failed");
    },
  });

  const handleRequestJsonChange = (value: string) => {
    if (useCanonicalRequestFormat) {
      const identStr = templateToPrettifiedJson(identityTemplates.request);
      if (value.trim() !== identStr.trim()) {
        setUseCanonicalRequestFormat(false);
      }
    }
    setRequestJson(value);
    setDirty(true);
    setSaveMessage(null);
    const result = parseMappingJson(value);
    setRequestError(result.ok ? null : result.error);
  };

  const handleResponseJsonChange = (value: string) => {
    setResponseJson(value);
    setDirty(true);
    setSaveMessage(null);
    const result = parseMappingJson(value);
    setResponseError(result.ok ? null : result.error);
  };

  const hasDirtyMappings = dirty;
  const saveDisabled =
    !hasDirtyMappings ||
    saveMutation.isPending ||
    (!useCanonicalRequestFormat && !derivedMappings.requestValid) ||
    (!useCanonicalResponseFormat && !derivedMappings.responseValid);

  const handleSave = () => {
    const req = parseMappingJson(requestJson);
    if (!req.ok && !useCanonicalRequestFormat) {
      setRequestError(req.error);
      setPanelTab("mappings");
      setActiveStageId("request-mapping");
      setSaveMessage({ type: "error", text: `Request mapping: ${req.error}` });
      return;
    }
    if (useCanonicalResponseFormat) {
      setRequestError(null);
      setResponseError(null);
      setSaveMessage(null);
      const reqToSave =
        useCanonicalRequestFormat
          ? {}
          : req.ok
            ? flowData?.requiresRequestMapping === false &&
                mappingEqualsTemplate(req.data as Record<string, string>, identityTemplates.request)
              ? {}
              : (req.data as Record<string, unknown>)
            : {};
      saveMutation.mutate({
        requestMapping: reqToSave,
        responseMapping: null,
        useCanonicalRequest: useCanonicalRequestFormat,
        useCanonicalResponse: true,
      });
      return;
    }
    const resp = parseMappingJson(responseJson);
    if (!resp.ok) {
      setResponseError(resp.error);
      setPanelTab("mappings");
      setActiveStageId("response-mapping");
      setSaveMessage({ type: "error", text: `Response mapping: ${resp.error}` });
      return;
    }
    setRequestError(null);
    setResponseError(null);
    setSaveMessage(null);
    const reqToSave =
      useCanonicalRequestFormat
        ? {}
        : req.ok
          ? flowData?.requiresRequestMapping === false &&
              mappingEqualsTemplate(req.data as Record<string, string>, identityTemplates.request)
            ? {}
            : (req.data as Record<string, unknown>)
          : {};
    const respToSave =
      flowData?.requiresResponseMapping === false &&
      mappingEqualsTemplate(resp.data as Record<string, string>, identityTemplates.response)
        ? {}
        : (resp.data as Record<string, unknown>);
    saveMutation.mutate({
      requestMapping: reqToSave,
      responseMapping: respToSave,
      useCanonicalRequest: useCanonicalRequestFormat,
      useCanonicalResponse: useCanonicalResponseFormat,
    });
  };

  const handleRunTest = () => {
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(testInput) as Record<string, unknown>;
    } catch {
      setTestJsonError("Invalid JSON");
      return;
    }
    if (!parsed || typeof parsed !== "object") {
      setTestJsonError("Canonical request must be a JSON object");
      return;
    }
    testMutation.mutate();
  };

  const directionFromUrl = getDirectionFromSearch(location.search);

  const readinessRowForOp = useMemo(() => {
    if (!operationCode || !activeVendor) return null;
    const rows = buildReadinessRowsForLicensee({
      supported,
      catalog,
      vendorContracts,
      endpoints,
      mappings,
      outboundAllowlist: (bundleData?.myAllowlist ?? allowlistData)?.outbound ?? [],
      inboundAllowlist: (bundleData?.myAllowlist ?? allowlistData)?.inbound ?? [],
      eligibleOperations: (bundleData?.myAllowlist ?? allowlistData)?.eligibleOperations,
      accessOutcomes: (bundleData?.myAllowlist ?? allowlistData)?.accessOutcomes,
      vendorCode: activeVendor,
    });
    const match =
      directionFromUrl === "outbound"
        ? rows.find((r) => r.operationCode === operationCode && r.direction === "Outbound")
        : directionFromUrl === "inbound"
          ? rows.find((r) => r.operationCode === operationCode && r.direction === "Inbound")
          : rows.find((r) => r.operationCode === operationCode);
    return match ?? null;
  }, [
    operationCode,
    activeVendor,
    supported,
    catalog,
    vendorContracts,
    endpoints,
    mappings,
    allowlistData,
    directionFromUrl,
  ]);

  const availableOps = catalog.filter((c) =>
    supported.some((s) => (s.operationCode ?? "").toUpperCase() === (c.operationCode ?? "").toUpperCase())
  );

  const handleSelectOperation = (op: string, ver: string) => {
    navigate(`/builder/${encodeURIComponent(op)}/${encodeURIComponent(ver)}${location.search}`);
  };

  const canonicalReqFieldsList = schemaFieldList(flowData?.canonicalRequestSchema ?? {});
  const vendorReqFieldsList = schemaFieldList(flowData?.vendorRequestSchema ?? flowData?.canonicalRequestSchema ?? {});
  const canonicalRespFieldsList = schemaFieldList(flowData?.canonicalResponseSchema ?? {});
  const vendorRespFieldsList = schemaFieldList(flowData?.vendorResponseSchema ?? flowData?.canonicalResponseSchema ?? {});

  /** True when the operation has a canonical response schema (fields). Enables pass-through checkbox regardless of requiresResponseMapping. */
  const canUseCanonicalResponse = canonicalRespFieldsList.length > 0;
  /** True when the operation has a canonical request schema (fields). Enables request pass-through checkbox. */
  const canUseCanonicalRequest = canonicalReqFieldsList.length > 0;

  const flowStages = useMemo((): FlowStage[] => {
    const mappingHasKeys = (m: Record<string, unknown> | null | undefined) =>
      !!m && typeof m === "object" && Object.keys(m).length > 0;
    return buildFlowStages({
      canonicalRequestHasSchema: schemaExists(flowData?.canonicalRequestSchema),
      canonicalResponseHasSchema: schemaExists(flowData?.canonicalResponseSchema),
      vendorRequestHasSchema: schemaExists(
        flowData?.vendorRequestSchema ?? flowData?.canonicalRequestSchema
      ),
      vendorResponseHasSchema: schemaExists(
        flowData?.vendorResponseSchema ?? flowData?.canonicalResponseSchema
      ),
      hasRequestMapping: mappingHasKeys(mappingsData?.request?.mapping),
      hasResponseMapping: mappingHasKeys(mappingsData?.response?.mapping),
      requestMappingStatus: flowData?.requestMappingStatus,
      responseMappingStatus: flowData?.responseMappingStatus,
      useCanonicalRequestFormat,
      useCanonicalResponseFormat,
      hasEndpoint: !!(flowData?.endpoint?.url?.trim?.() ?? flowData?.endpoint?.url),
      endpointVerified:
        readinessRowForOp?.hasEndpoint && readinessRowForOp?.endpointVerified,
    });
  }, [flowData, mappingsData, useCanonicalResponseFormat, useCanonicalRequestFormat, readinessRowForOp]);

  // Apply ?stage= from URL on initial load (pill deep-link from Configuration Overview)
  useEffect(() => {
    const stageParam = parseFlowBuilderStage(location.search);
    if (stageParam) {
      const targetStageId = flowBuilderStageToFlowStageId(stageParam);
      setActiveStageId(targetStageId);
      if (targetStageId === "request-mapping") {
        setPanelTab("mappings");
        setTimeout(() => {
          requestMappingRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
        }, 300);
      } else {
        setPanelTab("fields");
      }
    }
  }, [operationCode, version, location.search]);

  const handleStageClick = (stageId: FlowStageId) => {
    setActiveStageId(stageId);
    if (stageId === "request-mapping" || stageId === "response-mapping") {
      setPanelTab("mappings");
      setTimeout(() => {
        if (stageId === "request-mapping") {
          requestMappingRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
        } else {
          responseMappingRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }, 100);
    } else if (
      stageId === "canonical-request" ||
      stageId === "vendor-request" ||
      stageId === "canonical-response" ||
      stageId === "vendor-response"
    ) {
      setPanelTab("fields");
    } else if (stageId === "endpoint") {
      setPanelTab("fields");
    }
  };

  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (dirty) e.preventDefault();
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  const returnPath = useMemo(() => {
    const filters = parseFilterParamsFromSearch(location.search);
    return buildContractsPathWithFilters(filters);
  }, [location.search]);

  const handleBackClick = (e: React.MouseEvent) => {
    if (dirty && !window.confirm("You have unsaved changes. Leave anyway?")) {
      e.preventDefault();
    }
  };

  const handleDiscard = () => {
    setDirty(false);
    setSaveMessage(null);
    setRequestError(null);
    setResponseError(null);
    if (mappingsData && flowData) {
      const hasReqMapping =
        mappingsData.request?.mapping &&
        typeof mappingsData.request.mapping === "object" &&
        Object.keys(mappingsData.request.mapping).length > 0;
      const hasRespMapping =
        mappingsData.response?.mapping &&
        typeof mappingsData.response.mapping === "object" &&
        Object.keys(mappingsData.response.mapping).length > 0;
      const hasResponseRow = mappingsData.response != null;
      const canPassThrough = schemaFieldList(flowData?.canonicalResponseSchema ?? {}).length > 0;
      const respUseCanonical =
        canPassThrough &&
        !hasRespMapping &&
        (flowData?.responseMappingStatus === "warning_optional_missing" ||
          (flowData?.responseMappingStatus === undefined &&
            flowData?.requiresResponseMapping === false));
      setUseCanonicalResponseFormat(hasRespMapping ? false : respUseCanonical);

      const canPassThroughRequest = schemaFieldList(flowData?.canonicalRequestSchema ?? {}).length > 0;
      const reqUseCanonical =
        canPassThroughRequest &&
        !hasReqMapping &&
        (flowData?.requestMappingStatus === "warning_optional_missing" ||
          (flowData?.requestMappingStatus === undefined &&
            flowData?.requiresRequestMapping === false));
      setUseCanonicalRequestFormat(hasReqMapping ? false : reqUseCanonical);

      const reqDisplay = hasReqMapping
        ? initialFlowMappings.requestJson
        : reqUseCanonical
          ? templateToPrettifiedJson(identityTemplates.request)
          : "{}";
      const respDisplay = hasRespMapping
        ? initialFlowMappings.responseJson
        : (canPassThrough || flowData?.requiresResponseMapping === false) && !hasResponseRow
          ? templateToPrettifiedJson(identityTemplates.response)
          : "{}";
      setRequestJson(reqDisplay);
      setResponseJson(respDisplay);
    }
  };

  if (!activeVendor) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Visual Flow Builder</h1>
        <div className="rounded-lg bg-gray-50 border border-gray-200 p-4">
          <p className="text-sm font-medium text-gray-700">Select an active licensee above.</p>
        </div>
      </div>
    );
  }

  if (!hasKey) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Visual Flow Builder</h1>
        <div className="rounded-lg bg-amber-50 border border-amber-200 p-4">
          <p className="text-sm font-medium text-amber-800">Active licensee not selected.</p>
          <OpenSettingsLink>Open Settings →</OpenSettingsLink>
        </div>
      </div>
    );
  }

  if (!operationCode || !version) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Visual Flow Builder</h1>
        <p className="text-sm text-gray-600">
          Select an operation and version to design your flow (canonical → mappings → vendor → endpoint →
          response).
        </p>
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="text-sm font-medium text-gray-700 mb-3">Select operation</h2>
          {catalog.length === 0 ? (
            <p className="text-sm text-amber-700">
              No admin-approved operations are available for this vendor. Contact your administrator.
            </p>
          ) : availableOps.length === 0 ? (
            <p className="text-sm text-gray-500">Add operations in Configuration → Supported.</p>
          ) : (
            <div className="grid gap-2">
              {availableOps.map((op) => (
                <button
                  key={`${op.operationCode}-${op.canonicalVersion ?? "v1"}`}
                  type="button"
                  onClick={() =>
                    handleSelectOperation(op.operationCode ?? "", op.canonicalVersion ?? "v1")
                  }
                  className="text-left px-4 py-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-sm font-mono"
                >
                  {op.operationCode} · {op.canonicalVersion ?? "v1"}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Visual Flow Builder</h1>
        <div className="rounded-lg bg-red-50 border border-red-200 p-4">
          <p className="text-sm font-medium text-red-800">Failed to load flow.</p>
          <button
            type="button"
            onClick={() => refetch()}
            className="mt-2 px-3 py-1.5 text-sm font-medium text-red-800 bg-red-100 hover:bg-red-200 rounded"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (isLoading && !flowData) {
    return (
      <VendorPageLayout>
        <FlowBuilderSkeleton />
      </VendorPageLayout>
    );
  }

  const catalogOp = catalog.find(
    (c) => (c.operationCode ?? "").toUpperCase() === (operationCode ?? "").toUpperCase()
  );
  const providerServiceLabel = catalogOp?.description ?? "Provider Services";
  const directionPillLabel =
    directionFromUrl === "outbound"
      ? `Outbound • ${activeVendor ?? "?"} → Provider – ${providerServiceLabel}`
      : directionFromUrl === "inbound"
        ? `Inbound • Any licensee (*) → ${activeVendor ?? "?"}`
        : null;

  return (
    <VendorPageLayout>
    <div className="space-y-6 relative pb-20">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <nav className="text-sm text-gray-500 mb-1" aria-label="Breadcrumb">
            <Link
              to={returnPath}
              onClick={handleBackClick}
              className="text-slate-600 hover:text-slate-800 hover:underline"
            >
              Supported Operations
            </Link>
            <span className="mx-1.5 text-gray-400">›</span>
            <span className="text-gray-700 font-medium" aria-current="page">
              {operationCode} {formatVersionLabel(version)}
            </span>
          </nav>
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-2xl font-bold text-gray-900">Visual Flow Builder</h1>
            {directionPillLabel && (
              <span
                className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700"
                title={
                  directionFromUrl === "outbound" ? "OUTBOUND" : "INBOUND"
                }
              >
                {directionPillLabel}
              </span>
            )}
          </div>
          <p className="text-sm text-gray-600 mt-1">
            {operationCode} · {formatVersionLabel(version)}
          </p>
        </div>
        <div className="flex gap-2 items-center shrink-0">
          {saveMessage && (
            <span
              className={`text-sm ${saveMessage.type === "success" ? "text-emerald-600" : "text-red-600"}`}
            >
              {saveMessage.text}
            </span>
          )}
          <Link
            to={returnPath}
            onClick={handleBackClick}
            className="px-3 py-2 text-sm font-medium text-slate-600 hover:text-slate-800 border border-gray-200 rounded-lg"
          >
            Back
          </Link>
          <button
            type="button"
            onClick={handleSave}
            disabled={saveDisabled || isLoading}
            className="px-4 py-2 text-sm font-medium text-white bg-slate-700 hover:bg-slate-800 rounded-lg disabled:opacity-50"
            data-testid="flow-builder-save-header"
          >
            {saveMutation.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      </div>

      {pendingChangeRequestId && (
        <div
          className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 mb-4"
          role="status"
        >
          Your change has been submitted for admin approval (Request ID: {pendingChangeRequestId}). It will take effect
          after approval.
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8">
        <div className="lg:col-span-3 rounded-xl border border-gray-200 bg-white p-4">
          <h3 className="text-base font-semibold text-gray-800 mb-2">Operation info</h3>
          <p className="text-sm font-mono text-gray-600">
            {operationCode} · {formatVersionLabel(version)}
          </p>
          {(() => {
            const supportedOp = supported.find(
              (s) => (s.operationCode ?? "").toUpperCase() === (operationCode ?? "").toUpperCase()
            );
            const so = supportedOp?.supportsOutbound !== false;
            const si = supportedOp?.supportsInbound !== false;
            const catalogOp = catalog.find(
              (c) => (c.operationCode ?? "").toUpperCase() === (operationCode ?? "").toUpperCase()
            );
            const directionPolicy =
              (catalogOp as { directionPolicy?: string })?.directionPolicy;
            const dirLabel =
              readinessRowForOp
                ? getDirectionLabelWithPolicy(readinessRowForOp.direction, directionPolicy)
                : so && si
                  ? "Inbound & Outbound"
                  : so
                    ? getDirectionLabelWithPolicy("Outbound", directionPolicy)
                    : getDirectionLabelWithPolicy("Inbound", directionPolicy);
            return (
              <p
                className="text-xs text-slate-500 mt-1 font-normal"
                title={
                  readinessRowForOp
                    ? getDirectionCellTooltip(readinessRowForOp.direction, directionPolicy)
                    : undefined
                }
              >
                {dirLabel}
              </p>
            );
          })()}
          <div className="mt-3 space-y-1.5">
            {(() => {
              const readiness = computeFlowReadiness(flowData ?? null);
              const requestStatus = useCanonicalRequestFormat ? "warning_optional_missing" : readiness.request;
              const responseStatus = useCanonicalResponseFormat ? "warning_optional_missing" : readiness.response;
              return (
                <>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500 w-16 shrink-0">Request</span>
                    <MappingStatusChip
                      status={requestStatus}
                      title={requestBadgeTooltip(
                        useCanonicalRequestFormat ? "warning_optional_missing" : flowData?.requestMappingStatus
                      )}
                      iconOnlyWhenReady
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500 w-16 shrink-0">Response</span>
                    <MappingStatusChip
                      status={responseStatus}
                      title={responseBadgeTooltip(
                        useCanonicalResponseFormat ? "warning_optional_missing" : flowData?.responseMappingStatus
                      )}
                      iconOnlyWhenReady
                    />
                  </div>
                </>
              );
            })()}
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500 w-16 shrink-0">Contract</span>
              {readinessRowForOp ? (
                (() => {
                  const d = getContractStatusDisplay(readinessRowForOp.hasContract);
                  return (
                    <StatusPill
                      label={d.label}
                      variant={d.variant}
                      title={d.tooltip}
                      iconOnlyWhenReady
                    />
                  );
                })()
              ) : (
                <FlowReadinessPill status="missing" title="Contract not yet configured. Add from canonical operations." />
              )}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500 w-16 shrink-0">Endpoint</span>
              {readinessRowForOp ? (
                (() => {
                  const d = getEndpointStatusDisplay(
                    readinessRowForOp.hasEndpoint,
                    readinessRowForOp.endpointVerified,
                    readinessRowForOp.direction
                  );
                  return (
                    <StatusPill
                      label={d.label}
                      variant={d.variant}
                      title={d.tooltip}
                      iconOnlyWhenReady
                    />
                  );
                })()
              ) : (
                <FlowReadinessPill
                  status="missing"
                  title="Endpoint URL is required. Configure in Auth & Endpoints."
                />
              )}
            </div>
          </div>
          {(() => {
            const supportedOp = supported.find(
              (s) => (s.operationCode ?? "").toUpperCase() === (operationCode ?? "").toUpperCase()
            );
            const so = supportedOp?.supportsOutbound !== false;
            const si = supportedOp?.supportsInbound !== false;
            const endpointOk =
              !!(flowData?.endpoint?.url?.trim?.() ?? flowData?.endpoint?.url) &&
              ((flowData?.endpoint?.verificationStatus ?? "").toUpperCase() === "VERIFIED" ||
                (flowData?.endpoint?.verificationStatus ?? "").toUpperCase() === "OK");
            const mappingsOk =
              (flowData?.requestMappingStatus !== "error_required_missing" || flowData?.requiresRequestMapping === false) &&
              (flowData?.responseMappingStatus !== "error_required_missing" || flowData?.requiresResponseMapping === false);
            const configReady = endpointOk && mappingsOk;
            const outboundRules = allowlistData?.outbound ?? [];
            const inboundRules = allowlistData?.inbound ?? [];
            const hasOutboundRule = outboundRules.some(
              (r) => (r.operation ?? "").toUpperCase() === (operationCode ?? "").toUpperCase()
            );
            const hasInboundRule = inboundRules.some(
              (r) => (r.operation ?? "").toUpperCase() === (operationCode ?? "").toUpperCase()
            );
            const needsOutboundAccess = so && configReady && !hasOutboundRule;
            const needsInboundAccess = si && configReady && !hasInboundRule;
            if (!needsOutboundAccess && !needsInboundAccess) return null;
            return (
              <div className="mt-3 p-3 rounded-lg bg-amber-50 border border-amber-200">
                <p className="text-xs font-medium text-amber-800 mb-2">
                  {needsOutboundAccess && needsInboundAccess
                    ? "Configuration is ready. Add access rules to go live."
                    : needsOutboundAccess
                      ? "Outbound configuration is ready. Add an outbound access rule to start sending traffic."
                      : "Inbound configuration is ready. Add an inbound access rule to start receiving calls."}
                </p>
                <Link
                  to={`/configuration/allowlist${operationCode ? `?operation=${encodeURIComponent(operationCode)}` : ""}`}
                  className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-amber-800 bg-amber-100 hover:bg-amber-200 rounded-lg"
                >
                  Manage access
                </Link>
              </div>
            );
          })()}
          <p className="text-xs text-gray-500 mt-2">
            Editing version {version}. Changes apply to live traffic when saved.
          </p>
        </div>

        <div className="lg:col-span-5 rounded-xl border border-gray-200 bg-gray-50 p-4 min-h-[200px]">
          <h3 className="text-base font-semibold text-gray-800 mb-3">Flow pipeline</h3>
          <div className="flex flex-wrap gap-3">
            {flowStages.map((stage) => (
              <button
                key={stage.id}
                type="button"
                onClick={() => handleStageClick(stage.id)}
                title={getStageTooltip(stage.id, stage.status)}
                className={`inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm transition ${
                  activeStageId === stage.id
                    ? "border-slate-900 bg-slate-900 text-white"
                    : "border-slate-200 bg-white text-slate-800 hover:bg-slate-50"
                } ${
                  stage.status === "ok" ? "shadow-sm" : ""
                } ${
                  stage.status === "warning" ? "border-amber-300" : ""
                } ${
                  stage.status === "missing" && activeStageId !== stage.id
                    ? "border-rose-300 text-rose-700"
                    : ""
                }`}
              >
                <span
                  className="inline-block h-1.5 w-1.5 rounded-full shrink-0"
                  aria-hidden
                  style={{
                    backgroundColor:
                      activeStageId === stage.id
                        ? "currentColor"
                        : stage.status === "ok"
                          ? "#16a34a"
                          : stage.status === "warning"
                            ? "#d97706"
                            : "#dc2626",
                  }}
                />
                <span>
                  {stage.label}
                  {stage.subtitle && (
                    <span className="ml-1 opacity-80 font-normal">
                      ({stage.subtitle})
                    </span>
                  )}
                </span>
              </button>
            ))}
          </div>
        </div>

        <div className="lg:col-span-4 rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div className="flex border-b border-gray-200">
            {(["fields", "mappings", "test"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setPanelTab(t)}
                className={`px-4 py-3 text-base font-semibold capitalize -mb-px ${
                  panelTab === t
                    ? "border-b-2 border-emerald-600 text-slate-800"
                    : "text-gray-500 hover:text-slate-700 border-b-2 border-transparent"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
          <div className="p-4">
            {panelTab === "fields" && (
              activeStageId === "endpoint" ? (
                <div>
                  <h4 className="text-sm font-medium text-gray-700 mb-1">Endpoint</h4>
                  <p className="text-xs text-gray-500 mb-3">
                    {directionFromUrl === "outbound"
                      ? "Defines where the platform routes your request to the target licensee's API."
                      : "Defines where other licensees call your API for this operation."}
                  </p>
                  <EndpointSummaryPanel
                    operationCode={operationCode ?? ""}
                    version={version ?? "v1"}
                    direction={directionFromUrl === "outbound" ? "outbound" : "inbound"}
                  />
                </div>
              ) : (
              <div className="space-y-4">
                <div
                  className={`rounded p-2 -m-2 transition-colors ${
                    activeStageId === "canonical-request" ? "ring-1 ring-slate-300 bg-slate-50" : ""
                  }`}
                >
                  <h4 className="text-xs font-medium text-gray-500 mb-1">Canonical request</h4>
                  <ul className="text-sm font-mono space-y-1">
                    {canonicalReqFieldsList.length
                      ? canonicalReqFieldsList.map((f) => <li key={f}>{f}</li>)
                      : [<li key="_" className="text-gray-400">—</li>]}
                  </ul>
                </div>
                <div
                  className={`rounded p-2 -m-2 transition-colors ${
                    activeStageId === "vendor-request" ? "ring-1 ring-slate-300 bg-slate-50" : ""
                  }`}
                >
                  <h4 className="text-xs font-medium text-gray-500 mb-1">Vendor request</h4>
                  <p className="text-xs text-gray-400 mb-1">Payload sent to the vendor endpoint.</p>
                  <ul className="text-sm font-mono space-y-1">
                    {vendorReqFieldsList.length
                      ? vendorReqFieldsList.map((f) => <li key={f}>{f}</li>)
                      : [<li key="_" className="text-gray-400">—</li>]}
                  </ul>
                </div>
                <div
                  className={`rounded p-2 -m-2 transition-colors ${
                    activeStageId === "canonical-response" ? "ring-1 ring-slate-300 bg-slate-50" : ""
                  }`}
                >
                  <h4 className="text-xs font-medium text-gray-500 mb-1">Canonical response</h4>
                  <p className="text-xs text-gray-400 mb-1">Final response returned back to the caller.</p>
                  <ul className="text-sm font-mono space-y-1">
                    {canonicalRespFieldsList.length
                      ? canonicalRespFieldsList.map((f) => <li key={f}>{f}</li>)
                      : [<li key="_" className="text-gray-400">—</li>]}
                  </ul>
                </div>
                <div
                  className={`rounded p-2 -m-2 transition-colors ${
                    activeStageId === "vendor-response" ? "ring-1 ring-slate-300 bg-slate-50" : ""
                  }`}
                >
                  <h4 className="text-xs font-medium text-gray-500 mb-1">Vendor response</h4>
                  <p className="text-xs text-gray-400 mb-1">Raw response received from the vendor endpoint.</p>
                  <ul className="text-sm font-mono space-y-1">
                    {vendorRespFieldsList.length
                      ? vendorRespFieldsList.map((f) => <li key={f}>{f}</li>)
                      : [<li key="_" className="text-gray-400">—</li>]}
                  </ul>
                </div>
              </div>
              )
            )}
            {panelTab === "mappings" && (
              <div className="space-y-4">
                {/*
                  CANONICAL CHECKBOX BEHAVIOUR (manual repro):
                  1. Toggling "Use canonical request/response format" is local state only – no API call until Save.
                  2. After Save, vendor sees "Mapping: Configured" for the operation.
                  3. Test: Toggle checkbox → putOperationMappings should NOT be called until Save clicked.
                */}
                {useCanonicalRequestFormat && useCanonicalResponseFormat && (
                  <div
                    className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800"
                    role="status"
                  >
                    Mapping uses canonical pass-through. No changes required.
                  </div>
                )}
                {(canUseCanonicalRequest || canUseCanonicalResponse) &&
                  !(useCanonicalRequestFormat && useCanonicalResponseFormat) && (
                    <div
                      className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800"
                      role="status"
                    >
                      Using canonical pass-through for this direction. The editors show an identity template (for
                      display only; not saved until you change it). Add mapping only if you need transformations.
                    </div>
                  )}
                <p className="text-xs text-gray-500">
                  Edit request and response mappings as JSON. Format:{" "}
                  <code className="bg-gray-100 px-1 rounded">{"{ vendorPath: \"$.canonicalPath\" }"}</code>
                </p>
                <div
                  className={`rounded p-2 -m-2 transition-colors ${
                    activeStageId === "request-mapping" ? "ring-1 ring-slate-300 bg-slate-50" : ""
                  }`}
                >
                  {canUseCanonicalRequest && (
                    <label className="flex items-center gap-2 cursor-pointer mb-3">
                      <input
                        type="checkbox"
                        checked={useCanonicalRequestFormat}
                        onChange={(e) => {
                          setUseCanonicalRequestFormat(e.target.checked);
                          setDirty(true);
                          setSaveMessage(null);
                        }}
                        className="h-4 w-4 rounded border-gray-300 text-slate-600 focus:ring-slate-500"
                        data-testid="flow-builder-use-canonical-request"
                      />
                      <span className="text-sm font-medium text-gray-700">
                        Use canonical request format (no mapping needed)
                      </span>
                    </label>
                  )}
                  {useCanonicalRequestFormat ? (
                    <p className="text-sm text-slate-600 bg-slate-50 border border-slate-200 rounded-md px-3 py-2">
                      Canonical request is passed through to vendor request as-is.
                    </p>
                  ) : (
                    <>
                      <label htmlFor="request-mapping-json" className="block text-xs font-medium text-gray-500 mb-1">
                        Request mapping (Canonical → Vendor)
                      </label>
                      <p className="text-xs text-gray-400 mb-1">
                        Transforms canonical fields to vendor-specific format.
                      </p>
                      <textarea
                        id="request-mapping-json"
                        ref={requestMappingRef}
                        value={requestJson}
                        onChange={(e) => handleRequestJsonChange(e.target.value)}
                        className={`w-full h-32 px-3 py-2 text-sm font-mono border rounded-md ${
                          requestError ? "border-red-300 bg-red-50" : "border-gray-200"
                        }`}
                        spellCheck={false}
                      />
                      {requestError && <p className="text-sm text-red-600 mt-1">{requestError}</p>}
                    </>
                  )}
                </div>
                <div
                  className={`rounded p-2 -m-2 transition-colors ${
                    activeStageId === "response-mapping" ? "ring-1 ring-slate-300 bg-slate-50" : ""
                  }`}
                >
                  {canUseCanonicalResponse && (
                    <label className="flex items-center gap-2 cursor-pointer mb-3">
                      <input
                        type="checkbox"
                        checked={useCanonicalResponseFormat}
                        onChange={(e) => {
                          setUseCanonicalResponseFormat(e.target.checked);
                          setDirty(true);
                          setSaveMessage(null);
                        }}
                        className="h-4 w-4 rounded border-gray-300 text-slate-600 focus:ring-slate-500"
                        data-testid="flow-builder-use-canonical-response"
                      />
                      <span className="text-sm font-medium text-gray-700">
                        Use canonical response format (no mapping needed)
                      </span>
                    </label>
                  )}
                  {useCanonicalResponseFormat ? (
                    <p className="text-sm text-slate-600 bg-slate-50 border border-slate-200 rounded-md px-3 py-2">
                      Vendor response is assumed to match canonical schema.
                    </p>
                  ) : (
                    <>
                      <label htmlFor="response-mapping-json" className="block text-xs font-medium text-gray-500 mb-1">
                        Response mapping (Vendor → Canonical)
                      </label>
                      <p className="text-xs text-gray-400 mb-1">Transforms vendor response back into canonical format.</p>
                      <textarea
                        id="response-mapping-json"
                        ref={responseMappingRef}
                        value={responseJson}
                        onChange={(e) => handleResponseJsonChange(e.target.value)}
                        className={`w-full h-32 px-3 py-2 text-sm font-mono border rounded-md ${
                          responseError ? "border-red-300 bg-red-50" : "border-gray-200"
                        }`}
                        spellCheck={false}
                      />
                      {responseError && <p className="text-sm text-red-600 mt-1">{responseError}</p>}
                    </>
                  )}
                </div>
              </div>
            )}
            {panelTab === "test" && (
              <div className="space-y-6">
                <div>
                  <h4 className="text-sm font-medium text-gray-700 mb-1">
                    Test request (canonical format)
                  </h4>
                  <p className="text-xs text-gray-500 mb-2">
                    This payload is in canonical request format. It will be transformed and sent to
                    the configured vendor endpoint.
                  </p>
                  <textarea
                    aria-label="Test request (canonical format)"
                    value={testInput}
                    onChange={(e) => {
                      setTestInput(e.target.value);
                      setTestJsonError(null);
                    }}
                    className="w-full h-40 px-3 py-2 text-sm font-mono border border-gray-200 rounded-md"
                    placeholder='{}'
                  />
                  {testJsonError && (
                    <p className="text-sm text-red-600 mt-1">{testJsonError}</p>
                  )}
                  <div className="mt-2 flex items-center gap-3">
                    {(() => {
                      const { allowed, reason } = canRunTest(readinessRowForOp);
                      return (
                        <>
                          <button
                            type="button"
                            onClick={handleRunTest}
                            disabled={testMutation.isPending || !allowed}
                            title={!allowed ? reason : undefined}
                            className="px-4 py-2 text-sm font-medium text-white bg-slate-700 hover:bg-slate-800 rounded-lg disabled:opacity-50"
                          >
                            {testMutation.isPending ? "Running…" : "Run test"}
                          </button>
                          {!allowed && (
                            <span className="text-xs text-amber-600">
                              {reason ?? "Configure this flow before running tests."}
                            </span>
                          )}
                        </>
                      );
                    })()}
                  </div>
                </div>
                <div className="border-t border-gray-200 pt-6">
                  <h4 className="text-sm font-medium text-gray-700 mb-1">Last response</h4>
                  {testJsonError && !testResult && (
                      <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2">
                        <p className="text-sm font-medium text-red-700">Test failed</p>
                        <p className="text-xs text-red-600 mt-1">{testJsonError}</p>
                      </div>
                    )}
                    {testResult ? (
                      <div className="space-y-3">
                        <div className="flex flex-col gap-3">
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-xs font-medium text-slate-600">Canonical request</span>
                              {testResult.contractSource && (
                                <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-700" title="Contract source">
                                  Contract: {testResult.contractSource}
                                </span>
                              )}
                            </div>
                            <pre className="p-2 bg-gray-100 rounded text-xs max-h-48 overflow-y-auto whitespace-pre-wrap break-words">
                              {JSON.stringify(testResult.canonicalRequest ?? {}, null, 2)}
                            </pre>
                          </div>
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-xs font-medium text-slate-600">Vendor request</span>
                              {testResult.mappingRequestSource && (
                                <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-700" title="Mapping source">
                                  Mapping: {testResult.mappingRequestSource === "vendor_mapping" ? "vendor" : "canonical pass-through"}
                                </span>
                              )}
                            </div>
                            <pre className="p-2 bg-gray-100 rounded text-xs max-h-48 overflow-y-auto whitespace-pre-wrap break-words">
                              {JSON.stringify(testResult.vendorRequest ?? {}, null, 2)}
                            </pre>
                          </div>
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-xs font-medium text-slate-600">Vendor response</span>
                              {testResult.mappingResponseSource && (
                                <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-700" title="Mapping source">
                                  Mapping: {testResult.mappingResponseSource === "vendor_mapping" ? "vendor" : "canonical pass-through"}
                                </span>
                              )}
                            </div>
                            <pre className="p-2 bg-gray-100 rounded text-xs max-h-48 overflow-y-auto whitespace-pre-wrap break-words">
                              {JSON.stringify(testResult.vendorResponse ?? {}, null, 2)}
                            </pre>
                          </div>
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-xs font-medium text-slate-600">Canonical response</span>
                              {testResult.contractSource && (
                                <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-700" title="Contract source">
                                  Contract: {testResult.contractSource}
                                </span>
                              )}
                            </div>
                            <pre className="p-2 bg-gray-100 rounded text-xs max-h-48 overflow-y-auto whitespace-pre-wrap break-words">
                              {JSON.stringify(testResult.canonicalResponse ?? {}, null, 2)}
                            </pre>
                          </div>
                        </div>
                        {((testResult.errors?.mappingRequest?.length ?? 0) > 0 ||
                          (testResult.errors?.downstream?.length ?? 0) > 0 ||
                          (testResult.errors?.mappingResponse?.length ?? 0) > 0) && (
                          <div className="text-amber-700 text-sm">
                            {[
                              ...(testResult.errors?.mappingRequest ?? []),
                              ...(testResult.errors?.downstream ?? []),
                              ...(testResult.errors?.mappingResponse ?? []),
                            ].map((e, i) => (
                              <p key={i}>{e}</p>
                            ))}
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm text-gray-500 italic py-4">
                        No test run yet. Use a sample payload and click <strong>Run test</strong> to
                        verify this flow.
                      </p>
                    )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {dirty && !saveMutation.isPending && (
        <div
          className="fixed bottom-4 right-4 z-40 flex flex-col items-end gap-2 rounded-lg bg-slate-900/95 px-4 py-3 text-sm text-slate-50 shadow-lg max-w-sm"
          role="status"
          aria-live="polite"
        >
          <div className="flex items-center gap-3">
            <span className="text-xs font-semibold tracking-wider uppercase text-amber-300">
              UNSAVED CHANGES
            </span>
            <button
              type="button"
              className="rounded bg-slate-100 px-3 py-1 text-xs font-medium text-slate-900 hover:bg-white"
              onClick={handleDiscard}
            >
              Discard
            </button>
            <button
              type="button"
              className="rounded bg-emerald-500 px-3 py-1 text-xs font-semibold text-white hover:bg-emerald-400"
              onClick={handleSave}
              data-testid="flow-builder-save-sticky"
            >
              Save
            </button>
          </div>
          <p className="text-xs text-slate-400">
            Changes apply immediately to live traffic once saved.
          </p>
        </div>
      )}
    </div>
    </VendorPageLayout>
  );
}
