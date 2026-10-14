import type { JsonSchema } from "@/controllers/API/queries/business";
import type { FormOptions } from "./SchemaForm";

export type LookupConfig = {
  connection?: string;
  schema?: string;
  table?: string;
  timezone?: string;
  binding_source?: { connection: string; schema: string; table: string };
  keys?: { left: string; right: string }[];
  conditions?: Record<string, unknown>[];
  returns?: {
    field: string;
    output: string;
    type?: string;
    timezone?: string;
  }[];
  source_identity?: { name?: string; namespace?: string; keys: string[] };
  source_required?: string[];
  checks?: { required?: string[]; conditions?: Record<string, unknown>[] };
};
export const lookupSource = (config: LookupConfig) => ({
  connection: config.connection ?? "",
  schema: config.schema ?? "",
  table: config.table ?? "",
});
export const sourceBindingsChanged = (config: LookupConfig) =>
  !!config.binding_source &&
  (
    Object.keys(lookupSource(config)) as (keyof NonNullable<
      LookupConfig["binding_source"]
    >)[]
  ).some((key) => config.binding_source![key] !== lookupSource(config)[key]);
export function managedLookup(
  config: LookupConfig,
  nodeId: string,
): LookupConfig {
  const identity = config.source_identity;
  return {
    ...config,
    ...(config.connection && config.table && !config.binding_source
      ? { binding_source: lookupSource(config) }
      : {}),
    ...(identity
      ? {
          source_identity: {
            ...identity,
            name: identity.name || "source",
            namespace: identity.namespace || `lookup:${nodeId}`,
          },
        }
      : {}),
  };
}

/** Count missing values and stale field references even when their section is folded. */
export function lookupProblems(
  schema: JsonSchema,
  value: unknown,
  options: FormOptions,
): number {
  if (schema.type === "array")
    return (
      (Array.isArray(value) && value.length >= (schema.minItems ?? 0)
        ? 0
        : schema.minItems
          ? 1
          : 0) +
      (Array.isArray(value) ? value : []).reduce(
        (n, item) => n + lookupProblems(schema.items ?? {}, item, options),
        0,
      )
    );
  if (schema.type === "object" && schema.properties) {
    const obj = (value ?? {}) as Record<string, unknown>;
    return Object.entries(schema.properties).reduce(
      (n, [key, child]) =>
        n +
        (schema.required?.includes(key) &&
        (obj[key] === undefined ||
          obj[key] === "" ||
          (Array.isArray(obj[key]) && !obj[key].length))
          ? 1
          : obj[key] === undefined
            ? 0
            : lookupProblems(child, obj[key], options)),
      0,
    );
  }
  let choices: string[] | undefined;
  if (schema.enum) choices = schema.enum.map(String);
  if (schema.format?.startsWith("field") && !options.fieldsLoading)
    choices = options.fields?.[schema.format.split(":")[1] ?? "data"]?.map(
      (f) => f.name,
    );
  if (schema.format === "parameter") choices = options.parameters;
  if (schema.format === "table") choices = options.tables;
  if (schema.format === "database_schema") choices = options.databaseSchemas;
  if (schema.format === "connection")
    choices = options.connections?.map((c) => c.id);
  return choices && value && !choices.includes(String(value)) ? 1 : 0;
}
