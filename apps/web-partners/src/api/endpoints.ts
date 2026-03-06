import { vendorApi, vendorApiPublic, runtimeApi } from "./client";
import type {
  AllowlistEntry,
  Vendor,
  Operation,
  RegistryContract,
  VendorOperationCatalogItem,
  VendorSupportedOperation,
  VendorEndpoint,
  VendorContract,
  VendorMapping,
  MappingDirection,
  UpsertAllowlistPayload,
  OnboardVendorPayload,
  OnboardVendorResponse,
  ExecuteIntegrationPayload,
  ExecuteIntegrationResponse,
  AiExecuteEnvelope,
} from "frontend-shared";

export interface ListRegistryParams {
  limit?: number;
  cursor?: string;
  vendorCode?: string;
  operationCode?: string;
  canonicalVersion?: string;
  sourceVendorCode?: string;
  targetVendorCode?: string;
  isActive?: boolean;
}

export interface ListRegistryResponse<T> {
  items: T[];
  nextCursor: string | null;
}

export interface VendorListResponse<T> {
  items: T[];
  nextCursor?: string | null;
}

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

export interface VendorPlatformFeaturesResponse {
  currentPhase: string | null;
  effectiveFeatures: Record<string, boolean>;
}

function buildListParams(
  params: ListRegistryParams | undefined,
  keys: (keyof ListRegistryParams)[],
): string {
  if (!params) return "";
  const q = new URLSearchParams();
  for (const k of keys) {
    const v = params[k];
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  }
  return q.toString();
}

// --- Vendor API (allowlist, vendors, operations, auth profiles) ---

export interface MyAllowlistEntry {
  id?: string;
  sourceVendor: string;
  targetVendor: string;
  operation: string;
  createdAt?: string;
}

export type AccessOutcome =
  | "ALLOWED_BY_ADMIN"
  | "ALLOWED_NARROWED_BY_VENDOR"
  | "BLOCKED_BY_ADMIN";

export interface EligibleOperationItem {
  operationCode: string;
  canCallOutbound: boolean;
  canReceiveInbound: boolean;
  eligibleByWildcard?: boolean;
  hasVendorOutboundRule?: boolean;
  hasVendorInboundRule?: boolean;
  accessOutcomeOutbound?: AccessOutcome;
  accessOutcomeInbound?: AccessOutcome;
  accessStatusOutbound?: "ALLOWED" | "BLOCKED";
  accessStatusInbound?: "ALLOWED" | "BLOCKED";
}

export interface AccessOutcomeItem {
  operationCode: string;
  direction: "OUTBOUND" | "INBOUND";
  accessOutcome: AccessOutcome;
  accessStatus: "ALLOWED" | "BLOCKED";
  /** When ALLOWED_NARROWED_BY_VENDOR: count of vendor-selected callers. */
  vendorNarrowedCount?: number;
  /** When ALLOWED_NARROWED_BY_VENDOR: count of admin-allowed callers. */
  adminEnvelopeCount?: number;
}

export interface MyAllowlistResponse {
  outbound: MyAllowlistEntry[];
  inbound: MyAllowlistEntry[];
  eligibleOperations?: EligibleOperationItem[];
  accessOutcomes?: AccessOutcomeItem[];
}

export interface EligibleAccessResponse {
  outboundTargets: string[];
  inboundSources: string[];
  canUseWildcardOutbound: boolean;
  canUseWildcardInbound: boolean;
  /** True when admin has no rules allowing any partner for this op */
  isBlockedByAdmin?: boolean;
}

/** Vendor change request (approval flow) */
export interface VendorChangeRequestItem {
  id: string;
  requestType: string;
  status: string;
  requestingVendorCode?: string;
  targetVendorCode?: string;
  operationCode?: string;
  flowDirection?: string;
  summary?: { title?: string };
  createdAt?: string;
  updatedAt?: string;
}

/** GET /v1/vendor/my-change-requests?status=PENDING&limit= */
export async function getVendorChangeRequests(params?: {
  status?: string;
  limit?: number;
}): Promise<{ items: VendorChangeRequestItem[] }> {
  const q = new URLSearchParams();
  if (params?.status) q.set("status", params.status);
  if (params?.limit != null) q.set("limit", String(params.limit));
  const query = q.toString();
  const { data } = await vendorApi.get<{ items: VendorChangeRequestItem[] }>(
    `/v1/vendor/my-change-requests${query ? `?${query}` : ""}`
  );
  return { items: data?.items ?? [] };
}

export async function getMyAllowlist(): Promise<MyAllowlistResponse> {
  const { data } = await vendorApi.get<MyAllowlistResponse>(
    "/v1/vendor/my-allowlist",
  );
  return data;
}

/** GET /v1/vendor/platform/features */
export async function getVendorPlatformFeatures(): Promise<VendorPlatformFeaturesResponse> {
  const { data } = await vendorApi.get<VendorPlatformFeaturesResponse>(
    "/v1/vendor/platform/features",
  );
  return data;
}

