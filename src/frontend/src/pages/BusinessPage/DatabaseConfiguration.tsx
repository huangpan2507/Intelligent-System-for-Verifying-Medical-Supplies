import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { JsonSchema } from "@/controllers/API/queries/business";
import ConfigurationSection from "./ConfigurationSection";
import { conditionSummary, configurationShape } from "./configuration-layout";
import { lookupProblems } from "./lookup-config";
import { type FormOptions, SchemaForm } from "./SchemaForm";

export default function DatabaseConfiguration({
  value,
  onChange,
  schema,
  options,
  preview,
}: {
  value: Record<string, unknown>;
  onChange: (v: unknown) => void;
  schema: JsonSchema;
  options: FormOptions;
  preview?: ReactNode;
}) {
  const { t } = useTranslation();
  const sql = !!value.sql;
  const form = (keys: string[]) => (
    <SchemaForm
      schema={configurationShape(schema, keys)}
      value={value}
      onChange={onChange}
      options={{ ...options, compact: true }}
    />
  );
  const errors = (keys: string[]) =>
    lookupProblems(configurationShape(schema, keys), value, options);
  const conditions = (value.conditions ?? []) as Record<string, unknown>[];
  const fields = sql
    ? ((value.fields as { name: string; type: string }[] | undefined) ?? [])
    : (options.fields?.data ?? []);
  return (
    <div className="space-y-3">
      <p className="rounded bg-muted p-2 text-sm">
        {t(sql ? "business.layout.sqlMode" : "business.layout.tableMode")}
      </p>
      <ConfigurationSection
        id="database-source"
        title={t("business.lookup.source")}
        summary={
          sql
            ? t("business.layout.sqlMode")
            : `${value.schema ?? "—"} / ${value.table ?? "—"}`
        }
        errors={
          errors(sql ? ["connection"] : ["connection", "schema", "table"]) +
          (!sql && !value.table ? 1 : 0)
        }
        defaultOpen
      >
        {form(sql ? ["connection"] : ["connection", "schema", "table"])}
      </ConfigurationSection>
      {!sql && (
        <ConfigurationSection
          id="database-range"
          title={t("business.layout.range")}
          summary={conditionSummary(conditions)}
          errors={errors(["conditions"])}
          defaultOpen
        >
          <p className="text-xs text-muted-foreground">
            {t("business.layout.rangeHint")}
          </p>
          <SchemaForm
            schema={schema.properties?.conditions ?? {}}
            value={conditions}
            name="conditions"
            onChange={(next) => onChange({ ...value, conditions: next })}
            options={{ ...options, compact: true }}
          />
        </ConfigurationSection>
      )}
      <ConfigurationSection
        id="database-preview"
        title={t("business.layout.preview")}
        summary={t("business.layout.fieldCount", { count: fields.length })}
      >
        <p className="text-sm">
          {t(sql ? "business.layout.sqlOutput" : "business.layout.tableOutput")}
        </p>
        <details>
          <summary className="cursor-pointer text-sm">
            {t("business.field.fields")}
          </summary>
          <dl className="max-h-64 overflow-auto text-xs">
            {fields.map((field) => (
              <div
                key={field.name}
                className="flex flex-wrap justify-between gap-2 border-b py-1"
              >
                <dt className="break-all">{field.name}</dt>
                <dd>{field.type}</dd>
              </div>
            ))}
          </dl>
        </details>
        <p className="text-xs text-muted-foreground">
          {t("business.layout.previewHint")}
        </p>
        {preview}
      </ConfigurationSection>
      <ConfigurationSection
        id="database-advanced"
        title={t("business.layout.advancedRead")}
        summary={
          sql ? t("business.layout.sqlMode") : String(value.timezone || "—")
        }
        errors={errors(sql ? ["sql", "parameters", "timezone"] : ["timezone"])}
        defaultOpen={sql}
      >
        <p className="text-xs text-muted-foreground">
          {t("business.layout.sqlHint")}
        </p>
        {form(["timezone"])}
        <label className="block space-y-1 text-sm">
          {t("business.field.sql")}
          <SchemaForm
            schema={
              schema.properties?.sql ?? { type: "string", format: "multiline" }
            }
            name="sql"
            value={value.sql ?? ""}
            onChange={(next) => onChange({ ...value, sql: next })}
            options={options}
          />
        </label>
        {sql && form(["parameters"])}
      </ConfigurationSection>
    </div>
  );
}
