import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useBusinessQuery } from "@/controllers/API/queries/business";
import { useTranslation } from "./business-i18n";
import ResultEvidenceDialog from "./ResultEvidenceDialog";
import { FieldTable, ResultPages } from "./ResultFields";

type Item = {
  id: string;
  kind: string;
  title: string[];
  details: Record<string, unknown>;
  available: boolean;
  sources: string[];
  children: number;
};
type EvidencePage = {
  items: Item[];
  total: number;
  counts: Record<string, number>;
};
type Selection = { id: string; kind: string };
const pagePath = (
  base: string,
  group: string,
  offset: number,
  parent?: string,
) =>
  `${base}/evidence-view?group=${group}&limit=20&offset=${offset}${parent ? `&parent=${encodeURIComponent(parent)}` : ""}`;

export default function BusinessResultEvidence({
  taskId,
  resultId,
}: {
  taskId: string;
  resultId: string;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [selection, setSelection] = useState<Selection | null>(null);
  const base = `tasks/${taskId}/results/${resultId}`;
  const summary = useBusinessQuery<EvidencePage>(
    pagePath(base, "settlement", 0),
    open,
    false,
    { staleTime: Infinity },
  );
  return (
    <>
      <details onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary className="cursor-pointer font-medium">
          {t("business.results.evidence")}
        </summary>
        <p className="my-2 text-xs text-muted-foreground">
          {t("business.resultEvidence.hierarchyHint")}
        </p>
        {summary.error && <p role="alert">{summary.error.message}</p>}
        {summary.isLoading && (
          <p role="status">{t("business.taskInput.loading")}</p>
        )}
        {summary.data && (
          <div className="space-y-2">
            <p className="text-xs">
              {t("business.resultEvidence.counts", {
                studies: summary.data.counts.study,
                series: summary.data.counts.series,
                images: summary.data.counts.image,
              })}
            </p>
            {(["settlement", "study", "recognition", "unlinked"] as const).map(
              (group) =>
                group === "unlinked" && !summary.data.counts.unlinked ? null : (
                  <details key={group} className="rounded border p-2">
                    <summary className="cursor-pointer text-sm font-medium">
                      {t(`business.resultEvidence.group.${group}`)} ·{" "}
                      {summary.data.counts[group] ?? 0}
                    </summary>
                    <EvidenceGroup
                      base={base}
                      group={group}
                      select={setSelection}
                    />
                  </details>
                ),
            )}
          </div>
        )}
      </details>
      <ResultEvidenceDialog
        base={base}
        selection={selection}
        close={() => setSelection(null)}
      />
    </>
  );
}

function EvidenceGroup({
  base,
  group,
  parent,
  select,
}: {
  base: string;
  group: string;
  parent?: string;
  select: (s: Selection) => void;
}) {
  const { t } = useTranslation();
  const [offset, setOffset] = useState(0);
  const query = useBusinessQuery<EvidencePage>(
    pagePath(base, group, offset, parent),
    true,
    false,
    { staleTime: Infinity },
  );
  return (
    <div className="mt-2 min-w-0 space-y-2">
      {query.isLoading && (
        <p role="status">{t("business.taskInput.loading")}</p>
      )}
      {query.error && <p role="alert">{query.error.message}</p>}
      {query.data?.total === 0 && (
        <p className="text-sm">{t("business.resultEvidence.noneLinked")}</p>
      )}
      {query.data?.items.map((item) => (
        <EvidenceItem key={item.id} base={base} item={item} select={select} />
      ))}
      {query.data && (
        <ResultPages
          offset={offset}
          total={query.data.total}
          size={20}
          change={setOffset}
        />
      )}
    </div>
  );
}

function EvidenceItem({
  base,
  item,
  select,
}: {
  base: string;
  item: Item;
  select: (s: Selection) => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <details
      className="min-w-0 rounded border p-2"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary className="cursor-pointer break-words text-sm [overflow-wrap:anywhere]">
        {t(`business.resultEvidence.kind.${item.kind}`, {
          defaultValue: item.kind,
        })}
        {item.title.length > 0 && <span> · {item.title.join(" · ")}</span>}
      </summary>
      {open && (
        <div className="mt-3 space-y-3">
          {!item.available && (
            <p role="status" className="text-destructive">
              {t("business.resultEvidence.unavailable")}
            </p>
          )}
          {Object.keys(item.details).length > 0 && (
            <FieldTable values={item.details} />
          )}
          {item.sources.map((id, index) => (
            <Button
              key={id}
              variant="outline"
              size="sm"
              className="mr-2"
              onClick={() => select({ id, kind: "source" })}
            >
              {t("business.resultEvidence.viewSource", { number: index + 1 })}
            </Button>
          ))}
          {item.kind === "recognition" && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => select({ id: item.id, kind: "recognition" })}
            >
              {t("business.results.request")}
            </Button>
          )}
          {item.kind === "study" && (
            <EvidenceGroup
              base={base}
              group="series"
              parent={item.id}
              select={select}
            />
          )}
          {item.kind === "series" && (
            <EvidenceGroup
              base={base}
              group="image"
              parent={item.id}
              select={select}
            />
          )}
        </div>
      )}
    </details>
  );
}