export async function getEligibleAccess(
  operationCode: string,
  direction?: "outbound" | "inbound"
): Promise<EligibleAccessResponse> {
  const qs = new URLSearchParams({ operationCode });
  if (direction) qs.set("direction", direction);
  const { data } = await vendorApi.get<EligibleAccessResponse>(
    `/v1/vendor/eligible-access?${qs}`,
  );
  return data;
}

/** Provider narrowing (PROVIDER_RECEIVES_ONLY): admin envelope + vendor whitelist */
export interface ProviderNarrowingResponse {
  operationCode: string;
  adminEnvelope: string[];
  vendorWhitelist: string[];
}

/** POST provider-narrowing: caller perspective - candidates the vendor can request to call */
export interface ProviderNarrowingCandidate {
  vendorCode: string;
  vendorName: string;
  allowedByAdmin: boolean;
  hasVendorRule: boolean;
  requestable: boolean;
  currentScope: "WILDCARD" | "VENDOR_ONLY";
}

export interface ProviderNarrowingCandidatesResponse {
  operationCode: string;
  callerVendorCodes: string[];
  candidates: ProviderNarrowingCandidate[];
}

export async function getProviderNarrowing(
  operationCode: string
): Promise<ProviderNarrowingResponse> {
  const qs = new URLSearchParams({ operationCode });
  const { data } = await vendorApi.get<ProviderNarrowingResponse>(
    `/v1/vendor/provider-narrowing?${qs}`,
  );
  return data;
}

export async function postProviderNarrowingCandidates(
  operationCode: string,
  callerVendorCodes: string[]
): Promise<ProviderNarrowingCandidatesResponse> {
  const { data } = await vendorApi.post<ProviderNarrowingCandidatesResponse>(
    "/v1/vendor/provider-narrowing",
    { operationCode, callerVendorCodes },
  );
  return data;
}

export async function putProviderNarrowing(
  operationCode: string,
  callerVendorCodes: string[]
): Promise<{ operationCode: string; callerVendorCodes: string[] }> {
  const { data } = await vendorApi.put<{
    operationCode: string;
    callerVendorCodes: string[];
  }>("/v1/vendor/provider-narrowing", {
    operationCode,
    callerVendorCodes,
  });
  return data;
}

/** Contract status for a row. */
export type ContractStatus = "OK" | "MISSING" | "INACTIVE";
/** Mapping status for a row (legacy aggregate). */
export type MappingStatus =
  | "OK"
  | "MISSING_REQUEST"
  | "MISSING_RESPONSE"
  | "MISSING_BOTH"
  | "OPTIONAL_MISSING_REQUEST"
  | "OPTIONAL_MISSING_RESPONSE"
  | "OPTIONAL_MISSING_BOTH";

/** Per-direction mapping status: ok | warning_optional_missing | error_required_missing */
export type MappingStatusDetail =
  | "ok"
  | "warning_optional_missing"
  | "error_required_missing";
/** Endpoint status for a row. */
export type EndpointStatus = "OK" | "MISSING" | "UNVERIFIED";
/** Allowlist status for a row. */
export type AllowlistStatus = "OK" | "MISSING";

/** Per-operation mapping status item (Contracts overview). */
export interface OperationMappingStatusItem {
  operationCode: string;
  canonicalVersion: string;
  requiresRequestMapping: boolean;
  requiresResponseMapping: boolean;
  requestMappingStatus: MappingStatusDetail;
  responseMappingStatus: MappingStatusDetail;
}

/** My Operations flow readiness item (outbound or inbound). */
export interface MyOperationItem {
  operationCode: string;
  canonicalVersion: string;
  partnerVendorCode: string;
  direction: "outbound" | "inbound";
  hasCanonicalOperation: boolean;
  hasVendorContract: boolean;
  hasRequestMapping: boolean;
  hasResponseMapping: boolean;
  /** True when mapping is configured (explicit or canonical pass-through). */
  mappingConfigured?: boolean;
  /** True when mapping is configured (explicit mappings or canonical pass-through for both). */
  effectiveMappingConfigured?: boolean;
  /** "vendor_mapping" or "canonical_pass_through" – same semantics as Flow Test. */
  mappingRequestSource?: "vendor_mapping" | "canonical_pass_through";
  /** "vendor_mapping" or "canonical_pass_through" – same semantics as Flow Test. */
  mappingResponseSource?: "vendor_mapping" | "canonical_pass_through";
  /** True when vendor has explicit request mapping. */
  hasVendorRequestMapping?: boolean;
  /** True when vendor has explicit response mapping. */
  hasVendorResponseMapping?: boolean;
  /** True when both request and response use canonical pass-through (no vendor mapping rows). */
  usesCanonicalPassThrough?: boolean;
  /** True when using canonical request format (no vendor mapping). */
  usesCanonicalRequestMapping?: boolean;
  /** True when using canonical response format (no vendor mapping). */
  usesCanonicalResponseMapping?: boolean;
  requiresRequestMapping?: boolean;
  requiresResponseMapping?: boolean;
  requestMappingStatus?: MappingStatusDetail;
  responseMappingStatus?: MappingStatusDetail;
  hasEndpoint: boolean;
  hasAllowlist: boolean;
  /** Explicit status fields from backend. */
  contractStatus?: ContractStatus;
  mappingStatus?: MappingStatus;
  endpointStatus?: EndpointStatus;
  allowlistStatus?: AllowlistStatus;
  issues: string[];
  status: "ready" | "needs_setup" | "needs_attention" | "admin_pending";
}

