import { adminApi, vendorApi, vendorApiPublic, runtimeApi } from "./client";
import type {
  Transaction,
  ListTransactionsResponse,
  ListAuditEventsResponse,
  AuditEvent,
  ExecuteIntegrationPayload,
  ExecuteIntegrationResponse,
  AiExecuteEnvelope,
  RedriveResponse,
  Vendor,
  Operation,
  AllowlistEntry,
  Endpoint,
  RegistryContract,
  UpsertVendorPayload,
  UpsertOperationPayload,
  UpsertAllowlistPayload,
  UpsertEndpointPayload,
  OnboardVendorPayload,
  OnboardVendorResponse,
  VendorOperationCatalogItem,
  VendorSupportedOperation,
  VendorEndpoint,
  VendorContract,
  VendorMapping,
  MappingDirection,
  ListPolicyDecisionsResponse,
  PolicyDecisionItem,
  PolicySimulationResult,
  MissionControlTopologyResponse,
  MissionControlActivityResponse,
  MissionControlTransactionSummary,
  MissionControlTransactionDetail,
} from "../types";

export interface ListTransactionsFilters {
  /** When absent or "ALL", fetches from all licensees. Otherwise filters by source_vendor. */
  vendorCode?: string;
  from?: string;
  to?: string;
  status?: string;
  operation?: string;
  limit?: number;
  cursor?: string;
}

/** GET /v1/audit/transactions. vendorCode optional; omit for all licensees. */
export async function listTransactions(
  filters: ListTransactionsFilters
): Promise<ListTransactionsResponse> {
  const params = new URLSearchParams();
  if (filters.vendorCode && filters.vendorCode !== "ALL") {
    params.set("vendorCode", filters.vendorCode);
  }
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);
  if (filters.status) params.set("status", filters.status);
  if (filters.operation) params.set("operation", filters.operation);
  if (filters.limit != null) params.set("limit", String(filters.limit));
  if (filters.cursor) params.set("cursor", filters.cursor);

  const { data } = await adminApi.get<ListTransactionsResponse>(
    `/v1/audit/transactions?${params.toString()}`
  );
  return data;
}

/** Fetch transactions from all vendors in parallel and merge. limitPerVendor capped at 100 (API max). */
export async function listTransactionsAllVendors(params: {
  vendorCodes: string[];
  from?: string;
  to?: string;
  operation?: string;
  limitPerVendor?: number;
}): Promise<Transaction[]> {
  const { vendorCodes, from, to, operation, limitPerVendor = 100 } = params;
  const limit = Math.min(limitPerVendor, 100);
  if (vendorCodes.length === 0) return [];

  const results = await Promise.all(
    vendorCodes.map((vendorCode) =>
      listTransactions({
        vendorCode,
        from,
        to,
        operation,
        limit,
      })
    )
  );

  const all = results.flatMap((r) => r.transactions ?? []);
  all.sort((a, b) => {
    const da = a.created_at ?? "";
    const db = b.created_at ?? "";
    return db.localeCompare(da);
  });
  return all;
}

/** GET /v1/audit/transactions/{transactionId} - returns transaction, auditEvents, authSummary, contractMappingSummary */
export async function getTransaction(
  transactionId: string,
  options?: { vendorCode?: string; expandSensitive?: boolean; reason?: string }
): Promise<import("../types").TransactionDetailResponse> {
  const params: Record<string, string> = {};
  if (options?.vendorCode) params.vendorCode = options.vendorCode;
  if (options?.expandSensitive) params.expandSensitive = "true";
  if (options?.reason) params.reason = options.reason;
  const { data } = await adminApi.get<import("../types").TransactionDetailResponse>(
    `/v1/audit/transactions/${encodeURIComponent(transactionId)}`,
    { params: Object.keys(params).length ? params : undefined }
  );
  return data;
}

/**
 * GET /v1/audit/events?transactionId=<id>&limit=100
 * Requires JWT (admin). Returns { items, nextCursor: null }.
 * On 404/405, fallback to transaction only.
 */
export async function listAuditEvents(
  transactionId: string,
  options?: { vendorCode?: string; limit?: number }
): Promise<ListAuditEventsResponse> {
  const params = new URLSearchParams();
  params.set("transactionId", transactionId);
  if (options?.limit != null) params.set("limit", String(options.limit));

  try {
    const { data } = await adminApi.get<{ items: AuditEvent[]; nextCursor: string | null }>(
      `/v1/audit/events?${params.toString()}`
    );
    const items = data?.items;
    if (Array.isArray(items)) {
      return { events: items };
    }
    return { events: [] };
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status;
    if (status === 404 || status === 405) {
      const detail =
        options?.vendorCode != null
          ? await getTransaction(transactionId, { vendorCode: options.vendorCode })
          : undefined;
      return {
        events: detail?.auditEvents ?? [],
        transaction: detail?.transaction,
      };
    }
    throw err;
  }
}



export interface SimulatePolicyDecisionParams {
  vendorCode?: string;
  operationCode?: string;
  targetVendorCode?: string;
  action: "EXECUTE" | "AI_EXECUTE_DATA" | "AI_EXECUTE_PROMPT" | "AUDIT_READ" | "AUDIT_EXPAND_SENSITIVE";
}

/** GET /v1/registry/policy-simulator */
export async function simulatePolicyDecision(
  params: SimulatePolicyDecisionParams
): Promise<PolicySimulationResult> {
  const query = new URLSearchParams();
  if (params.vendorCode) query.set("vendorCode", params.vendorCode);
  if (params.operationCode) query.set("operationCode", params.operationCode);
  if (params.targetVendorCode) query.set("targetVendorCode", params.targetVendorCode);
  query.set("action", params.action);
  const { data } = await adminApi.get<PolicySimulationResult>(
    `/v1/registry/policy-simulator?${query.toString()}`
  );
  return data;
}
export interface ListPolicyDecisionFilters {
  vendorCode?: string;
  operationCode?: string;
  decisionCode?: string;
  dateFrom?: string;
  dateTo?: string;
  limit?: number;
  cursor?: string;
}

