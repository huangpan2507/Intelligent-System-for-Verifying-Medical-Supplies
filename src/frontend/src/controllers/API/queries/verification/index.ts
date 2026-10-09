import type {
  useMutationFunctionType,
  useQueryFunctionType,
} from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";

export type Rule = {
  code: string;
  name: string;
  flow_id: string;
  revision: number;
  draft_revision: number;
  draft_config: { catalog_mapping?: Record<string, string>; note?: string };
  active_release_id: string | null;
  active_version: number | null;
};
export type Release = {
  id: string;
  version: number;
  content_hash: string;
  created_at: string;
  note: string;
  simulated: boolean;
  runtime_digest: string;
};
export type Candidate = {
  id: string;
  content_hash: string;
  validation: Record<string, string>;
};
export type ReleaseDetail = Release & {
  package: {
    graph: {
      nodes: Array<{
        id: string;
        position: { x: number; y: number };
        data: {
          node: {
            display_name: string;
            template: Record<
              string,
              { display_name?: string; value?: unknown }
            >;
          };
        };
      }>;
      edges: Array<{ id: string; source: string; target: string }>;
    };
  };
};
const path = (code: string) =>
  `${getURL("VERIFICATION")}/rules/${encodeURIComponent(code)}`;

export const useVerificationRules: useQueryFunctionType<undefined, Rule[]> = (
  options,
) => {
  const { query } = UseRequestProcessor();
  return query(
    ["useVerificationRules"],
    async () => (await api.get(`${getURL("VERIFICATION")}/rules`)).data,
    { retry: false, ...options },
  );
};
export const useVerificationReleases: useQueryFunctionType<
  { code: string },
  Release[]
> = ({ code }, options) => {
  const { query } = UseRequestProcessor();
  return query(
    ["useVerificationReleases", code],
    async () => (await api.get(`${path(code)}/releases`)).data,
    { enabled: !!code, retry: false, ...options },
  );
};
export const useVerificationRelease: useQueryFunctionType<
  { code: string; id: string },
  ReleaseDetail
> = ({ code, id }, options) => {
  const { query } = UseRequestProcessor();
  return query(
    ["useVerificationRelease", code, id],
    async () => (await api.get(`${path(code)}/releases/${id}`)).data,
    { enabled: !!code && !!id, retry: false, ...options },
  );
};
export const useCreateVerificationRule: useMutationFunctionType<
  undefined,
  { code: string; name: string; flow_id: string },
  Rule
> = (options) => {
  const { mutate, queryClient } = UseRequestProcessor();
  return mutate(
    ["useCreateVerificationRule"],
    async (body) =>
      (await api.post(`${getURL("VERIFICATION")}/rules`, body)).data,
    {
      retry: false,
      onSettled: () =>
        queryClient.invalidateQueries({ queryKey: ["useVerificationRules"] }),
      ...options,
    },
  );
};
export const usePrepareVerification: useMutationFunctionType<
  undefined,
  { code: string; catalog_mapping: Record<string, string>; note: string },
  Candidate
> = (options) => {
  const { mutate } = UseRequestProcessor();
  return mutate(
    ["usePrepareVerification"],
    async ({ code, ...body }) =>
      (await api.post(`${path(code)}/candidates`, body)).data,
    { retry: false, ...options },
  );
};
export const usePublishVerification: useMutationFunctionType<
  undefined,
  { code: string; candidate_id: string; content_hash: string },
  Release
> = (options) => {
  const { mutate, queryClient } = UseRequestProcessor();
  return mutate(
    ["usePublishVerification"],
    async ({ code, ...body }) =>
      (await api.post(`${path(code)}/releases`, body)).data,
    {
      retry: false,
      onSettled: () =>
        queryClient.invalidateQueries({
          queryKey: ["useVerificationReleases"],
        }),
      ...options,
    },
  );
};
export const useActivateVerification: useMutationFunctionType<
  undefined,
  { code: string; release_id: string | null; expected_revision: number },
  Rule
> = (options) => {
  const { mutate, queryClient } = UseRequestProcessor();
  return mutate(
    ["useActivateVerification"],
    async ({ code, ...body }) =>
      (await api.put(`${path(code)}/active`, body)).data,
    {
      retry: false,
      onSettled: () =>
        queryClient.invalidateQueries({ queryKey: ["useVerificationRules"] }),
      ...options,
    },
  );
};

export const useSaveVerificationDraft: useMutationFunctionType<
  undefined,
  {
    code: string;
    catalog_mapping: Record<string, string>;
    note: string;
    expected_revision: number;
  },
  Rule
> = (options) => {
  const { mutate, queryClient } = UseRequestProcessor();
  return mutate(
    ["useSaveVerificationDraft"],
    async ({ code, ...body }) =>
      (await api.put(`${path(code)}/draft`, body)).data,
    {
      retry: false,
      onSettled: () =>
        queryClient.invalidateQueries({ queryKey: ["useVerificationRules"] }),
      ...options,
    },
  );
};