export interface MyOperationsResponse {
  outbound: MyOperationItem[];
  inbound: MyOperationItem[];
}

export async function getMyOperations(): Promise<MyOperationsResponse> {
  const { data } = await vendorApi.get<MyOperationsResponse>(
    "/v1/vendor/my-operations",
  );
  return data;
}

/** Config bundle: all vendor config slices in one response */
export interface VendorConfigBundleResponse {
  vendorCode: string;
  contracts: VendorContract[];
  operationsCatalog: VendorOperationCatalogItem[];
  supportedOperations: VendorSupportedOperation[];
  endpoints: VendorEndpoint[];
  mappings: VendorMapping[];
  myAllowlist: MyAllowlistResponse;
  myOperations: MyOperationsResponse;
}

export async function getVendorConfigBundle(): Promise<VendorConfigBundleResponse> {
  const { data } = await vendorApi.get<VendorConfigBundleResponse>(
    "/v1/vendor/config-bundle",
  );
  return data;
}

/** List allowlist - uses getMyAllowlist and filters client-side for backward compat. */
export async function listAllowlist(
  params?: ListRegistryParams,
): Promise<ListRegistryResponse<AllowlistEntry>> {
  const { data } = await vendorApi.get<MyAllowlistResponse>("/v1/vendor/my-allowlist");
  const outbound = data?.outbound ?? [];
  const inbound = data?.inbound ?? [];
  let items: AllowlistEntry[] = [
    ...outbound.map((a) => ({
      id: a.id,
      sourceVendorCode: a.sourceVendor,
      targetVendorCode: a.targetVendor,
      operationCode: a.operation,
      createdAt: a.createdAt,
    })),
    ...inbound.map((a) => ({
      id: a.id,
      sourceVendorCode: a.sourceVendor,
      targetVendorCode: a.targetVendor,
      operationCode: a.operation,
      createdAt: a.createdAt,
    })),
  ];
  const source = params?.sourceVendorCode?.trim().toUpperCase();
  const target = params?.targetVendorCode?.trim().toUpperCase();
  if (source) items = items.filter((a) => a.sourceVendorCode?.toUpperCase() === source);
  if (target) items = items.filter((a) => a.targetVendorCode?.toUpperCase() === target);
  return { items, nextCursor: null };
}

export async function upsertAllowlist(
  payload: UpsertAllowlistPayload & { flow_direction?: string },
): Promise<{ allowlist: AllowlistEntry } | { id: string; status: string }> {
  const body: Record<string, string> = {
    operation_code: payload.operation_code,
  };
  if (payload.source_vendor_code) {
    body.source_vendor_code = payload.source_vendor_code;
  }
  if (payload.target_vendor_code) {
    body.target_vendor_code = payload.target_vendor_code;
  }
  if (payload.flow_direction) {
    body.flow_direction = payload.flow_direction;
  }
  const res = await vendorApi.post<
    | { allowlist: { id?: string; sourceVendorCode?: string; targetVendorCode?: string; operationCode?: string; createdAt?: string } }
    | { id: string; status: string; changeRequestId?: string }
  >("/v1/vendor/allowlist", body);
  const data = res.data;
  if (res.status === 202 && data && "id" in data) {
    return { id: data.id, status: data.status };
  }
  const a = (data as { allowlist?: AllowlistEntry })?.allowlist;
  return {
    allowlist: {
      id: a?.id,
      sourceVendorCode: a?.sourceVendorCode ?? payload.source_vendor_code,
      targetVendorCode: a?.targetVendorCode ?? payload.target_vendor_code,
      operationCode: a?.operationCode ?? payload.operation_code,
      createdAt: (a as { createdAt?: string })?.createdAt,
    },
  };
}

export async function deleteAllowlist(
  id: string,
): Promise<{ deleted: boolean; id: string }> {
  const { data } = await vendorApi.delete<{ deleted: boolean; id: string }>(
    `/v1/vendor/allowlist/${encodeURIComponent(id)}`,
  );
  return data ?? { deleted: true, id };
}

export async function listVendors(
  params?: ListRegistryParams,
): Promise<ListRegistryResponse<Vendor>> {
  const q = new URLSearchParams();
  if (params?.limit != null) q.set("limit", String(params.limit));
  const { data } = await vendorApi.get<{ items: Vendor[] }>(
    `/v1/vendor/canonical/vendors${q.toString() ? `?${q}` : ""}`,
  );
  return { items: data?.items ?? [], nextCursor: null };
}

export async function listOperations(
  params?: ListRegistryParams,
): Promise<ListRegistryResponse<Operation>> {
  const q = buildListParams(params, [
    "limit",
    "cursor",
    "operationCode",
    "isActive",
    "sourceVendorCode",
    "targetVendorCode",
  ]);
  const { data } = await vendorApi.get<ListRegistryResponse<Operation>>(
    `/v1/vendor/canonical/operations${q ? `?${q}` : ""}`,
  );
  const items = data?.items ?? [];
  return { items, nextCursor: data?.nextCursor ?? null };
}