/** GET /v1/registry/policy-decisions */
export async function listPolicyDecisions(
  filters: ListPolicyDecisionFilters = {}
): Promise<ListPolicyDecisionsResponse> {
  const params = new URLSearchParams();
  if (filters.vendorCode) params.set("vendorCode", filters.vendorCode);
  if (filters.operationCode) params.set("operationCode", filters.operationCode);
  if (filters.decisionCode) params.set("decisionCode", filters.decisionCode);
  if (filters.dateFrom) params.set("dateFrom", filters.dateFrom);
  if (filters.dateTo) params.set("dateTo", filters.dateTo);
  if (filters.limit != null) params.set("limit", String(filters.limit));
  if (filters.cursor) params.set("cursor", filters.cursor);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const { data } = await adminApi.get<ListPolicyDecisionsResponse>(
    `/v1/registry/policy-decisions${suffix}`
  );
  return {
    items: Array.isArray(data?.items) ? data.items as PolicyDecisionItem[] : [],
    nextCursor: data?.nextCursor ?? null,
    count: Number(data?.count ?? 0),
  };
}

/** GET /v1/registry/mission-control/topology */
export async function getMissionControlTopology(): Promise<MissionControlTopologyResponse> {
  const { data } = await adminApi.get<MissionControlTopologyResponse>(
    "/v1/registry/mission-control/topology"
  );
  return {
    nodes: Array.isArray(data?.nodes) ? data.nodes : [],
    edges: Array.isArray(data?.edges) ? data.edges : [],
  };
}

/** GET /v1/registry/mission-control/activity */
export async function getMissionControlActivity(params?: {
  lookbackMinutes?: number;
  limit?: number;
}): Promise<MissionControlActivityResponse> {
  const query = new URLSearchParams();
  if (params?.lookbackMinutes != null) query.set("lookbackMinutes", String(params.lookbackMinutes));
  if (params?.limit != null) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const { data } = await adminApi.get<MissionControlActivityResponse>(
    `/v1/registry/mission-control/activity${suffix}`
  );
  return {
    items: Array.isArray(data?.items) ? data.items : [],
    count: Number(data?.count ?? 0),
    lookbackMinutes: Number(data?.lookbackMinutes ?? 10),
  };
}

export interface ListMissionControlTransactionsFilters {
  operationCode?: string;
  sourceVendor?: string;
  targetVendor?: string;
  status?: string;
  mode?: string;
  correlationId?: string;
  limit?: number;
  lookbackMinutes?: number;
}

/** GET /v1/registry/mission-control/transactions */
export async function listMissionControlTransactions(
  filters?: ListMissionControlTransactionsFilters
): Promise<{ items: MissionControlTransactionSummary[] }> {
  const params = new URLSearchParams();
  if (filters?.operationCode) params.set("operationCode", filters.operationCode);
  if (filters?.sourceVendor) params.set("sourceVendor", filters.sourceVendor);
  if (filters?.targetVendor) params.set("targetVendor", filters.targetVendor);
  if (filters?.status) params.set("status", filters.status);
  if (filters?.mode) params.set("mode", filters.mode);
  if (filters?.correlationId) params.set("correlationId", filters.correlationId);
  if (filters?.limit != null) params.set("limit", String(filters.limit));
  if (filters?.lookbackMinutes != null) params.set("lookbackMinutes", String(filters.lookbackMinutes));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const { data } = await adminApi.get<{ items: MissionControlTransactionSummary[] }>(
    `/v1/registry/mission-control/transactions${suffix}`
  );
  return {
    items: Array.isArray(data?.items) ? data.items : [],
  };
}

/** GET /v1/registry/mission-control/transactions/{transactionId} */
export async function getMissionControlTransaction(
  transactionId: string
): Promise<MissionControlTransactionDetail> {
  const { data } = await adminApi.get<MissionControlTransactionDetail>(
    `/v1/registry/mission-control/transactions/${encodeURIComponent(transactionId)}`
  );
  return data;
}

/** POST /v1/admin/redrive/{transactionId} */
export async function redrive(transactionId: string): Promise<RedriveResponse> {
  const { data } = await adminApi.post<RedriveResponse>(
    `/v1/admin/redrive/${encodeURIComponent(transactionId)}`,
    {}
  );
  return data;
}

/** POST /v1/ai/execute (Runtime API - single source for execute) */
export async function executeAiIntegration(
  payload: ExecuteIntegrationPayload
): Promise<ExecuteIntegrationResponse> {
  const body = {
    requestType: "DATA",
    operationCode: payload.operation,
    sourceVendorCode: payload.sourceVendor,
    targetVendorCode: payload.targetVendor,
    payload: payload.parameters ?? {},
    idempotencyKey: payload.idempotencyKey,
  };
  const { data } = await runtimeApi.post<AiExecuteEnvelope>(
    "/v1/ai/execute",
    body
  );
  if (data.error) {
    const err = new Error(data.error.message ?? data.error.code ?? "Execute failed") as Error & {
      response?: { data?: unknown };
    };
    err.response = { data: { error: data.error } };
    throw err;
  }
  const raw = data.rawResult as Record<string, unknown> | undefined;
  return {
    transactionId: (raw?.transactionId as string) ?? data.transactionId ?? "",
    correlationId: (raw?.correlationId as string) ?? data.correlationId,
    responseBody: (raw?.responseBody as Record<string, unknown>) ?? raw,
  };
}

// --- Registry: list (GET) ---

/** Shared list response shape for registry GET endpoints */
export interface ListRegistryResponse<T> {
  items: T[];
  nextCursor: string | null;
}

/** Query params for registry list endpoints */
export interface ListRegistryParams {
  limit?: number;
  cursor?: string;
  vendorCode?: string;
  operationCode?: string;
  canonicalVersion?: string;
  sourceVendorCode?: string;
  targetVendorCode?: string;
  isActive?: boolean;
  /** scope for allowlist: global | vendor_specific | all */
  scope?: "global" | "vendor_specific" | "all";
}

const REGISTRY_MAX_LIMIT = 200;

