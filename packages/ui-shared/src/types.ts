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
  canonicalRequestBody?: Record<string, unknown> | null;
  targetRequestBody?: Record<string, unknown> | null;
  targetResponseBody?: Record<string, unknown> | null;
  canonicalResponseBody?: Record<string, unknown> | null;
  errorCode?: string | null;
  httpStatus?: number | null;
  failureStage?: string | null;
  canonical_request_body?: Record<string, unknown> | null;
  target_request_body?: Record<string, unknown> | null;
  target_response_body?: Record<string, unknown> | null;
  canonical_response_body?: Record<string, unknown> | null;
  redrive_count?: number;
  parent_transaction_id?: number | null;
}

export interface ListTransactionsResponse {
  transactions: Transaction[];
  count: number;
  nextCursor?: string;
}

export interface AuditEvent {
  id?: string;
  transactionId: string;
  action: string;
  vendorCode: string;
  details?: Record<string, unknown>;
  createdAt?: string;
}

export interface ListAuditEventsResponse {
  events?: AuditEvent[];
  transaction?: Transaction;
}

export interface AuthProfileSummary {
  id: string | null;
  name: string | null;
  authType: string | null;
}

export type AuthMode = "JWT" | "API_KEY" | "ADMIN_SECRET" | "UNKNOWN";

export interface AuthSummary {
  mode: AuthMode;
  sourceVendor: string | null;
  idpIssuer?: string | null;
  idpAudience?: string | null;
  jwtVendorClaim?: string | null;
  authProfile?: AuthProfileSummary | null;
}

export interface VendorContractSideSummary {
  vendorCode: string | null;
  hasVendorContract: boolean;
  hasRequestSchema: boolean;
  hasResponseSchema: boolean;
  hasFromCanonicalRequestMapping: boolean;
  hasToCanonicalResponseMapping: boolean;
}

export interface CanonicalContractSummary {
  hasRequestSchema: boolean;
  hasResponseSchema: boolean;
}

export interface ContractMappingSummary {
  operationCode: string | null;
  canonicalVersion: string | null;
  canonical: CanonicalContractSummary;
  sourceVendor: VendorContractSideSummary;
  targetVendor: VendorContractSideSummary;
}

export interface TransactionDetailResponse {
  transaction: Transaction;
  auditEvents?: AuditEvent[];
  authSummary?: AuthSummary;
  contractMappingSummary?: ContractMappingSummary;
}

export interface ExecuteIntegrationPayload {
  sourceVendor?: string;
  targetVendor: string;
  operation: string;
  idempotencyKey?: string;
  parameters?: Record<string, unknown>;
}

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

export interface RedriveResponse {
  transactionId: string;
  correlationId?: string;
  responseBody?: Record<string, unknown>;
}

export interface Vendor {
  id?: string;
  vendorCode: string;
  vendorName: string;
  isActive?: boolean;
  createdAt?: string;
  updatedAt?: string;
}

export interface Operation {
  id?: string;
  operationCode: string;
  description?: string;
  canonicalVersion?: string;
  isAsyncCapable?: boolean;
  isActive?: boolean;
  directionPolicy?: "PROVIDER_RECEIVES_ONLY" | "TWO_WAY";
  aiPresentationMode?: "RAW_ONLY" | "RAW_AND_FORMATTED" | "FORMAT_ONLY";
  aiFormatterPrompt?: string | null;
  aiFormatterModel?: string | null;
  createdAt?: string;
  updatedAt?: string;
}

/** flow_direction from API – INBOUND, OUTBOUND, or BOTH */
export type FlowDirection = "INBOUND" | "OUTBOUND" | "BOTH";

export interface AllowlistEntry {
  id?: string;
  sourceVendorCode?: string | null;
  targetVendorCode?: string | null;
  operationCode: string;
  /** flow_direction when returned by API; admin rules default to BOTH */
  flowDirection?: FlowDirection;
  /** rule_scope when returned by API; admin list returns admin-scoped rules */
  ruleScope?: string;
  /** Wildcard: true when any source; source_vendor_code is null when true */
  isAnySource?: boolean;
  /** Wildcard: true when any target; target_vendor_code is null when true */
  isAnyTarget?: boolean;
  createdAt?: string;
  updatedAt?: string;
  /** Derived: true when isAnySource or isAnyTarget (no more * in vendor codes) */
  isGlobal?: boolean;
}

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

export interface OperationContract {
  operationCode: string;
  canonicalVersion: string;
  requestSchema?: Record<string, unknown>;
  isActive?: boolean;
}

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

export interface UpsertVendorPayload {
  vendor_code: string;
  vendor_name: string;
  is_active?: boolean;
}

export interface UpsertOperationPayload {
  operation_code: string;
  description?: string;
  canonical_version?: string;
  is_async_capable?: boolean;
  is_active?: boolean;
  direction_policy?: "PROVIDER_RECEIVES_ONLY" | "TWO_WAY";
  ai_presentation_mode?: "RAW_ONLY" | "RAW_AND_FORMATTED" | "FORMAT_ONLY";
  ai_formatter_prompt?: string;
  ai_formatter_model?: string;
}

export interface UpsertAllowlistPayload {
  source_vendor_code?: string | null;
  target_vendor_code?: string | null;
  operation_code: string;
  /** INBOUND | OUTBOUND | BOTH. Required for admin allowlist. */
  flow_direction?: FlowDirection;
  /** For wildcard: true = any source; source_vendor_code must be null */
  is_any_source?: boolean;
  /** For wildcard: true = any target; target_vendor_code must be null */
  is_any_target?: boolean;
}

export interface UpsertEndpointPayload {
  vendor_code: string;
  operation_code: string;
  url: string;
  http_method?: string;
  payload_format?: string;
  timeout_ms?: number;
  is_active?: boolean;
  auth_profile_id?: string | null;
  /** INBOUND or OUTBOUND. Defaults to OUTBOUND if omitted. */
  flow_direction?: "INBOUND" | "OUTBOUND";
}

export interface OnboardVendorPayload {
  vendorCode: string;
  vendorName: string;
  forceRotate?: boolean;
}

export interface OnboardVendorResponse {
  apiKey: string;
  vendorCode?: string;
  message?: string;
}

/** Operation-level direction policy for canonical operations */
export type HubDirectionPolicy =
  | "service_outbound_only"
  | "exchange_bidirectional";

export interface VendorOperationCatalogItem {
  operationCode: string;
  description?: string;
  canonicalVersion?: string;
  /** Operation-level: PROVIDER_RECEIVES_ONLY or TWO_WAY */
  directionPolicy?: string;
  /** @deprecated Use directionPolicy */
  hubDirectionPolicy?: HubDirectionPolicy;
}

export interface VendorSupportedOperation {
  operationCode: string;
  isActive?: boolean;
  /** Vendor declared intent: this licensee will call other APIs for this operation */
  supportsOutbound?: boolean;
  /** Vendor declared intent: other licensees may call this licensee for this operation */
  supportsInbound?: boolean;
}

export interface VendorEndpoint {
  id?: string;
  operationCode: string;
  flowDirection?: string | null;
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