export async function listContracts(
  params?: ListRegistryParams,
): Promise<ListRegistryResponse<RegistryContract>> {
  const q = buildListParams(params, [
    "limit",
    "operationCode",
    "canonicalVersion",
    "isActive",
  ]);
  const { data } = await vendorApi.get<{
    contracts?: RegistryContract[];
    items?: RegistryContract[];
    nextCursor?: string | null;
  }>(`/v1/vendor/canonical/contracts${q ? `?${q}` : ""}`);
  const items = data?.contracts ?? data?.items ?? [];
  return { items, nextCursor: data?.nextCursor ?? null };
}

export async function listAuthProfiles(
  _vendorCode?: string,
  _params?: { limit?: number; cursor?: string; isActive?: boolean },
): Promise<{ items: AuthProfile[]; nextCursor?: string | null }> {
  const { data } = await vendorApi.get<{ items: AuthProfile[] }>(
    "/v1/vendor/auth-profiles",
  );
  return { items: data?.items ?? [], nextCursor: null };
}

export async function upsertAuthProfile(payload: {
  id?: string;
  vendorCode: string;
  name: string;
  authType: string;
  config?: Record<string, unknown>;
  isActive?: boolean;
}): Promise<{ authProfile: AuthProfile }> {
  const { data } = await vendorApi.post<{
    authProfile?: AuthProfile;
    item?: AuthProfile;
  }>("/v1/vendor/auth-profiles", payload);
  return { authProfile: data?.authProfile ?? data?.item! };
}

export async function deleteAuthProfile(
  id: string,
): Promise<{ id: string; isActive: boolean }> {
  const { data } = await vendorApi.delete<{ id: string; isActive: boolean }>(
    `/v1/vendor/auth-profiles/${encodeURIComponent(id)}`,
  );
  return data ?? { id, isActive: false };
}

export async function testAuthProfileConnection(
  payload: TestConnectionRequest
): Promise<TestConnectionResponse> {
  const { data } = await vendorApi.post<TestConnectionResponse>(
    "/v1/vendor/auth-profiles/test-connection",
    payload
  );
  return data;
}

export async function previewAuthProfileToken(payload: {
  authType: string;
  authConfig: Record<string, unknown>;
  timeoutMs?: number;
}): Promise<JwtTokenPreviewResponse> {
  const { data } = await vendorApi.post<JwtTokenPreviewResponse>(
    "/v1/vendor/auth-profiles/token-preview",
    payload
  );
  return data;
}

export async function validateAuthProfileMtls(payload: {
  certificatePem: string;
  privateKeyPem: string;
  caBundlePem?: string | null;
}): Promise<MtlsValidateResponse> {
  const { data } = await vendorApi.post<MtlsValidateResponse>(
    "/v1/vendor/auth-profiles/mtls-validate",
    payload
  );
  return data;
}

// --- Vendor API ---

export async function getVendorOperationsCatalog(): Promise<
  VendorListResponse<VendorOperationCatalogItem>
> {
  const { data } = await vendorApi.get<
    VendorListResponse<VendorOperationCatalogItem>
  >("/v1/vendor/operations-catalog");
  return data;
}

export async function getVendorSupportedOperations(): Promise<
  VendorListResponse<VendorSupportedOperation>
> {
  const { data } = await vendorApi.get<
    VendorListResponse<VendorSupportedOperation>
  >("/v1/vendor/supported-operations");
  return data;
}

export async function upsertVendorSupportedOperation(payload: {
  operationCode: string;
  isActive?: boolean;
  supportsOutbound?: boolean;
  supportsInbound?: boolean;
}): Promise<{ item: VendorSupportedOperation }> {
  const { data } = await vendorApi.post<{
    item: VendorSupportedOperation;
  }>("/v1/vendor/supported-operations", payload);
  return data;
}

export async function deleteVendorSupportedOperation(operationCode: string): Promise<{ deleted: boolean }> {
  const encoded = encodeURIComponent(operationCode);
  const { data } = await vendorApi.delete<{ deleted: boolean }>(
    `/v1/vendor/supported-operations/${encoded}`
  );
  return data;
}

/** PATCH /v1/vendor/operations/{operationCode} - toggle isActive only */
export async function patchVendorOperation(operationCode: string, payload: { isActive: boolean }): Promise<{ item: VendorSupportedOperation }> {
  const encoded = encodeURIComponent(operationCode);
  const { data } = await vendorApi.patch<{ item: VendorSupportedOperation }>(
    `/v1/vendor/operations/${encoded}`,
    payload
  );
  return data;
}

/** DELETE /v1/vendor/operations/{operationCode} - cascade remove all vendor config */
export async function deleteVendorOperation(operationCode: string): Promise<{ operationCode: string }> {
  const encoded = encodeURIComponent(operationCode);
  const { data } = await vendorApi.delete<{ operationCode: string }>(
    `/v1/vendor/operations/${encoded}`
  );
  return data;
}

export async function getVendorEndpoints(): Promise<
  VendorListResponse<VendorEndpoint>
