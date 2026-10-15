import { Button } from "@/components/ui/button";
import { useTranslation } from "./business-i18n";

export const resultText = (value: unknown) =>
  value == null
    ? "—"
    : typeof value === "object"
      ? JSON.stringify(value, null, 2)
      : String(value);

export function FieldTable({ values }: { values: Record<string, unknown> }) {
  const { t } = useTranslation();
  return (
    <dl className="divide-y rounded border text-sm">
      {Object.entries(values).map(([name, value]) => (
        <div
          key={name}
          className="grid min-w-0 gap-1 p-2 sm:grid-cols-[minmax(8rem,1fr)_minmax(0,2fr)]"
        >
          <dt className="min-w-0 break-words">
            <span className="font-medium">
              {t(`business.resultFields.${name}`, { defaultValue: name })}
            </span>
            {t(`business.resultFields.${name}`, { defaultValue: name }) !==
              name && (
              <span className="block break-all text-xs text-muted-foreground">
                {name}
              </span>
            )}
          </dt>
          <dd className="min-w-0 whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
            {resultText(value).length > 300 ? (
              <details>
                <summary className="cursor-pointer">
                  {t("business.resultEvidence.expandValue")}
                </summary>
                {resultText(value)}
              </details>
            ) : typeof value === "boolean" ? (
              t(
                value
                  ? "business.resultEvidence.yes"
                  : "business.resultEvidence.no",
              )
            ) : (
              resultText(value)
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

const classification = [
  "target_category",
  "classification_method",
  "classification_reason",
  "classification_evidence_field",
  "classification_evidence_text",
  "classification_confidence",
];
const recognition = [
  "recognized_category",
  "recognized_quantity",
  "recognition_confirmed",
  "coverage_confirmed",
  "simulated",
];
const comparison = [
  "settled_amount",
  "observed_amount",
  "category_status",
  "quantity_status",
  "amount_status",
  "difference_1",
  "difference_2",
  "_comparison_status",
];
const evidence = [
  "unit_row_id",
  "_identity",
  "_request_id",
  "evidence_ref",
  "image_manifest",
  "image_manifest_context",
];

export function RetainedFields({
  columns,
  values,
}: {
  columns: string[];
  values?: Record<string, unknown>;
}) {
  const { t } = useTranslation();
  const groups = {
    source: columns.filter(
      (f) =>
        ![
          ...classification,
          ...recognition,
          ...comparison,
          ...evidence,
        ].includes(f),
    ),
    classification,
    recognition,
    comparison,
    evidence,
  };
  return (
    <div className="space-y-2">
      {(Object.keys(groups) as (keyof typeof groups)[]).map((group) => {
        const fields = groups[group].filter((name) => columns.includes(name));
        if (!fields.length) return null;
        return (
          <details key={group} className="rounded border p-2">
            <summary className="cursor-pointer text-sm font-medium">
              {t(`business.resultEvidence.fields.${group}`)} · {fields.length}
            </summary>
            <div className="mt-2">
              {values ? (
                <FieldTable
                  values={Object.fromEntries(fields.map((f) => [f, values[f]]))}
                />
              ) : (
                <dl className="divide-y text-sm">
                  {fields.map((name) => (
                    <div key={name} className="grid gap-1 py-2 sm:grid-cols-2">
                      <dt>
                        {t(`business.resultFields.${name}`, {
                          defaultValue: name,
                        })}
                      </dt>
                      <dd className="break-all text-xs text-muted-foreground">
                        {name}
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
            </div>
          </details>
        );
      })}
    </div>
  );
}

export function ResultPages({
  offset,
  total,
  size,
  change,
}: {
  offset: number;
  total: number;
  size: number;
  change: (offset: number) => void;
}) {
  const { t } = useTranslation();
  if (total <= size) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <Button
        size="sm"
        variant="outline"
        disabled={!offset}
        onClick={() => change(Math.max(0, offset - size))}
      >
        {t("business.previous")}
      </Button>
      <span>{t("business.totalRows", { count: total })}</span>
      <Button
        size="sm"
        variant="outline"
        disabled={offset + size >= total}
        onClick={() => change(offset + size)}
      >
        {t("business.next")}
      </Button>
    </div>
  );
}
