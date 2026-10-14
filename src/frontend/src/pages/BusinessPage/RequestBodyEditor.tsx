import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Field } from "@/controllers/API/queries/business";

function Constant({
  value,
  onChange,
}: {
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState(JSON.stringify(value ?? null));
  const [invalid, setInvalid] = useState(false);
  useEffect(() => {
    setText(JSON.stringify(value ?? null));
    setInvalid(false);
  }, [value]);
  return (
    <div>
      <Input
        aria-label={t("business.binding.constant")}
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          try {
            onChange(JSON.parse(event.target.value));
            setInvalid(false);
          } catch {
            setInvalid(true);
          }
        }}
      />
      {invalid && (
        <p role="alert" className="text-sm text-destructive">
          {t("business.binding.invalidConstant")}
        </p>
      )}
    </div>
  );
}

export default function RequestBodyEditor({
  value,
  onChange,
  fields,
  parameters,
  root = true,
  compact = false,
}: {
  value: unknown;
  onChange: (value: unknown) => void;
  fields: Field[];
  parameters: string[];
  root?: boolean;
  compact?: boolean;
}) {
  const { t } = useTranslation();
  const object =
    value && typeof value === "object" && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : {};
  const mode = Array.isArray(value)
    ? "array"
    : Object.keys(object).length === 1 && "field" in object
      ? "field"
      : Object.keys(object).length === 1 && "parameter" in object
        ? "parameter"
        : value !== null && typeof value === "object"
          ? "object"
          : "constant";
  const options =
    mode === "field"
      ? fields.map((field) => ({
          value: field.name,
          label: `${field.name} · ${field.type}`,
        }))
      : parameters.map((parameter) => ({ value: parameter, label: parameter }));
  const selected = String(object[mode] ?? "");
  return (
    <div
      className={
        compact && !root
          ? "grid grid-cols-[repeat(auto-fit,minmax(min(100%,9rem),1fr))] gap-2"
          : "space-y-2"
      }
    >
      {!root && (
        <select
          className="h-10 w-full rounded border bg-background px-2"
          aria-label={t("business.binding.mode")}
          value={mode}
          onChange={(event) => {
            const next = event.target.value;
            onChange(
              next === "object"
                ? {}
                : next === "array"
                  ? []
                  : next === "constant"
                    ? ""
                    : { [next]: "" },
            );
          }}
        >
          {(["constant", "field", "parameter", "object", "array"] as const).map(
            (kind) => (
              <option value={kind} key={kind}>
                {t(`business.binding.${kind}`)}
              </option>
            ),
          )}
        </select>
      )}
      {(mode === "field" || mode === "parameter") && (
        <select
          className="h-10 w-full rounded border bg-background px-2"
          aria-label={t(`business.binding.${mode}`)}
          value={selected}
          onChange={(event) => onChange({ [mode]: event.target.value })}
        >
          <option value="">{t("business.choose")}</option>
          {selected && !options.some((option) => option.value === selected) && (
            <option value={selected}>
              {t("business.invalidField", { field: selected })}
            </option>
          )}
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      )}
      {mode === "constant" && <Constant value={value} onChange={onChange} />}
      {mode === "object" && (
        <>
          {Object.entries(object).map(([key, child], index) => (
            <div
              key={index}
              className={
                compact
                  ? "grid grid-cols-[repeat(auto-fit,minmax(min(100%,9rem),1fr))] items-start gap-2 border-b py-2"
                  : "space-y-2 rounded border p-2"
              }
            >
              <Input
                aria-label={t("business.binding.key")}
                value={key}
                onChange={(event) => {
                  if (
                    event.target.value !== key &&
                    event.target.value in object
                  )
                    return;
                  onChange(
                    Object.fromEntries(
                      Object.entries(object).map(([name, item]) => [
                        name === key ? event.target.value : name,
                        item,
                      ]),
                    ),
                  );
                }}
              />
              <RequestBodyEditor
                value={child}
                onChange={(next) => onChange({ ...object, [key]: next })}
                fields={fields}
                parameters={parameters}
                root={false}
                compact={compact}
              />
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  onChange(
                    Object.fromEntries(
                      Object.entries(object).filter(([name]) => name !== key),
                    ),
                  )
                }
              >
                {t("business.remove")}
              </Button>
            </div>
          ))}
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              let index = Object.keys(object).length + 1;
              while (`param_${index}` in object) index++;
              onChange({ ...object, [`param_${index}`]: "" });
            }}
          >
            {t("business.binding.addProperty")}
          </Button>
        </>
      )}
      {mode === "array" && Array.isArray(value) && (
        <>
          {value.map((child, index) => (
            <div
              key={index}
              className={
                compact
                  ? "grid grid-cols-[repeat(auto-fit,minmax(min(100%,9rem),1fr))] items-start gap-2 border-b py-2"
                  : "space-y-2 rounded border p-2"
              }
            >
              <RequestBodyEditor
                value={child}
                onChange={(next) =>
                  onChange(value.map((item, i) => (i === index ? next : item)))
                }
                fields={fields}
                parameters={parameters}
                root={false}
                compact={compact}
              />
              <Button
                size="sm"
                variant="ghost"
                onClick={() => onChange(value.filter((_, i) => i !== index))}
              >
                {t("business.remove")}
              </Button>
            </div>
          ))}
          <Button
            size="sm"
            variant="outline"
            onClick={() => onChange([...value, ""])}
          >
            {t("business.add")}
          </Button>
        </>
      )}
    </div>
  );
}
