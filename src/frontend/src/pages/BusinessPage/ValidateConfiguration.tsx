import { useEffect } from "react";
import type { JsonSchema } from "@/controllers/API/queries/business";
import { useTranslation } from "./business-i18n";
import ConfigurationSection from "./ConfigurationSection";
import {
  conditionSummary,
  configurationShape,
  managedValidation,
  type ValidateConfig,
} from "./configuration-layout";
import LookupFieldList from "./LookupFieldList";
import { lookupProblems } from "./lookup-config";
import { type FormOptions, SchemaForm } from "./SchemaForm";

export default function ValidateConfiguration({
  value,
  onChange,
  schema,
  options,
  nodeId,
}: {
  value: ValidateConfig;
  onChange: (v: ValidateConfig) => void;
  schema: JsonSchema;
  options: FormOptions;
  nodeId: string;
}) {
  const { t } = useTranslation();
  const config = managedValidation(value, nodeId);
  const normalized = JSON.stringify(config);
  useEffect(() => {
    if (JSON.stringify(value) !== normalized) onChange(config);
  }, [normalized, value, onChange]);
  const update = (patch: Partial<ValidateConfig>) =>
    onChange(managedValidation({ ...config, ...patch }, nodeId));
  const problems = (keys: string[]) =>
    lookupProblems(configurationShape(schema, keys), config, options);
  const fields = options.fields?.data ?? [];
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        {t("business.layout.qualityHint")}
      </p>
      <ConfigurationSection
        id="required"
        title={t("business.layout.required")}
        summary={config.required?.join(" · ")}
        errors={problems(["required"])}
        defaultOpen
      >
        <p className="text-xs text-muted-foreground">
          {t("business.layout.nullHint")}
        </p>
        <LookupFieldList
          label={t("business.layout.required")}
          value={config.required ?? []}
          fields={fields}
          onChange={(required) => update({ required })}
        />
      </ConfigurationSection>
      <ConfigurationSection
        id="identity"
        title={t("business.layout.identity")}
        summary={config.identity?.keys.join(" + ")}
        errors={problems(["identity"])}
        defaultOpen
      >
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={!!config.identity}
            onChange={(e) => {
              if (e.target.checked) update({ identity: { keys: [] } });
              else {
                const { identity: _identity, ...rest } = config;
                onChange(rest);
              }
            }}
          />
          {t("business.layout.enableIdentity")}
        </label>
        {config.identity && (
          <>
            <LookupFieldList
              label={t("business.layout.identityKeys")}
              value={config.identity.keys}
              fields={fields}
              onChange={(keys) =>
                update({ identity: { ...config.identity, keys } })
              }
            />
            <details>
              <summary className="cursor-pointer text-sm">
                {t("business.lookup.identityDetails")}
              </summary>
              <dl className="break-all text-xs">
                <dt>{t("business.field.name")}</dt>
                <dd>{config.identity.name}</dd>
                <dt>{t("business.field.namespace")}</dt>
                <dd>{config.identity.namespace}</dd>
              </dl>
              <p className="text-xs text-muted-foreground">
                {t("business.lookup.identityHint")}
              </p>
            </details>
          </>
        )}
      </ConfigurationSection>
      <ConfigurationSection
        id="quality"
        title={t("business.layout.quality")}
        summary={[
          conditionSummary(config.conditions),
          config.unique?.length
            ? t("business.layout.unique", { count: config.unique.length })
            : "",
        ]
          .filter(Boolean)
          .join(" · ")}
        errors={problems(["conditions", "unique"])}
      >
        <SchemaForm
          schema={schema.properties?.conditions ?? {}}
          name="conditions"
          value={config.conditions ?? []}
          options={{ ...options, compact: true }}
          onChange={(conditions) =>
            update({ conditions: conditions as ValidateConfig["conditions"] })
          }
        />
        <details open={!!config.unique?.length}>
          <summary className="cursor-pointer text-sm">
            {t("business.layout.unique", { count: config.unique?.length ?? 0 })}
          </summary>
          <p className="text-xs text-muted-foreground">
            {t("business.layout.uniqueHint")}
          </p>
          <LookupFieldList
            label={t("business.field.unique")}
            value={config.unique ?? []}
            fields={fields}
            onChange={(unique) => update({ unique })}
          />
        </details>
      </ConfigurationSection>
      <ConfigurationSection
        id="quality-output"
        title={t("business.layout.output")}
        summary="Valid / Issues"
      >
        <p className="text-sm">{t("business.layout.qualityOutput")}</p>
      </ConfigurationSection>
    </div>
  );
}