> {
  const { data } = await vendorApi.get<VendorListResponse<VendorEndpoint>>(
    "/v1/vendor/endpoints",
  );
  return data;
}

export async function upsertVendorEndpoint(payload: {
  id?: string;
  operationCode: string;
  url: string;
  flowDirection?: string;
  httpMethod?: string;
  payloadFormat?: string;
  timeoutMs?: number;
  isActive?: boolean;
  authProfileId?: string | null;
  verificationRequest?: Record<string, unknown> | null;
}): Promise<{ endpoint: VendorEndpoint }> {
  const { data } = await vendorApi.post<{ endpoint: VendorEndpoint }>(
    "/v1/vendor/endpoints",
    payload,
  );
  return data;
}

export async function verifyVendorEndpoint(payload: {
  operationCode: string;
  flowDirection?: string;
}): Promise<{ endpoint: VendorEndpoint }> {
  const body: Record<string, string> = { operationCode: payload.operationCode };
  if (payload.flowDirection) {
    body.flowDirection = payload.flowDirection;
  }
  const { data } = await vendorApi.post<{ endpoint: VendorEndpoint }>(
    "/v1/vendor/endpoints/verify",
    body,
  );
  return data;
}

export async function getVendorContracts(): Promise<
  VendorListResponse<VendorContract>
> {
  const { data } = await vendorApi.get<VendorListResponse<VendorContract>>(
    "/v1/vendor/contracts",
  );
  return data;
}

export async function upsertVendorContract(payload: {
  operationCode: string;
  canonicalVersion?: string;
  requestSchema?: Record<string, unknown>;
  responseSchema?: Record<string, unknown>;
  isActive?: boolean;
}): Promise<{ contract: VendorContract } | { id: string; status: string }> {
  const res = await vendorApi.post<{ contract: VendorContract } | { id: string; status: string }>(
    "/v1/vendor/contracts",
    payload,
  );
  if (res.status === 202 && res.data && "id" in res.data) {
    return res.data as { id: string; status: string };
  }
  return res.data as { contract: VendorContract };
}

/** GET /v1/vendor/operations/{operationCode}/{canonicalVersion}/mappings - simplified shape for Visual Builder */
export interface OperationMappingsResponse {
  operationCode: string;
  canonicalVersion: string;
  usesCanonicalRequest?: boolean;
  usesCanonicalResponse?: boolean;
  request: {
    direction: string;
    mapping: Record<string, unknown> | null;
    usesCanonical?: boolean;
  } | null;
  response: {
    direction: string;
    mapping: Record<string, unknown> | null;
    usesCanonical?: boolean;
  } | null;
}

export async function getOperationMappings(
  operationCode: string,
  canonicalVersion: string
): Promise<OperationMappingsResponse> {
  const { data } = await vendorApi.get<OperationMappingsResponse>(
    `/v1/vendor/operations/${encodeURIComponent(operationCode)}/${encodeURIComponent(canonicalVersion)}/mappings`
  );
  return data;
}

/** PUT /v1/vendor/operations/{operationCode}/{canonicalVersion}/mappings */
export async function putOperationMappings(
  operationCode: string,
  canonicalVersion: string,
  payload: {
    useCanonicalRequest?: boolean;
    useCanonicalResponse?: boolean;
    request?: {
      direction?: string;
      mapping?: Record<string, unknown> | null;
      usesCanonical?: boolean;
    };
    response?: {
      direction?: string;
      mapping?: Record<string, unknown> | null;
      usesCanonical?: boolean;
    };
  }
): Promise<
  | OperationMappingsResponse
  | { changeRequestId: string; status: string }
> {
  const res = await vendorApi.put<
    OperationMappingsResponse | { changeRequestId: string; status: string }
  >(
    `/v1/vendor/operations/${encodeURIComponent(operationCode)}/${encodeURIComponent(canonicalVersion)}/mappings`,
    payload
  );
  if (res.status === 202 && res.data && "changeRequestId" in res.data) {
    return res.data as { changeRequestId: string; status: string };
  }
  return res.data as OperationMappingsResponse;
}

export async function getOperationsMappingStatus(): Promise<{
  items: OperationMappingStatusItem[];
}> {
  const { data } = await vendorApi.get<{ items: OperationMappingStatusItem[] }>(
    "/v1/vendor/operations-mapping-status",
  );
  return data ?? { items: [] };
}

export async function getVendorMappings(params?: {
  operationCode?: string;
  canonicalVersion?: string;
}): Promise<{ mappings: VendorMapping[] }> {
  const q = new URLSearchParams();
  if (params?.operationCode) q.set("operationCode", params.operationCode);
  if (params?.canonicalVersion)
    q.set("canonicalVersion", params.canonicalVersion);
  const query = q.toString();
  const { data } = await vendorApi.get<{ mappings: VendorMapping[] }>(
    `/v1/vendor/mappings${query ? `?${query}` : ""}`,
  );
  return data;
}

