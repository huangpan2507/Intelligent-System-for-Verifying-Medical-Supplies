import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import type { JsonSchema } from "@/controllers/API/queries/business";
import { businessOption, useTranslation } from "./business-i18n";
import ConfigurationSection from "./ConfigurationSection";
import { configurationShape } from "./configuration-layout";
import { lookupProblems } from "./lookup-config";
import { type FormOptions, SchemaForm } from "./SchemaForm";

type Item = Record<string, unknown>;

/** Match the executor's order and show only the inputs used by each operation. */
export function calculationShape(schema: JsonSchema, item: Item): JsonSchema {
  const operation = item.operation ?? "copy";
  const keys = ["operation", "output"];
  if (operation === "expression") keys.push("expression");
  else keys.push("field");
  if (operation === "cast") {
    keys.push("type");
    if (item.type === "number") keys.push("precision", "scale");
  }
  if (operation === "map") keys.push("mapping");
  return {
    ...configurationShape(schema, keys),
    required: [
      "operation",
      "output",
      operation === "expression" ? "expression" : "field",
      ...(operation === "cast" ? ["type"] : []),
    ],
  };
}

export default function CompareConfiguration({
  value,
  onChange,
  schema,
  options,
  children,
}: {
  value: Record<string, unknown>;
  onChange: (value: unknown) => void;
  schema: JsonSchema;
  options: FormOptions;
  children?: ReactNode;
}) {
  const { t } = useTranslation();
  const calculations = (value.calculations ?? []) as Item[];
  const comparisons = (value.comparisons ?? []) as Item[];
  const calculationSchema = schema.properties?.calculations?.items ?? {};
  const comparisonSchema = schema.properties?.comparisons?.items ?? {};
  const outputs = new Set([
    ...calculations.map((i) => i.output),
    ...comparisons.map((i) => i.output),
  ]);
  const upstream =
    options.fields?.upstream ??
    (options.fields?.data ?? []).filter(
      (f) =>
        !outputs.has(f.name) &&
        !/^(comparison_|difference_|_comparison_status$)/.test(f.name),
    );
  const available = (before: number): FormOptions => ({
    ...options,
    compact: true,
    fields: {
      ...options.fields,
      data: [
        ...upstream,
        ...calculations
          .slice(0, before)
          .filter((i) => i.output)
          .map(
            (i) =>
              options.fields?.result?.find((f) => f.name === i.output) ?? {
                name: String(i.output),
                type: "unknown",
              },
          ),
      ],
    },
  });
  const fieldLabel = (field: unknown) =>
    t(`business.compare.field.${String(field)}`, {
      defaultValue: String(field ?? "—"),
    });
  const formula = (item: Item) =>
    `${fieldLabel(item.output)} = ${item.operation === "expression" ? item.expression || "—" : item.field || "—"}`;
  const modeLabel = (mode: unknown) =>
    t(`business.compare.mode.${String(mode ?? "exact")}`, {
      defaultValue: String(mode ?? "exact"),
    });
  const comparisonSummary = (item: Item) =>
    `${fieldLabel(item.left)} ↔ ${fieldLabel(item.right)} · ${modeLabel(item.mode)}`;
  const isTrace = (item: Item) =>
    item.operation === "copy" &&
    item.field === "_representative_row_id" &&
    item.output === "unit_row_id";
  const update = (
    key: "calculations" | "comparisons",
    index: number,
    item: Item | null,
  ) => {
    const list = key === "calculations" ? calculations : comparisons;
    onChange({
      ...value,
      [key]:
        item === null
          ? list.filter((_, i) => i !== index)
          : list.map((old, i) => (i === index ? item : old)),
    });
  };
  const calculationErrors = (item: Item, index: number) =>
    lookupProblems(
      calculationShape(calculationSchema, item),
      item,
      available(index),
    );
  const comparisonErrors = (item: Item) =>
    lookupProblems(comparisonSchema, item, available(calculations.length));
  const calculationEditor = (item: Item, index: number) => (
    <details
      key={index}
      className="min-w-0 rounded border p-2"
      open={calculationErrors(item, index) > 0 ? true : undefined}
    >
      <summary className="cursor-pointer break-words text-sm">
        {formula(item)}
      </summary>
      <div className="mt-2 space-y-2">
        <SchemaForm
          schema={calculationShape(calculationSchema, item)}
          value={item}
          options={available(index)}
          onChange={(next) => {
            const changed = next as Item;
            // Changing operation discards only parameters no longer used by it.
            const keys = Object.keys(
              calculationShape(calculationSchema, changed).properties ?? {},
            );
            update(
              "calculations",
              index,
              changed.operation === item.operation
                ? changed
                : Object.fromEntries(
                    Object.entries(changed).filter(([key]) =>
                      keys.includes(key),
                    ),
                  ),
            );
          }}
        />
        <Button
          size="sm"
          variant="ghost"
          onClick={() => update("calculations", index, null)}
        >
          {t("business.remove")}
        </Button>
      </div>
    </details>
  );
  return (
    <div className="space-y-3">
      <ConfigurationSection
        id="compare-source"
        title={t("business.compare.source")}
        summary={t("business.lookup.upstream", {
          source:
            Array.from(
              new Set(upstream.map((f) => f.source).filter(Boolean)),
            ).join(" · ") || t("business.lookup.none"),
        })}
      >
        <p className="text-xs text-muted-foreground">
          {t("business.compare.sourceHint")}
        </p>
        <ul className="space-y-1 text-xs">
          {upstream
            .filter(
              (f) =>
                comparisons.some(
                  (c) => c.left === f.name || c.right === f.name,
                ) ||
                calculations.some(
                  (c) =>
                    c.field === f.name ||
                    (typeof c.expression === "string" &&
                      c.expression.includes(f.name)),
                ),
            )
            .map((field) => (
              <li key={field.name} className="break-words">
                {fieldLabel(field.name)} ·{" "}
                {field.source ? `${field.source}.` : ""}
                {field.name} · {field.type}
              </li>
            ))}
        </ul>
      </ConfigurationSection>
      <ConfigurationSection
        id="compare-calculations"
        title={t("business.compare.calculations")}
        summary={
          calculations
            .filter((c) => !isTrace(c))
            .map(formula)
            .join(" · ") || t("business.compare.noCalculations")
        }
        errors={calculations.reduce(
          (sum, item, index) => sum + calculationErrors(item, index),
          0,
        )}
        defaultOpen
      >
        <p className="text-xs text-muted-foreground">
          {t("business.compare.calculationHint")}
        </p>
        {calculations.map(
          (item, index) => !isTrace(item) && calculationEditor(item, index),
        )}
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            onChange({
              ...value,
              calculations: [
                ...calculations,
                { operation: "expression", output: "", expression: "" },
              ],
            })
          }
        >
          {t("business.compare.addCalculation")}
        </Button>
        {calculations.some(isTrace) && (
          <details
            open={
              calculations.some(
                (item, index) =>
                  isTrace(item) && calculationErrors(item, index) > 0,
              )
                ? true
                : undefined
            }
          >
            <summary className="cursor-pointer text-sm">
              {t("business.compare.trace")}
            </summary>
            <p className="my-2 text-xs text-muted-foreground">
              {t("business.compare.traceHint")}
            </p>
            {calculations.map(
              (item, index) => isTrace(item) && calculationEditor(item, index),
            )}
          </details>
        )}
      </ConfigurationSection>
      <ConfigurationSection
        id="compare-comparisons"
        title={t("business.compare.comparisons")}
        summary={comparisons.map(comparisonSummary).join(" · ")}
        errors={
          comparisons.length
            ? comparisons.reduce((sum, item) => sum + comparisonErrors(item), 0)
            : 1
        }
        defaultOpen
      >
        <p className="text-xs text-muted-foreground">
          {t("business.compare.strictHint")}
        </p>
        {comparisons.map((item, index) => (
          <div key={index} className="min-w-0 space-y-2 rounded border p-2">
            <p className="break-words text-sm font-medium">
              {fieldLabel(item.output || `comparison_${index}`)}
            </p>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,10rem),1fr))] gap-2">
              {["left", "mode", "right"].map((key) => (
                <label key={key} className="min-w-0 space-y-1 text-xs">
                  <span>
                    {t(`business.field.${key}`, { defaultValue: key })}
                  </span>
                  {key === "mode" ? (
                    <select
                      aria-label={t("business.field.mode")}
                      className="h-10 w-full rounded border bg-background px-2 text-sm"
                      value={String(item.mode ?? "exact")}
                      onChange={(e) =>
                        update("comparisons", index, {
                          ...item,
                          mode: e.target.value,
                        })
                      }
                    >
                      {Array.from(
                        new Set([
                          "exact",
                          "numeric",
                          "case_insensitive",
                          String(item.mode ?? "exact"),
                        ]),
                      ).map((mode) => (
                        <option key={mode} value={mode}>
                          {businessOption(`business.compare.mode.${mode}`, {
                            defaultValue: mode,
                          })}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <SchemaForm
                      schema={comparisonSchema.properties?.[key] ?? {}}
                      value={item[key]}
                      name={key}
                      options={available(calculations.length)}
                      onChange={(field) =>
                        update("comparisons", index, { ...item, [key]: field })
                      }
                    />
                  )}
                </label>
              ))}
            </div>
            <details>
              <summary className="cursor-pointer text-xs">
                {t("business.compare.resultDetails")}
              </summary>
              <SchemaForm
                schema={configurationShape(comparisonSchema, [
                  "output",
                  "null_equal",
                ])}
                value={item}
                options={{ ...options, compact: true }}
                onChange={(next) => update("comparisons", index, next as Item)}
              />
            </details>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => update("comparisons", index, null)}
            >
              {t("business.remove")}
            </Button>
          </div>
        ))}
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            onChange({
              ...value,
              comparisons: [
                ...comparisons,
                { left: "", right: "", mode: "exact" },
              ],
            })
          }
        >
          {t("business.compare.addComparison")}
        </Button>
      </ConfigurationSection>
      <ConfigurationSection
        id="compare-output"
        title={t("business.compare.output")}
        summary={t("business.compare.outputHint")}
      >
        <p className="text-xs text-muted-foreground">
          {t("business.compare.acceptanceHint")}
        </p>
        {children}
      </ConfigurationSection>
    </div>
  );
}
