import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Field } from "@/controllers/API/queries/business";
import { businessOption, useTranslation } from "./business-i18n";
import type { ClassificationConfig } from "./classification-config";

export default function ClassificationInputs({
  config,
  onChange,
  fields,
  part,
}: {
  config: ClassificationConfig;
  onChange: (value: ClassificationConfig) => void;
  fields: Field[];
  part: "fields" | "categories";
}) {
  const { t } = useTranslation();
  const update = (patch: Partial<ClassificationConfig>) =>
    onChange({ ...config, ...patch });
  const selectStyle = "min-w-0 w-full rounded border bg-background p-2 text-sm";
  const fieldNames = fields.map((f) => f.name);
  return (
    <>
      {part === "fields" && (
        <section className="space-y-2">
          <p className="text-xs text-muted-foreground">
            {t("business.classification.fieldsHint")}
          </p>
          {config.classification_fields.map((entry, index) => (
            <div
              key={index}
              className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,15rem),1fr))] items-end gap-2 border-b pb-2"
            >
              <label className="block text-sm">
                {t("business.classification.fieldNumber", {
                  number: index + 1,
                })}
                <select
                  className={selectStyle}
                  value={entry.field}
                  title={entry.field}
                  onChange={(e) =>
                    update({
                      classification_fields: config.classification_fields.map(
                        (f, i) =>
                          i === index ? { ...f, field: e.target.value } : f,
                      ),
                    })
                  }
                >
                  <option value="">
                    {businessOption("business.classification.chooseField")}
                  </option>
                  {entry.field && !fieldNames.includes(entry.field) && (
                    <option value={entry.field} disabled>
                      {entry.field}
                    </option>
                  )}
                  {fields.map((f) => (
                    <option
                      key={f.name}
                      value={f.name}
                      disabled={config.classification_fields.some(
                        (other, i) => i !== index && other.field === f.name,
                      )}
                    >
                      {f.source ? `${f.source}.` : ""}
                      {f.name} · {f.type}
                    </option>
                  ))}
                </select>
              </label>
              <div className="flex items-center gap-2">
                <label className="flex min-w-0 flex-1 items-center gap-2 text-sm">
                  <span className="shrink-0">
                    {t("business.classification.role")}
                  </span>
                  <select
                    className={selectStyle}
                    value={entry.role}
                    onChange={(e) =>
                      update({
                        classification_fields: config.classification_fields.map(
                          (f, i) =>
                            i === index
                              ? {
                                  ...f,
                                  role: e.target.value as typeof entry.role,
                                }
                              : f,
                        ),
                      })
                    }
                  >
                    <option value="evidence">
                      {businessOption("business.classification.evidence")}
                    </option>
                    <option value="context">
                      {businessOption("business.classification.context")}
                    </option>
                  </select>
                </label>
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={t("business.classification.removeField", {
                    field: entry.field,
                  })}
                  onClick={() =>
                    update({
                      classification_fields:
                        config.classification_fields.filter(
                          (_, i) => i !== index,
                        ),
                    })
                  }
                >
                  {t("business.remove")}
                </Button>
              </div>
            </div>
          ))}
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              update({
                classification_fields: [
                  ...config.classification_fields,
                  { field: "", role: "evidence" },
                ],
              })
            }
          >
            {t("business.classification.addField")}
          </Button>
          <p className="text-xs text-muted-foreground">
            {t("business.classification.changeFieldsHint")}
          </p>
        </section>
      )}
      {part === "categories" && (
        <section className="space-y-2">
          {config.category_routes.map((route, index) => (
            <div
              key={index}
              className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,15rem),1fr))] items-end gap-2 border-b pb-2"
            >
              <label className="block text-sm">
                {t("business.classification.categoryNumber", {
                  number: index + 1,
                })}
                <Input
                  value={route.category}
                  onChange={(e) =>
                    update({
                      category_routes: config.category_routes.map((r, i) =>
                        i === index ? { ...r, category: e.target.value } : r,
                      ),
                    })
                  }
                />
              </label>
              <div className="flex items-center gap-2">
                <label className="flex flex-1 items-center gap-2 text-sm">
                  {t("business.classification.disposition")}
                  <select
                    className={selectStyle}
                    value={route.continue ? "continue" : "excluded"}
                    onChange={(e) =>
                      update({
                        category_routes: config.category_routes.map((r, i) =>
                          i === index
                            ? { ...r, continue: e.target.value === "continue" }
                            : r,
                        ),
                      })
                    }
                  >
                    <option value="continue">
                      {businessOption("business.classification.continue")}
                    </option>
                    <option value="excluded">
                      {businessOption("business.classification.excluded")}
                    </option>
                  </select>
                </label>
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={t("business.classification.removeCategory", {
                    category: route.category,
                  })}
                  onClick={() =>
                    update({
                      category_routes: config.category_routes.filter(
                        (_, i) => i !== index,
                      ),
                    })
                  }
                >
                  {t("business.remove")}
                </Button>
              </div>
            </div>
          ))}
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              update({
                category_routes: [
                  ...config.category_routes,
                  { category: "", continue: true },
                ],
              })
            }
          >
            {t("business.classification.addCategory")}
          </Button>
          <p className="text-sm text-muted-foreground">
            {t("business.classification.unknownHint", {
              label: t("business.classification.unknown"),
            })}
          </p>
        </section>
      )}
    </>
  );
}
