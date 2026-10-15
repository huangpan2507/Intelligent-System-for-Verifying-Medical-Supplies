import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type {
  Connection,
  Field,
  JsonSchema,
} from "@/controllers/API/queries/business";
import { businessOption, useTranslation } from "./business-i18n";
import DatabaseConditionHelp from "./DatabaseConditionHelp";
import RequestBodyEditor from "./RequestBodyEditor";

export type FormOptions = {
  fieldsLoading?: boolean;
  compact?: boolean;
  labels?: Record<string, string>;
  fields?: Record<string, Field[]>;
  connections?: Connection[];
  tables?: string[];
  databaseSchemas?: string[];
  databaseConditions?: boolean;
  regulatoryTask?: boolean;
  parameters?: string[];
  nodes?: { id: string; label: string }[];
  schemas?: Record<string, Record<string, Field[]>>;
  ports?: string[];
};
const empty = (schema: JsonSchema): unknown =>
  schema.default ??
  (schema.type === "array"
    ? []
    : schema.type === "object"
      ? {}
      : schema.type === "boolean"
        ? false
        : schema.type === "integer" || schema.type === "number"
          ? 0
          : "");

function JsonValue({
  value,
  onChange,
  label,
}: {
  value: unknown;
  onChange: (v: unknown) => void;
  label: string;
}) {
  const [text, setText] = useState(
    value === undefined
      ? ""
      : typeof value === "string"
        ? value
        : JSON.stringify(value),
  );
  return (
    <Input
      aria-label={label}
      value={text}
      onChange={(e) => {
        const v = e.target.value;
        setText(v);
        try {
          onChange(JSON.parse(v));
        } catch {
          onChange(v);
        }
      }}
    />
  );
}

