import { useTranslation } from "react-i18next";
import type { Field, JsonSchema } from "@/controllers/API/queries/business";
import type { ClassificationConfig } from "./classification-config";
import { SchemaForm } from "./SchemaForm";

export function dictionaryFields(config: ClassificationConfig): Field[] {
  if (!config.dictionary) return [];
  return ["code_name", "code_status", "code_version", "code_source"].map(
    (suffix) => ({
      name: `${config.result_prefix || "classification"}_${suffix}`,
      type: "text",
    }),
  );
}

export default function ClassificationPreparation({
  config,
  onChange,
  fields,
  schema,
}: {
  config: ClassificationConfig;
  onChange: (value: ClassificationConfig) => void;
  fields: Field[];
  schema: JsonSchema;
}) {
  const { t } = useTranslation();
  return (
    <details
      open={!!config.dictionary}
      className="space-y-3 rounded border p-3"
    >
      <summary className="cursor-pointer text-sm font-medium">
        {t("business.classification.preparation")}
      </summary>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={!!config.dictionary}
          onChange={(e) => {
            if (e.target.checked)
              onChange({ ...config, dictionary: { id: "", field: "" } });
            else {
              const { dictionary: _dictionary, ...rest } = config;
              onChange(rest);
            }
          }}
        />
        {t("business.classification.useDictionary")}
      </label>
      {config.dictionary && (
        <>
          <SchemaForm
            schema={schema.properties!.dictionary}
            value={config.dictionary}
            options={{ fields: { data: fields } }}
            onChange={(v) =>
              onChange({
                ...config,
                dictionary: v as ClassificationConfig["dictionary"],
              })
            }
          />
          <p className="text-xs text-muted-foreground">
            {t("business.classification.dictionaryHint")}
          </p>
          <p className="break-all text-xs">
            {t("business.classification.derivedFields", {
              fields: dictionaryFields(config)
                .map((f) => f.name)
                .join(" · "),
            })}
          </p>
        </>
      )}
    </details>
  );
}
