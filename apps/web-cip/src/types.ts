/** Transaction from list or get endpoints */
export interface Transaction {
  id?: number;
  transaction_id: string;
  correlation_id?: string;
  source_vendor?: string;
  target_vendor?: string;
  operation?: string;
  idempotency_key?: string;
  status?: string;
  created_at?: string;
  request_body?: Record<string, unknown>;
  response_body?: Record<string, unknown>;
  /** Debug fields (camelCase from GET /v1/audit/transactions/{id}) */
  canonicalRequestBody?: Record<string, unknown> | null;
  targetRequestBody?: Record<string, unknown> | null;
  targetResponseBody?: Record<string, unknown> | null;
  canonicalResponseBody?: Record<string, unknown> | null;
  errorCode?: string | null;
  httpStatus?: number | null;
  failureStage?: string | null;
  /** Legacy snake_case (list endpoint) */
  canonical_request_body?: Record<string, unknown> | null;
  target_request_body?: Record<string, unknown> | null;
  target_response_body?: Record<string, unknown> | null;
  canonical_response_body?: Record<string, unknown> | null;
  redrive_count?: number;
  parent_transaction_id?: number | null;
}

/** List transactions response */
export interface ListTransactionsResponse {
  transactions: Transaction[];
  count: number;
  nextCursor?: string;
}

/** Audit event (when /v1/audit/events exists, camelCase from API) */
export interface AuditEvent {
  id?: string;
  transactionId: string;
  action: string;
  vendorCode: string;
  details?: Record<string, unknown>;
  createdAt?: string;
}

/** List audit events response (fallback uses transaction only) */
export interface ListAuditEventsResponse {
  events?: AuditEvent[];
  transaction?: Transaction;
}


export interface PolicyDecisionItem {
  id?: string | null;
  occurredAt?: string | null;
  surface?: string | null;
  action?: string | null;
  vendorCode?: string | null;
  targetVendorCode?: string | null;
  operationCode?: string | null;
  decisionCode?: string | null;
  allowed: boolean;
  httpStatus?: number | null;
  correlationId?: string | null;
  transactionId?: string | null;
  metadata?: Record<string, unknown>;
}

export interface ListPolicyDecisionsResponse {
  items: PolicyDecisionItem[];
  nextCursor?: string | null;
  count: number;
}

export interface MissionControlNode {
  vendorCode: string;
  vendorName: string;
}

export interface MissionControlEdge {
  sourceVendorCode: string;
  targetVendorCode: string;
  operationCode: string;
  flowDirection: string;
}

export interface MissionControlTopologyResponse {
  nodes: MissionControlNode[];
  edges: MissionControlEdge[];
}

export type MissionControlStage =
  | "EXECUTE_START"
  | "EXECUTE_SUCCESS"
  | "EXECUTE_ERROR"
  | "POLICY_DENY";

export interface MissionControlActivityEvent {
  ts: string | null;
  transactionId?: string | null;
  correlationId?: string | null;
  sourceVendorCode?: string | null;
  targetVendorCode?: string | null;
  operationCode?: string | null;
  stage: MissionControlStage;
  decisionCode?: string | null;
  statusCode?: number | null;
  latencyMs?: number | null;
}

export interface MissionControlActivityResponse {
  items: MissionControlActivityEvent[];
  count: number;
  lookbackMinutes: number;
}

export interface PolicySimulationResult {
  allowed: boolean;
  decisionCode: string;
  httpStatus: number;
  message: string;
  metadata?: Record<string, unknown>;
}

/** Auth profile summary (outbound) from transaction detail */
export interface AuthProfileSummary {
  id: string | null;
  name: string | null;
  authType: string | null;
}

export type AuthMode = "JWT" | "API_KEY" | "ADMIN_SECRET" | "UNKNOWN";

/** Auth summary from transaction detail */
export interface AuthSummary {
  mode: AuthMode;
  sourceVendor: string | null;
  idpIssuer?: string | null;
  idpAudience?: string | null;
  jwtVendorClaim?: string | null;
  authProfile?: AuthProfileSummary | null;
}

