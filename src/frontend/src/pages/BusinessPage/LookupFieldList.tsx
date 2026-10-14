import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Input } from "@/components/ui/input";
import type { Field } from "@/controllers/API/queries/business";

/** Selected fields stay visible; searching never drops a saved reference. */
export default function LookupFieldList({
  label,
  value,
  fields,
  onChange,
}: {
  label: string;
  value: string[];
  fields: Field[];
  onChange: (value: string[]) => void;
}) {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const names = Array.from(new Set([...value, ...fields.map((f) => f.name)]));
  return (
    <fieldset className="min-w-0 space-y-2">
      <legend className="text-sm font-medium">{label}</legend>
      <p className="break-words text-xs">
        {value.join(" · ") || t("business.lookup.none")}
      </p>
      <details>
        <summary className="cursor-pointer text-sm">
          {t("business.lookup.selectFields")}
        </summary>
        <Input
          aria-label={t("business.lookup.searchFields", { label })}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="max-h-48 overflow-auto space-y-1 p-1">
          {names
            .filter(
              (name) =>
                name.toLowerCase().includes(search.toLowerCase()) ||
                value.includes(name),
            )
            .map((name) => {
              const field = fields.find((f) => f.name === name);
              return (
                <label
                  key={name}
                  className="flex items-start gap-2 break-all text-sm"
                  title={field?.comment}
                >
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={value.includes(name)}
                    onChange={(e) =>
                      onChange(
                        e.target.checked
                          ? [...value, name]
                          : value.filter((v) => v !== name),
                      )
                    }
                  />
                  <span>
                    {field
                      ? `${name} · ${field.type}`
                      : t("business.invalidField", { field: name })}
                  </span>
                </label>
              );
            })}
        </div>
      </details>
    </fieldset>
  );
}
