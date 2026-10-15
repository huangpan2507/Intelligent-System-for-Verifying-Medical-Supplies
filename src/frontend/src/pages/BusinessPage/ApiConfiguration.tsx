import { type ReactNode, useRef } from "react";
import type { Field, JsonSchema } from "@/controllers/API/queries/business";
import { useTranslation } from "./business-i18n";
import ConfigurationSection from "./ConfigurationSection";
import { configurationShape } from "./configuration-layout";
import LookupFieldList from "./LookupFieldList";
import { lookupProblems } from "./lookup-config";
import { type FormOptions, SchemaForm } from "./SchemaForm";

export default function ApiConfiguration({
  value,
  onChange,
  schema,
  options,
  originFields,
  children,
}: {
  value: Record<string, unknown>;
  onChange: (v: unknown) => void;
  schema: JsonSchema;
  options: FormOptions;
  originFields?: Field[];
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const collection = value.collection as Record<string, unknown> | undefined;
  const lastCollection = useRef(collection);
  if (collection) lastCollection.current = collection;
  const completeness = value.completeness as
    | Record<string, unknown>
    | undefined;
  const conditions = (value.response_conditions ?? []) as {
    path: string;
    equals: unknown;
  }[];
  const retained = (collection?.retain_fields ?? []) as string[];
  const sourceCount = retained.filter((name) =>
    originFields?.some((f) => f.name === name),
  ).length;
  const retainSummary = originFields?.length
    ? t("business.api.retainSources", {
        source: sourceCount,
        derived: retained.length - sourceCount,
      })
    : t("business.api.retainCount", { count: retained.length });
  const form = (keys: string[]) => (
    <SchemaForm
      schema={configurationShape(schema, keys)}
      value={value}
      onChange={onChange}
      options={{ ...options, compact: true }}
    />
  );
  const errors = (keys: string[]) =>
    lookupProblems(configurationShape(schema, keys), value, options);
  const lists = (
    keys: (
      | "group_by"
      | "retain_fields"
      | "address_fields"
      | "item_keys"
      | "item_context"
    )[],
    response = false,
  ) =>
    keys.map((key) => (
      <LookupFieldList
        key={key}
        label={t(`business.field.${key}`)}
        value={(collection?.[key] ?? []) as string[]}
        fields={options.fields?.[response ? "response" : "data"] ?? []}
        onChange={(next) =>
          onChange({ ...value, collection: { ...collection, [key]: next } })
        }
      />
    ));
  const pagination = String(value.pagination ?? "none");
  return (
    <div className="space-y-3">
      <ConfigurationSection
        id="api-service"
        title={t("business.api.service")}
        summary={`${value.method ?? "GET"} ${value.path ?? "—"}`}
        errors={errors(["connection", "path", "method"])}
        defaultOpen
      >
        {form(["connection"])}
        <details>
          <summary className="cursor-pointer text-sm">
            {t("business.api.endpoint")}
          </summary>
          {form(["path", "method"])}
        </details>
      </ConfigurationSection>
      <ConfigurationSection
        id="api-request"
        title={t("business.api.request")}
        summary={
          Object.keys((value.body ?? {}) as object).join(" · ") ||
          t("business.lookup.none")
        }
        errors={errors(["body"])}
        defaultOpen
      >
        <p className="text-xs text-muted-foreground">
          {t("business.api.requestHint")}
        </p>
        {form(["body"])}
      </ConfigurationSection>
      <ConfigurationSection
        id="api-validity"
        title={t("business.api.validity")}
        summary={`${conditions.map((c) => `${c.path} = ${JSON.stringify(c.equals)}`).join(" · ") || t("business.api.noSuccessConditions")} · ${completeness?.basis ?? t("business.api.noCompleteness")}`}
        errors={errors([
          "items_path",
          "response_conditions",
          "completeness",
          "pagination",
          "max_calls",
          "max_pages",
          ...(pagination === "cursor"
            ? ["cursor_path", "cursor_parameter"]
            : pagination === "page"
              ? ["page_parameter"]
              : []),
        ])}
      >
        {form(["items_path", "pagination"])}
        {pagination === "cursor" && form(["cursor_path", "cursor_parameter"])}
        {pagination === "page" && form(["page_parameter"])}
        <details>
          <summary className="cursor-pointer text-sm">
            {t("business.api.successDetails")}
          </summary>
          {form([
            "response_conditions",
            "completeness",
            "max_calls",
            ...(pagination !== "none" ? ["max_pages"] : []),
          ])}
        </details>
      </ConfigurationSection>
      <ConfigurationSection
        id="api-collection"
        title={t("business.api.collection")}
        summary={
          collection
            ? `${((collection.group_by as string[]) ?? []).join(" + ")} · ${retainSummary}`
            : t("business.api.rawOutput")
        }
        errors={errors(["collection", "context_fields"])}
      >
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={!!collection}
            onChange={(e) => {
              if (e.target.checked)
                onChange({
                  ...value,
                  collection: lastCollection.current ?? {
                    group_by: [],
                    retain_fields: [],
                    address_fields: [],
                    item_keys: [],
                    output: "image_manifest",
                  },
                });
              else {
                const { collection: _collection, ...rest } = value;
                onChange(rest);
              }
            }}
          />
          {t("business.field.collection")}
        </label>
        {collection && (
          <>
            {lists(["group_by"])}
            <p className="text-xs">
              {t("business.api.address", {
                fields:
                  ((collection.address_fields as string[]) ?? []).join(" + ") ||
                  "—",
              })}
            </p>
            <p className="text-sm">{retainSummary}</p>
            <p className="text-xs text-muted-foreground">
              {t("business.api.retainHint")}
            </p>
            <details>
              <summary className="cursor-pointer text-sm">
                {t("business.api.retainedDetails")}
              </summary>
              {lists(["retain_fields"])}
            </details>
            <details>
              <summary className="cursor-pointer text-sm">
                {t("business.api.imageDetails")}
              </summary>
              {lists(["address_fields", "item_keys"], true)}
              {lists(["item_context"])}
              <SchemaForm
                schema={configurationShape(
                  schema.properties?.collection ?? {},
                  ["output"],
                )}
                value={collection}
                onChange={(next) => onChange({ ...value, collection: next })}
                options={{ ...options, compact: true }}
              />
            </details>
          </>
        )}
        <details>
          <summary className="cursor-pointer text-sm">
            {t("business.field.context_fields")}
          </summary>
          <p className="text-xs">{t("business.api.contextHint")}</p>
          <LookupFieldList
            label={t("business.field.context_fields")}
            fields={options.fields?.data ?? []}
            value={(value.context_fields ?? []) as string[]}
            onChange={(next) => onChange({ ...value, context_fields: next })}
          />
        </details>
      </ConfigurationSection>
      {children}
    </div>
  );
}
