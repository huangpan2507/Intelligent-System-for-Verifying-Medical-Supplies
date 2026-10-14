import { type ReactNode, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import type { JsonSchema } from "@/controllers/API/queries/business";
import LookupFieldList from "./LookupFieldList";
import {
  type LookupConfig,
  lookupProblems,
  lookupSource,
  managedLookup,
  sourceBindingsChanged,
} from "./lookup-config";
import { type FormOptions, SchemaForm } from "./SchemaForm";

export default function LookupConfiguration({
  value,
  onChange,
  schema,
  options,
  nodeId,
  upstream,
}: {
  value: LookupConfig;
  onChange: (value: LookupConfig) => void;
  schema: JsonSchema;
  options: FormOptions;
  nodeId: string;
  upstream: string;
}) {
  const { t } = useTranslation();
  const config = managedLookup(value, nodeId);
  const normalized = JSON.stringify(config);
  useEffect(() => {
    if (JSON.stringify(value) !== normalized) onChange(config);
  }, [normalized, value, onChange]);
  const update = (patch: Partial<LookupConfig>) =>
    onChange(managedLookup({ ...config, ...patch }, nodeId));
  const properties = schema.properties ?? {};
  const compact = { ...options, compact: true };
  const shape = (keys: string[]): JsonSchema => ({
    type: "object",
    properties: Object.fromEntries(
      keys.filter((k) => properties[k]).map((k) => [k, properties[k]]),
    ),
    required: (schema.required ?? []).filter((k) => keys.includes(k)),
  });
  const problems = (keys: string[]) =>
    lookupProblems(shape(keys), config, options);
  const sourceChanged = sourceBindingsChanged(config);
  const form = (
    key: string,
    v: unknown,
    change: (v: unknown) => void,
    override?: JsonSchema,
  ) => (
    <SchemaForm
      schema={override ?? properties[key] ?? {}}
      name={key}
      value={v}
      onChange={change}
      options={compact}
    />
  );
  function section(
    key: "source" | "join" | "range" | "returns" | "quality" | "checks",
    count: number,
    summary: string,
    errors: number,
    children: ReactNode,
  ) {
    return (
      <details
        open={key === "source" || key === "join"}
        className="rounded border p-3"
        data-testid={`lookup-section-${key}`}
      >
        <summary className="cursor-pointer space-y-1">
          <span className="font-medium">
            {t(`business.lookup.${key}`)}{" "}
            <span className="text-muted-foreground">({count})</span>
          </span>
          {errors > 0 && (
            <span role="alert" className="ml-2 text-sm text-destructive">
              {t("business.lookup.errors", { count: errors })}
            </span>
          )}
          <p className="break-words text-xs text-muted-foreground">
            {summary || t("business.lookup.none")}
          </p>
        </summary>
        <div className="mt-3 space-y-3">{children}</div>
      </details>
    );
  }
  const fieldList = (
    label: string,
    values: string[],
    port: string,
    change: (v: string[]) => void,
  ) => (
    <LookupFieldList
      label={label}
      value={values}
      fields={options.fields?.[port] ?? []}
      onChange={change}
    />
  );
  return (
    <div className="space-y-3" data-testid="lookup-configuration">
      <p className="text-sm break-words">
        {t("business.lookup.upstream", {
          source: upstream || t("business.lookup.none"),
        })}
      </p>
      {sourceChanged && (
        <div
          role="alert"
          className="space-y-2 rounded border border-destructive p-2 text-sm"
        >
          <p>{t("business.lookup.sourceChanged")}</p>
          <p className="break-all">
            {Object.values(config.binding_source!).join(" / ")} →{" "}
            {Object.values(lookupSource(config)).join(" / ")}
          </p>
          <Button
            size="sm"
            variant="outline"
            disabled={
              !config.connection ||
              !config.table ||
              [
                "connection",
                "schema",
                "table",
                "keys",
                "conditions",
                "returns",
                "source_identity",
                "source_required",
                "checks",
              ].some((k) => problems([k]) > 0)
            }
            onClick={() => update({ binding_source: lookupSource(config) })}
          >
            {t("business.lookup.confirmSource")}
          </Button>
        </div>
      )}
      {section(
        "source",
        3,
        `${config.schema ?? "—"} / ${config.table ?? "—"}`,
        problems(["connection", "schema", "table"]),
        <SchemaForm
          schema={shape(["connection", "schema", "table"])}
          value={config}
          onChange={(v) => onChange(managedLookup(v as LookupConfig, nodeId))}
          options={options}
        />,
      )}
      {section(
        "join",
        config.keys?.length ?? 0,
        (config.keys ?? []).map((k) => `${k.left} ↔ ${k.right}`).join(" · "),
        problems(["keys"]),
        <>
          <p className="text-xs text-muted-foreground">
            {t("business.lookup.joinHint")}
          </p>
          <div data-testid="business-field-keys">
            {form("keys", config.keys, (v) =>
              update({ keys: v as LookupConfig["keys"] }),
            )}
          </div>
        </>,
      )}
      {section(
        "range",
        config.conditions?.length ?? 0,
        (config.conditions ?? [])
          .map(
            (c) =>
              `${c.field ?? "—"} ${c.op ?? ""} ${c.parameter ? "$" + c.parameter : JSON.stringify(c.value ?? "")}`,
          )
          .join(" · "),
        problems(["conditions"]),
        <>
          <p className="text-xs text-muted-foreground">
            {t("business.lookup.rangeHint")}
          </p>
          {form("conditions", config.conditions, (v) =>
            update({ conditions: v as LookupConfig["conditions"] }),
          )}
          <details>
            <summary className="text-sm">
              {t("business.lookup.timezone")}
            </summary>
            {form("timezone", config.timezone, (v) =>
              update({ timezone: String(v) }),
            )}
          </details>
        </>,
      )}
      {section(
        "returns",
        config.returns?.length ?? 0,
        (config.returns ?? []).map((r) => r.output).join(" · "),
        problems(["returns"]),
        <div className="space-y-2" data-testid="business-field-returns">
          <p className="text-xs text-muted-foreground">
            {t("business.lookup.returnsHint")}
          </p>
          {(config.returns ?? []).map((row, index) => {
            const change = (next: unknown) =>
              update({
                returns: config.returns!.map((r, i) =>
                  i === index ? (next as typeof row) : r,
                ),
              });
            const rowProperties = properties.returns?.items?.properties ?? {};
            return (
              <div key={index} className="space-y-1 border-b pb-2">
                <SchemaForm
                  schema={{
                    type: "object",
                    properties: {
                      field: rowProperties.field,
                      output: rowProperties.output,
                    },
                    required: ["field", "output"],
                  }}
                  value={row}
                  onChange={change}
                  options={compact}
                />
                <div className="flex items-start justify-between gap-2">
                  <details className="min-w-0 flex-1">
                    <summary className="text-xs">
                      {t("business.lookup.conversion", {
                        type: row.type ?? t("business.lookup.originalType"),
                        timezone: row.timezone ?? "—",
                      })}
                    </summary>
                    <SchemaForm
                      schema={{
                        type: "object",
                        properties: {
                          type: rowProperties.type,
                          timezone: rowProperties.timezone,
                        },
                      }}
                      value={row}
                      onChange={(next) => {
                        const cleaned = { ...(next as typeof row) };
                        if (!cleaned.type) delete cleaned.type;
                        if (!cleaned.timezone) delete cleaned.timezone;
                        change(cleaned);
                      }}
                      options={compact}
                    />
                  </details>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={t("business.lookup.removeMapping", {
                      field: row.output || index + 1,
                    })}
                    onClick={() =>
                      update({
                        returns: config.returns!.filter((_, i) => i !== index),
                      })
                    }
                  >
                    {t("business.remove")}
                  </Button>
                </div>
              </div>
            );
          })}
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              update({
                returns: [...(config.returns ?? []), { field: "", output: "" }],
              })
            }
          >
            {t("business.add")}
          </Button>
        </div>,
      )}
      {section(
        "quality",
        (config.source_identity?.keys.length ?? 0) +
          (config.source_required?.length ?? 0),
        t("business.lookup.identitySummary", {
          fields:
            config.source_identity?.keys.join(" · ") ||
            t("business.lookup.none"),
        }),
        problems(["source_identity", "source_required"]),
        <>
          <p className="text-xs text-muted-foreground">
            {t("business.lookup.qualityHint")}
          </p>
          {fieldList(
            t("business.lookup.identityFields"),
            config.source_identity?.keys ?? [],
            "database",
            (keys) => {
              if (keys.length)
                update({
                  source_identity: { ...config.source_identity, keys },
                });
              else {
                const next = { ...config };
                delete next.source_identity;
                onChange(next);
              }
            },
          )}
          {fieldList(
            t("business.lookup.sourceRequired"),
            config.source_required ?? [],
            "database",
            (v) => update({ source_required: v }),
          )}
          <details>
            <summary className="text-sm">
              {t("business.lookup.identityDetails")}
            </summary>
            <dl className="text-xs break-all">
              <dt>{t("business.field.name")}</dt>
              <dd>{config.source_identity?.name ?? "—"}</dd>
              <dt>{t("business.field.namespace")}</dt>
              <dd>{config.source_identity?.namespace ?? "—"}</dd>
            </dl>
            <p className="text-xs text-muted-foreground">
              {t("business.lookup.identityHint")}
            </p>
          </details>
        </>,
      )}
      {section(
        "checks",
        (config.checks?.required?.length ?? 0) +
          (config.checks?.conditions?.length ?? 0),
        (config.checks?.conditions ?? [])
          .map(
            (c) =>
              `${c.field ?? "—"} ${c.op ?? ""} ${c.right_field ?? JSON.stringify(c.value ?? "")}`,
          )
          .join(" · "),
        problems(["checks"]),
        <>
          <p className="text-xs text-muted-foreground">
            {t("business.lookup.checksHint")}
          </p>
          {fieldList(
            t("business.lookup.resultRequired"),
            config.checks?.required ?? [],
            "result",
            (required) => update({ checks: { ...config.checks, required } }),
          )}
          {form(
            "conditions",
            config.checks?.conditions,
            (v) =>
              update({
                checks: {
                  ...config.checks,
                  conditions: v as Record<string, unknown>[],
                },
              }),
            properties.checks?.properties?.conditions,
          )}
        </>,
      )}
      <p className="rounded bg-muted p-2 text-sm">
        {t("business.lookup.outputs")}
      </p>
    </div>
  );
}
