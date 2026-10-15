import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  type Catalog,
  type Connection,
  type Field,
  type SourcePreview,
  useBusinessQuery,
  useBusinessUpload,
} from "@/controllers/API/queries/business";
import {
  businessNodeDescription,
  businessNodeName,
} from "@/pages/BusinessPage/business-node-presentation";
import useFlowStore from "@/stores/flowStore";
import type { NodeDataType } from "@/types/flow";
import ApiConfiguration from "./ApiConfiguration";
import ApiFieldConfiguration from "./ApiFieldConfiguration";
import { useTranslation } from "./business-i18n";
import ClassificationConfiguration from "./ClassificationConfiguration";
import CompareConfiguration from "./CompareConfiguration";
import DatabaseConfiguration from "./DatabaseConfiguration";
import DatabasePreview from "./DatabasePreview";
import { businessError } from "./errors";
import ImagingConfiguration from "./ImagingConfiguration";
import LookupConfiguration from "./LookupConfiguration";
import ResultsConfiguration from "./ResultsConfiguration";
import { SchemaForm } from "./SchemaForm";
import TaskInputPanel from "./TaskInputPanel";
import {
  previewKey,
  useCanvasFieldDiscovery,
} from "./use-canvas-field-discovery";
import ValidateConfiguration from "./ValidateConfiguration";