/** GET /v1/registry/vendors */
export async function listVendors(
  params?: ListRegistryParams
): Promise<ListRegistryResponse<Vendor>> {
  const q = buildListParams(params, ["limit", "cursor", "vendorCode", "isActive"]);
  const { data } = await adminApi.get<ListRegistryResponse<Vendor>>(
    `/v1/registry/vendors${q ? `?${q}` : ""}`
  );
  return data;
}

/** GET /v1/registry/operations */
export async function listOperations(
  params?: ListRegistryParams
): Promise<ListRegistryResponse<Operation>> {
  const q = buildListParams(params, [
    "limit",
    "cursor",
    "operationCode",
    "isActive",
    "sourceVendorCode",
    "targetVendorCode",
  ]);
  const { data } = await adminApi.get<ListRegistryResponse<Operation>>(
    `/v1/registry/operations${q ? `?${q}` : ""}`
  );
  return data;
}

/** GET /v1/registry/allowlist */
export async function listAllowlist(
  params?: ListRegistryParams
): Promise<ListRegistryResponse<AllowlistEntry>> {
  const q = buildListParams(params, [
    "limit",
    "cursor",
    "vendorCode",
    "operationCode",
    "sourceVendorCode",
    "targetVendorCode",
    "scope",
  ]);
  const { data } = await adminApi.get<ListRegistryResponse<AllowlistEntry>>(
    `/v1/registry/allowlist${q ? `?${q}` : ""}`
  );
  return data;
}

/** GET /v1/registry/endpoints */
export async function listEndpoints(
  params?: ListRegistryParams
): Promise<ListRegistryResponse<Endpoint>> {
  const q = buildListParams(params, [
    "limit",
    "cursor",
    "vendorCode",
    "operationCode",
    "isActive",
  ]);
  const { data } = await adminApi.get<ListRegistryResponse<Endpoint>>(
    `/v1/registry/endpoints${q ? `?${q}` : ""}`
  );
  return data;
}

/** GET /v1/registry/contracts - returns { contracts?: RegistryContract[], items?: RegistryContract[], nextCursor? } */
export async function listContracts(
  params?: ListRegistryParams
): Promise<ListRegistryResponse<RegistryContract>> {
  const q = buildListParams(params, [
    "limit",
    "operationCode",
    "canonicalVersion",
    "isActive",
  ]);
  const { data } = await adminApi.get<{
    contracts?: RegistryContract[];
    items?: RegistryContract[];
    nextCursor?: string | null;
  }>(`/v1/registry/contracts${q ? `?${q}` : ""}`);
  const items = data?.contracts ?? data?.items ?? [];
  return { items, nextCursor: data?.nextCursor ?? null };
}

/** Canonical operation list item */
export interface CanonicalOperationItem {
  operationCode: string;
  latestVersion: string;
  title?: string;
  description?: string;
  versions?: string[];
}

/** Canonical operation detail with schemas and examples */
export interface CanonicalOperationDetail {
  operationCode: string;
  version: string;
  latestVersion?: string;
  title?: string;
  description?: string;
  versionAliases?: string[];
  requestPayloadSchema: Record<string, unknown>;
  responsePayloadSchema: Record<string, unknown>;
  examples: {
    request: Record<string, unknown>;
    response: Record<string, unknown>;
    requestEnvelope?: Record<string, unknown>;
    responseEnvelope?: Record<string, unknown>;
  };
}

/** GET /v1/registry/canonical/operations */
export async function listCanonicalOperations(): Promise<{ items: CanonicalOperationItem[] }> {
  const { data } = await adminApi.get<{ items: CanonicalOperationItem[] }>(
    "/v1/registry/canonical/operations"
  );
  return data;
}

/** GET /v1/registry/canonical/operations/{operationCode} */
export async function getCanonicalOperation(
  operationCode: string,
  version?: string
): Promise<CanonicalOperationDetail> {
  const params = version ? `?version=${encodeURIComponent(version)}` : "";
  const { data } = await adminApi.get<CanonicalOperationDetail>(
    `/v1/registry/canonical/operations/${encodeURIComponent(operationCode)}${params}`
  );
  return data;
}

// --- Flow Builder (canonical-driven, read-only) ---

/** GET /v1/flow/canonical/operations */
export async function listFlowCanonicalOperations(): Promise<{ items: CanonicalOperationItem[] }> {
  const { data } = await adminApi.get<{ items: CanonicalOperationItem[] }>(
    "/v1/flow/canonical/operations"
  );
  return data;
}

/** GET /v1/flow/canonical/operations/{operationCode} */
export async function getFlowCanonicalOperation(
  operationCode: string,
  version?: string
): Promise<CanonicalOperationDetail> {
  const params = version ? `?version=${encodeURIComponent(version)}` : "";
  const { data } = await adminApi.get<CanonicalOperationDetail>(
    `/v1/flow/canonical/operations/${encodeURIComponent(operationCode)}${params}`
  );
  return data;
}

/** Flow draft payload for validation */
export interface FlowDraftPayload {
  name: string;
  operationCode: string;
  version: string;
  sourceVendor: string;
  targetVendor: string;
  trigger: { type: "MANUAL" | "API" };
  mappingMode: "CANONICAL_FIRST";
  notes?: string;
}

/** POST /v1/flow/draft/validate response */
export interface FlowDraftValidateResponse {
  valid: boolean;
  errors?: Array<{ message: string; field?: string | null }>;
  normalizedDraft?: FlowDraftPayload & { notes?: string | null };
}

/** Alias for FlowDraftValidateResponse */
export type FlowDraftValidateResult = FlowDraftValidateResponse;

/** POST /v1/flow/draft/validate */
export async function validateFlowDraft(
  payload: FlowDraftPayload
): Promise<FlowDraftValidateResponse> {
  const { data } = await adminApi.post<FlowDraftValidateResponse>(
    "/v1/flow/draft/validate",
    payload
  );
  return data;
}

// --- Sandbox (canonical-driven, mock-only) ---

