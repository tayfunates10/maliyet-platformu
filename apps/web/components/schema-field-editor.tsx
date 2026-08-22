"use client";

import type { ReactNode } from "react";
import styles from "./calculation-workspace.module.css";

type JsonObject = Readonly<Record<string, unknown>>;

type Props = Readonly<{
  schema: JsonObject;
  value: Readonly<Record<string, unknown>>;
  disabled: boolean;
  onChange: (value: Readonly<Record<string, unknown>>) => void;
}>;

const ITEM_IDS = new WeakMap<object, string>();

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function stableItemKey(item: unknown): string {
  if (item !== null && typeof item === "object") {
    const existing = ITEM_IDS.get(item);
    if (existing !== undefined) return existing;
    const created = crypto.randomUUID();
    ITEM_IDS.set(item, created);
    return created;
  }
  return `${typeof item}:${String(item)}`;
}

function resolveRef(root: JsonObject, schema: JsonObject): JsonObject {
  const ref = schema.$ref;
  if (typeof ref !== "string") return schema;
  const prefix = "#/$defs/";
  if (!ref.startsWith(prefix)) throw new Error("unsupported_schema_ref");
  const defs = root.$defs;
  const name = ref.slice(prefix.length);
  if (!isRecord(defs) || !isRecord(defs[name])) throw new Error("invalid_schema_ref");
  return defs[name] as JsonObject;
}

function effectiveSchema(root: JsonObject, schema: JsonObject): JsonObject {
  const resolved = resolveRef(root, schema);
  const anyOf = resolved.anyOf;
  if (!Array.isArray(anyOf)) return resolved;
  const candidates = anyOf.filter(isRecord);
  const nonNull = candidates.find((candidate) => resolveRef(root, candidate).type !== "null");
  return nonNull === undefined ? resolved : resolveRef(root, nonNull);
}

function labelFor(key: string, schema: JsonObject): string {
  const title = schema.title;
  if (typeof title === "string" && title.trim() !== "") return title;
  return key.replaceAll("_", " ");
}

function cloneRecord(value: Readonly<Record<string, unknown>>, key: string, nextValue: unknown): Readonly<Record<string, unknown>> {
  return Object.freeze({ ...value, [key]: nextValue });
}

function createArrayItem(schema: JsonObject, root: JsonObject): unknown {
  const resolved = effectiveSchema(root, schema);
  const items = resolved.items;
  if (!isRecord(items)) throw new Error("invalid_array_items_schema");
  return createValue(items, root);
}

function createValue(schema: JsonObject, root: JsonObject): unknown {
  const resolved = effectiveSchema(root, schema);
  if (resolved.default !== undefined) return structuredClone(resolved.default);
  const enumValues = resolved.enum;
  if (Array.isArray(enumValues) && enumValues.length > 0) return structuredClone(enumValues[0]);
  if (resolved.type === "string") return "";
  if (resolved.type === "integer" || resolved.type === "number") return 0;
  if (resolved.type === "boolean") return false;
  if (resolved.type === "array") return [];
  if (resolved.type === "object") {
    const properties = resolved.properties;
    if (!isRecord(properties)) return {};
    const required = new Set(Array.isArray(resolved.required) ? resolved.required.filter((item): item is string => typeof item === "string") : []);
    const result: Record<string, unknown> = {};
    for (const [key, child] of Object.entries(properties)) {
      if (!isRecord(child)) continue;
      const childSchema = effectiveSchema(root, child);
      if (required.has(key)) {
        result[key] = childSchema.type === "array" && childSchema.default === undefined
          ? [createArrayItem(childSchema, root)]
          : createValue(child, root);
      } else if (child.default !== undefined) {
        result[key] = createValue(child, root);
      }
    }
    return result;
  }
  return null;
}

