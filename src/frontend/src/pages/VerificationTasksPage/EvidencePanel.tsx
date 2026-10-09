import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useGetVerificationEvidence } from "@/controllers/API/queries/verification/tasks";
import { JsonDetails, Pagination, QueryError, StatusBadge } from "./shared";

export default function EvidencePanel({
  taskId,
  runId,
  running,
}: {
  taskId: string;
  runId: string;
  running: boolean;
}) {
  const { t } = useTranslation();
  const [offset, setOffset] = useState(0);
  const evidence = useGetVerificationEvidence(
    { taskId, runId, offset, limit: 20 },
    { refetchInterval: running ? 5000 : false },
  );
  if (evidence.error)
    return <QueryError retry={() => void evidence.refetch()} />;
  if (!evidence.data)
    return <p role="status">{t("verificationTasks.loading")}</p>;
  const { artifacts, model_requests: requests, pagination } = evidence.data;
  return (
    <div className="space-y-5">
      <p className="text-sm text-muted-foreground">
        {t("verificationTasks.evidenceDescription", {
          artifacts: pagination.artifacts_total,
          requests: pagination.model_requests_total,
        })}
      </p>
      {!artifacts.length && !requests.length && (
        <p>{t("verificationTasks.noEvidence")}</p>
      )}
      {requests.length > 0 && (
        <section
          className="space-y-3"
          aria-label={t("verificationTasks.modelRequests")}
        >
          <h3 className="font-semibold">
            {t("verificationTasks.modelRequests")}
          </h3>
          {requests.map((request) => (
            <article key={request.request_id} className="rounded-lg border p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="break-all text-sm">{request.request_id}</p>
                <StatusBadge status={request.status} />
              </div>
              {request.raw_response && (
                <p className="mt-2 text-sm">
                  {t("verificationTasks.modelResponse", {
                    model: request.raw_response.model_version,
                    quantity:
                      request.raw_response.count ??
                      t("verificationTasks.unavailable"),
                  })}
                </p>
              )}
              <JsonDetails value={request} />
            </article>
          ))}
        </section>
      )}
      {artifacts.length > 0 && (
        <section
          className="space-y-3"
          aria-label={t("verificationTasks.artifacts")}
        >
          <h3 className="font-semibold">{t("verificationTasks.artifacts")}</h3>
          {artifacts.map((artifact) => (
            <article
              key={artifact.artifact_id}
              className="rounded-lg border p-4"
            >
              <h4 className="text-sm font-medium">
                {t(`verificationTasks.artifact.${artifact.kind}`, {
                  defaultValue: artifact.kind,
                })}
              </h4>
              <p className="mt-1 break-all text-xs text-muted-foreground">
                {artifact.key}
              </p>
              <JsonDetails value={artifact.payload} />
            </article>
          ))}
        </section>
      )}
      <Pagination
        offset={offset}
        limit={20}
        total={Math.max(
          pagination.artifacts_total,
          pagination.model_requests_total,
        )}
        busy={evidence.isFetching}
        onChange={setOffset}
      />
    </div>
  );
}
