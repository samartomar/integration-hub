/**
 * Identity mapping template for Visual Flow Builder.
 *
 * When requiresMapping=false and there is no saved mapping, we show a generated
 * identity template in the UI so users see what pass-through would look like.
 * This is a UI convenience only - we do NOT persist it. If the user saves without
 * changing it, we treat it as "no mapping" (hasMapping=false).
 */

function schemaFieldList(schema: Record<string, unknown>): string[] {
  const props = (schema?.properties as Record<string, unknown>) ?? {};
  return Object.keys(props);
}

/**
 * Known canonical↔vendor field aliases for GET_RECEIPT (hard-coded for now).
 * Request: vendor field name -> canonical field to read from (e.g. txnId <- transactionId)
 * Response: canonical field name -> vendor field to read from (e.g. receipt <- result)
 */
const GET_RECEIPT_REQUEST_ALIASES: Record<string, string> = {
  txnId: "transactionId",
};
const GET_RECEIPT_RESPONSE_ALIASES: Record<string, string> = {
  receipt: "result",
};

export interface IdentityTemplates {
  request: Record<string, string>;
  response: Record<string, string>;
}

/**
 * Build identity mapping templates from schemas.
 *
 * Request (canonical → vendor): keys = vendor field names, values = $.canonicalPath
 * Response (vendor → canonical): keys = canonical field names, values = $.vendorPath
 *
 * For matching names: { "fieldName": "$.fieldName" }
 * For GET_RECEIPT known aliases: txnId↔transactionId, receipt↔result
 */
export function getIdentityMappingTemplate(
  operationCode: string,
  canonicalReqSchema: Record<string, unknown>,
  vendorReqSchema: Record<string, unknown>,
  canonicalRespSchema: Record<string, unknown>,
  vendorRespSchema: Record<string, unknown>
): IdentityTemplates {
  const canonReq = schemaFieldList(canonicalReqSchema);
  const vendorReq = schemaFieldList(vendorReqSchema);
  const canonResp = schemaFieldList(canonicalRespSchema);
  const vendorResp = schemaFieldList(vendorRespSchema);

  const request: Record<string, string> = {};
  const response: Record<string, string> = {};

  const isGetReceipt = (operationCode ?? "").toUpperCase() === "GET_RECEIPT";

  // Request: canonical → vendor. Output keys are vendor fields.
  for (const vf of vendorReq) {
    const canonPath = isGetReceipt && GET_RECEIPT_REQUEST_ALIASES[vf]
      ? GET_RECEIPT_REQUEST_ALIASES[vf]
      : canonReq.includes(vf)
        ? vf
        : null;
    if (canonPath) {
      request[vf] = `$.${canonPath}`;
    }
  }
  // If no vendor fields, fall back to canonical fields with matching names
  if (Object.keys(request).length === 0) {
    for (const cf of canonReq) {
      if (vendorReq.includes(cf)) {
        request[cf] = `$.${cf}`;
      }
    }
  }

  // Response: vendor → canonical. Output keys are canonical fields.
  for (const cf of canonResp) {
    const vendorPath = isGetReceipt && GET_RECEIPT_RESPONSE_ALIASES[cf]
      ? GET_RECEIPT_RESPONSE_ALIASES[cf]
      : vendorResp.includes(cf)
        ? cf
        : null;
    if (vendorPath) {
      response[cf] = `$.${vendorPath}`;
    }
  }
  if (Object.keys(response).length === 0) {
    for (const vf of vendorResp) {
      if (canonResp.includes(vf)) {
        response[vf] = `$.${vf}`;
      }
    }
  }

  return { request, response };
}

/** Check if mapping equals identity template (same keys/values). Treat as "no mapping" on save. */
export function mappingEqualsTemplate(
  mapping: Record<string, unknown>,
  template: Record<string, string>
): boolean {
  const keys = Object.keys(template);
  if (Object.keys(mapping).length !== keys.length) return false;
  for (const k of keys) {
    const want = template[k];
    const got = mapping[k];
    if (typeof got !== "string" || got !== want) return false;
  }
  return true;
}

export function templateToPrettifiedJson(template: Record<string, string>): string {
  if (Object.keys(template).length === 0) return "{}";
  return JSON.stringify(template, null, 2);
}
