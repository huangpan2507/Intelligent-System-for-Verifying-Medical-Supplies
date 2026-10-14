import type { JsonSchema } from "@/controllers/API/queries/business";

export function configurationShape(
  schema: JsonSchema,
  keys: string[],
): JsonSchema {
  return {
    type: "object",
    properties: Object.fromEntries(
      keys
        .filter((k) => schema.properties?.[k])
        .map((k) => [k, schema.properties![k]]),
    ),
    required: schema.required?.filter((k) => keys.includes(k)),
  };
}

export function conditionSummary(conditions: Record<string, unknown>[] = []) {
  return conditions
    .map(
      (c) =>
        `${c.field ?? "—"} ${c.op ?? ""} ${c.parameter ? "$" + c.parameter : (c.right_field ?? JSON.stringify(c.value ?? ""))}`,
    )
    .join(" · ");
}

export type ValidateConfig = {
  required?: string[];
  unique?: string[];
  conditions?: Record<string, unknown>[];
  identity?: { name?: string; namespace?: string; keys: string[] };
};

export function managedValidation(
  config: ValidateConfig,
  nodeId: string,
): ValidateConfig {
  if (!config.identity) return config;
  return {
    ...config,
    identity: {
      ...config.identity,
      name: config.identity.name || "detail",
      namespace: config.identity.namespace || `validate:${nodeId}`,
    },
  };
}
