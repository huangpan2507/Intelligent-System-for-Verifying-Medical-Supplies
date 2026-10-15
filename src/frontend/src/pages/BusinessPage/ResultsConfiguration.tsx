import { type ReactNode, useState } from "react";
import {
  type Task,
  useBusinessQuery,
} from "@/controllers/API/queries/business";
import BusinessResults, {
  BusinessResultCard,
  type SavedResult,
} from "./BusinessResults";
import { businessOption, useTranslation } from "./business-i18n";
import ConfigurationSection from "./ConfigurationSection";
import { ResultPages } from "./ResultFields";
import ResultStorage from "./ResultStorage";

type ResultTemplate = {
  id: string;
  name: string;
  version: number;
  columns: string[];
  obligation: unknown;
  example: SavedResult;
};
export default function ResultsConfiguration({
  value,
  onChange,
  flowId,
  nodeId,
  children,
}: {
  value: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
  flowId?: string;
  nodeId: string;
  children?: ReactNode;
}) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState("");
  const [offset, setOffset] = useState(0);
  const templates = useBusinessQuery<ResultTemplate[]>("result-templates");
  const tasks = useBusinessQuery<{ items: Task[]; total: number }>(
    `tasks?flow_id=${encodeURIComponent(flowId ?? "")}&limit=20&offset=${offset}`,
    !!flowId,
  );
  const profile = templates.data?.find(
    (item) => item.id === value.result_template,
  );
  return (
    <div className="space-y-3">
      <ConfigurationSection
        id="results-template"
        title={t("business.results.template")}
        summary={
          profile
            ? `${profile.name} · v${profile.version}`
            : t("business.results.generic")
        }
        defaultOpen
      >
        {templates.error && <p role="alert">{templates.error.message}</p>}
        {!value.result_template && (
          <label className="block space-y-1 text-sm">
            <span>{t("business.field.name")}</span>
            <input
              className="h-9 w-full rounded border bg-background px-2"
              value={String(value.name ?? "")}
              onChange={(e) => onChange({ ...value, name: e.target.value })}
            />
          </label>
        )}
        <label className="block space-y-1 text-sm">
          <span>{t("business.results.template")}</span>
          <select
            className="h-9 w-full rounded border bg-background px-2"
            value={String(value.result_template ?? "")}
            disabled={!!value.result_template}
            onChange={(e) =>
              onChange({
                name: value.name || t("business.results.title"),
                ...(e.target.value ? { result_template: e.target.value } : {}),
              })
            }
          >
            <option value="">
              {businessOption("business.results.generic")}
            </option>
            {templates.data?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <p className="text-xs text-muted-foreground">
          {t("business.results.templateHint")}
        </p>
      </ConfigurationSection>
      <ConfigurationSection
        id="results-preview"
        title={t("business.results.preview")}
        summary={selected || t("business.results.example")}
        defaultOpen
      >
        <label className="block space-y-1 text-sm">
          <span>{t("business.taskInput.select")}</span>
          <select
            className="h-9 w-full rounded border bg-background px-2"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            <option value="">
              {businessOption("business.results.example")}
            </option>
            {selected &&
              !tasks.data?.items.some((task) => task.id === selected) && (
                <option value={selected}>{selected}</option>
              )}
            {tasks.data?.items
              .filter((task) => task.status === "completed")
              .map((task) => (
                <option key={task.id} value={task.id}>
                  {task.task_input?.task.external_task_id} · {task.id}
                </option>
              ))}
          </select>
        </label>
        {tasks.error && <p role="alert">{tasks.error.message}</p>}
        {(tasks.data?.total ?? 0) > 20 && (
          <ResultPages
            offset={offset}
            total={tasks.data!.total}
            size={20}
            change={setOffset}
          />
        )}
        {selected ? (
          <BusinessResults
            key={selected}
            taskId={selected}
            nodeId={nodeId}
            showStorage={false}
          />
        ) : profile ? (
          <BusinessResultCard result={profile.example} example />
        ) : (
          <p className="text-sm">{t("business.results.genericHint")}</p>
        )}
      </ConfigurationSection>
      <ConfigurationSection
        id="results-storage"
        title={t("business.results.storage")}
        summary={t("business.resultEvidence.storageSummary")}
      >
        <ResultStorage
          key={selected}
          taskId={selected || undefined}
          nodeId={nodeId}
          template={profile}
        />
        {children}
      </ConfigurationSection>
    </div>
  );
}
