import { useContext, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import PageLayout from "@/components/common/pageLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { AuthContext } from "@/contexts/authContext";
import {
  RUN_STATUSES,
  useGetVerificationTasks,
} from "@/controllers/API/queries/verification/tasks";
import { CustomLink } from "@/customization/components/custom-link";
import { Pagination, QueryError, StatusBadge, useResultFormat } from "./shared";

export default function VerificationTasksPage() {
  const { t } = useTranslation();
  const { userData } = useContext(AuthContext);
  const isAdmin = !!userData?.is_superuser;
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const status = params.get("status") ?? "";
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const [search, setSearch] = useState(q);
  const tasks = useGetVerificationTasks(
    { q, status, offset, limit: 20 },
    { enabled: isAdmin },
  );
  const format = useResultFormat();
  const update = (values: Record<string, string>) =>
    setParams({ q, status, offset: "0", ...values });
  return (
    <PageLayout
      title={t("verificationTasks.title")}
      description={t("verificationTasks.description")}
      button={
        <Button variant="outline" asChild>
          <CustomLink to="/verification">{t("verification.title")}</CustomLink>
        </Button>
      }
    >
      <main className="w-full min-w-0 space-y-5">
        {!isAdmin ? (
          <p role="alert">{t("verification.adminOnly")}</p>
        ) : (
          <>
            <form
              className="flex flex-wrap items-end gap-3"
              onSubmit={(event) => {
                event.preventDefault();
                update({ q: search.trim() });
              }}
            >
              <label className="min-w-60 flex-1 space-y-1 text-sm">
                {t("verificationTasks.searchLabel")}
                <Input
                  value={search}
                  maxLength={200}
                  placeholder={t("verificationTasks.searchPlaceholder")}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </label>
              <label className="space-y-1 text-sm">
                {t("verificationTasks.statusLabel")}
                <select
                  className="block h-10 rounded border bg-background px-3"
                  value={status}
                  onChange={(event) => update({ status: event.target.value })}
                >
                  <option value="">{t("verificationTasks.allStatuses")}</option>
                  {RUN_STATUSES.map((value) => (
                    <option key={value} value={value}>
                      {t(`verificationTasks.status.${value}`)}
                    </option>
                  ))}
                </select>
              </label>
              <Button type="submit">{t("verificationTasks.search")}</Button>
              <Button
                type="button"
                variant="outline"
                disabled={tasks.isFetching}
                onClick={() => void tasks.refetch()}
              >
                {t("verificationTasks.refresh")}
              </Button>
            </form>
            <p className="text-sm text-muted-foreground">
              {t("verificationTasks.autoRefresh")}
            </p>
            {tasks.error ? (
              <QueryError retry={() => void tasks.refetch()} />
            ) : tasks.isPending ? (
              <p role="status">{t("verificationTasks.loading")}</p>
            ) : (
              <>
                {!tasks.data?.items.length ? (
                  <p className="rounded-lg border p-8 text-center text-muted-foreground">
                    {t("verificationTasks.empty")}
                  </p>
                ) : (
                  <div className="overflow-x-auto rounded-lg border">
                    <Table aria-label={t("verificationTasks.title")}>
                      <TableHeader>
                        <TableRow>
                          {(
                            [
                              "reference",
                              "hospital",
                              "rule",
                              "statusLabel",
                              "stageLabel",
                              "createdAt",
                            ] as const
                          ).map((key) => (
                            <TableHead key={key}>
                              {t(`verificationTasks.${key}`)}
                            </TableHead>
                          ))}
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {tasks.data.items.map((task) => (
                          <TableRow key={task.task_id}>
                            <TableCell>
                              <CustomLink
                                className="font-medium text-primary underline underline-offset-4"
                                to={`/verification/tasks/${task.task_id}?run_id=${task.run_id}`}
                              >
                                {task.external_task_id}
                              </CustomLink>
                              <p className="mt-1 text-xs text-muted-foreground">
                                {task.source_system}
                              </p>
                            </TableCell>
                            <TableCell>{task.scope.hospital_scope}</TableCell>
                            <TableCell>
                              {task.scope.rule}
                              <p className="text-xs text-muted-foreground">
                                {task.rule_version}
                              </p>
                            </TableCell>
                            <TableCell>
                              <StatusBadge status={task.status} />
                            </TableCell>
                            <TableCell className="whitespace-nowrap">
                              {format.stage(task.stage)}
                            </TableCell>
                            <TableCell className="whitespace-nowrap">
                              {format.date(task.created_at)}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
                <Pagination
                  offset={offset}
                  limit={20}
                  total={tasks.data?.total ?? 0}
                  busy={tasks.isFetching}
                  onChange={(next) => update({ offset: String(next) })}
                />
              </>
            )}
          </>
        )}
      </main>
    </PageLayout>
  );
}
