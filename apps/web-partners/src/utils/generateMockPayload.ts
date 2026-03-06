/**
 * Generate a mock payload from a JSON Schema for Test tab.
 * Used only in UI; not persisted.
 */

export type CanonicalSchemaType = Record<string, unknown>;

function sampleForType(
  propName: string,
  propSchema: Record<string, unknown>
): unknown {
  const type = propSchema.type as string | undefined;
  const enumVal = propSchema.enum;

  if (Array.isArray(enumVal) && enumVal.length > 0) {
    return enumVal[0];
  }

  if (type === "string") {
    const name = (propName || "value").toLowerCase();
    if (name.includes("id")) return "sample-id";
    if (name.includes("city")) return "sampleCity";
    if (name.includes("email")) return "sample@example.com";
    if (name.includes("date")) return "2024-01-15";
    if (name.includes("url")) return "https://example.com";
    return "sample";
  }
  if (type === "number" || type === "integer") {
    return 123;
  }
  if (type === "boolean") {
    return true;
  }
  if (type === "array") {
    const items = propSchema.items as Record<string, unknown> | undefined;
    const itemSchema = items && typeof items === "object" ? items : {};
    return [generateMockPayloadFromSchema(itemSchema as CanonicalSchemaType)];
  }
  if (type === "object") {
    const props = (propSchema.properties as Record<string, unknown>) ?? {};
    return generateMockPayloadFromSchema(props);
  }

  return "sample";
}

/**
 * Generate a mock payload from a JSON Schema.
 * - string -> "sample" or field-name-based sample
 * - number/integer -> 123
 * - boolean -> true
 * - array -> [mockItem] (single item)
 * - object -> recurse on properties
 * - enum -> first enum value
 */
export function generateMockPayloadFromSchema(
  schema: CanonicalSchemaType
): unknown {
  const props = (schema?.properties as Record<string, unknown>) ?? {};
  if (Object.keys(props).length === 0) {
    return {};
  }

  const result: Record<string, unknown> = {};
  for (const key of Object.keys(props)) {
    const propSchema = (props[key] as Record<string, unknown>) ?? {};
    result[key] = sampleForType(key, propSchema);
  }
  return result;
}