/** GET /v1/sandbox/canonical/operations */
export async function listSandboxCanonicalOperations(): Promise<{
  items: CanonicalOperationItem[];
}> {
  const { data } = await adminApi.get<{ items: CanonicalOperationItem[] }>(
    "/v1/sandbox/canonical/operations"
  );
  return data;
}

/** GET /v1/sandbox/canonical/operations/{operationCode} */
export async function getSandboxCanonicalOperation(
  operationCode: string,
  version?: string
): Promise<CanonicalOperationDetail> {
  const params = version ? `?version=${encodeURIComponent(version)}` : "";
  const { data } = await adminApi.get<CanonicalOperationDetail>(
    `/v1/sandbox/canonical/operations/${encodeURIComponent(operationCode)}${params}`
  );
  return data;
}

/** POST /v1/sandbox/request/validate request */
export interface SandboxValidateRequestPayload {
  operationCode: string;
  version?: string;
  payload: Record<string, unknown>;
}

/** POST /v1/sandbox/request/validate response */
export interface SandboxValidateResponse {
  valid: boolean;
  errors?: Array<{ field: string; message: string }>;
  normalizedVersion?: string;
}

/** POST /v1/sandbox/request/validate */
export async function validateSandboxRequest(
  body: SandboxValidateRequestPayload
): Promise<SandboxValidateResponse> {
  const { data } = await adminApi.post<SandboxValidateResponse>(
    "/v1/sandbox/request/validate",
    body
  );
  return data;
}

/** POST /v1/sandbox/mock/run request */
export interface SandboxMockRunPayload {
  operationCode: string;
  version?: string;
  payload: Record<string, unknown>;
  context?: Record<string, unknown>;
}

/** POST /v1/sandbox/mock/run response */
export interface SandboxMockRunResponse {
  operationCode: string;
  version: string;
  mode: "MOCK";
  valid: boolean;
  requestPayloadValid: boolean;
  requestEnvelopeValid: boolean;
  responseEnvelopeValid: boolean;
  requestEnvelope?: Record<string, unknown>;
  responseEnvelope?: Record<string, unknown>;
  notes?: string[];
  errors?: Array<{ field: string; message: string }>;
}

/** POST /v1/sandbox/mock/run */
export async function runMockSandboxTest(
  body: SandboxMockRunPayload
): Promise<SandboxMockRunResponse> {
  const { data } = await adminApi.post<SandboxMockRunResponse>(
    "/v1/sandbox/mock/run",
    body
  );
  return data;
}

/** AI Debugger: debug report shape */
export interface DebugReport {
  debugType: "CANONICAL_REQUEST" | "FLOW_DRAFT" | "SANDBOX_RESULT";
  status: "PASS" | "WARN" | "FAIL";
  operationCode: string;
  version: string;
  summary: string;
  findings: Array<{
    severity: "ERROR" | "WARNING" | "INFO";
    code: string;
    title: string;
    message: string;
    field: string | null;
    suggestion: string | null;
  }>;
  normalizedArtifacts: Record<string, unknown>;
  notes: string[];
}

/** POST /v1/ai/debug/request/analyze */
export async function analyzeDebugRequest(body: {
  operationCode: string;
  version?: string;
  payload: Record<string, unknown>;
}): Promise<DebugReport> {
  const { data } = await adminApi.post<DebugReport>(
    "/v1/ai/debug/request/analyze",
    body
  );
  return data;
}

/** POST /v1/ai/debug/flow-draft/analyze */
export async function analyzeDebugFlowDraft(body: {
  draft: Record<string, unknown>;
}): Promise<DebugReport> {
  const { data } = await adminApi.post<DebugReport>(
    "/v1/ai/debug/flow-draft/analyze",
    body
  );
  return data;
}

/** POST /v1/ai/debug/sandbox-result/analyze */
export async function analyzeDebugSandboxResult(body: {
  result: Record<string, unknown>;
}): Promise<DebugReport> {
  const { data } = await adminApi.post<DebugReport>(
    "/v1/ai/debug/sandbox-result/analyze",
    body
  );
  return data;
}

/** Runtime Preflight: POST /v1/runtime/canonical/preflight request */
export interface CanonicalRuntimePreflightPayload {
  sourceVendor: string;
  targetVendor: string;
  envelope: {
    operationCode: string;
    version?: string;
    direction: string;
    correlationId?: string;
    timestamp?: string;
    context?: Record<string, unknown>;
    payload: Record<string, unknown>;
  };
}

/** Runtime Preflight response */
export interface CanonicalRuntimePreflightResponse {
  valid: boolean;
  status: "READY" | "WARN" | "BLOCKED";
  operationCode?: string;
  canonicalVersion?: string;
  sourceVendor?: string;
  targetVendor?: string;
  normalizedEnvelope?: Record<string, unknown>;
  checks?: Array<{ code: string; status: string; message: string }>;
  executionPlan?: { mode: string; canExecute: boolean; nextStep?: string };
  errors?: Array<{ field: string; message: string }>;
  notes?: string[];
}

/** POST /v1/runtime/canonical/preflight */
export async function runCanonicalRuntimePreflight(
  body: CanonicalRuntimePreflightPayload
): Promise<CanonicalRuntimePreflightResponse> {
  const { data } = await adminApi.post<CanonicalRuntimePreflightResponse>(
    "/v1/runtime/canonical/preflight",
    body
  );
  return data;
}

/** Canonical Bridge Execute: POST /v1/runtime/canonical/execute request */
export interface CanonicalBridgePayload {
  sourceVendor: string;
  targetVendor: string;
  mode: "DRY_RUN" | "EXECUTE";
  envelope: {
    operationCode: string;
    version?: string;
    direction: string;
    correlationId?: string;
    timestamp?: string;
    context?: Record<string, unknown>;
    payload: Record<string, unknown>;
  };
}