export function SchemaForm({
  schema,
  value,
  onChange,
  options = {},
  name = "configuration",
}: {
  schema: JsonSchema;
  value: unknown;
  onChange: (value: unknown) => void;
  options?: FormOptions;
  name?: string;
}) {
  const { t } = useTranslation();
  const objectValue =
    value !== null && typeof value === "object" && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : {};
  const listValue: unknown[] = Array.isArray(value) ? value : [];
  const label =
    options.labels?.[name] ??
    t(`business.field.${name}`, { defaultValue: name });
  if (schema.format === "condition" && schema.properties) {
    const source =
      "right_field" in objectValue
        ? "right_field"
        : "parameter" in objectValue
          ? "parameter"
          : "value";
    const noValue = ["is_null", "not_null"].includes(String(objectValue.op));
    const changeSource = (key: string, next: unknown) => {
      const {
        value: _value,
        parameter: _parameter,
        right_field: _field,
        ...rest
      } = objectValue;
      onChange({ ...rest, [key]: next });
    };
    const sources: [string, "constant" | "parameter" | "field"][] = [
      ["value", "constant"],
      ["parameter", "parameter"],
    ];
    if (
      schema.properties.right_field &&
      !["in", "not_in"].includes(String(objectValue.op))
    ) {
      sources.push(["right_field", "field"]);
    }
    return (
      <div
        className={
          options.compact
            ? "grid grid-cols-[repeat(auto-fit,minmax(min(100%,10rem),1fr))] items-end gap-2 [&>div:first-child]:contents"
            : "space-y-3"
        }
      >
        <SchemaForm
          schema={{
            ...schema,
            format: undefined,
            properties: {
              field: schema.properties.field,
              op: schema.properties.op,
            },
          }}
          value={objectValue}
          onChange={(next) => {
            const updated = next as Record<string, unknown>;
            if (["is_null", "not_null"].includes(String(updated.op))) {
              delete updated.value;
              delete updated.parameter;
              delete updated.right_field;
            } else if (
              ["in", "not_in"].includes(String(updated.op)) &&
              "right_field" in updated
            ) {
              delete updated.right_field;
              updated.value = [];
            }
            onChange(updated);
          }}
          options={options}
        />
        {!noValue && (
          <>
            <select
              aria-label={t("business.binding.mode")}
              className="h-10 w-full rounded border bg-background px-2 text-sm"
              value={source}
              onChange={(event) => changeSource(event.target.value, "")}
            >
              {sources.map(([key, mode]) => (
                <option key={key} value={key}>
                  {businessOption(`business.binding.${mode}`)}
                </option>
              ))}
            </select>
            <SchemaForm
              key={source}
              schema={schema.properties[source]}
              value={objectValue[source]}
              onChange={(next) => changeSource(source, next)}
              options={options}
              name={source}
            />
          </>
        )}
      </div>
    );
  }
  if (name === "body" && schema.type === "object" && !schema.properties)
    return (
      <RequestBodyEditor
        value={value ?? {}}
        onChange={onChange}
        fields={options.fields?.data ?? []}
        parameters={options.parameters ?? []}
        compact={options.compact}
      />
    );
  if (schema.type === "object" && schema.properties)
    return (
      <div
        className={
          options.compact
            ? "grid grid-cols-[repeat(auto-fit,minmax(min(100%,14rem),1fr))] gap-2"
            : "space-y-3"
        }
      >
        {Object.entries(schema.properties).map(([key, child]) => {
          const advanced = [
            "collection",
            "result_checks",
            "calculations",
            "prompt",
            "conflicts",
          ].includes(key);
          const Container = advanced ? "details" : "div";
          const Label = advanced ? "summary" : "label";
          return (
            <Container
              key={key}
              className="min-w-0 space-y-1"
              data-testid={`business-field-${key}`}
            >
              <Label className="text-sm font-medium">
                {options.labels?.[key] ??
                  t(`business.field.${key}`, { defaultValue: key })}
                {schema.required?.includes(key) ? " *" : ""}
              </Label>
              <SchemaForm
                schema={child}
                value={objectValue[key]}
                onChange={(v) => onChange({ ...objectValue, [key]: v })}
                options={
                  typeof objectValue.node === "string"
                    ? {
                        ...options,
                        ports: Object.keys(
                          options.schemas?.[objectValue.node] ?? {},
                        ),
                        fields: {
                          data:
                            options.schemas?.[objectValue.node]?.[
                              String(objectValue.port ?? "data")
                            ] ?? [],
                        },
                      }
                    : options
                }
                name={key}
              />
            </Container>
          );
        })}
      </div>
    );
  if (schema.type === "array")
    return (
      <div className="space-y-2">
        {listValue.map((item, index) => (
          <div
            key={index}
            className={options.compact ? "border-b pb-2" : "rounded border p-3"}
          >
            <SchemaForm
              schema={schema.items ?? {}}
              value={item}
              onChange={(v) =>
                onChange(
                  listValue.map((old: unknown, i: number) =>
                    i === index ? v : old,
                  ),
                )
              }
              options={options}
              name={name}
            />
            <Button
              variant="ghost"
              size="sm"
              className="mt-2"
              onClick={() =>
                onChange(
                  listValue.filter((_: unknown, i: number) => i !== index),
                )
              }
            >
              {t("business.remove")}
            </Button>
            {options.databaseConditions && name === "conditions" && (
              <DatabaseConditionHelp
                value={item}
                regulatoryTask={options.regulatoryTask}
              />
            )}
          </div>
        ))}
        <Button
          variant="outline"
          size="sm"
          onClick={() =>
            onChange([
              ...(Array.isArray(value) ? value : []),
              empty(schema.items ?? {}),
            ])
          }
        >
          {t("business.add")}
        </Button>
      </div>
    );
  if (schema.type === "boolean")
    return (
      <input
        type="checkbox"
        aria-label={label}
        checked={!!value}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4"
      />
    );
  let choices: { value: string; label: string }[] | undefined;
  if (schema.enum)
    choices = schema.enum.map((v) => ({
      value: String(v),
      label: businessOption(`business.value.${String(v)}`, {
        defaultValue: String(v),
      }),
    }));
  if (schema.format?.startsWith("field")) {
    const port = schema.format.split(":")[1] ?? "data";
    choices = (options.fields?.[port] ?? []).map((f) => ({
      value: f.name,
      label: `${f.source ? f.source + "." : ""}${f.name} · ${f.type}`,
    }));
  }
  if (schema.format === "connection")
    choices = (options.connections ?? []).map((c) => ({
      value: c.id,
      label: `${c.name} · ${c.kind}`,
    }));
  if (schema.format === "table")
    choices = (options.tables ?? []).map((v) => ({ value: v, label: v }));
  if (schema.format === "database_schema")
    choices = (options.databaseSchemas ?? []).map((v) => ({
      value: v,
      label: v,
    }));
  if (schema.format === "node")
    choices = (options.nodes ?? []).map((n) => ({
      value: n.id,
      label: `${n.label} · ${n.id}`,
    }));
  if (schema.format === "output_port")
    choices = (options.ports ?? []).map((v) => ({
      value: v,
      label: businessOption(`business.port.${v}`, { defaultValue: v }),
    }));
  if (schema.format === "parameter")
    choices = (options.parameters ?? []).map((value) => ({
      value,
      label: value,
    }));
  if (choices)
    return (
      <select
        aria-label={label}
        className="h-10 w-full rounded border bg-background px-2 text-sm"
        value={String(value ?? "")}
        title={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">{businessOption("business.choose")}</option>
        {Boolean(value) && !choices.some((c) => c.value === String(value)) && (
          <option value={String(value)}>
            {businessOption("business.invalidField", { field: value })}
          </option>
        )}
        {choices.map((c) => (
          <option key={c.value} value={c.value}>
            {c.label}
          </option>
        ))}
      </select>
    );
  if (schema.format === "multiline")
    return (
      <Textarea
        aria-label={label}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  if (schema.type === "integer" || schema.type === "number")
    return (
      <Input
        type="number"
        aria-label={label}
        value={String(value ?? "")}
        onChange={(e) =>
          onChange(e.target.value === "" ? undefined : Number(e.target.value))
        }
      />
    );
  if (schema.type === "string")
    return (
      <Input
        aria-label={label}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  return (
    <JsonValue key={name} value={value} onChange={onChange} label={label} />
  );
}
