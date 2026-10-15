import { useState } from "react";
import { useBusinessQuery } from "@/controllers/API/queries/business";
import BusinessResultEvidence from "./BusinessResultEvidence";
import { useTranslation } from "./business-i18n";
import {
  ResultPages,
  RetainedFields,
  resultText as text,
} from "./ResultFields";
import ResultStorage from "./ResultStorage";

export type SavedResult = {
  id?: string;
  task_id?: string;
  release_id?: string;
  node_id?: string;
  template_id: string;
  template_version: number;
  status: "normal" | "difference" | "incomplete";
  complete: boolean;
  narrative: string;
  facts: Record<string, unknown>;
  checks: {
    name: string;
    label: string;
    status: string;
    left: unknown;
    right: unknown;
    difference: unknown;
    reason?: string;
  }[];
};
export function BusinessResultCard({
  result,
  example = false,
}: {
  result: SavedResult;
  example?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <article
      className="min-w-0 space-y-3 rounded border p-3"
      data-testid="business-result-card"
    >
      <div className="flex flex-wrap gap-2 text-sm font-semibold">
        <span>{t(`business.results.${result.status}`)}</span>
        <span>
          {example
            ? t("business.results.example")
            : t("business.results.saved")}
        </span>
        {result.facts.simulated === true && (
          <span>{t("business.results.simulated")}</span>
        )}
      </div>
      <p className="break-words text-sm leading-relaxed">{result.narrative}</p>
      <div className="overflow-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr>
              {(["check", "settled", "observed", "state"] as const).map((k) => (
                <th className="border-b p-2" key={k}>
                  {t(`business.results.${k}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.checks.map((c) => (
              <tr key={c.name}>
                <td className="p-2">{c.label}</td>
                <td className="p-2">{text(c.left)}</td>
                <td className="p-2">{text(c.right)}</td>
                <td className="p-2">
                  {t(`business.results.checkStatus.${c.status}`, {
                    defaultValue: c.status,
                  })}
                  {c.reason && <p className="text-xs">{c.reason}</p>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!example && result.task_id && result.id && (
        <BusinessResultEvidence taskId={result.task_id} resultId={result.id} />
      )}
      <details>
        <summary className="cursor-pointer text-sm">
          {t("business.resultEvidence.savedFields")}
        </summary>
        <p className="mt-2 text-xs">
          {result.template_id} · v{result.template_version}
        </p>
        <RetainedFields
          columns={Object.keys(result.facts)}
          values={result.facts}
        />
        <details>
          <summary>{t("business.layout.technical")}</summary>
          <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-all rounded bg-muted p-3 text-xs">
            {JSON.stringify(result, null, 2)}
          </pre>
        </details>
      </details>
    </article>
  );
}

export default function BusinessResults({
  taskId,
  nodeId,
  showStorage = true,
}: {
  taskId: string;
  nodeId?: string;
  showStorage?: boolean;
}) {
  const { t } = useTranslation();
  const [offset, setOffset] = useState(0);
  const results = useBusinessQuery<{ items: SavedResult[]; total: number }>(
    `tasks/${taskId}/results?limit=20&offset=${offset}${nodeId ? `&node_id=${encodeURIComponent(nodeId)}` : ""}`,
    !!taskId,
    true,
  );
  return (
    <section className="space-y-3" aria-label={t("business.results.title")}>
      <h3 className="font-semibold">{t("business.results.title")}</h3>
      <p className="text-xs text-muted-foreground">
        {t("business.results.taskHint")}
      </p>
      {showStorage && (
        <details className="rounded border p-3">
          <summary className="cursor-pointer text-sm font-medium">
            {t("business.results.storage")}
          </summary>
          <div className="mt-3">
            <ResultStorage taskId={taskId} nodeId={nodeId} />
          </div>
        </details>
      )}
      {results.error && <p role="alert">{results.error.message}</p>}
      {results.isLoading && (
        <p role="status">{t("business.taskInput.loading")}</p>
      )}
      {results.data?.total === 0 && (
        <p className="text-sm">{t("business.results.empty")}</p>
      )}
      {results.data?.items.map((r) => (
        <BusinessResultCard key={r.id} result={r} />
      ))}
      {!!results.data?.total && (
        <ResultPages
          offset={offset}
          total={results.data.total}
          size={20}
          change={setOffset}
        />
      )}
    </section>
  );
}