/** Vendor-side contract/mapping summary */
export interface VendorContractSideSummary {
  vendorCode: string | null;
  hasVendorContract: boolean;
  hasRequestSchema: boolean;
  hasResponseSchema: boolean;
  hasFromCanonicalRequestMapping: boolean;
  hasToCanonicalResponseMapping: boolean;
}

/** Canonical contract summary */
export interface CanonicalContractSummary {
  hasRequestSchema: boolean;
  hasResponseSchema: boolean;
}

/** Contract & mapping summary from transaction detail */
export interface ContractMappingSummary {
  operationCode: string | null;
  canonicalVersion: string | null;
  canonical: CanonicalContractSummary;
  sourceVendor: VendorContractSideSummary;
  targetVendor: VendorContractSideSummary;
}

/** Full transaction detail response (GET /v1/audit/transactions/{id}) */
export interface TransactionDetailResponse {
  transaction: Transaction;
  auditEvents?: AuditEvent[];
  authSummary?: AuthSummary;
  contractMappingSummary?: ContractMappingSummary;
}

/** Execute integration request payload.
 * sourceVendor is derived from JWT; include for documentation/consistency if desired.
 */
export interface ExecuteIntegrationPayload {
  sourceVendor?: string;
  targetVendor: string;
  operation: string;
  idempotencyKey?: string;
  parameters?: Record<string, unknown>;
}

/** Execute integration response */
export interface ExecuteIntegrationResponse {
  transactionId: string;
  correlationId?: string;
  responseBody?: Record<string, unknown>;
}

/** AI endpoint envelope: rawResult, aiFormatter, finalText, error */
export interface AiExecuteEnvelope {
  transactionId: string;
  correlationId?: string;
  requestType?: string;
  rawResult?: Record<string, unknown> | null;
  aiFormatter?: {
    applied?: boolean;
    mode?: string;
    model?: string;
    reason?: string;
    error?: string;
    formattedText?: string;
  };
  finalText?: string | null;
  error?: { code?: string; message?: string; category?: string; retryable?: boolean } | null;
  operationCode?: string;
  targetVendorCode?: string;
}

/** Redrive response */
export interface RedriveResponse {
  transactionId: string;
  correlationId?: string;
  responseBody?: Record<string, unknown>;
}

/** Vendor from registry (camelCase from API) */
export interface Vendor {
  id?: string;
  vendorCode: string;
  vendorName: string;
  isActive?: boolean;
  createdAt?: string;
  updatedAt?: string;
}

/** Operation-level direction policy. Direction is operation-owned, not per-rule. */
export type OperationDirectionPolicy =
  | "PROVIDER_RECEIVES_ONLY"
  | "TWO_WAY";

export type OperationAiPresentationMode =
  | "RAW_ONLY"
  | "RAW_AND_FORMATTED"
  | "FORMAT_ONLY";

/** @deprecated Use OperationDirectionPolicy. Kept for API compat. */
export type HubDirectionPolicy =
  | "service_outbound_only"
  | "exchange_bidirectional"
  | OperationDirectionPolicy;

/** Operation from registry (camelCase from API) */
export interface Operation {
  id?: string;
  operationCode: string;
  description?: string;
  canonicalVersion?: string;
  isAsyncCapable?: boolean;
  isActive?: boolean;
  /** PROVIDER_RECEIVES_ONLY | TWO_WAY. API returns directionPolicy (was hubDirectionPolicy). */
  directionPolicy?: OperationDirectionPolicy;
  aiPresentationMode?: OperationAiPresentationMode;
  aiFormatterPrompt?: string | null;
  aiFormatterModel?: string | null;
  /** @deprecated Use directionPolicy. Kept for API compat during transition. */
  hubDirectionPolicy?: HubDirectionPolicy | OperationDirectionPolicy;
  createdAt?: string;
  updatedAt?: string;
}

/** Allowlist entry (camelCase from API) */
export interface AllowlistEntry {
  id?: string;
  sourceVendorCode: string;
  targetVendorCode: string;
  operationCode: string;
  /** flow_direction when returned by API; admin rules default to BOTH */
  flowDirection?: string;
  /** rule_scope when returned by API */
  ruleScope?: string;
  createdAt?: string;
  updatedAt?: string;
  /** Derived: true when source or target is * */
  isGlobal?: boolean;
  /** Derived: true when rule uses admin/wildcard semantics (e.g. ruleScope admin or * vendor) */
  isHubRule?: boolean;
}