export async function upsertVendorMapping(payload: {
  operationCode: string;
  canonicalVersion: string;
  direction: MappingDirection;
  mapping: Record<string, unknown>;
  isActive?: boolean;
}): Promise<{ mapping: VendorMapping } | { id: string; status: string }> {
  const res = await vendorApi.post<{ mapping: VendorMapping } | { id: string; status: string }>(
    "/v1/vendor/mappings",
    payload,
  );
  if (res.status === 202 && res.data && "id" in res.data) {
    return res.data as { id: string; status: string };
  }
  return res.data as { mapping: VendorMapping };
}

// --- Vendor Metrics & Transactions ---

export interface VendorMetricsOverview {
  from: string;
  to: string;
  totals: { count: number; completed: number; failed: number };
  byStatus: { status: string; count: number }[];
  byOperation: { operation: string; count: number; failed: number }[];
  timeseries: { bucket: string; count: number; failed: number }[];
}

export async function getVendorMetricsOverview(params: {
  from: string;
  to: string;
}): Promise<VendorMetricsOverview> {
  const q = new URLSearchParams();
  q.set("from", params.from);
  q.set("to", params.to);
  const { data } = await vendorApi.get<VendorMetricsOverview>(
    `/v1/vendor/metrics/overview?${q.toString()}`,
  );
  return data;
}

export interface VendorTransaction {
  id?: string;
  transactionId?: string;
  correlationId?: string;
  sourceVendor?: string;
  targetVendor?: string;
  operation?: string;
  idempotencyKey?: string;
  status?: string;
  createdAt?: string;
}

export interface VendorTransactionsResponse {
  transactions: VendorTransaction[];
  count: number;
  nextCursor?: string | null;
}

export async function listVendorTransactions(params: {
  from: string;
  to: string;
  direction?: "outbound" | "inbound" | "all";
  operation?: string;
  status?: string;
  search?: string;
  limit?: number;
  cursor?: string;
}): Promise<VendorTransactionsResponse> {
  const q = new URLSearchParams();
  q.set("from", params.from);
  q.set("to", params.to);
  if (params.direction && params.direction !== "all")
    q.set("direction", params.direction);
  if (params.operation) q.set("operation", params.operation);
  if (params.status) q.set("status", params.status);
  if (params.search?.trim()) q.set("search", params.search.trim());
  if (params.limit != null) q.set("limit", String(params.limit));
  if (params.cursor) q.set("cursor", params.cursor);
  const { data } = await vendorApi.get<VendorTransactionsResponse>(
    `/v1/vendor/transactions?${q.toString()}`,
  );
  return data;
}

export interface VendorAuditEvent {
  id?: string;
  transactionId?: string;
  action: string;
  vendorCode?: string;
  details?: Record<string, unknown>;
  createdAt?: string;
}

export interface VendorTransactionDetail {
  transactionId?: string;
  correlationId?: string;
  sourceVendor?: string;
  targetVendor?: string;
  operation?: string;
  status?: string;
  idempotencyKey?: string;
  createdAt?: string;
  requestBody?: Record<string, unknown>;
  responseBody?: Record<string, unknown>;
  canonicalRequestBody?: Record<string, unknown>;
  targetRequestBody?: Record<string, unknown>;
  targetResponseBody?: Record<string, unknown>;
  canonicalResponseBody?: Record<string, unknown>;
  errorCode?: string;
  httpStatus?: number;
  retryable?: boolean;
  failureStage?: string;
  parentTransactionId?: string;
  redriveCount?: number;
  canRedrive?: boolean;
  redriveReason?: string;
  auditEvents?: VendorAuditEvent[];
  /** Optional: contract and mapping metadata for UI display */
  contractInfo?: {
    canonicalRequestSchema?: string;
    canonicalResponseSchema?: string;
    vendorRequestSchema?: string;
    vendorResponseSchema?: string;
    requestMapping?: string;
    responseMapping?: string;
  };
}

export interface VendorRedriveResponse {
  transactionId: string;
  correlationId?: string;
  responseBody?: {
    parentTransactionId?: string;
    redriveCount?: number;
    status?: string;
  };
}

export async function getVendorTransactionDetail(
  transactionId: string,
): Promise<VendorTransactionDetail> {
  const { data } = await vendorApi.get<VendorTransactionDetail>(
    `/v1/vendor/transactions/${encodeURIComponent(transactionId)}`,
  );
  return data;
}

export async function postVendorRedrive(
  transactionId: string,
): Promise<VendorRedriveResponse> {
  const { data } = await vendorApi.post<VendorRedriveResponse>(
    `/v1/vendor/transactions/${encodeURIComponent(transactionId)}/redrive`,
    {},
  );
  return data;
}

export async function onboardVendor(
  payload: OnboardVendorPayload,
): Promise<OnboardVendorResponse> {
  const body: Record<string, unknown> = {
    vendorCode: payload.vendorCode,
    vendorName: payload.vendorName,
  };
  if (payload.forceRotate !== undefined) body.forceRotate = payload.forceRotate;
  const { data } = await vendorApiPublic.post<OnboardVendorResponse>(
    "/v1/onboarding/register",
    body,
  );
  return data;
}

