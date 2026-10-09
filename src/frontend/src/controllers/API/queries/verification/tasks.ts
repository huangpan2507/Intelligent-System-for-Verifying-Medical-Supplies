import type { useQueryFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";

export const RUN_STATUSES = [
  "waiting",
  "running",
  "completed",
  "partial_failed",
  "failed",
  "needs_confirmation",
] as const;
export type RunStatus = (typeof RUN_STATUSES)[number];
export type VerificationRun = {
  task_id: string;
  run_id: string;
  job_id: string;
  release_id: string;
  status: RunStatus;
  stage: string | null;
  stage_event: string | null;
  rule_version: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  progress: Record<string, number | boolean>;
  error: { code: string; message: string } | null;
};
export type VerificationTask = VerificationRun & {
  current_run_id: string;
  external_task_id: string;
  source_system: string;
  scope: {
    hospital_scope: string;
    settlement_time_range: { start_inclusive: string; end_exclusive: string };
    rule: string;
    rule_code: string;
  };
};
export type Comparison = {
  status: string;
  reasons: string[];
  delta?: string | null;
  settlement?: string;
  recognized?: string;
  source_amount?: string;
  converted_amount?: string;
  currency?: string;
  unit?: string;
};
export type UnitResult = {
  scope_id?: string;
  category?: string | null;
  detail_ids: string[];
  conclusion: string;
  type?: Comparison;
  quantity?: Comparison;
  fee?: Comparison;
  reasons?: string[];
  review_evidence?: string;
  request_id?: string;
  raw_recognition?: Record<string, unknown>;
  execution_status?: string;
};
export type TaskResults = VerificationTask & {
  available: boolean;
  result_id: string | null;
  result: {
    simulated: boolean;
    summary: Record<string, number | boolean>;
    results: UnitResult[];
    offset: number;
    limit: number;
  } | null;
};
export type TaskEvidence = {
  task_id: string;
  run_id: string;
  artifacts: Array<{
    artifact_id: string;
    kind: string;
    key: string;
    payload: unknown;
  }>;
  model_requests: Array<{
    request_id: string;
    status: string;
    input: unknown;
    raw_response: Record<string, unknown> | null;
    error: unknown;
  }>;
  pagination: {
    offset: number;
    limit: number;
    artifacts_total: number;
    model_requests_total: number;
  };
};
type PageParams = { limit: number; offset: number };
type RunParams = PageParams & { taskId: string; runId: string };
const path = (taskId: string) =>
  `${getURL("VERIFICATION")}/tasks/${encodeURIComponent(taskId)}`;

export const useGetVerificationTasks: useQueryFunctionType<
  PageParams & { status: string; q: string },
  { items: VerificationTask[]; total: number; limit: number; offset: number }
> = (params, options) => {
  const { query } = UseRequestProcessor();
  return query(
    ["useGetVerificationTasks", params],
    async () =>
      (
        await api.get(`${getURL("VERIFICATION")}/tasks`, {
          params: { ...params, status: params.status || undefined },
        })
      ).data,
    { retry: false, refetchInterval: 5000, ...options },
  );
};

export const useGetVerificationTask: useQueryFunctionType<
  { taskId: string },
  VerificationTask
> = ({ taskId }, options) => {
  const { query } = UseRequestProcessor();
  return query(
    ["useGetVerificationTask", taskId],
    async () => (await api.get(path(taskId))).data,
    {
      retry: false,
      refetchInterval: 5000,
      ...options,
      enabled: !!taskId && (options?.enabled ?? true),
    },
  );
};

export const useGetVerificationRuns: useQueryFunctionType<
  PageParams & { taskId: string },
  VerificationRun[]
> = ({ taskId, ...params }, options) => {
  const { query } = UseRequestProcessor();
  return query(
    ["useGetVerificationRuns", taskId, params],
    async () => (await api.get(`${path(taskId)}/runs`, { params })).data,
    {
      retry: false,
      refetchInterval: 5000,
      ...options,
      enabled: !!taskId && (options?.enabled ?? true),
    },
  );
};

export const useGetVerificationResults: useQueryFunctionType<
  RunParams,
  TaskResults
> = ({ taskId, runId, ...params }, options) => {
  const { query } = UseRequestProcessor();
  return query(
    ["useGetVerificationResults", taskId, runId, params],
    async () =>
      (
        await api.get(`${path(taskId)}/results`, {
          params: { ...params, run_id: runId },
        })
      ).data,
    {
      retry: false,
      refetchInterval: 5000,
      ...options,
      enabled: !!taskId && !!runId && (options?.enabled ?? true),
    },
  );
};

export const useGetVerificationEvidence: useQueryFunctionType<
  RunParams,
  TaskEvidence
> = ({ taskId, runId, ...params }, options) => {
  const { query } = UseRequestProcessor();
  return query(
    ["useGetVerificationEvidence", taskId, runId, params],
    async () =>
      (
        await api.get(`${path(taskId)}/evidence`, {
          params: { ...params, run_id: runId },
        })
      ).data,
    {
      retry: false,
      ...options,
      enabled: !!taskId && !!runId && (options?.enabled ?? true),
    },
  );
};
