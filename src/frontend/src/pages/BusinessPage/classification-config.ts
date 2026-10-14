export type ClassificationRule = {
  fields?: string[];
  op: "contains" | "eq" | "contains_all";
  value?: string;
  keywords?: string[];
  category: string;
  when?: { field: string; value: string }[];
};
export type ClassificationConfig = {
  result_prefix?: string;
  dictionary?: { id: string; field: string };
  classification_fields: { field: string; role: "evidence" | "context" }[];
  category_routes: { category: string; continue: boolean }[];
  business_guidance: string;
  rules: ClassificationRule[];
  connection: string;
  model: string;
  path: string;
  max_calls?: number;
  ambiguity_hints?: string[];
  conflicts?: {
    category: string;
    field: string;
    contains: string;
    when?: { field: string; value: string }[];
  }[];
};

export function classificationConfig(
  value: Record<string, unknown>,
): ClassificationConfig {
  return {
    connection: "",
    model: "",
    path: "/v1/chat/completions",
    rules: [],
    classification_fields: [],
    category_routes: [],
    business_guidance: "",
    ...value,
  } as ClassificationConfig;
}
