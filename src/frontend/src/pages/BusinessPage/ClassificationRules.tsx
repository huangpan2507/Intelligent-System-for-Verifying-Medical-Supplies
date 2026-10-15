import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Field } from "@/controllers/API/queries/business";
import { businessOption, useTranslation } from "./business-i18n";
import type {
  ClassificationConfig,
  ClassificationRule,
} from "./classification-config";
import { SchemaForm } from "./SchemaForm";

const selectStyle = "min-w-0 w-full rounded border bg-background p-2 text-sm";
export default function ClassificationRules({
  config,
  onChange,
  fields,
}: {
  config: ClassificationConfig;
  onChange: (value: ClassificationConfig) => void;
  fields: Field[];
}) {
  const { t } = useTranslation();
  const evidence = config.classification_fields
    .filter((f) => f.role === "evidence")
    .map((f) => f.field);
  const categories = config.category_routes.map((c) => c.category);
  const update = (index: number, patch: Partial<ClassificationRule>) =>
    onChange({
      ...config,
      rules: config.rules.map((r, i) => (i === index ? { ...r, ...patch } : r)),
    });
  return (
    <section className="space-y-3">
      <h3 className="font-medium">{t("business.classification.rules")}</h3>
      <p className="text-sm break-words">
        {t("business.classification.sharedFields", {
          fields: evidence.join(" · ") || "—",
        })}
      </p>
      <p className="text-xs text-muted-foreground">
        {t("business.classification.matchHint")}
      </p>
      {config.rules.map((rule, index) => {
        const invalidFields =
          rule.fields?.filter((f) => !evidence.includes(f)) ?? [];
        const invalid =
          invalidFields.length > 0 ||
          rule.fields?.length === 0 ||
          !categories.includes(rule.category);
        return (
          <fieldset key={index} className="min-w-0 space-y-2 border-b pb-3">
            <legend className="px-1 text-sm">
              {t("business.classification.ruleNumber", { number: index + 1 })}
            </legend>
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm">
                {t(
                  rule.fields
                    ? "business.classification.customFields"
                    : "business.classification.inheritFields",
                )}
              </span>
              <Button
                size="sm"
                variant="ghost"
                aria-label={t("business.classification.removeRule", {
                  number: index + 1,
                })}
                onClick={() =>
                  onChange({
                    ...config,
                    rules: config.rules.filter((_, i) => i !== index),
                  })
                }
              >
                {t("business.remove")}
              </Button>
            </div>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,13rem),1fr))] items-end gap-2">
              <label className="space-y-1 text-sm">
                {t("business.classification.operation")}
                <select
                  className={selectStyle}
                  value={rule.op}
                  onChange={(e) => {
                    const op = e.target.value as ClassificationRule["op"];
                    const { value, keywords, ...rest } = rule;
                    const next = {
                      ...rest,
                      op,
                      ...(op === "contains_all"
                        ? { keywords: keywords ?? [value ?? ""] }
                        : { value: value ?? (keywords ?? []).join("") }),
                    };
                    onChange({
                      ...config,
                      rules: config.rules.map((r, i) =>
                        i === index ? next : r,
                      ),
                    });
                  }}
                >
                  {(["contains", "eq", "contains_all"] as const).map((op) => (
                    <option key={op} value={op}>
                      {businessOption(`business.classification.op.${op}`)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block space-y-1 text-sm">
                {t(
                  rule.op === "contains_all"
                    ? "business.classification.keywords"
                    : "business.classification.comparison",
                )}
                <Input
                  value={
                    rule.op === "contains_all"
                      ? (rule.keywords ?? []).join(", ")
                      : (rule.value ?? "")
                  }
                  onChange={(e) =>
                    update(
                      index,
                      rule.op === "contains_all"
                        ? {
                            keywords: e.target.value
                              .split(/[,，]/)
                              .map((v) => v.trim()),
                          }
                        : { value: e.target.value },
                    )
                  }
                />
              </label>

              <label className="space-y-1 text-sm">
                {t("business.classification.category")}
                <select
                  className={selectStyle}
                  value={rule.category}
                  onChange={(e) => update(index, { category: e.target.value })}
                >
                  <option value="">
                    {businessOption("business.classification.chooseCategory")}
                  </option>
                  {rule.category && !categories.includes(rule.category) && (
                    <option value={rule.category} disabled>
                      {rule.category}
                    </option>
                  )}
                  {categories.filter(Boolean).map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {invalid && (
              <p role="alert" className="text-sm text-destructive">
                {t("business.classification.invalidRule", {
                  fields: invalidFields.join(", "),
                  category: rule.category,
                })}
              </p>
            )}
            <details open={invalid}>
              <summary className="cursor-pointer text-sm">
                {t("business.layout.ruleDetails", {
                  conditions: rule.when?.length ?? 0,
                  fields: rule.fields?.length ?? 0,
                })}
              </summary>
              <p className="my-2 text-xs">
                {t("business.classification.whenHint")}
              </p>
              <SchemaForm
                schema={{
                  type: "array",
                  items: {
                    type: "object",
                    properties: {
                      field: { type: "string", format: "field" },
                      value: { type: "string" },
                    },
                    required: ["field", "value"],
                  },
                }}
                value={rule.when ?? []}
                name="when"
                options={{ fields: { data: fields }, compact: true }}
                onChange={(v) =>
                  update(index, { when: v as ClassificationRule["when"] })
                }
              />
              <p className="mt-2 text-xs">
                {t("business.classification.fieldOverride")}
              </p>
              <label className="my-2 flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={rule.fields !== undefined}
                  onChange={(e) => {
                    if (e.target.checked)
                      update(index, { fields: [...evidence] });
                    else {
                      const { fields: _fields, ...shared } = rule;
                      onChange({
                        ...config,
                        rules: config.rules.map((r, i) =>
                          i === index ? shared : r,
                        ),
                      });
                    }
                  }}
                />
                {t("business.classification.useCustom")}
              </label>
              {rule.fields &&
                Array.from(new Set([...evidence, ...rule.fields])).map(
                  (field) => (
                    <label
                      key={field}
                      className="flex items-center gap-2 py-1 text-sm break-all"
                    >
                      <input
                        type="checkbox"
                        checked={rule.fields!.includes(field)}
                        onChange={(e) =>
                          update(index, {
                            fields: e.target.checked
                              ? [...rule.fields!, field]
                              : rule.fields!.filter((f) => f !== field),
                          })
                        }
                      />
                      {field}
                    </label>
                  ),
                )}
            </details>
          </fieldset>
        );
      })}
      <Button
        size="sm"
        variant="outline"
        onClick={() =>
          onChange({
            ...config,
            rules: [
              ...config.rules,
              {
                op: "contains_all",
                keywords: [""],
                category: categories[0] ?? "",
              },
            ],
          })
        }
      >
        {t("business.classification.addRule")}
      </Button>
    </section>
  );
}
