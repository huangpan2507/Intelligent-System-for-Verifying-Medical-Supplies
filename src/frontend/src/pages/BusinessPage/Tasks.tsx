import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  type DatasetPage,
  type Task,
  useBusinessQuery,
} from "@/controllers/API/queries/business";
import AssessmentPanel from "./AssessmentPanel";
import BusinessResults from "./BusinessResults";
import RequestLog from "./RequestLog";
import { TaskInputValues } from "./TaskInputPanel";

const cell = (value: unknown) =>
  value === null || value === undefined
    ? "—"
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);
export default function Tasks() {
  const { taskId } = useParams();
  return taskId ? <TaskDetail taskId={taskId} /> : <TaskList />;
}
function TaskList() {
  const { t, i18n } = useTranslation();
  const [offset, setOffset] = useState(0);
  const query = useBusinessQuery<{ items: Task[]; total: number }>(
    `tasks?limit=50&offset=${offset}`,
    true,
    true,
  );
  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">{t("business.tasksHint")}</p>
      {query.error && <p role="alert">{query.error.message}</p>}
      <div className="overflow-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr>
              {(["scheme", "status", "source", "createdAt"] as const).map(
                (k) => (
                  <th className="border-b p-3" key={k}>
                    {t(`business.${k}`)}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {query.data?.items.map((task) => (
              <tr key={task.id}>
                <td className="border-b p-3">
                  <Link
                    className="text-primary underline"
                    to={`/business/tasks/${task.id}`}
                  >
                    {task.scheme_code}
                  </Link>
                  <p className="text-xs text-muted-foreground">{task.id}</p>
                </td>
                <td className="border-b p-3">
                  {t(`business.status.${task.status}`, {
                    defaultValue: task.status,
                  })}
                </td>
                <td className="border-b p-3">{task.source}</td>
                <td className="border-b p-3">
                  {new Date(task.created_at).toLocaleString(i18n.language)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex gap-2">
        <Button
          variant="outline"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 50))}
        >
          {t("business.previous")}
        </Button>
        <Button
          variant="outline"
          disabled={offset + 50 >= (query.data?.total ?? 0)}
          onClick={() => setOffset(offset + 50)}
        >
          {t("business.next")}
        </Button>
      </div>
    </div>
  );
}
function TaskDetail({ taskId }: { taskId: string }) {
  const { t } = useTranslation();
  const task = useBusinessQuery<Task>(`tasks/${taskId}`, true, true);
  const [selected, setSelected] = useState("");
  const [rawOpen, setRawOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const businessResult = task.data?.results?.find((resultId) =>
    task.data?.datasets?.some((d) => d.id === resultId && d.port === "data"),
  );
  const id =
    selected ||
    businessResult ||
    task.data?.results?.[0] ||
    task.data?.datasets?.[0]?.id ||
    "";
  const dataset = useBusinessQuery<DatasetPage>(
    `tasks/${taskId}/datasets/${id}?limit=50&offset=${offset}`,
    !!id,
  );
  return (
    <div className="space-y-5">
      <Link className="text-primary underline" to="/business/tasks">
        {t("business.backTasks")}
      </Link>
      {task.error && <p role="alert">{task.error.message}</p>}
      {task.data && (
        <>
          <div className="rounded border p-4">
            <h2 className="font-semibold">
              {task.data.scheme_code} ·{" "}
              {t("business.version", { version: task.data.version })}
            </h2>
            <p>
              {t("business.executionStatus")}:{" "}
              {t(`business.status.${task.data.status}`, {
                defaultValue: task.data.status,
              })}
            </p>
            <p>
              {t("business.unresolved", {
                count: task.data.unresolved_rows ?? 0,
              })}
            </p>
            {task.data.classification_counts && (
              <p>
                {t("business.classification.counts", {
                  continued: task.data.classification_counts.continue,
                  excluded: task.data.classification_counts.excluded,
                  undetermined: task.data.classification_counts.uncompared,
                })}
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              {t("business.coverageHint")}
            </p>
            {task.data.error && (
              <p role="alert" className="mt-2 text-destructive">
                {task.data.error.message}
              </p>
            )}
          </div>
          <BusinessResults key={taskId} taskId={taskId} />
          {task.data.task_input && (
            <section className="rounded border p-4 space-y-3">
              <h3 className="font-semibold">{t("business.taskInput.title")}</h3>
              <TaskInputValues input={task.data.task_input} />
            </section>
          )}
          <AssessmentPanel
            assessment={task.data.assessment}
            select={(id) => {
              setSelected(id);
              setRawOpen(true);
              setOffset(0);
            }}
          />
          <RequestLog taskId={taskId} />
          <details>
            <summary>{t("business.nodeProgress")}</summary>
            <div className="mt-2 space-y-1">
              {Object.entries(task.data.progress).map(([node, state]) => (
                <p key={node} className="text-sm">
                  {node} ·{" "}
                  {t(`business.status.${state.status}`, {
                    defaultValue: state.status,
                  })}{" "}
                  {state.elapsed_seconds != null &&
                    `· ${state.elapsed_seconds.toFixed(2)} s`}
                </p>
              ))}
            </div>
          </details>
          <details
            open={rawOpen}
            onToggle={(e) => setRawOpen(e.currentTarget.open)}
          >
            <summary className="cursor-pointer font-medium">
              {t("business.results.rawData")}
            </summary>
            <div className="mt-3 space-y-3">
              <label className="block space-y-2">
                <span className="font-medium">{t("business.dataset")}</span>
                <select
                  className="h-10 w-full rounded border bg-background px-2"
                  value={id}
                  onChange={(e) => {
                    setSelected(e.target.value);
                    setOffset(0);
                  }}
                >
                  {task.data.datasets?.map((d) => (
                    <option key={d.id} value={d.id}>
                      {task.data!.results.includes(d.id)
                        ? t("business.result")
                        : d.raw
                          ? t("business.raw")
                          : t(`business.port.${d.port}`, {
                              defaultValue: d.port,
                            })}{" "}
                      · {d.name} · {d.node_id} · {d.row_count}
                    </option>
                  ))}
                </select>
              </label>
              {dataset.error && <p role="alert">{dataset.error.message}</p>}
              {dataset.data && (
                <>
                  <p className="text-sm">
                    {t("business.totalRows", { count: dataset.data.total })}
                  </p>
                  <div className="max-h-[55vh] overflow-auto rounded border">
                    <table className="w-full whitespace-nowrap text-left text-sm">
                      <thead className="sticky top-0 bg-muted">
                        <tr>
                          {dataset.data.fields.map((f) => (
                            <th key={f.name} className="p-3">
                              <p>
                                {f.name === "classification_disposition"
                                  ? t("business.classification.statusColumn")
                                  : f.name === "_issue_severity"
                                    ? t("business.validationIssueType")
                                    : f.name}
                              </p>
                              <p className="text-xs font-normal text-muted-foreground">
                                {f.type}
                              </p>
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {dataset.data.rows.map((row, i) => (
                          <tr key={i}>
                            {dataset.data!.fields.map((f) => (
                              <td
                                key={f.name}
                                className="max-w-96 truncate border-t p-3"
                                title={cell(row[f.name])}
                              >
                                {f.name === "classification_disposition" &&
                                ["continue", "excluded", "uncompared"].includes(
                                  String(row[f.name]),
                                )
                                  ? t(
                                      `business.classification.${String(row[f.name])}`,
                                      { defaultValue: cell(row[f.name]) },
                                    )
                                  : f.name === "_issue_severity" &&
                                      row[f.name] === "info"
                                    ? t("business.validationDuplicateNotice")
                                    : f.name === "_issue_severity" &&
                                        row[f.name] === "error"
                                      ? t("business.validationError")
                                      : cell(row[f.name])}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      disabled={!offset}
                      onClick={() => setOffset(Math.max(0, offset - 50))}
                    >
                      {t("business.previous")}
                    </Button>
                    <Button
                      variant="outline"
                      disabled={offset + 50 >= dataset.data.total}
                      onClick={() => setOffset(offset + 50)}
                    >
                      {t("business.next")}
                    </Button>
                  </div>
                  <details>
                    <summary>{t("business.provenance")}</summary>
                    <pre className="max-h-64 overflow-auto text-xs">
                      {JSON.stringify(dataset.data.provenance, null, 2)}
                    </pre>
                  </details>
                </>
              )}
            </div>
          </details>
        </>
      )}
    </div>
  );
}
