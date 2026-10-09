import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { useGetVerificationRuns } from "@/controllers/API/queries/verification/tasks";
import { Pagination, QueryError, StatusBadge, useResultFormat } from "./shared";

export default function RunHistory({
  taskId,
  runId,
  selectRun,
}: {
  taskId: string;
  runId: string;
  selectRun: (id: string) => void;
}) {
  const { t } = useTranslation();
  const format = useResultFormat();
  const [offset, setOffset] = useState(0);
  const runs = useGetVerificationRuns({ taskId, offset, limit: 20 });
  return (
    <details className="rounded-lg border p-4">
      <summary className="cursor-pointer font-medium">
        {t("verificationTasks.runHistory")}
      </summary>
      <p className="my-3 text-sm text-muted-foreground">
        {t("verificationTasks.historyHint")}
      </p>
      {runs.error ? (
        <QueryError retry={() => void runs.refetch()} />
      ) : !runs.data ? (
        <p role="status">{t("verificationTasks.loading")}</p>
      ) : (
        <>
          <ul className="space-y-3">
            {runs.data.map((run) => (
              <li
                key={run.run_id}
                className="flex flex-wrap items-center justify-between gap-3 rounded border p-3"
              >
                <div>
                  <p className="text-sm">
                    {format.date(run.created_at)} · {run.rule_version}
                  </p>
                  <p className="break-all text-xs text-muted-foreground">
                    {run.run_id}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <StatusBadge status={run.status} />
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={run.run_id === runId}
                    onClick={() => selectRun(run.run_id)}
                  >
                    {t(
                      run.run_id === runId
                        ? "verificationTasks.selectedRun"
                        : "verificationTasks.viewRun",
                    )}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
          <Pagination
            offset={offset}
            limit={20}
            hasNext={runs.data.length === 20}
            busy={runs.isFetching}
            onChange={setOffset}
          />
        </>
      )}
    </details>
  );
}
