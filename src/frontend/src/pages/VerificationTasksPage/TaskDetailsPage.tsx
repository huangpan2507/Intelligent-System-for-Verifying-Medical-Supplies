import { useContext, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams, useSearchParams } from "react-router-dom";
import PageLayout from "@/components/common/pageLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AuthContext } from "@/contexts/authContext";
import {
  useGetVerificationResults,
  useGetVerificationTask,
} from "@/controllers/API/queries/verification/tasks";
import { CustomLink } from "@/customization/components/custom-link";
import EvidencePanel from "./EvidencePanel";
import ResultsTable from "./ResultsTable";
import RunHistory from "./RunHistory";
import { Pagination, QueryError, StatusBadge, useResultFormat } from "./shared";

export default function TaskDetailsPage() {
  const { taskId = "" } = useParams();
  return <TaskDetails key={taskId} taskId={taskId} />;
}

function TaskDetails({ taskId }: { taskId: string }) {
  const { t } = useTranslation();
  const { userData } = useContext(AuthContext);
  const isAdmin = !!userData?.is_superuser;
  const [params, setParams] = useSearchParams();
  const [offset, setOffset] = useState(0);
  const task = useGetVerificationTask({ taskId }, { enabled: isAdmin });
  const runId = params.get("run_id") || task.data?.run_id || "";
  useEffect(() => setOffset(0), [runId]);
  const results = useGetVerificationResults(
    { taskId, runId, offset, limit: 20 },
    { enabled: isAdmin },
  );
  const view = results.data ?? task.data;
  const format = useResultFormat();
  const selectRun = (id: string) => {
    setOffset(0);
    setParams({ run_id: id });
  };
  const refresh = () => {
    void task.refetch();
    void results.refetch();
  };
  const running = view?.status === "waiting" || view?.status === "running";
  const saved = results.data?.result;
  return (
    <PageLayout
      title={t("verificationTasks.detailTitle")}
      description={t("verificationTasks.detailDescription")}
      backTo="/verification/tasks"
      button={
        <Button
          variant="outline"
          disabled={!isAdmin || !runId || results.isFetching}
          onClick={refresh}
        >
          {t("verificationTasks.refresh")}
        </Button>
      }
    >
      <main className="w-full min-w-0 space-y-5">
        {!isAdmin ? (
          <p role="alert">{t("verification.adminOnly")}</p>
        ) : task.error || results.error ? (
          <QueryError retry={refresh} />
        ) : !view || !results.data ? (
          <p role="status">{t("verificationTasks.loading")}</p>
        ) : (
          <>
            <section
              className="space-y-4 rounded-lg border p-5"
              aria-label={t("verificationTasks.overview")}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h3 className="break-all text-lg font-semibold">
                  {view.external_task_id}
                </h3>
                <div className="flex gap-2">
                  <StatusBadge status={view.status} />
                  {saved && (
                    <Badge variant="outline">
                      {t(
                        saved.simulated
                          ? "verification.simulation"
                          : "verification.production",
                      )}
                    </Badge>
                  )}
                </div>
              </div>
              <dl className="grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-3">
                <div>
                  <dt className="text-muted-foreground">
                    {t("verificationTasks.hospital")}
                  </dt>
                  <dd>{view.scope.hospital_scope}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">
                    {t("verificationTasks.rule")}
                  </dt>
                  <dd>
                    {view.scope.rule}
                    <p className="text-xs">{view.rule_version}</p>
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">
                    {t("verificationTasks.source")}
                  </dt>
                  <dd>{view.source_system}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">
                    {t("verificationTasks.period")}
                  </dt>
                  <dd>
                    {t("verificationTasks.periodValue", {
                      start: format.date(
                        view.scope.settlement_time_range.start_inclusive,
                      ),
                      end: format.date(
                        view.scope.settlement_time_range.end_exclusive,
                      ),
                    })}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">
                    {t("verificationTasks.stageLabel")}
                  </dt>
                  <dd>{format.stage(view.stage)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">
                    {t("verificationTasks.finishedAt")}
                  </dt>
                  <dd>{format.date(view.finished_at)}</dd>
                </div>
              </dl>
              {running && (
                <p role="status" className="text-sm text-muted-foreground">
                  {t("verificationTasks.processing", {
                    details: format.number(
                      typeof view.progress.discovered === "number"
                        ? view.progress.discovered
                        : undefined,
                    ),
                    units: format.number(
                      typeof view.progress.units === "number"
                        ? view.progress.units
                        : undefined,
                    ),
                  })}
                </p>
              )}
              <details>
                <summary className="cursor-pointer text-sm text-muted-foreground">
                  {t("verificationTasks.traceability")}
                </summary>
                <dl className="mt-3 grid gap-2 break-all text-xs sm:grid-cols-2">
                  {(["task_id", "run_id", "job_id", "release_id"] as const).map(
                    (key) => (
                      <div key={key}>
                        <dt>{t(`verificationTasks.${key}`)}</dt>
                        <dd>{view[key]}</dd>
                      </div>
                    ),
                  )}
                </dl>
              </details>
            </section>
            {view.error && (
              <div
                role="alert"
                className="rounded-lg border border-destructive p-4 text-destructive"
              >
                <p className="font-medium">
                  {t("verificationTasks.executionError")}
                </p>
                <p className="mt-1 break-words text-sm">{view.error.message}</p>
                <p className="text-xs">{view.error.code}</p>
              </div>
            )}
            {view.run_id !== view.current_run_id && (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-4">
                <p>{t("verificationTasks.historicalRun")}</p>
                <Button
                  variant="outline"
                  onClick={() => selectRun(view.current_run_id)}
                >
                  {t("verificationTasks.latestRun")}
                </Button>
              </div>
            )}
            <RunHistory taskId={taskId} runId={runId} selectRun={selectRun} />
            <Tabs defaultValue="results">
              <TabsList aria-label={t("verificationTasks.detailTitle")}>
                <TabsTrigger value="results">
                  {t("verificationTasks.resultDetails")}
                </TabsTrigger>
                <TabsTrigger value="evidence">
                  {t("verificationTasks.evidence")}
                </TabsTrigger>
              </TabsList>
              <TabsContent value="results" className="space-y-4 pt-3">
                {!saved ? (
                  <p className="rounded-lg border p-6 text-muted-foreground">
                    {t(
                      running
                        ? "verificationTasks.resultPending"
                        : "verificationTasks.resultUnavailable",
                    )}
                  </p>
                ) : (
                  <>
                    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                      {(
                        [
                          "units",
                          "consistent",
                          "difference",
                          "not_compared",
                        ] as const
                      ).map((key) => (
                        <div key={key} className="rounded-lg border p-4">
                          <p className="text-sm text-muted-foreground">
                            {t(`verificationTasks.summary.${key}`)}
                          </p>
                          <p className="mt-2 text-2xl font-semibold">
                            {format.number(Number(saved.summary[key]))}
                          </p>
                        </div>
                      ))}
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {t("verificationTasks.resultSummary", {
                        details: saved.summary.details,
                        failed:
                          Number(saved.summary.failed) +
                          Number(saved.summary.partial_failed),
                      })}
                    </p>
                    {saved.simulated && (
                      <p className="rounded-lg bg-muted p-3 text-sm">
                        {t("verificationTasks.simulationHint")}
                      </p>
                    )}
                    <p className="text-sm text-muted-foreground">
                      {t("verificationTasks.differenceHint")}
                    </p>
                    {saved.summary.empty ? (
                      <p className="rounded-lg border p-6">
                        {t("verificationTasks.emptyScope")}
                      </p>
                    ) : (
                      <ResultsTable results={saved.results} />
                    )}
                    <Pagination
                      offset={offset}
                      limit={20}
                      total={Number(saved.summary.units)}
                      busy={results.isFetching}
                      onChange={setOffset}
                    />
                  </>
                )}
              </TabsContent>
              <TabsContent value="evidence" className="pt-3">
                <EvidencePanel
                  key={runId}
                  taskId={taskId}
                  runId={runId}
                  running={running}
                />
              </TabsContent>
            </Tabs>
            <Button variant="outline" asChild>
              <CustomLink to="/verification/tasks">
                {t("verificationTasks.backToTasks")}
              </CustomLink>
            </Button>
          </>
        )}
      </main>
    </PageLayout>
  );
}