/** Canonical Bridge Execute response */
export interface CanonicalBridgeResponse {
  mode: "DRY_RUN" | "EXECUTE";
  valid: boolean;
  status: string;
  operationCode?: string;
  canonicalVersion?: string;
  sourceVendor?: string;
  targetVendor?: string;
  normalizedEnvelope?: Record<string, unknown>;
  preflight?: CanonicalRuntimePreflightResponse;
  executeRequestPreview?: Record<string, unknown>;
  executionPlan?: { canExecute?: boolean; reason?: string };
  executeResult?: { statusCode?: number; body?: unknown; error?: string };
  errors?: Array<{ field: string; message: string }>;
  notes?: string[];
}

/** POST /v1/runtime/canonical/execute */
export async function runCanonicalBridgeExecution(
  body: CanonicalBridgePayload
): Promise<CanonicalBridgeResponse> {
  const { data } = await adminApi.post<CanonicalBridgeResponse>(
    "/v1/runtime/canonical/execute",
    body
  );
  return data;
}

/** Admin: GET /v1/registry/contracts with optional filters */
export async function adminListContracts(filters?: {
  operationCode?: string;
  canonicalVersion?: string;
  isActive?: boolean;
}): Promise<RegistryContract[]> {
  const { items } = await listContracts(filters);
  return items;
}

/** Readiness report item (per operation) */
export interface ReadinessItem {
  vendorCode: string;
  operationCode: string;
  checks: Array<{ name: string; ok: boolean; details?: Record<string, unknown> }>;
  overallOk: boolean;
}

/** GET /v1/registry/readiness?vendorCode=X&operationCode=Y (operationCode optional) */
export async function getReadiness(vendorCode: string, operationCode?: string): Promise<
  | { vendorCode: string; operationCode?: string; items?: ReadinessItem[]; checks?: ReadinessItem["checks"]; overallOk?: boolean }
> {
  const q = new URLSearchParams();
  q.set("vendorCode", vendorCode);
  if (operationCode) q.set("operationCode", operationCode);
  const { data } = await adminApi.get<{
    vendorCode: string;
    operationCode?: string;
    items?: ReadinessItem[];
    checks?: ReadinessItem["checks"];
    overallOk?: boolean;
  }>(`/v1/registry/readiness?${q.toString()}`);
  return data;
}

/** Batch readiness item: either full readiness or per-op items + optional error */
export interface BatchReadinessItem {
  vendorCode: string;
  operationCode?: string;
  items?: ReadinessItem[];
  checks?: ReadinessItem["checks"];
  overallOk?: boolean;
  error?: { code: string; message: string };
}

/** POST /v1/registry/readiness/batch response */
export interface BatchReadinessResponse {
  items: BatchReadinessItem[];
}

/** POST /v1/registry/readiness/batch - batch readiness for multiple vendors */
export async function getBatchReadiness(
  vendorCodes: string[],
  operationCode?: string
): Promise<BatchReadinessResponse> {
  const { data } = await adminApi.post<BatchReadinessResponse>(
    "/v1/registry/readiness/batch",
    { vendorCodes, operationCode }
  );
  return data;
}

/** Admin: POST /v1/registry/contracts (upsert) */
export async function adminUpsertContract(payload: {
  operation_code: string;
  canonical_version: string;
  request_schema: Record<string, unknown>;
  response_schema?: Record<string, unknown> | null;
  is_active?: boolean;
}): Promise<{ contract: RegistryContract }> {
  return upsertContract(payload);
}

/** POST /v1/registry/contracts */
export async function upsertContract(
  payload: {
    operation_code: string;
    canonical_version: string;
    request_schema: Record<string, unknown>;
    response_schema?: Record<string, unknown> | null;
    is_active?: boolean;
  }
): Promise<{ contract: RegistryContract }> {
  const { data } = await adminApi.post<{ contract: RegistryContract }>(
    "/v1/registry/contracts",
    payload
  );
  return data;
}

function buildListParams(
  params: ListRegistryParams | undefined,
  keys: (keyof ListRegistryParams)[]
): string {
  if (!params) return "";
  const q = new URLSearchParams();
  for (const k of keys) {
    const v = params[k];
    if (v === undefined || v === null || v === "") continue;
    if (k === "limit") {
      const parsed = Number(v);
      if (!Number.isFinite(parsed)) continue;
      const clamped = Math.max(1, Math.min(REGISTRY_MAX_LIMIT, Math.trunc(parsed)));
      q.set(k, String(clamped));
      continue;
    }
    q.set(k, String(v));
  }
  return q.toString();
}

// --- Registry: upsert (POST) ---

/** POST /v1/registry/vendors */
export async function upsertVendor(
  payload: UpsertVendorPayload
): Promise<{ vendor: Vendor }> {
  const body: Record<string, unknown> = {
    vendor_code: payload.vendor_code,
    vendor_name: payload.vendor_name,
  };
  if (payload.is_active !== undefined) {
    body.is_active = payload.is_active;
  }
  const { data } = await adminApi.post<{ vendor: Vendor }>(
    "/v1/registry/vendors",
    body
  );
  return data;
}

/** POST /v1/registry/operations */
export async function upsertOperation(
  payload: UpsertOperationPayload
): Promise<{ operation: Operation }> {
  const body: Record<string, unknown> = {
    operation_code: payload.operation_code,
    description: payload.description,
    canonical_version: payload.canonical_version,
    is_async_capable: payload.is_async_capable,
    is_active: payload.is_active,
  };
  if (payload.direction_policy) {
    body.direction_policy = payload.direction_policy;
  } else if (payload.hub_direction_policy) {
    body.direction_policy = payload.hub_direction_policy;
  }
  if (payload.ai_presentation_mode) {
    body.ai_presentation_mode = payload.ai_presentation_mode;
  }
  if (payload.ai_formatter_prompt !== undefined) {
    body.ai_formatter_prompt = payload.ai_formatter_prompt;
  }
  if (payload.ai_formatter_model !== undefined) {
    body.ai_formatter_model = payload.ai_formatter_model;
  }
  const { data } = await adminApi.post<{ operation: Operation }>(
    "/v1/registry/operations",
    body
  );
  return data;
}

