/**
 * API client for vendor change requests (approval flow).
 */

import { vendorApi } from "./client";

export type AllowlistChangeRequestBody = {
  direction: "OUTBOUND" | "INBOUND";
  operationCode: string;
  targetVendorCodes: string[];
  useWildcardTarget: boolean;
  ruleScope?: "vendor";
  requestType?: "ALLOWLIST_RULE" | "PROVIDER_NARROWING" | "CALLER_NARROWING";
};

export type ChangeRequest = {
  id: string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";
  requestType: "ALLOWLIST_RULE" | "PROVIDER_NARROWING" | string;
  summary?: Record<string, unknown>;
  createdAt?: string;
  updatedAt?: string;
};

export type AllowlistChangeRequestResponse = {
  id: string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";
  transactionId?: string;
  correlationId?: string;
};

/** Create allowlist change request via dedicated allowlist-change-requests API. */
export async function createAllowlistChangeRequest(
  body: AllowlistChangeRequestBody
): Promise<AllowlistChangeRequestResponse> {
  const payload = {
    ...body,
    requestType: body.requestType ?? "ALLOWLIST_RULE",
  };
  const res = await vendorApi.post<AllowlistChangeRequestResponse>(
    "/v1/vendor/allowlist-change-requests",
    payload
  );
  return res.data;
}

/** List vendor's allowlist change requests from allowlist_change_requests table. */
export async function listMyAllowlistChangeRequests(
  status: "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED" = "PENDING"
): Promise<AllowlistChangeRequestItem[]> {
  const res = await vendorApi.get<{ items: AllowlistChangeRequestItem[] }>(
    `/v1/vendor/my-change-requests?status=${status}`
  );
  return res.data?.items ?? [];
}

/** List recent access requests across all statuses (for "My access requests" panel). */
export async function listMyAccessRequestsAllStatuses(): Promise<AllowlistChangeRequestItem[]> {
  const [pending, approved, rejected] = await Promise.all([
    listMyAllowlistChangeRequests("PENDING"),
    listMyAllowlistChangeRequests("APPROVED"),
    listMyAllowlistChangeRequests("REJECTED"),
  ]);
  const merged = [...(pending ?? []), ...(approved ?? []), ...(rejected ?? [])];
  merged.sort((a, b) => {
    const da = a.createdAt ?? a.requestedAt ?? "";
    const db = b.createdAt ?? b.requestedAt ?? "";
    return db.localeCompare(da);
  });
  return merged;
}

export type AllowlistChangeRequestItem = {
  id: string;
  sourceVendorCode: string;
  targetVendorCodes: string[];
  useWildcardTarget: boolean;
  operationCode: string;
  direction: string;
  requestType: string;
  ruleScope: string;
  status: string;
  requestedBy?: string;
  reviewedBy?: string;
  decisionReason?: string;
  createdAt?: string;
  updatedAt?: string;
  /** Alias for createdAt when backend returns requestedAt */
  requestedAt?: string;
};

/** Legacy helper name; reads the strict my-change-requests endpoint. */
export async function listMyChangeRequests(
  status: "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED" = "PENDING"
): Promise<ChangeRequest[]> {
  const res = await vendorApi.get<{ items: ChangeRequest[] }>(
    `/v1/vendor/my-change-requests?status=${status}`
  );
  return res.data?.items ?? [];
}
