import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";
import type { useMutationFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";

export type Field = {
  name: string;
  type: string;
  nullable?: boolean;
  required?: boolean;
  comment?: string;
  source?: string;
};
export type FieldEvidence = {
  kind: "document" | "sample" | "sql";
  reference?: string;
  source: Record<string, unknown>;
  fields: Field[];
  proof?: string;
};
export type SourcePreview = {
  fields: Field[];
  rows: Record<string, unknown>[];
  field_evidence?: FieldEvidence;
  uncertain_types?: string[];
  contract_errors?: string[];
};
export type JsonSchema = {
  minItems?: number;
  type?: string;
  format?: string;
  enum?: unknown[];
  properties?: Record<string, JsonSchema>;
  items?: JsonSchema;
  required?: string[];
  default?: unknown;
};
export type BusinessNode = {
  id: string;
  kind: string;
  label?: string;
  config: Record<string, unknown>;
  position?: { x: number; y: number };
};
export type BusinessGraph = {
  nodes: BusinessNode[];
  edges: { source: string; target: string; port: string; input: string }[];
};
export type Scheme = {
  code: string;
  name: string;
  flow_id: string;
  revision: number;
  active_release_id: string | null;
  draft: BusinessGraph;
  allowed_sources: string[];
};
export type Release = {
  id: string;
  version: number;
  note: string;
  package: {
    task_input?: string | null;
    parameters: {
      name: string;
      type: string;
      default?: unknown;
      required?: boolean;
      description?: string;
    }[];
    schemas: Record<string, Record<string, Field[]>>;
    graph: BusinessGraph;
    connections: Record<string, unknown>;
    summary?: Record<string, unknown>;
    contract_version?: number;
  };
};
export type Connection = {
  id: string;
  name: string;
  kind: string;
  config: Record<string, string | number>;
};
export type Catalog = {
  task_input?: {
    contract: string;
    parameters: { name: string; type: string }[];
    context: { name: string; type: string }[];
  };
  sources: string[];
  nodes: Record<
    string,
    { ports: string[]; inputs: string[]; schema: JsonSchema }
  >;
};
export type Inspection = {
  classification_prompts?: Record<string, string>;
  schemas: Record<string, Record<string, Field[]>>;
  errors: Record<string, string>;
};
export type Dataset = {
  id: string;
  name: string;
  node_id: string;
  port: string;
  fields: Field[];
  row_count: number;
  raw: boolean;
  provenance: Record<string, unknown>;
};
export type AcceptedTaskInput = {
  parameters: Record<string, unknown>;
  task: {
    scheme: string;
    rule_name: string;
    external_task_id: string;
    task_id: string;
    release_id: string;
    version: number;
  };
};
export type Task = {
  id: string;
  flow_id?: string;
  task_input?: AcceptedTaskInput | null;
  scheme_code: string;
  source: string;
  status: string;
  release_id: string;
  created_at: string;
  parameters: Record<string, unknown>;
  error?: { message: string };
  results: string[];
  progress: Record<string, { status: string; elapsed_seconds?: number }>;
  datasets?: Dataset[];
  unresolved_rows?: number;
  classification_counts?: {
    continue: number;
    excluded: number;
    uncompared: number;
  };
  version?: number;
  assessment?: Assessment;
};
export type Assessment = {
  mode: string;
  state: string;
  discovery_complete?: boolean;
  received_records?: number;
  business_identities?: number;
  missing_identity_records?: number;
  coverage_gap_records?: number;
  dispositions_dataset_id?: string;
  sources?: {
    node: string;
    state: string;
    received_rows: number;
    dataset_id: string;
    basis?: string;
  }[];
  checks?: {
    name: string;
    units: number;
    effective?: number;
    coverage_gaps?: number;
    counts?: Record<string, number>;
    dataset_id?: string;
  }[];
};
export type ExternalRequest = {
  id: string;
  node_id: string;
  input_dataset_id: string;
  input_row_id: number;
  transport: string;
  remote: string;
  validity: string;
  payload: unknown;
  response: unknown;
  error?: string;
};
export type DatasetPage = {
  id: string;
  name: string;
  total: number;
  fields: Field[];
  rows: Record<string, unknown>[];
  provenance: Record<string, unknown>;
};

export function useBusinessQuery<T>(
  path: string,
  enabled = true,
  polling = false,
  { staleTime = 0 }: { staleTime?: number } = {},
): UseQueryResult<T, Error> {
  const { query } = UseRequestProcessor();
  return query(
    ["useBusinessQuery", path],
    async () => (await api.get(`${getURL("BUSINESS")}/${path}`)).data,
    {
      enabled,
      retry: false,
      refetchInterval: polling ? 2500 : false,
      staleTime,
    },
  );
}
type BusinessMutationVariables = {
  path: string;
  method?: "POST" | "PUT";
  body?: unknown;
  key?: string;
};
export function useBusinessMutation<T = unknown>(
  options?: Parameters<
    useMutationFunctionType<undefined, BusinessMutationVariables, T, Error>
  >[0],
): UseMutationResult<T, Error, BusinessMutationVariables> {
  const { mutate, queryClient } = UseRequestProcessor();
  return mutate(
    ["useBusinessMutation"],
    async ({ path, method = "POST", body, key }) =>
      (
        await api.request({
          url: `${getURL("BUSINESS")}/${path}`,
          method,
          data: body,
          headers: key ? { "Idempotency-Key": key } : undefined,
        })
      ).data,
    {
      retry: false,
      onSettled: () => {
        void queryClient.invalidateQueries({ queryKey: ["useBusinessQuery"] });
      },
      ...options,
    },
  );
}
export const useInspectBusiness: useMutationFunctionType<
  undefined,
  unknown,
  Inspection,
  Error
> = (options) => {
  const { mutate } = UseRequestProcessor();
  return mutate(
    ["useInspectBusiness"],
    async (body) =>
      (await api.post(`${getURL("BUSINESS")}/inspect`, body)).data,
    { retry: false, ...options },
  );
};
export const useBusinessUpload: useMutationFunctionType<
  undefined,
  File,
  { file_id: string; format: string; fields: Field[] }
> = (options) => {
  const { mutate } = UseRequestProcessor();
  return mutate(
    ["useBusinessUpload"],
    async (file) => {
      const body = new FormData();
      body.append("file", file);
      return (await api.post(`${getURL("BUSINESS")}/files`, body)).data;
    },
    { retry: false, ...options },
  );
};