/** POST /v1/registry/operations/{operationCode}/canonical-version - set default version */
export async function setOperationCanonicalVersion(
  operationCode: string,
  canonicalVersion: string
): Promise<{ operationCode: string; canonicalVersion: string; updatedAt?: string }> {
  const { data } = await adminApi.post<{
    operationCode: string;
    canonicalVersion: string;
    updatedAt?: string;
  }>(
    `/v1/registry/operations/${encodeURIComponent(operationCode)}/canonical-version`,
    { canonicalVersion }
  );
  return data;
}

/** POST /v1/registry/allowlist */
export async function upsertAllowlist(
  payload: UpsertAllowlistPayload
): Promise<{ allowlist: AllowlistEntry }> {
  const body: Record<string, unknown> = {
    operation_code: payload.operation_code,
  };
  if (payload.source_vendor_codes?.length) {
    body.source_vendor_codes = payload.source_vendor_codes;
  } else if (payload.source_vendor_code) {
    body.source_vendor_code = payload.source_vendor_code;
  }
  if (payload.target_vendor_codes?.length) {
    body.target_vendor_codes = payload.target_vendor_codes;
  } else if (payload.target_vendor_code) {
    body.target_vendor_code = payload.target_vendor_code;
  }
  if (payload.flow_direction) {
    body.flow_direction = payload.flow_direction;
  }
  const { data } = await adminApi.post<{ allowlist: AllowlistEntry }>(
    "/v1/registry/allowlist",
    body
  );
  return data;
}

// --- Change Requests (admin approvals) ---

export interface ChangeRequestItem {
  id: string;
  requestType: string;
  vendorCode?: string;
  requestingVendorCode?: string;
  sourceVendorCode?: string;
  targetVendorCode?: string;
  targetVendorCodes?: string[];
  useWildcardTarget?: boolean;
  operationCode?: string;
  flowDirection?: string;
  direction?: string;
  ruleScope?: string;
  status: string;
  requestedBy?: string;
  requestedVia?: string;
  reviewedBy?: string;
  decisionReason?: string;
  summary?: { title?: string; source_vendor?: string; target_vendor?: string };
  createdAt?: string;
  updatedAt?: string;
  payload?: Record<string, unknown>;
  rawPayload?: Record<string, unknown>;
}

// --- Feature Gates (vendor change approvals) ---

export interface FeatureGate {
  gateKey: string;
  enabled: boolean;
  description: string;
  updatedAt?: string | null;
}

export interface PlatformFeatureItem {
  featureCode: string;
  description?: string | null;
  isEnabled: boolean | null;
  overrideState: "INHERIT" | "ENABLED" | "DISABLED";
  phaseEnabled: boolean;
  effectiveEnabled: boolean;
}

export interface PlatformFeaturesResponse {
  currentPhase: string | null;
  features: PlatformFeatureItem[];
  effectiveFeatures: Record<string, boolean>;
}

export interface PlatformPhase {
  phaseCode: string;
  phaseName: string;
  description?: string | null;
  features: Array<{ featureCode: string; isEnabled: boolean }>;
}

/** GET /v1/registry/feature-gates - returns array of feature gates */
export async function listFeatureGates(): Promise<FeatureGate[]> {
  const { data } = await adminApi.get<FeatureGate[] | { items: FeatureGate[] }>(
    "/v1/registry/feature-gates"
  );
  if (Array.isArray(data)) return data;
  return (data as { items?: FeatureGate[] })?.items ?? [];
}

/** PUT /v1/registry/feature-gates/{gateKey} - update enabled */
export async function updateFeatureGate(gateKey: string, enabled: boolean): Promise<FeatureGate> {
  const { data } = await adminApi.put<FeatureGate>(
    `/v1/registry/feature-gates/${encodeURIComponent(gateKey)}`,
    { enabled }
  );
  return data;
}

/** GET /v1/registry/platform/features */
export async function getAdminPlatformFeatures(): Promise<PlatformFeaturesResponse> {
  const { data } = await adminApi.get<PlatformFeaturesResponse>(
    "/v1/registry/platform/features"
  );
  return data;
}

/** GET /v1/registry/platform/phases */
export async function getAdminPlatformPhases(): Promise<PlatformPhase[]> {
  const { data } = await adminApi.get<{ items?: PlatformPhase[] } | PlatformPhase[]>(
    "/v1/registry/platform/phases"
  );
  if (Array.isArray(data)) return data;
  return data?.items ?? [];
}

/** PUT /v1/registry/platform/settings/current-phase */
export async function updateCurrentPlatformPhase(phaseCode: string): Promise<{
  currentPhase: string;
  effectiveFeatures: Record<string, boolean>;
}> {
  const { data } = await adminApi.put<{
    currentPhase: string;
    effectiveFeatures: Record<string, boolean>;
  }>("/v1/registry/platform/settings/current-phase", { phaseCode });
  return data;
}

/** PUT /v1/registry/platform/features/{featureCode} */
export async function updatePlatformFeatureOverride(
  featureCode: string,
  payload: { isEnabled: boolean | null; description?: string | null }
): Promise<{
  featureCode: string;
  isEnabled: boolean | null;
  description?: string | null;
  effectiveEnabled: boolean;
}> {
  const { data } = await adminApi.put<{
    featureCode: string;
    isEnabled: boolean | null;
    description?: string | null;
    effectiveEnabled: boolean;
  }>(
    `/v1/registry/platform/features/${encodeURIComponent(featureCode)}`,
    payload
  );
  return data;
}

/** GET /v1/registry/change-requests?status=PENDING&vendorCode=&source=allowlist */
export async function listChangeRequests(params?: {
  status?: string;
  vendorCode?: string;
  requestType?: string;
  source?: "allowlist" | "vendor";
  limit?: number;
}): Promise<{ items: ChangeRequestItem[] }> {
  const q = new URLSearchParams();
  if (params?.status) q.set("status", params.status);
  if (params?.vendorCode) q.set("vendorCode", params.vendorCode);
  if (params?.requestType) q.set("requestType", params.requestType);
  if (params?.source) q.set("source", params.source);
  if (params?.limit != null) q.set("limit", String(params.limit));
  const url = q.toString() ? `/v1/registry/change-requests?${q.toString()}` : "/v1/registry/change-requests?status=PENDING";
  const { data } = await adminApi.get<{ items: ChangeRequestItem[] }>(url);
  return { items: data?.items ?? [] };
}

