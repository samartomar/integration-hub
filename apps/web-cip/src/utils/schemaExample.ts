/**
 * Build an example object from a JSON Schema.
 * Uses schema.required and schema.properties to produce sample values.
 * Minimal implementation for Execute Parameters UX.
 */
export function buildExampleFromSchema(
  schema: Record<string, unknown> | null | undefined
): Record<string, unknown> {
  if (!schema || typeof schema !== "object") return {};
  const props = schema.properties as Record<string, Record<string, unknown>> | undefined;
  if (!props || typeof props !== "object") return {};
  const required = Array.isArray(schema.required)
    ? (schema.required as string[])
    : [];
  const result: Record<string, unknown> = {};
  for (const [key, propSchema] of Object.entries(props)) {
    if (typeof propSchema !== "object" || propSchema === null) continue;
    const typ = propSchema.type as string | undefined;
    const enumVal = Array.isArray(propSchema.enum) ? propSchema.enum[0] : undefined;
    if (enumVal !== undefined) {
      result[key] = enumVal;
    } else if (typ === "string") {
      result[key] = propSchema.example ?? "example";
    } else if (typ === "number" || typ === "integer") {
      result[key] = propSchema.example ?? 123;
    } else if (typ === "boolean") {
      result[key] = propSchema.example ?? true;
    } else if (typ === "object") {
      result[key] = buildExampleFromSchema(propSchema as Record<string, unknown>) || {};
    } else if (typ === "array") {
      result[key] = [];
    } else {
      result[key] = propSchema.example ?? null;
    }
  }
  // Prefer required keys first; ensure at least those are present
  const ordered: Record<string, unknown> = {};
  for (const k of required) {
    if (k in result) ordered[k] = result[k];
  }
  for (const [k, v] of Object.entries(result)) {
    if (!(k in ordered)) ordered[k] = v;
  }
  return ordered;
}

/**
 * Build a minimal JSON skeleton from a JSON Schema.
 * Uses schema.required and schema.properties; required fields get empty string placeholders.
 * Use for Execute Parameters "Reset from schema" UX.
 */
export function buildSkeletonFromSchema(
  schema: Record<string, unknown> | null | undefined
): Record<string, unknown> {
  if (!schema || typeof schema !== "object") return {};
  const props = schema.properties as Record<string, Record<string, unknown>> | undefined;
  if (!props || typeof props !== "object") return {};
  const required = Array.isArray(schema.required)
    ? (schema.required as string[])
    : Object.keys(props);
  const result: Record<string, unknown> = {};
  for (const key of required) {
    if (!(key in props)) continue;
    const propSchema = props[key];
    if (typeof propSchema !== "object" || propSchema === null) continue;
    const typ = propSchema.type as string | undefined;
    const enumVal = Array.isArray(propSchema.enum) ? propSchema.enum[0] : undefined;
    if (enumVal !== undefined) {
      result[key] = enumVal;
    } else if (typ === "string") {
      result[key] = "";
    } else if (typ === "number" || typ === "integer") {
      result[key] = 0;
    } else if (typ === "boolean") {
      result[key] = false;
    } else if (typ === "object") {
      result[key] = buildSkeletonFromSchema(propSchema as Record<string, unknown>) || {};
    } else if (typ === "array") {
      result[key] = [];
    } else {
      result[key] = "";
    }
  }
  return result;
}