/** POST /v1/ai/execute (Runtime API - single source for execute) */
export async function executeAiIntegration(
  payload: ExecuteIntegrationPayload & { aiFormatter?: boolean },
): Promise<AiExecuteEnvelope & ExecuteIntegrationResponse> {
  const body = {
    requestType: "DATA",
    operationCode: payload.operation,
    targetVendorCode: payload.targetVendor,
    payload: payload.parameters ?? {},
    idempotencyKey: payload.idempotencyKey,
    aiFormatter: payload.aiFormatter ?? false,
  };
  const { data } = await runtimeApi.post<AiExecuteEnvelope>(
    "/v1/ai/execute",
    body,
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
    ...data,
    transactionId: (raw?.transactionId as string) ?? data.transactionId ?? "",
    correlationId: (raw?.correlationId as string) ?? data.correlationId,
    responseBody: (raw?.responseBody as Record<string, unknown>) ?? raw,
  };
}

// --- Partner Syntegris API (/v1/vendor/syntegris/*) ---
// Vendor-scoped; sourceVendor derived from JWT. Do NOT send sourceVendor from client.

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

/** POST /v1/sandbox/request/validate response */
export interface SandboxValidateResponse {
  valid: boolean;
  errors?: Array<{ field: string; message: string }>;
  normalizedVersion?: string;
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

/** GET /v1/sandbox/canonical/operations */
export async function listSandboxCanonicalOperations(): Promise<{
  items: CanonicalOperationItem[];
}> {
  const { data } = await vendorApi.get<{ items: CanonicalOperationItem[] }>(
    "/v1/sandbox/canonical/operations",
  );
  return data;
}

/** GET /v1/sandbox/canonical/operations/{operationCode} */
export async function getSandboxCanonicalOperation(
  operationCode: string,
  version?: string,
): Promise<CanonicalOperationDetail> {
  const params = version ? `?version=${encodeURIComponent(version)}` : "";
  const { data } = await vendorApi.get<CanonicalOperationDetail>(
    `/v1/sandbox/canonical/operations/${encodeURIComponent(operationCode)}${params}`,
  );
  return data;
}

/** GET /v1/registry/canonical/operations */
export async function listCanonicalOperations(): Promise<{
  items: CanonicalOperationItem[];
}> {
  const { data } = await vendorApi.get<{ items: CanonicalOperationItem[] }>(
    "/v1/registry/canonical/operations",
  );
  return data;
}

/** GET /v1/registry/canonical/operations/{operationCode} */
export async function getCanonicalOperation(
  operationCode: string,
  version?: string,
): Promise<CanonicalOperationDetail> {
  const params = version ? `?version=${encodeURIComponent(version)}` : "";
  const { data } = await vendorApi.get<CanonicalOperationDetail>(
    `/v1/registry/canonical/operations/${encodeURIComponent(operationCode)}${params}`,
  );
  return data;
}

/** POST /v1/sandbox/request/validate */
export async function validateSandboxRequest(body: {
  operationCode: string;
  version?: string;
  payload: Record<string, unknown>;
}): Promise<SandboxValidateResponse> {
  const { data } = await vendorApi.post<SandboxValidateResponse>(
    "/v1/sandbox/request/validate",
    body,
  );
  return data;
}

/** POST /v1/sandbox/mock/run */
export async function runMockSandboxTest(body: {
  operationCode: string;
  version?: string;
  payload: Record<string, unknown>;
  context?: Record<string, unknown>;
}): Promise<SandboxMockRunResponse> {
  const { data } = await vendorApi.post<SandboxMockRunResponse>(
    "/v1/sandbox/mock/run",
    body,
  );
  return data;
}

/** POST /v1/ai/debug/request/analyze */
export async function analyzeDebugRequest(body: {
  operationCode: string;
  version?: string;
  payload: Record<string, unknown>;
}): Promise<DebugReport> {
  const { data } = await vendorApi.post<DebugReport>(
    "/v1/ai/debug/request/analyze",
    body,
  );
  return data;
}

/** POST /v1/ai/debug/flow-draft/analyze */
export async function analyzeDebugFlowDraft(body: {
  draft: Record<string, unknown>;
}): Promise<DebugReport> {
  const { data } = await vendorApi.post<DebugReport>(
    "/v1/ai/debug/flow-draft/analyze",
    body,
  );
  return data;
}

/** POST /v1/ai/debug/sandbox-result/analyze */
export async function analyzeDebugSandboxResult(body: {
  result: Record<string, unknown>;
}): Promise<DebugReport> {
  const { data } = await vendorApi.post<DebugReport>(
    "/v1/ai/debug/sandbox-result/analyze",
    body,
  );
  return data;
}

/** POST /v1/runtime/canonical/preflight */
export async function runCanonicalRuntimePreflight(
  body: CanonicalRuntimePreflightPayload,
): Promise<CanonicalRuntimePreflightResponse> {
  const { data } = await vendorApi.post<CanonicalRuntimePreflightResponse>(
    "/v1/runtime/canonical/preflight",
    body,
  );
  return data;
}

/** POST /v1/runtime/canonical/execute */
export async function runCanonicalBridgeExecution(
  body: CanonicalBridgePayload,
): Promise<CanonicalBridgeResponse> {
  const { data } = await vendorApi.post<CanonicalBridgeResponse>(
    "/v1/runtime/canonical/execute",
    body,
  );
  return data;
}

// --- Partner Syntegris API (/v1/vendor/syntegris/*) ---
// Vendor-scoped; sourceVendor derived from JWT. Do NOT send sourceVendor from client.

/** GET /v1/vendor/syntegris/canonical/operations */
export async function listPartnerSyntegrisCanonicalOperations(): Promise<{
  items: CanonicalOperationItem[];
}> {
  const { data } = await vendorApi.get<{ items: CanonicalOperationItem[] }>(
    "/v1/vendor/syntegris/canonical/operations",
  );
  return data;
}

/** GET /v1/vendor/syntegris/canonical/operations/{operationCode} */
export async function getPartnerSyntegrisCanonicalOperation(
  operationCode: string,
  version?: string,
): Promise<CanonicalOperationDetail> {
  const params = version ? `?version=${encodeURIComponent(version)}` : "";
  const { data } = await vendorApi.get<CanonicalOperationDetail>(
    `/v1/vendor/syntegris/canonical/operations/${encodeURIComponent(operationCode)}${params}`,
  );
  return data;
}

/** POST /v1/vendor/syntegris/sandbox/request/validate */
export async function validatePartnerSandboxRequest(body: {
  operationCode: string;
  version?: string;
  payload: Record<string, unknown>;
}): Promise<SandboxValidateResponse> {
  const { data } = await vendorApi.post<SandboxValidateResponse>(
    "/v1/vendor/syntegris/sandbox/request/validate",
    body,
  );
  return data;
}

/** POST /v1/vendor/syntegris/sandbox/mock/run */
export async function runPartnerMockSandboxTest(body: {
  operationCode: string;
  version?: string;
  payload: Record<string, unknown>;
  context?: Record<string, unknown>;
}): Promise<SandboxMockRunResponse> {
  const { data } = await vendorApi.post<SandboxMockRunResponse>(
    "/v1/vendor/syntegris/sandbox/mock/run",
    body,
  );
  return data;
}

/** POST /v1/vendor/syntegris/ai/debug/request/analyze */
export async function analyzePartnerDebugRequest(body: {
  operationCode: string;
  version?: string;
  payload: Record<string, unknown>;
}): Promise<DebugReport> {
  const { data } = await vendorApi.post<DebugReport>(
    "/v1/vendor/syntegris/ai/debug/request/analyze",
    body,
  );
  return data;
}

/** POST /v1/vendor/syntegris/ai/debug/flow-draft/analyze */
export async function analyzePartnerDebugFlowDraft(body: {
  draft: Record<string, unknown>;
}): Promise<DebugReport> {
  const { data } = await vendorApi.post<DebugReport>(
    "/v1/vendor/syntegris/ai/debug/flow-draft/analyze",
    body,
  );
  return data;
}

/** POST /v1/vendor/syntegris/ai/debug/sandbox-result/analyze */
export async function analyzePartnerDebugSandboxResult(body: {
  result: Record<string, unknown>;
}): Promise<DebugReport> {
  const { data } = await vendorApi.post<DebugReport>(
    "/v1/vendor/syntegris/ai/debug/sandbox-result/analyze",
    body,
  );
  return data;
}

/** Partner preflight payload - sourceVendor omitted; backend derives from JWT */
export interface PartnerCanonicalPreflightPayload {
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

/** POST /v1/vendor/syntegris/runtime/canonical/preflight */
export async function runPartnerCanonicalPreflight(
  body: PartnerCanonicalPreflightPayload,
): Promise<CanonicalRuntimePreflightResponse> {
  const { data } = await vendorApi.post<CanonicalRuntimePreflightResponse>(
    "/v1/vendor/syntegris/runtime/canonical/preflight",
    body,
  );
  return data;
}

/** Partner bridge payload - sourceVendor omitted; backend derives from JWT */
export interface PartnerCanonicalBridgePayload {
  targetVendor: string;
  mode?: "DRY_RUN" | "EXECUTE";
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

/** POST /v1/vendor/syntegris/runtime/canonical/execute */
export async function runPartnerCanonicalBridgeExecution(
  body: PartnerCanonicalBridgePayload,
): Promise<CanonicalBridgeResponse> {
  const { data } = await vendorApi.post<CanonicalBridgeResponse>(
    "/v1/vendor/syntegris/runtime/canonical/execute",
    body,
  );
  return data;
}

export interface PolicyPreviewCheck {
  passed: boolean;
  reason: string;
}

export interface PolicyPreviewDecision {
  allowed: boolean;
  reason: string;
  checks: {
    jwt: PolicyPreviewCheck;
    allowlist: PolicyPreviewCheck;
    endpoint: PolicyPreviewCheck;
    contracts: PolicyPreviewCheck;
    usageLimit: PolicyPreviewCheck;
    ai: PolicyPreviewCheck;
  };
  whatToFix: string[];
}

export async function previewPolicy(
  operationCode: string,
  targetVendorCode: string,
  aiRequested: boolean,
): Promise<PolicyPreviewDecision> {
  const { data } = await vendorApi.post<PolicyPreviewDecision>(
    "/v1/vendor/policy/preview",
    { operationCode, targetVendorCode, aiRequested },
  );
  return data;
}