/** POST /v1/registry/change-requests/{id}/approve */
export async function approveChangeRequest(id: string): Promise<{ id: string; status: string; appliedAt?: string }> {
  const { data } = await adminApi.post<{ id: string; status: string; appliedAt?: string }>(
    `/v1/registry/change-requests/${encodeURIComponent(id)}/approve`
  );
  return data;
}

/** POST /v1/registry/change-requests/{id}/reject */
export async function rejectChangeRequest(id: string, reason?: string): Promise<{ id: string; status: string }> {
  const { data } = await adminApi.post<{ id: string; status: string }>(
    `/v1/registry/change-requests/${encodeURIComponent(id)}/reject`,
    reason != null ? { reason } : undefined
  );
  return data;
}

/** POST /v1/registry/change-requests/{id}/decision - unified approve/reject */
export async function decideChangeRequest(
  id: string,
  action: "APPROVE" | "REJECT",
  reason?: string
): Promise<{ id: string; status: string; decidedAt?: string }> {
  const { data } = await adminApi.post<{ id: string; status: string; decidedAt?: string }>(
    `/v1/registry/change-requests/${encodeURIComponent(id)}/decision`,
    { action, reason }
  );
  return data;
}

/** DELETE /v1/registry/allowlist/{id} */
export async function deleteAllowlist(id: string): Promise<{ deleted: boolean; id: string }> {
  const { data } = await adminApi.delete<{ deleted: boolean; id: string }>(
    `/v1/registry/allowlist/${encodeURIComponent(id)}`
  );
  return data;
}

/** POST /v1/registry/endpoints */
export async function upsertEndpoint(
  payload: UpsertEndpointPayload
): Promise<{ endpoint: Endpoint }> {
  const body: Record<string, unknown> = {
    vendor_code: payload.vendor_code,
    operation_code: payload.operation_code,
    url: payload.url,
    http_method: payload.http_method,
    payload_format: payload.payload_format,
    timeout_ms: payload.timeout_ms,
    is_active: payload.is_active,
  };
  if (payload.auth_profile_id !== undefined) {
    body.auth_profile_id = payload.auth_profile_id;
  }
  if (payload.flow_direction !== undefined) {
    body.flow_direction = payload.flow_direction;
  }
  const { data } = await adminApi.post<{ endpoint: Endpoint }>(
    "/v1/registry/endpoints",
    body
  );
  return data;
}

// --- Auth Profiles (registry, admin API) ---

export interface AuthProfile {
  id?: string;
  vendorCode: string;
  name: string;
  authType: string;
  config?: Record<string, unknown>;
  isActive?: boolean;
  createdAt?: string;
  updatedAt?: string;
}

export interface TestConnectionRequest {
  authProfileId?: string | null;
  authType: string;
  authConfig: Record<string, unknown>;
  url: string;
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  headers?: Record<string, string>;
  body?: Record<string, unknown> | string | null;
  timeoutMs?: number;
}

export interface TestConnectionResponse {
  ok: boolean;
  httpStatus?: number | null;
  latencyMs: number;
  responsePreview: string;
  error?: { category: string; message: string } | null;
  debug?: {
    resolvedAuth?: {
      type?: string | null;
      appliedHeaders?: Record<string, string>;
      appliedQuery?: Record<string, string>;
    };
  };
}

export interface JwtTokenPreviewResponse {
  ok: boolean;
  tokenRedacted?: string | null;
  tokenLength?: number | null;
  expiresIn?: number | null;
  jwtClaims?: {
    iss?: string;
    aud?: string | string[];
    exp?: number;
    iat?: number;
  } | null;
  cacheDiagnostics?: {
    cacheKeyHash?: string;
    expiresAt?: string | null;
    lastFetchedAt?: string | null;
    fromCache?: boolean;
  } | null;
  error?: { category: string; message: string } | null;
}

export interface MtlsValidateResponse {
  ok: boolean;
  expiresAt?: string | null;
  daysRemaining?: number | null;
  subject?: string | null;
  issuer?: string | null;
  sans?: string[];
  warnings?: string[];
  error?: { category: string; message: string } | null;
}

/** GET /v1/registry/auth-profiles?vendorCode=&isActive= (vendorCode optional) */
export async function listAuthProfiles(
  vendorCode?: string,
  params?: { limit?: number; cursor?: string; isActive?: boolean }
): Promise<{ items: AuthProfile[]; nextCursor?: string | null }> {
  const q = new URLSearchParams();
  if (vendorCode && vendorCode.trim()) q.set("vendorCode", vendorCode.trim());
  if (params?.isActive !== undefined) q.set("isActive", String(params.isActive));
  if (params?.limit != null) q.set("limit", String(params.limit));
  if (params?.cursor) q.set("cursor", params.cursor);
  const url = q.toString() ? `/v1/registry/auth-profiles?${q.toString()}` : "/v1/registry/auth-profiles";
  const { data } = await adminApi.get<{ items: AuthProfile[]; nextCursor?: string | null }>(url);
  return { items: data?.items ?? [], nextCursor: data?.nextCursor ?? null };
}

/** DELETE /v1/registry/auth-profiles/{id} - soft delete */
export async function deleteAuthProfile(id: string): Promise<{ id: string; isActive: boolean }> {
  const { data } = await adminApi.delete<{ id: string; isActive: boolean }>(
    `/v1/registry/auth-profiles/${encodeURIComponent(id)}`
  );
  return data;
}

/** Alias for listAuthProfiles - GET /v1/registry/auth-profiles?vendorCode=... */
export const fetchAuthProfiles = listAuthProfiles;

/** POST /v1/registry/auth-profiles */
export async function upsertAuthProfile(payload: {
  id?: string;
  vendorCode: string;
  name: string;
  authType: string;
  config?: Record<string, unknown>;
  isActive?: boolean;
}): Promise<{ authProfile: AuthProfile }> {
  const { data } = await adminApi.post<{ item?: AuthProfile; authProfile?: AuthProfile }>(
    "/v1/registry/auth-profiles",
    payload
  );
  return { authProfile: data.item ?? data.authProfile! };
}

