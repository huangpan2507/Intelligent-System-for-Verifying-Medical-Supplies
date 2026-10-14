import { useTranslation } from "react-i18next";
import { Textarea } from "@/components/ui/textarea";
import type {
  Connection,
  Field,
  JsonSchema,
} from "@/controllers/API/queries/business";
import ClassificationInputs from "./ClassificationInputs";
import ClassificationPreparation, {
  dictionaryFields,
} from "./ClassificationPreparation";
import ClassificationRules from "./ClassificationRules";
import ConfigurationSection from "./ConfigurationSection";
import {
  type ClassificationConfig,
  classificationConfig,
} from "./classification-config";
import { configurationShape } from "./configuration-layout";
import { lookupProblems } from "./lookup-config";
import { SchemaForm } from "./SchemaForm";

export default function ClassificationConfiguration({
  value,
  onChange,
  fields,
  connections,
  schema,
  prompt,
  fieldsLoading = false,
}: {
  value: Record<string, unknown>;
  onChange: (value: ClassificationConfig) => void;
  fields: Field[];
  connections?: Connection[];
  schema: JsonSchema;
  prompt?: string;
  fieldsLoading?: boolean;
}) {
  const { t } = useTranslation();
  const config = classificationConfig(value);
  const update = (patch: Partial<ClassificationConfig>) =>
    onChange({ ...config, ...patch });
  const preparedFields = [...fields, ...dictionaryFields(config)];
  const options = {
    fieldsLoading,
    fields: { data: preparedFields },
    connections,
    compact: true,
  };
  const categories = config.category_routes.map((c) => c.category);
  const evidence = config.classification_fields.filter(
    (f) => f.role === "evidence",
  );
  const problems = (keys: string[]) =>
    lookupProblems(configurationShape(schema, keys), config, options);
  const invalidRules = config.rules.filter(
    (r) =>
      !categories.includes(r.category) ||
      r.fields?.length === 0 ||
      r.fields?.some((f) => !evidence.some((e) => e.field === f)),
  ).length;
  const section = (keys: string[]) => (
    <SchemaForm
      schema={configurationShape(schema, keys)}
      value={config}
      options={options}
      onChange={(v) => onChange(v as ClassificationConfig)}
    />
  );
  return (
    <div className="space-y-3">
      <ConfigurationSection
        id="classification-input"
        title={t("business.classification.fields")}
        summary={t("business.layout.evidenceSummary", {
          evidence: evidence.length,
          contextFields: config.classification_fields.length - evidence.length,
        })}
        errors={problems(["classification_fields", "dictionary"])}
        defaultOpen
      >
        {schema.properties?.dictionary && (
          <ClassificationPreparation
            config={config}
            onChange={onChange}
            fields={fields}
            schema={schema}
          />
        )}
        <ClassificationInputs
          part="fields"
          config={config}
          onChange={onChange}
          fields={preparedFields}
        />
      </ConfigurationSection>
      <ConfigurationSection
        id="classification-categories"
        title={t("business.classification.categories")}
        summary={config.category_routes
          .map(
            (r) =>
              `${r.category} → ${t(r.continue ? "business.classification.continue" : "business.classification.excluded")}`,
          )
          .join(" · ")}
        errors={problems(["category_routes"])}
        defaultOpen={!categories.length}
      >
        <ClassificationInputs
          part="categories"
          config={config}
          onChange={onChange}
          fields={preparedFields}
        />
        <p className="text-sm text-muted-foreground">
          {t("business.classification.outputsHint")}
        </p>
      </ConfigurationSection>
      <ConfigurationSection
        id="classification-rules"
        title={t("business.layout.rulesReview")}
        summary={t("business.layout.rulesSummary", {
          rules: config.rules.length,
          hints: config.ambiguity_hints?.length ?? 0,
          conflicts: config.conflicts?.length ?? 0,
        })}
        errors={problems(["rules", "conflicts"]) + invalidRules}
        defaultOpen
      >
        <ClassificationRules
          config={config}
          onChange={onChange}
          fields={preparedFields}
        />
        <details>
          <summary className="cursor-pointer text-sm">
            {t("business.classification.ambiguity")}
          </summary>
          <p className="text-xs text-muted-foreground">
            {t("business.classification.ambiguityHint")}
          </p>
          <label className="block text-sm">
            {t("business.classification.hints")}
            <Textarea
              value={(config.ambiguity_hints ?? []).join("\n")}
              onChange={(e) =>
                update({
                  ambiguity_hints: e.target.value
                    ? e.target.value.split("\n")
                    : [],
                })
              }
            />
          </label>
        </details>
        <details>
          <summary className="cursor-pointer text-sm">
            {t("business.layout.conflicts", {
              count: config.conflicts?.length ?? 0,
            })}
          </summary>
          <p className="text-xs text-muted-foreground">
            {t("business.layout.conflictHint")}
          </p>
          <SchemaForm
            schema={{
              ...schema.properties!.conflicts,
              items: {
                ...schema.properties!.conflicts?.items,
                properties: {
                  ...schema.properties!.conflicts?.items?.properties,
                  category: { type: "string", enum: categories },
                },
              },
            }}
            value={config.conflicts ?? []}
            name="conflicts"
            options={options}
            onChange={(v) =>
              update({ conflicts: v as ClassificationConfig["conflicts"] })
            }
          />
        </details>
      </ConfigurationSection>
      <ConfigurationSection
        id="classification-model"
        title={t("business.classification.model")}
        summary={config.model || t("business.lookup.none")}
        errors={problems([
          "connection",
          "model",
          "business_guidance",
          "path",
          "max_calls",
        ])}
        defaultOpen={!config.connection || !config.model}
      >
        <p className="text-xs text-muted-foreground">
          {t("business.layout.modelHint")}
        </p>
        {section(["connection", "model"])}
        <label className="block space-y-1 text-sm">
          {t("business.classification.guidance")}
          <Textarea
            value={config.business_guidance}
            onChange={(e) => update({ business_guidance: e.target.value })}
          />
        </label>
        <details>
          <summary className="cursor-pointer text-sm">
            {t("business.classification.promptPreview")}
          </summary>
          <p className="my-2 text-xs text-muted-foreground">
            {t("business.classification.promptHint")}
          </p>
          <pre className="whitespace-pre-wrap break-words rounded bg-muted p-2 text-xs">
            {prompt ?? t("business.classification.previewPending")}
          </pre>
        </details>
        <details>
          <summary className="cursor-pointer text-sm">
            {t("business.layout.modelTechnical")}
          </summary>
          {section(["path", "max_calls"])}
        </details>
      </ConfigurationSection>
      <ConfigurationSection
        id="classification-output"
        title={t("business.layout.output")}
        summary={`Data / Issues · ${config.result_prefix || "classification"}`}
        errors={problems(["result_prefix"])}
      >
        <p className="text-sm">{t("business.classification.outputsHint")}</p>
        <p className="text-xs text-muted-foreground">
          {t("business.classification.prefixHint")}
        </p>
        <p className="text-xs text-muted-foreground">
          {t("business.layout.prefixHint")}
        </p>
        <label className="block space-y-1 text-sm">
          {t("business.field.result_prefix")}
          <SchemaForm
            schema={schema.properties?.result_prefix ?? { type: "string" }}
            value={config.result_prefix ?? "classification"}
            name="result_prefix"
            onChange={(v) => update({ result_prefix: String(v) })}
          />
        </label>
      </ConfigurationSection>
    </div>
  );
}
