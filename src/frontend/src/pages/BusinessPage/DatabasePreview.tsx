import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  type Field,
  type FieldEvidence,
  type SourcePreview,
  useBusinessMutation,
} from "@/controllers/API/queries/business";
import { businessError } from "./errors";
import SourceFieldEditor, { fieldType } from "./SourceFieldEditor";

export default function DatabasePreview({
  connection,
  config,
  onFields,
  onPreview,
}: {
  connection: string;
  config: Record<string, unknown>;
  onFields?: (fields: Field[], evidence?: FieldEvidence) => void;
  onPreview?: (preview: SourcePreview) => void;
}) {
  const { t } = useTranslation();
  const mutation = useBusinessMutation<SourcePreview>();
  const [result, setResult] = useState<SourcePreview | null>(null);
  const [chosenFields, setChosenFields] = useState<Field[]>([]);
  const [error, setError] = useState("");
  const [bindings, setBindings] = useState("{}");
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const latest = useRef("");
  const revision = JSON.stringify({ config, bindings });
  latest.current = revision;
  return (
    <div className="space-y-2">
      <label className="block text-sm">
        {t("business.previewBindings")}
        <textarea
          className="w-full rounded border bg-background p-2 font-mono text-xs"
          value={bindings}
          onChange={(e) => setBindings(e.target.value)}
        />
      </label>
      <Button
        type="button"
        variant="outline"
        disabled={mutation.isPending}
        onClick={() => {
          try {
            const parameters = JSON.parse(bindings);
            mutation.mutate(
              {
                path: `connections/${encodeURIComponent(connection)}/preview`,
                body: { config, parameters },
              },
              {
                onSuccess: (r) => {
                  if (!mounted.current || latest.current !== revision) return;
                  setResult(r);
                  setChosenFields(
                    r.fields.map((field) => ({
                      name: field.name,
                      type: fieldType(field.type),
                      nullable: true,
                      required: true,
                    })),
                  );
                  onPreview?.(r);
                  setError("");
                },
                onError: (e) => {
                  if (mounted.current && latest.current === revision)
                    setError(businessError(e));
                },
              },
            );
          } catch {
            setError(t("business.invalidJson"));
          }
        }}
      >
        {t("business.previewData")}
      </Button>
      <p className="text-xs text-muted-foreground">
        {t("business.previewHint")}
      </p>
      {error && <p role="alert">{error}</p>}
      {result && (
        <>
          {!!result.uncertain_types?.length && (
            <p role="status">
              {t("business.fields.uncertainTypes", {
                fields: result.uncertain_types.join(", "),
              })}
            </p>
          )}
          <div className="max-h-64 overflow-auto">
            <table className="w-full text-xs">
              <thead>
                <tr>
                  {result.fields.map((f) => (
                    <th
                      className="whitespace-nowrap border p-2 text-left"
                      key={f.name}
                      title={f.comment}
                    >
                      {f.name}
                      <br />
                      {f.type}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row, i) => (
                  <tr key={i}>
                    {result.fields.map((f) => (
                      <td className="whitespace-nowrap border p-2" key={f.name}>
                        {row[f.name] == null ? "—" : String(row[f.name])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {onFields && (
            <SourceFieldEditor
              fields={chosenFields}
              onChange={setChosenFields}
            />
          )}
          {onFields && (
            <Button
              type="button"
              variant="outline"
              onClick={() => onFields(chosenFields, result.field_evidence)}
            >
              {t("business.usePreviewFields")}
            </Button>
          )}
        </>
      )}
    </div>
  );
}