function FieldEditor({
  root,
  schema,
  value,
  disabled,
  path,
  label,
  onChange,
}: Readonly<{
  root: JsonObject;
  schema: JsonObject;
  value: unknown;
  disabled: boolean;
  path: string;
  label: string | null;
  onChange: (value: unknown) => void;
}>): ReactNode {
  const resolved = effectiveSchema(root, schema);
  const controlId = `schema-${path.replaceAll(/[^a-zA-Z0-9_-]/g, "-")}`;
  const enumValues = resolved.enum;

  if (Array.isArray(enumValues) && enumValues.every((item) => typeof item === "string")) {
    return (
      <label className={styles.schemaField} htmlFor={controlId}>
        {label !== null ? <span className={styles.schemaFieldLabel}>{label}</span> : null}
        <select id={controlId} value={typeof value === "string" ? value : ""} onChange={(event) => onChange(event.target.value)} disabled={disabled}>
          {enumValues.map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
      </label>
    );
  }

  if (resolved.type === "string") {
    return (
      <label className={styles.schemaField} htmlFor={controlId}>
        {label !== null ? <span className={styles.schemaFieldLabel}>{label}</span> : null}
        <input id={controlId} value={typeof value === "string" ? value : ""} onChange={(event) => onChange(event.target.value)} disabled={disabled} />
      </label>
    );
  }
  if (resolved.type === "integer") {
    return (
      <label className={styles.schemaField} htmlFor={controlId}>
        {label !== null ? <span className={styles.schemaFieldLabel}>{label}</span> : null}
        <input
          id={controlId}
          type="number"
          step={1}
          value={typeof value === "number" && Number.isSafeInteger(value) ? value : 0}
          onChange={(event) => {
            const next = event.target.valueAsNumber;
            if (Number.isSafeInteger(next)) onChange(next);
          }}
          disabled={disabled}
        />
      </label>
    );
  }
  if (resolved.type === "number") {
    return (
      <label className={styles.schemaField} htmlFor={controlId}>
        {label !== null ? <span className={styles.schemaFieldLabel}>{label}</span> : null}
        <input
          id={controlId}
          type="number"
          value={typeof value === "number" && Number.isFinite(value) ? value : 0}
          onChange={(event) => {
            const next = event.target.valueAsNumber;
            if (Number.isFinite(next)) onChange(next);
          }}
          disabled={disabled}
        />
      </label>
    );
  }
  if (resolved.type === "boolean") {
    return (
      <label className={styles.schemaField} htmlFor={controlId}>
        {label !== null ? <span className={styles.schemaFieldLabel}>{label}</span> : null}
        <input id={controlId} type="checkbox" checked={value === true} onChange={(event) => onChange(event.target.checked)} disabled={disabled} />
      </label>
    );
  }
  if (resolved.type === "object") {
    const properties = resolved.properties;
    const recordValue = isRecord(value) ? value : {};
    if (!isRecord(properties)) return <p>Bu nesnenin düzenlenebilir alanı yok.</p>;
    return (
      <fieldset className={styles.fieldGroup}>
        {label !== null ? <legend className={styles.fieldLegend}>{label}</legend> : null}
        {Object.entries(properties).map(([key, child]) => {
          if (!isRecord(child)) return null;
          const childSchema = effectiveSchema(root, child);
          const childValue = recordValue[key] ?? createValue(child, root);
          return (
            <FieldEditor
              key={`${path}.${key}`}
              root={root}
              schema={child}
              value={childValue}
              disabled={disabled}
              path={`${path}.${key}`}
              label={labelFor(key, childSchema)}
              onChange={(next) => onChange(cloneRecord(recordValue, key, next))}
            />
          );
        })}
      </fieldset>
    );
  }
  if (resolved.type === "array") {
    const items = resolved.items;
    if (!isRecord(items)) return <p>Bu listenin öğe şeması desteklenmiyor.</p>;
    const arrayValue = Array.isArray(value) ? value : [];
    return (
      <fieldset className={styles.fieldGroup}>
        {label !== null ? <legend className={styles.fieldLegend}>{label}</legend> : null}
        <div className={styles.arrayEditor}>
          {arrayValue.map((item) => {
            const identity = stableItemKey(item);
            return (
              <div key={identity} className={styles.arrayItem}>
                <div className={styles.arrayHeader}>
                  <strong>Öğe</strong>
                  <button
                    type="button"
                    className={styles.secondary}
                    onClick={() => onChange(Object.freeze(arrayValue.filter((current) => current !== item)))}
                    disabled={disabled}
                  >
                    Sil
                  </button>
                </div>
                <FieldEditor
                  root={root}
                  schema={items}
                  value={item}
                  disabled={disabled}
                  path={`${path}.${identity}`}
                  label={null}
                  onChange={(next) => onChange(Object.freeze(arrayValue.map((current) => current === item ? next : current)))}
                />
              </div>
            );
          })}
          <button
            type="button"
            className={styles.secondary}
            onClick={() => onChange(Object.freeze([...arrayValue, createArrayItem(resolved, root)]))}
            disabled={disabled}
          >
            Öğe ekle
          </button>
        </div>
      </fieldset>
    );
  }
  return <p>Bu alan türü görsel editörde desteklenmiyor.</p>;
}

export function SchemaFieldEditor({ schema, value, disabled, onChange }: Props) {
  return (
    <div className={styles.schemaEditor}>
      <FieldEditor root={schema} schema={schema} value={value} disabled={disabled} path="root" label={null} onChange={(next) => {
        if (isRecord(next)) onChange(Object.freeze({ ...next }));
      }} />
    </div>
  );
}