export default function CanvasConfiguration() {
  const { t } = useTranslation();
  const nodes = useFlowStore((s) => s.nodes);
  const edges = useFlowStore((s) => s.edges);
  const setNode = useFlowStore((s) => s.setNode);
  const flowId = useFlowStore((s) => s.currentFlow?.id);
  const selected = nodes.find(
    (n) => n.selected && (n.data as NodeDataType).type?.includes("Business"),
  );
  const business = nodes.some((n) =>
    (n.data as NodeDataType).type?.includes("Business"),
  );
  const [open, setOpen] = useState(true);
  const [wide, setWide] = useState(false);
  const [error, setError] = useState("");
  const catalog = useBusinessQuery<Catalog>("catalog", business);
  const connections = useBusinessQuery<Connection[]>("connections", business);
  const upload = useBusinessUpload();
  const data = selected?.data as NodeDataType | undefined;
  const kind =
    data?.type
      ?.split(":")
      .at(-1)
      ?.split("@")[0]
      ?.replace("Business", "")
      .toLowerCase() ?? "";
  const configText = data?.node?.template.configuration?.value ?? "{}";
  const config = useMemo(() => {
    try {
      return JSON.parse(configText);
    } catch {
      return {};
    }
  }, [configText]);
  const databaseSource = ["database", "databaselookup"].includes(kind);
  const sourceMetadata = useBusinessQuery<{
    default_schema?: string;
    schemas?: string[];
  }>(
    `connections/${encodeURIComponent(config.connection ?? "")}/schema`,
    business && !!config.connection && databaseSource,
  );
  const schemaAvailable =
    !config.schema ||
    sourceMetadata.data?.schemas?.includes(config.schema) === true;
  const schema = useBusinessQuery<{
    default_schema?: string;
    tables?: string[];
    schemas?: string[];
    fields?: Field[];
  }>(
    `connections/${encodeURIComponent(config.connection ?? "")}/schema?schema=${encodeURIComponent(config.schema ?? "")}`,
    business && !!config.connection && databaseSource && schemaAvailable,
  );
  const tableFields = useBusinessQuery<{ fields: Field[] }>(
    `connections/${encodeURIComponent(config.connection ?? "")}/schema?table=${encodeURIComponent(config.table ?? "")}&schema=${encodeURIComponent(config.schema ?? "")}`,
    business &&
      !!config.connection &&
      !!config.table &&
      databaseSource &&
      schemaAvailable &&
      schema.data?.tables?.includes(config.table) === true,
  );
  const discovery = useCanvasFieldDiscovery(
    nodes,
    edges,
    business,
    selected?.id,
  );
  useEffect(() => {
    const defaultSchema = sourceMetadata.data?.default_schema;
    if (
      !selected ||
      !databaseSource ||
      !config.connection ||
      config.schema ||
      !defaultSchema ||
      !sourceMetadata.data?.schemas?.includes(defaultSchema) ||
      sourceMetadata.isFetching ||
      sourceMetadata.error
    )
      return;
    // A populated table without an explicit schema already relies on this default.
    setNode(selected.id, (old) => {
      if (old.data.node?.template.configuration?.value !== configText)
        return old;
      const next = structuredClone(old);
      next.data.node!.template.configuration.value = JSON.stringify({
        ...config,
        schema: defaultSchema,
        ...(config.binding_source &&
        !config.binding_source.schema &&
        config.binding_source.connection === config.connection &&
        config.binding_source.table === config.table
          ? {
              binding_source: {
                ...config.binding_source,
                schema: defaultSchema,
              },
            }
          : {}),
      });
      return next;
    });
  }, [
    selected?.id,
    databaseSource,
    configText,
    sourceMetadata.data,
    sourceMetadata.isFetching,
    sourceMetadata.error,
    setNode,
  ]);
  if (!business) return null;
  const currentInspection = discovery.inspection;
  const fields = { ...discovery.fields };
  if (kind === "database") fields.data = tableFields.data?.fields ?? [];
  if (kind === "databaselookup")
    fields.database = (tableFields.data?.fields ?? []).map((field) => ({
      ...field,
      source: config.table,
    }));
  fields.response = config.fields ?? [];
  fields.result = currentInspection?.schemas[selected?.id ?? ""]?.data ?? [];
  if (kind === "databaselookup" && !fields.result.length) {
    const returns: Field[] = (config.returns ?? []).flatMap(
      (binding: { field: string; output: string; type?: string }) => {
        const original = fields.database?.find(
          (field) => field.name === binding.field,
        );
        return original && binding.output
          ? [
              {
                ...original,
                name: binding.output,
                type: binding.type ?? original.type,
              },
            ]
          : [];
      },
    );
    fields.result = [...(fields.data ?? []), ...returns];
  }
  fields.upstream = fields.data ?? [];
  if (kind === "compare" && config.calculations?.length)
    fields.data = Array.from(
      new Map(
        [...(fields.data ?? []), ...fields.result].map((field) => [
          field.name,
          field,
        ]),
      ).values(),
    );
  const sourceKey = previewKey(config);
  const upstreamRows = discovery.upstreamRows;
  const savePreview = (result: SourcePreview) =>
    discovery.savePreview(config, result);
  const formSchema = catalog.data?.nodes[kind]?.schema;
  const databaseFieldOrder: Record<string, number> = {
    connection: 0,
    schema: 1,
    table: 2,
  };
  const sourceFormSchema =
    formSchema && ["database", "databaselookup", "api"].includes(kind)
      ? {
          ...formSchema,
          properties: Object.fromEntries(
            Object.entries(formSchema.properties ?? {})
              .sort(([left], [right]) =>
                databaseSource
                  ? (databaseFieldOrder[left] ?? 3) -
                    (databaseFieldOrder[right] ?? 3)
                  : 0,
              )
              .filter(
                ([key]) =>
                  key !== "field_evidence" &&
                  key !== "fields" &&
                  !(
                    kind === "database" &&
                    config.sql &&
                    ["table", "schema", "conditions"].includes(key)
                  ),
              ),
          ),
        }
      : formSchema;
  const change = (value: unknown) => {
    if (!selected) return;
    setNode(selected.id, (old) => {
      if (
        (old.data as NodeDataType).node?.template.configuration?.value !==
        configText
      )
        return old;
      const next = structuredClone(old);
      (next.data as NodeDataType).node!.template.configuration.value =
        JSON.stringify(value);
      return next;
    });
  };
  const connectionKind = connections.data?.find(
    (c) => c.id === config.connection,
  )?.kind;
  const formOptions = {
    fieldsLoading: databaseSource ? !tableFields.data : !currentInspection,
    databaseConditions: kind === "database",
    regulatoryTask: nodes.some((node) =>
      node.data.type?.includes("BusinessTaskinput"),
    ),
    nodes: nodes.map((n) => ({
      id: n.id,
      label: String(n.data.node?.display_name ?? n.id),
    })),
    schemas: currentInspection?.schemas,
    connections: connections.data,
    tables: schema.data?.tables,
    databaseSchemas: sourceMetadata.data?.schemas,
    fields,
    parameters: nodes.flatMap((node) => {
      if (node.data.type?.includes("BusinessTaskinput")) {
        return [
          ...(catalog.data?.task_input?.parameters ?? []),
          ...(catalog.data?.task_input?.context ?? []),
        ].map((p) => p.name);
      }
      try {
        const definition = JSON.parse(
          node.data.node?.template.configuration?.value ?? "{}",
        );
        return (definition.parameters ?? [])
          .filter((p: unknown) => p && typeof p === "object" && "name" in p)
          .map((p: { name: string }) => p.name);
      } catch {
        return [];
      }
    }),
    labels: databaseSource
      ? {
          schema: t(
            connectionKind === "mysql"
              ? "business.lookup.database"
              : connectionKind === "postgresql"
                ? "business.lookup.pgSchema"
                : "business.field.schema",
          ),
        }
      : undefined,
  };
  const ResultConfiguration =
    kind === "compare" ? CompareConfiguration : ImagingConfiguration;
  return (
    <div
      className={`absolute right-3 top-16 z-30 max-h-[80%] max-w-[calc(100%-1.5rem)] overflow-auto rounded-lg border bg-background p-4 shadow-lg ${wide && ["databaselookup", "database", "validate", "classification", "taskinput", "api", "imaging", "compare", "output"].includes(kind) ? "w-[56rem]" : "w-96"}`}
      data-testid="business-canvas-configuration"
    >
      <div className="flex items-center justify-between">
        <strong>
          {t(
            kind === "taskinput"
              ? "business.layout.taskTitle"
              : "business.configure",
          )}
        </strong>
        {[
          "databaselookup",
          "database",
          "validate",
          "classification",
          "taskinput",
          "api",
          "imaging",
          "compare",
          "output",
        ].includes(kind) && (
          <Button size="sm" variant="ghost" onClick={() => setWide(!wide)}>
            {t(
              kind === "taskinput"
                ? wide
                  ? "business.layout.narrowView"
                  : "business.layout.wideView"
                : wide
                  ? "business.lookup.narrow"
                  : "business.lookup.wide",
            )}
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={() => setOpen(!open)}>
          {t(open ? "business.collapse" : "business.expand")}
        </Button>
      </div>
      {open && (
        <div className="mt-3 space-y-3">
          <p className="text-xs text-muted-foreground">
            {t(
              kind === "taskinput"
                ? "business.taskInput.title"
                : "business.canvasHint",
            )}
          </p>
          {(error || discovery.error) && (
            <p role="alert" className="text-destructive">
              {error || discovery.error}
            </p>
          )}
          {!selected ? (
            <p>{t("business.selectNode")}</p>
          ) : (
            <>
              <p className="font-medium">
                {businessNodeName(data?.type, data?.node?.display_name)}
              </p>
              {["validate", "classification"].includes(kind) && (
                <p className="break-words text-xs text-muted-foreground">
                  {t("business.lookup.upstream", {
                    source:
                      Array.from(
                        new Set(
                          (fields.data ?? [])
                            .map((f) => f.source)
                            .filter(Boolean),
                        ),
                      ).join(" · ") || t("business.lookup.none"),
                  })}
                </p>
              )}
              {currentInspection?.errors[selected.id] && (
                <p role="alert" className="text-sm text-destructive">
                  {currentInspection.errors[selected.id]}
                </p>
              )}
              {databaseSource &&
                (sourceMetadata.error || schema.error || tableFields.error) && (
                  <p role="alert" className="text-destructive">
                    {businessError(
                      sourceMetadata.error ?? schema.error ?? tableFields.error,
                    )}
                  </p>
                )}
              {databaseSource &&
                (sourceMetadata.isFetching ||
                  schema.isFetching ||
                  tableFields.isFetching) && (
                  <p role="status">{t("business.fields.loading")}</p>
                )}
              {kind === "file" && (
                <label className="block text-sm">
                  {t("business.uploadFile")}
                  <input
                    type="file"
                    accept=".csv,.json,.parquet"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file)
                        upload.mutate(file, {
                          onSuccess: (r) =>
                            change({
                              ...config,
                              file_id: r.file_id,
                              format: r.format,
                              fields: r.fields,
                            }),
                          onError: (e) => setError(e.message),
                        });
                    }}
                  />
                </label>
              )}
              {kind === "taskinput" && (
                <TaskInputPanel
                  key={`${flowId}-${selected.id}`}
                  flowId={flowId}
                  definition={catalog.data?.task_input}
                />
              )}
              {sourceFormSchema && kind === "classification" && (
                <ClassificationConfiguration
                  key={selected.id}
                  value={config}
                  onChange={change}
                  fields={fields.data ?? []}
                  connections={connections.data}
                  schema={sourceFormSchema}
                  prompt={
                    currentInspection?.classification_prompts?.[selected.id]
                  }
                  fieldsLoading={!currentInspection}
                />
              )}
              {sourceFormSchema && kind === "databaselookup" && (
                <LookupConfiguration
                  key={selected.id}
                  value={config}
                  onChange={change}
                  schema={sourceFormSchema}
                  options={formOptions}
                  nodeId={selected.id}
                  upstream={Array.from(
                    new Set(
                      (fields.data ?? []).map((f) => f.source).filter(Boolean),
                    ),
                  ).join(" · ")}
                />
              )}
              {sourceFormSchema &&
                ![
                  "taskinput",
                  "classification",
                  "databaselookup",
                  "database",
                  "validate",
                  "api",
                  "imaging",
                  "compare",
                  "output",
                ].includes(kind) && (
                  <SchemaForm
                    key={`configuration-${selected.id}`}
                    schema={sourceFormSchema}
                    value={config}
                    onChange={change}
                    options={formOptions}
                  />
                )}
              {sourceFormSchema && kind === "validate" && (
                <ValidateConfiguration
                  key={selected.id}
                  value={config}
                  onChange={change}
                  schema={sourceFormSchema}
                  options={formOptions}
                  nodeId={selected.id}
                />
              )}
              {kind === "output" && (
                <ResultsConfiguration
                  key={`${flowId}-${selected.id}`}
                  value={config}
                  onChange={change}
                  flowId={flowId}
                  nodeId={selected.id}
                />
              )}
              {sourceFormSchema && kind === "database" && (
                <DatabaseConfiguration
                  key={selected.id}
                  value={config}
                  onChange={change}
                  schema={sourceFormSchema}
                  options={formOptions}
                  preview={
                    config.connection && (config.table || config.sql) ? (
                      <DatabasePreview
                        key={`preview-${selected.id}-${sourceKey}`}
                        connection={config.connection}
                        config={config}
                        onFields={
                          config.sql
                            ? (fields, field_evidence) =>
                                change({ ...config, fields, field_evidence })
                            : undefined
                        }
                        onPreview={savePreview}
                      />
                    ) : undefined
                  }
                />
              )}
              {["imaging", "compare"].includes(kind) && sourceFormSchema && (
                <ResultConfiguration
                  key={selected.id}
                  value={config}
                  onChange={change}
                  schema={sourceFormSchema}
                  options={formOptions}
                >
                  <details>
                    <summary>{t("business.outputFields")}</summary>
                    <pre className="max-h-64 overflow-auto text-xs">
                      {JSON.stringify(
                        currentInspection?.schemas[selected.id],
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                </ResultConfiguration>
              )}
              {kind === "api" && sourceFormSchema && (
                <ApiConfiguration
                  key={selected.id}
                  value={config}
                  onChange={change}
                  schema={sourceFormSchema}
                  options={formOptions}
                  originFields={(() => {
                    const ancestors = new Set<string>();
                    const visit = (id: string) => {
                      for (const edge of edges.filter((e) => e.target === id)) {
                        if (!ancestors.has(edge.source)) {
                          ancestors.add(edge.source);
                          visit(edge.source);
                        }
                      }
                    };
                    visit(selected.id);
                    const sources = nodes.filter(
                      (n) =>
                        ancestors.has(n.id) &&
                        n.data.type?.split(":").at(-1)?.split("@")[0] ===
                          "BusinessDatabase",
                    );
                    return sources.length === 1
                      ? currentInspection?.schemas[sources[0].id]?.data
                      : undefined;
                  })()}
                >
                  <ApiFieldConfiguration
                    key={`api-fields-${selected.id}-${sourceKey}`}
                    config={config}
                    upstreamRows={upstreamRows}
                    onPreview={savePreview}
                    contractError={currentInspection?.errors[selected.id]}
                    onApply={(fields, field_evidence) =>
                      change({ ...config, fields, field_evidence })
                    }
                    output={
                      <details>
                        <summary>{t("business.outputFields")}</summary>
                        <pre className="max-h-64 overflow-auto text-xs">
                          {JSON.stringify(
                            currentInspection?.schemas[selected.id],
                            null,
                            2,
                          )}
                        </pre>
                      </details>
                    }
                  />
                </ApiConfiguration>
              )}
              {!["taskinput", "api", "imaging", "compare", "output"].includes(
                kind,
              ) && (
                <details>
                  <summary>{t("business.outputFields")}</summary>
                  <pre className="overflow-auto text-xs">
                    {JSON.stringify(
                      currentInspection?.schemas[selected.id],
                      null,
                      2,
                    )}
                  </pre>
                </details>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
