type JsonObject = Readonly<Record<string, unknown>>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function cloneJson(value: unknown): unknown {
  return JSON.parse(JSON.stringify(value));
}

function resolveRef(root: JsonObject, ref: string): JsonObject {
  const prefix = "#/$defs/";
  if (!ref.startsWith(prefix)) throw new Error("unsupported_schema_ref");
  const name = ref.slice(prefix.length);
  const defs = root.$defs;
  if (!isRecord(defs) || !isRecord(defs[name])) throw new Error("invalid_schema_ref");
  return defs[name] as JsonObject;
}

function templateFor(schema: JsonObject, root: JsonObject, depth: number): unknown {
  if (depth > 12) throw new Error("schema_depth_exceeded");
  if (typeof schema.$ref === "string") return templateFor(resolveRef(root, schema.$ref), root, depth + 1);
  if (schema.default !== undefined) return cloneJson(schema.default);

  const enumValues = schema.enum;
  if (Array.isArray(enumValues) && enumValues.length > 0) return cloneJson(enumValues[0]);

  const type = schema.type;
  if (type === "string") return "";
  if (type === "integer" || type === "number") return 0;
  if (type === "boolean") return false;
  if (type === "array") return [];
  if (type !== "object") throw new Error("unsupported_schema_type");

  const properties = schema.properties;
  if (!isRecord(properties)) return {};
  const required = new Set(Array.isArray(schema.required) ? schema.required.filter((item): item is string => typeof item === "string") : []);
  const result: Record<string, unknown> = {};
  for (const [key, child] of Object.entries(properties)) {
    if (!isRecord(child)) continue;
    if (required.has(key) || child.default !== undefined) result[key] = templateFor(child, root, depth + 1);
  }
  return result;
}

export function buildSchemaTemplate(schema: unknown): Readonly<Record<string, unknown>> {
  if (!isRecord(schema) || schema.type !== "object") throw new Error("invalid_engine_schema");
  const template = templateFor(schema, schema, 0);
  if (!isRecord(template)) throw new Error("invalid_engine_schema");
  return Object.freeze(template);
}

export function listRequiredFields(schema: unknown): readonly string[] {
  if (!isRecord(schema) || !Array.isArray(schema.required)) return Object.freeze([]);
  return Object.freeze(schema.required.filter((item): item is string => typeof item === "string"));
}