export async function testAuthProfileConnection(
  payload: TestConnectionRequest
): Promise<TestConnectionResponse> {
  const { data } = await adminApi.post<TestConnectionResponse>(
    "/v1/registry/auth-profiles/test-connection",
    payload
  );
  return data;
}

export async function previewAuthProfileToken(payload: {
  authType: string;
  authConfig: Record<string, unknown>;
  timeoutMs?: number;
}): Promise<JwtTokenPreviewResponse> {
  const { data } = await adminApi.post<JwtTokenPreviewResponse>(
    "/v1/registry/auth-profiles/token-preview",
    payload
  );
  return data;
}

export async function validateAuthProfileMtls(payload: {
  certificatePem: string;
  privateKeyPem: string;
  caBundlePem?: string | null;
}): Promise<MtlsValidateResponse> {
  const { data } = await adminApi.post<MtlsValidateResponse>(
    "/v1/registry/auth-profiles/mtls-validate",
    payload
  );
  return data;
}

/** Create auth profile - POST /v1/registry/auth-profiles (same as upsertAuthProfile) */
export const createAuthProfile = upsertAuthProfile;

// --- Vendor Config (vendor portal, vendor_code derived from key) ---

export interface VendorListResponse<T> {
  items: T[];
  nextCursor?: string | null;
}

/** GET /v1/vendor/operations-catalog */
export async function getVendorOperationsCatalog(): Promise<
  VendorListResponse<VendorOperationCatalogItem>
> {
  const { data } = await vendorApi.get<VendorListResponse<VendorOperationCatalogItem>>(
    "/v1/vendor/operations-catalog"
  );
  return data;
}

/** GET /v1/vendor/supported-operations */
export async function getVendorSupportedOperations(): Promise<
  VendorListResponse<VendorSupportedOperation>
> {
  const { data } = await vendorApi.get<VendorListResponse<VendorSupportedOperation>>(
    "/v1/vendor/supported-operations"
  );
  return data;
}

/** POST /v1/vendor/supported-operations */
export async function upsertVendorSupportedOperation(
  payload: { operationCode: string; isActive?: boolean }
): Promise<{ item: VendorSupportedOperation }> {
  const { data } = await vendorApi.post<{ item: VendorSupportedOperation }>(
    "/v1/vendor/supported-operations",
    payload
  );
  return data;
}

/** GET /v1/vendor/endpoints */
export async function getVendorEndpoints(): Promise<VendorListResponse<VendorEndpoint>> {
  const { data } = await vendorApi.get<VendorListResponse<VendorEndpoint>>(
    "/v1/vendor/endpoints"
  );
  return data;
}

/** POST /v1/vendor/endpoints */
export async function upsertVendorEndpoint(
  payload: {
    operationCode: string;
    url: string;
    httpMethod?: string;
    payloadFormat?: string;
    timeoutMs?: number;
    isActive?: boolean;
    authProfileId?: string | null;
    verificationRequest?: Record<string, unknown> | null;
  }
): Promise<{ endpoint: VendorEndpoint }> {
  const { data } = await vendorApi.post<{ endpoint: VendorEndpoint }>(
    "/v1/vendor/endpoints",
    payload
  );
  return data;
}

/** POST /v1/vendor/endpoints/verify */
export async function verifyVendorEndpoint(payload: {
  operationCode: string;
}): Promise<{ endpoint: VendorEndpoint }> {
  const { data } = await vendorApi.post<{ endpoint: VendorEndpoint }>(
    "/v1/vendor/endpoints/verify",
    payload
  );
  return data;
}

/** GET /v1/vendor/contracts */
export async function getVendorContracts(): Promise<VendorListResponse<VendorContract>> {
  const { data } = await vendorApi.get<VendorListResponse<VendorContract>>(
    "/v1/vendor/contracts"
  );
  return data;
}

/** POST /v1/vendor/contracts */
export async function upsertVendorContract(
  payload: {
    operationCode: string;
    canonicalVersion?: string;
    requestSchema?: Record<string, unknown>;
    responseSchema?: Record<string, unknown>;
    isActive?: boolean;
  }
): Promise<{ contract: VendorContract }> {
  const { data } = await vendorApi.post<{ contract: VendorContract }>(
    "/v1/vendor/contracts",
    payload
  );
  return data;
}

/** GET /v1/vendor/mappings */
export async function getVendorMappings(params?: {
  operationCode?: string;
  canonicalVersion?: string;
}): Promise<{ mappings: VendorMapping[] }> {
  const q = new URLSearchParams();
  if (params?.operationCode) q.set("operationCode", params.operationCode);
  if (params?.canonicalVersion) q.set("canonicalVersion", params.canonicalVersion);
  const query = q.toString();
  const { data } = await vendorApi.get<{ mappings: VendorMapping[] }>(
    `/v1/vendor/mappings${query ? `?${query}` : ""}`
  );
  return data;
}

/** POST /v1/vendor/mappings */
export async function upsertVendorMapping(
  payload: {
    operationCode: string;
    canonicalVersion: string;
    direction: MappingDirection;
    mapping: Record<string, unknown>;
    isActive?: boolean;
  }
): Promise<{ mapping: VendorMapping }> {
  const { data } = await vendorApi.post<{ mapping: VendorMapping }>(
    "/v1/vendor/mappings",
    payload
  );
  return data;
}

/** POST /v1/onboarding/register (first-time registration) */
export async function onboardVendor(
  payload: OnboardVendorPayload
): Promise<OnboardVendorResponse> {
  const body: Record<string, unknown> = {
    vendorCode: payload.vendorCode,
    vendorName: payload.vendorName,
  };
  if (payload.forceRotate !== undefined) {
    body.forceRotate = payload.forceRotate;
  }
  const { data } = await vendorApiPublic.post<OnboardVendorResponse>(
    "/v1/onboarding/register",
    body
  );
  return data;
}