/** Endpoint from registry (camelCase from API) */
export interface Endpoint {
  id?: string;
  vendorCode: string;
  operationCode: string;
  url: string;
  httpMethod?: string | null;
  payloadFormat?: string | null;
  timeoutMs?: number | null;
  isActive?: boolean;
  authProfileId?: string | null;
  verificationStatus?: string;
  createdAt?: string;
  updatedAt?: string;
}

/** Operation contract */
export interface OperationContract {
  operationCode: string;
  canonicalVersion: string;
  requestSchema?: Record<string, unknown>;
  isActive?: boolean;
}

/** Canonical contract from registry (control_plane.operation_contracts) */
export interface RegistryContract {
  id?: string;
  operationCode: string;
  canonicalVersion: string;
  requestSchema?: Record<string, unknown>;
  responseSchema?: Record<string, unknown> | null;
  isActive?: boolean;
  createdAt?: string;
  updatedAt?: string;
}

/** Upsert vendor payload */
export interface UpsertVendorPayload {
  vendor_code: string;
  vendor_name: string;
  is_active?: boolean;
}

/** Upsert operation payload */
export interface UpsertOperationPayload {
  operation_code: string;
  description?: string;
  canonical_version?: string;
  is_async_capable?: boolean;
  is_active?: boolean;
  direction_policy?: OperationDirectionPolicy;
  ai_presentation_mode?: OperationAiPresentationMode;
  ai_formatter_prompt?: string;
  ai_formatter_model?: string;
  /** @deprecated Use direction_policy. */
  hub_direction_policy?: HubDirectionPolicy;
}

/** Upsert allowlist payload */
export interface UpsertAllowlistPayload {
  source_vendor_code?: string;
  target_vendor_code?: string;
  source_vendor_codes?: string[];
  target_vendor_codes?: string[];
  operation_code: string;
  /**
   * @deprecated Direction is derived from operation. Ignored by backend.
   * Kept optional for backward compat.
   */
  flow_direction?: string;
}

/** Upsert endpoint payload */
export interface UpsertEndpointPayload {
  vendor_code: string;
  operation_code: string;
  url: string;
  http_method?: string;
  payload_format?: string;
  timeout_ms?: number;
  is_active?: boolean;
  auth_profile_id?: string | null;
  flow_direction?: string;
}

/** Onboard vendor payload */
export interface OnboardVendorPayload {
  vendorCode: string;
  vendorName: string;
  forceRotate?: boolean;
}

/** Onboard vendor response */
export interface OnboardVendorResponse {
  apiKey: string;
  vendorCode?: string;
  message?: string;
}

// --- Vendor Config (vendor API, vendor_code derived from key) ---

export interface VendorOperationCatalogItem {
  operationCode: string;
  description?: string;
  canonicalVersion?: string;
}

export interface VendorSupportedOperation {
  operationCode: string;
  isActive?: boolean;
}

export interface VendorEndpoint {
  id?: string;
  operationCode: string;
  url: string;
  httpMethod?: string | null;
  payloadFormat?: string | null;
  timeoutMs?: number | null;
  isActive?: boolean;
  authProfileId?: string | null;
  verificationStatus?: string;
  lastVerifiedAt?: string | null;
  lastVerificationError?: string | null;
  verificationRequest?: Record<string, unknown> | null;
  verificationResult?: {
    status: string;
    httpStatus?: number | null;
    responseSnippet?: string | null;
  };
}

export interface VendorContract {
  id?: string;
  operationCode: string;
  canonicalVersion?: string;
  requestSchema?: Record<string, unknown>;
  responseSchema?: Record<string, unknown>;
  isActive?: boolean;
}

/** Allowed mapping directions for vendor_operation_mappings */
export type MappingDirection =
  | "TO_CANONICAL"
  | "FROM_CANONICAL"
  | "TO_CANONICAL_RESPONSE"
  | "FROM_CANONICAL_RESPONSE";

export interface VendorMapping {
  id?: string;
  operationCode: string;
  canonicalVersion: string;
  direction: MappingDirection;
  mapping: Record<string, unknown>;
  isActive?: boolean;
  createdAt?: string;
  updatedAt?: string;
}
