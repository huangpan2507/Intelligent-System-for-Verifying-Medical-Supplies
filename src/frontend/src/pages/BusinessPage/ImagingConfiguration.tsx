import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { JsonSchema } from "@/controllers/API/queries/business";
import ConfigurationSection from "./ConfigurationSection";
import { conditionSummary, configurationShape } from "./configuration-layout";
import LookupFieldList from "./LookupFieldList";
import { lookupProblems } from "./lookup-config";
import { type FormOptions, SchemaForm } from "./SchemaForm";

const comparisonSymbols: Record<string, string> = {
  eq: "=",
  ne: "≠",
  ge: "≥",
  gt: ">",
  le: "≤",
  lt: "<",
};

export default function ImagingConfiguration({
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
  const inputs = ["evidence_field", "category_field", "evidence_context_field"];
  const scope = ["hospital_field", "patient_field", "encounter_field"];
  const checks = value.result_checks as
    | { required?: string[]; conditions?: Record<string, unknown>[] }
    | undefined;
  const resultLabel = (field: string) =>
    t(`business.imaging.result.${field}`, { defaultValue: field });
  const errors = (keys: string[]) =>
    lookupProblems(configurationShape(schema, keys), value, options);
  const form = (keys: string[]) => (
    <SchemaForm
      schema={configurationShape(schema, keys)}
      value={value}
      onChange={onChange}
      options={{ ...options, compact: true }}
    />
  );
  const summary = (keys: string[]) =>
    keys
      .map((key) =>
        t("business.imaging.binding", {
          label: t(`business.field.${key}`, { defaultValue: key }),
          field: value[key] || t("business.lookup.none"),
        }),
      )
      .join(" · ");
  const bindings = (keys: string[]) => (
    <details open={errors(keys) > 0 ? true : undefined}>
      <summary className="cursor-pointer text-sm">
        {t("business.imaging.editBindings")}
      </summary>
      <div className="mt-2">{form(keys)}</div>
    </details>
  );
  return (
    <div className="space-y-3">
      <ConfigurationSection
        id="imaging-service"
        title={t("business.imaging.service")}
        summary={
          options.connections?.find((c) => c.id === value.connection)?.name
        }
        errors={errors(["connection", "path", "max_calls"])}
        defaultOpen
      >
        {form(["connection"])}
        <p className="text-xs text-muted-foreground">
          {t("business.imaging.serviceHint")}
        </p>
        <details open={!value.path ? true : undefined}>
          <summary className="cursor-pointer text-sm">
            {t("business.imaging.serviceDetails")}
          </summary>
          {form(["path", "max_calls"])}
          <p className="text-xs text-muted-foreground">
            {t("business.imaging.callsHint")}
          </p>
        </details>
      </ConfigurationSection>
      <ConfigurationSection
        id="imaging-evidence"
        title={t("business.imaging.evidence")}
        summary={summary(inputs)}
        errors={errors(inputs)}
      >
        <p className="text-xs text-muted-foreground">
          {t("business.imaging.evidenceHint")}
        </p>
        {bindings(inputs)}
      </ConfigurationSection>
      <ConfigurationSection
        id="imaging-scope"
        title={t("business.imaging.scope")}
        summary={summary(scope)}
        errors={errors(scope)}
      >
        <p className="text-xs text-muted-foreground">
          {t("business.imaging.scopeHint")}
        </p>
        {bindings(scope)}
      </ConfigurationSection>
      <ConfigurationSection
        id="imaging-validity"
        title={t("business.imaging.validity")}
        summary={[
          checks?.required?.map(resultLabel).join(" · "),
          conditionSummary(
            checks?.conditions?.map((condition) => ({
              ...condition,
              field: resultLabel(String(condition.field)),
              op: comparisonSymbols[String(condition.op)] ?? condition.op,
            })),
          ),
          t("business.imaging.numericHint"),
        ]
          .filter(Boolean)
          .join(" · ")}
        errors={errors(["result_checks"])}
      >
        <details>
          <summary className="cursor-pointer text-sm">
            {t("business.field.result_checks")}
          </summary>
          <div className="mt-2 space-y-3">
            <LookupFieldList
              label={t("business.field.required")}
              value={checks?.required ?? []}
              fields={options.fields?.result ?? []}
              onChange={(required) =>
                onChange({ ...value, result_checks: { ...checks, required } })
              }
            />
            <SchemaForm
              schema={configurationShape(
                schema.properties?.result_checks ?? {},
                ["conditions"],
              )}
              value={checks ?? {}}
              onChange={(result_checks) =>
                onChange({ ...value, result_checks })
              }
              options={{ ...options, compact: true }}
            />
          </div>
        </details>
      </ConfigurationSection>
      <ConfigurationSection
        id="imaging-output"
        title={t("business.imaging.output")}
        summary={t("business.imaging.outputHint")}
      >
        <p className="text-xs text-muted-foreground">
          {t("business.imaging.acceptanceHint")}
        </p>
        {children}
      </ConfigurationSection>
    </div>
  );
}
