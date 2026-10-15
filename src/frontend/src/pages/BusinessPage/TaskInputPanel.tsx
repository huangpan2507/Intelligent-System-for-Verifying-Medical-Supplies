import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  type AcceptedTaskInput,
  type Catalog,
  type Task,
  useBusinessQuery,
} from "@/controllers/API/queries/business";
import { businessOption, useTranslation } from "./business-i18n";
import ConfigurationSection from "./ConfigurationSection";
import { businessError } from "./errors";

export function TaskInputValues({
  input,
  definition,
}: {
  input?: AcceptedTaskInput | null;
  definition?: Catalog["task_input"];
}) {
  const { t } = useTranslation();
  const values = { ...input?.parameters, ...input?.task };
  const fields = definition
    ? [...definition.parameters, ...definition.context]
    : Object.keys(values).map((name) => ({ name, type: "" }));
  const groups = [
    {
      id: "task-business",
      title: t("business.layout.taskBusiness"),
      names: ["hospital_name", "start", "end", "rule_name"],
      open: true,
    },
    {
      id: "task-trace",
      title: t("business.layout.taskTrace"),
      names: ["external_task_id", "task_id", "version"],
      open: false,
    },
    {
      id: "task-technical",
      title: t("business.layout.technical"),
      names: fields
        .map((f) => f.name)
        .filter(
          (name) =>
            ![
              "hospital_name",
              "start",
              "end",
              "rule_name",
              "external_task_id",
              "task_id",
              "version",
            ].includes(name),
        ),
      open: false,
    },
  ];
  return (
    <div className="space-y-3" data-testid="business-task-input-values">
      {groups.map((group) => {
        const entries = fields.filter((field) =>
          group.names.includes(field.name),
        );
        if (!entries.length) return null;
        return (
          <ConfigurationSection
            key={group.id}
            id={group.id}
            title={group.title}
            defaultOpen={group.open}
            summary={
              input
                ? t("business.layout.receivedFields", {
                    count: entries.filter((field) => values[field.name] != null)
                      .length,
                  })
                : t("business.taskInput.notReceived")
            }
          >
            <dl className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,16rem),1fr))] gap-x-4">
              {entries.map((field) => (
                <div key={field.name} className="min-w-0 border-b py-2">
                  <dt className="text-sm font-medium">
                    {t(`business.taskInput.${field.name}`, {
                      defaultValue: field.name,
                    })}
                  </dt>
                  <dd className="select-text break-words text-sm">
                    {input
                      ? String(
                          values[field.name] ??
                            t("business.layout.missingValue"),
                        )
                      : t("business.taskInput.notReceived")}
                  </dd>
                  <dd className="break-all text-xs text-muted-foreground">
                    {field.name}
                    {field.type ? ` · ${field.type}` : ""}
                  </dd>
                </div>
              ))}
            </dl>
          </ConfigurationSection>
        );
      })}
    </div>
  );
}

export default function TaskInputPanel({
  flowId,
  definition,
}: {
  flowId?: string;
  definition?: Catalog["task_input"];
}) {
  const { t } = useTranslation();
  const [selection, setSelection] = useState({ flowId, id: "" });
  const [page, setPage] = useState({ flowId, offset: 0 });
  const selected = selection.flowId === flowId ? selection.id : "";
  const offset = page.flowId === flowId ? page.offset : 0;
  const tasks = useBusinessQuery<{ items: Task[]; total: number }>(
    `tasks?flow_id=${encodeURIComponent(flowId ?? "")}&limit=20&offset=${offset}`,
    !!flowId,
    true,
  );
  const detail = useBusinessQuery<Task>(`tasks/${selected}`, !!selected);
  const current =
    detail.data?.id === selected && detail.data.flow_id === flowId
      ? detail.data
      : undefined;
  return (
    <section className="space-y-3" data-testid="business-task-input">
      <p className="text-sm text-muted-foreground">
        {t("business.taskInput.hint")}
      </p>
      <label className="block space-y-1">
        <span className="text-sm font-medium">
          {t("business.taskInput.select")}
        </span>
        <select
          className="h-10 w-full rounded border bg-background px-2 text-sm"
          value={selected}
          disabled={!flowId}
          onChange={(e) => setSelection({ flowId, id: e.target.value })}
        >
          <option value="">
            {businessOption("business.taskInput.definition")}
          </option>
          {current &&
            !tasks.data?.items.some((task) => task.id === selected) && (
              <option value={selected}>
                {current.task_input?.task.external_task_id} · {selected}
              </option>
            )}
          {tasks.data?.items.map((task) => (
            <option key={task.id} value={task.id}>
              {task.task_input?.task.external_task_id} · {task.id}
            </option>
          ))}
        </select>
      </label>
      {!!tasks.data?.total && tasks.data.total > 20 && (
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={offset === 0}
            onClick={() => setPage({ flowId, offset: offset - 20 })}
          >
            {t("business.previous")}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={offset + 20 >= tasks.data.total}
            onClick={() => setPage({ flowId, offset: offset + 20 })}
          >
            {t("business.next")}
          </Button>
        </div>
      )}
      {(tasks.error || detail.error) && (
        <p role="alert">{businessError(tasks.error ?? detail.error)}</p>
      )}
      {selected && !current ? (
        <p role="status">{t("business.taskInput.loading")}</p>
      ) : (
        <TaskInputValues input={current?.task_input} definition={definition} />
      )}
      <p className="text-xs text-muted-foreground">
        {t("business.taskInput.testHint")}
      </p>
    </section>
  );
}
