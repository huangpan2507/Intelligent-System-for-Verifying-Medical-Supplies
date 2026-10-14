import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Field } from "@/controllers/API/queries/business";

export const fieldType = (value: string) => {
  const type = value.toLowerCase();
  if (type.includes("int")) return "integer";
  if (/number|decimal|numeric|float|double|real/.test(type)) return "number";
  if (/bool/.test(type)) return "boolean";
  if (/timestamp|datetime/.test(type)) return "datetime";
  if (type.startsWith("date")) return "date";
  return "text";
};

export default function SourceFieldEditor({
  fields,
  onChange,
  namesEditable = false,
}: {
  fields: Field[];
  onChange: (fields: Field[]) => void;
  namesEditable?: boolean;
}) {
  const { t } = useTranslation();
  const update = (index: number, change: Partial<Field>) =>
    onChange(
      fields.map((field, i) => (i === index ? { ...field, ...change } : field)),
    );
  return (
    <div className="space-y-2">
      {fields.map((field, index) => (
        <div key={index} className="space-y-2 rounded border p-2">
          <Input
            aria-label={t("business.field.name")}
            value={field.name}
            readOnly={!namesEditable}
            onChange={(event) => update(index, { name: event.target.value })}
          />
          <select
            aria-label={t("business.field.type")}
            className="h-10 w-full rounded border bg-background px-2"
            value={field.type}
            onChange={(event) => update(index, { type: event.target.value })}
          >
            {["text", "integer", "number", "boolean", "date", "datetime"].map(
              (type) => (
                <option key={type} value={type}>
                  {t(`business.value.${type}`, { defaultValue: type })}
                </option>
              ),
            )}
          </select>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={field.required !== false}
              onChange={(event) =>
                update(index, { required: event.target.checked })
              }
            />
            {t("business.fields.propertyRequired")}
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={field.nullable !== false}
              onChange={(event) =>
                update(index, { nullable: event.target.checked })
              }
            />
            {t("business.fields.allowNull")}
          </label>
          {namesEditable && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onChange(fields.filter((_, i) => i !== index))}
            >
              {t("business.remove")}
            </Button>
          )}
        </div>
      ))}
      {namesEditable && (
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            onChange([
              ...fields,
              { name: "", type: "text", required: true, nullable: true },
            ])
          }
        >
          {t("business.add")}
        </Button>
      )}
    </div>
  );
}
