/**
 * Build an identity mapping from a JSON Schema's properties.
 * Each property maps to itself (vendor field = canonical field).
 * Use for "Generate identity mapping from schemas" UX.
 */
export function buildIdentityMappingFromSchema(
  schema: Record<string, unknown> | null | undefined
): Record<string, string> {
  if (!schema || typeof schema !== "object") return {};
  const props = schema.properties as Record<string, unknown> | undefined;
  if (!props || typeof props !== "object") return {};
  const result: Record<string, string> = {};
  for (const key of Object.keys(props)) {
    result[key] = key;
  }
  return result;
}
