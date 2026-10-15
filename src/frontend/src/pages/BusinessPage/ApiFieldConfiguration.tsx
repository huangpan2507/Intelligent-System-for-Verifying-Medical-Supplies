import { type ReactNode, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  type Field,
  type FieldEvidence,
  type SourcePreview,
  useBusinessMutation,
} from "@/controllers/API/queries/business";
import { businessOption, useTranslation } from "./business-i18n";
import ConfigurationSection from "./ConfigurationSection";
import { businessError } from "./errors";
import SourceFieldEditor from "./SourceFieldEditor";

export default function ApiFieldConfiguration({
  config,
  onApply,
  onPreview,
  upstreamRows,
  output,
  contractError,
}: {
  output?: ReactNode;
  contractError?: string;
  config: Record<string, unknown>;
  onApply: (fields: Field[], evidence: FieldEvidence) => void;
  onPreview: (result: SourcePreview) => void;
  upstreamRows: { label: string; row: Record<string, unknown> }[];
}) {
  const { t } = useTranslation();
  const mutation = useBusinessMutation<SourcePreview>();
  const [fields, setFields] = useState<Field[]>(
    (config.fields as Field[]) ?? [],
  );
  const [reference, setReference] = useState(
    (config.field_evidence as FieldEvidence)?.reference ?? "",
  );
  const [document, setDocument] = useState("");
  const [parameters, setParameters] = useState("{}");
  const [record, setRecord] = useState("{}");
  const [preview, setPreview] = useState<SourcePreview>();
  const [sampleFields, setSampleFields] = useState<Field[]>([]);
  const [error, setError] = useState("");
  const current = useRef("");
  const revision = JSON.stringify({
    config,
    fields,
    reference,
    document,
    parameters,
    record,
  });
  current.current = revision;
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const applyContract = (imported: boolean) => {
    try {
      mutation.mutate(
        {
          path: `connections/${encodeURIComponent(String(config.connection))}/contract`,
          body: {
            config,
            reference,
            ...(imported ? { document: JSON.parse(document) } : { fields }),
          },
        },
        {
          onSuccess: (result) => {
            if (
              !mounted.current ||
              current.current !== revision ||
              !result.field_evidence
            )
              return;
            setFields(result.fields);
            onApply(result.fields, result.field_evidence);
            setError("");
          },
          onError: (e) => {
            if (mounted.current && current.current === revision)
              setError(businessError(e));
          },
        },
      );
    } catch {
      setError(t("business.invalidJson"));
    }
  };
  return (
    <div className="space-y-3">
      <ConfigurationSection
        id="api-contract"
        title={t("business.api.contract")}
        summary={t("business.api.contractSummary", {
          count: (config.fields as Field[] | undefined)?.length ?? 0,
          source:
            (config.field_evidence as FieldEvidence)?.reference ||
            t("business.api.evidenceMissing"),
        })}
        errors={contractError || !config.field_evidence ? 1 : 0}
      >
        <p
          role="status"
          className={contractError ? "text-destructive text-sm" : "text-sm"}
        >
          {contractError ||
            t(
              config.field_evidence
                ? "business.api.evidenceBound"
                : "business.api.evidenceMissing",
            )}
        </p>
        <p className="font-medium">{t("business.fields.apiTitle")}</p>
        <p className="text-xs text-muted-foreground">
          {t("business.fields.apiHint")}
        </p>
        {Boolean(config.field_evidence) && (
          <p className="text-sm">
            {t(
              `business.fields.evidence.${(config.field_evidence as FieldEvidence).kind}`,
            )}{" "}
            {(config.field_evidence as FieldEvidence).reference}
          </p>
        )}
        <details>
          <summary>{t("business.fields.documentTitle")}</summary>
          <div className="mt-2 space-y-3">
            <label className="block text-sm">
              {t("business.fields.reference")}
              <Input
                value={reference}
                onChange={(event) => setReference(event.target.value)}
              />
            </label>
            <SourceFieldEditor
              fields={fields}
              onChange={setFields}
              namesEditable
            />
            <Button
              variant="outline"
              disabled={
                mutation.isPending ||
                !config.connection ||
                !reference.trim() ||
                !fields.length
              }
              onClick={() => applyContract(false)}
            >
              {t("business.fields.applyDocument")}
            </Button>
            <label className="block text-sm">
              {t("business.fields.importSchema")}
              <Textarea
                value={document}
                onChange={(event) => setDocument(event.target.value)}
              />
            </label>
            <label className="block text-sm">
              {t("business.fields.importFile")}
              <input
                type="file"
                accept=".json,application/json"
                onChange={async (event) => {
                  const file = event.target.files?.[0];
                  if (!file) return;
                  if (file.size > 1024 * 1024) {
                    setError(t("business.fields.importTooLarge"));
                    return;
                  }
                  try {
                    const text = await file.text();
                    JSON.parse(text);
                    if (mounted.current && current.current === revision) {
                      setDocument(text);
                      setError("");
                    }
                  } catch {
                    if (mounted.current) setError(t("business.invalidJson"));
                  }
                }}
              />
            </label>
            <p className="text-xs text-muted-foreground">
              {t("business.fields.importHint")}
            </p>
            <Button
              variant="outline"
              disabled={
                mutation.isPending ||
                !config.connection ||
                !reference.trim() ||
                !document.trim()
              }
              onClick={() => applyContract(true)}
            >
              {t("business.fields.applyImport")}
            </Button>
          </div>
        </details>
      </ConfigurationSection>
      <ConfigurationSection
        id="api-test"
        title={t("business.api.test")}
        summary={t(
          config.collection
            ? "business.api.collectedOutput"
            : "business.api.rawOutput",
        )}
        errors={error ? 1 : 0}
      >
        <p className="text-xs text-muted-foreground">
          {t("business.api.testHint")}
        </p>
        <details>
          <summary>{t("business.fields.testTitle")}</summary>
          <div className="mt-2 space-y-3">
            <label className="block text-sm">
              {t("business.previewBindings")}
              <Textarea
                value={parameters}
                onChange={(event) => setParameters(event.target.value)}
              />
            </label>
            <label className="block text-sm">
              {t("business.fields.testRecord")}
              <Textarea
                value={record}
                onChange={(event) => setRecord(event.target.value)}
              />
            </label>
            <label className="block text-sm">
              {t("business.fields.upstreamSample")}
              <select
                className="h-10 w-full rounded border bg-background px-2"
                value=""
                onChange={(event) => {
                  const sample = upstreamRows[Number(event.target.value)];
                  if (sample) setRecord(JSON.stringify(sample.row, null, 2));
                }}
              >
                <option value="">{businessOption("business.choose")}</option>
                {upstreamRows.map((sample, index) => (
                  <option key={index} value={index}>
                    {sample.label}
                  </option>
                ))}
              </select>
            </label>
            <Button
              variant="outline"
              disabled={mutation.isPending || !config.connection}
              onClick={() => {
                try {
                  mutation.mutate(
                    {
                      path: `connections/${encodeURIComponent(String(config.connection))}/preview`,
                      body: {
                        config,
                        parameters: JSON.parse(parameters),
                        record: JSON.parse(record),
                      },
                    },
                    {
                      onSuccess: (result) => {
                        if (!mounted.current || current.current !== revision)
                          return;
                        setPreview(result);
                        setSampleFields(result.fields);
                        onPreview(result);
                        setError("");
                      },
                      onError: (e) => {
                        if (mounted.current && current.current === revision)
                          setError(businessError(e));
                      },
                    },
                  );
                } catch {
                  setError(t("business.invalidJson"));
                }
              }}
            >
              {t("business.fields.testRequest")}
            </Button>
            {preview && (
              <>
                {!!preview.contract_errors?.length && (
                  <p role="alert" className="text-destructive">
                    {t("business.fields.conflicts", {
                      details: preview.contract_errors.join("; "),
                    })}
                  </p>
                )}
                <p className="text-xs">
                  {preview.rows.length
                    ? t("business.fields.sampleHint")
                    : t("business.fields.emptySample")}
                </p>
                {!!preview.uncertain_types?.length && (
                  <p role="status">
                    {t("business.fields.uncertainTypes", {
                      fields: preview.uncertain_types.join(", "),
                    })}
                  </p>
                )}
                <pre className="max-h-48 overflow-auto text-xs">
                  {JSON.stringify(preview.rows, null, 2)}
                </pre>
                <SourceFieldEditor
                  fields={sampleFields}
                  onChange={setSampleFields}
                />
                <Button
                  variant="outline"
                  disabled={!sampleFields.length || !preview.field_evidence}
                  onClick={() => {
                    if (preview.field_evidence)
                      onApply(sampleFields, preview.field_evidence);
                  }}
                >
                  {t("business.fields.applySample")}
                </Button>
              </>
            )}
          </div>
        </details>
        {output}
        {error && (
          <p role="alert" className="text-destructive">
            {error}
          </p>
        )}
      </ConfigurationSection>
    </div>
  );
}
