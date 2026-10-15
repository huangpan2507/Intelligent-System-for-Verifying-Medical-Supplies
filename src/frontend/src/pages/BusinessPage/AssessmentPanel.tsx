import { Button } from "@/components/ui/button";
import type { Assessment } from "@/controllers/API/queries/business";
import { useTranslation } from "./business-i18n";

export default function AssessmentPanel({
  assessment,
  select,
}: {
  assessment?: Assessment;
  select: (id: string) => void;
}) {
  const { t } = useTranslation();
  if (!assessment || assessment.state === "unassessed")
    return <p>{t("business.assessmentPending")}</p>;
  return (
    <section className="space-y-3 rounded border p-4">
      <h3 className="font-semibold">{t("business.assessmentTitle")}</h3>
      <p>
        {t(`business.assessment.${assessment.state}`, {
          defaultValue: assessment.state,
        })}
      </p>
      {assessment.mode === "verification" && (
        <>
          <p>
            {t("business.assessmentCounts", {
              records: assessment.received_records,
              identities: assessment.business_identities,
              missing: assessment.missing_identity_records,
              gaps: assessment.coverage_gap_records,
            })}
          </p>
          {!assessment.discovery_complete && (
            <p role="status" className="text-destructive">
              {t("business.discoveryUnknown")}
            </p>
          )}
          {assessment.dispositions_dataset_id && (
            <Button
              variant="outline"
              onClick={() => select(assessment.dispositions_dataset_id!)}
            >
              {t("business.viewDispositions")}
            </Button>
          )}
          <div className="overflow-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr>
                  {(
                    [
                      "check",
                      "units",
                      "equal",
                      "different",
                      "uncompared",
                      "gaps",
                    ] as const
                  ).map((key) => (
                    <th className="p-2" key={key}>
                      {t(`business.assessmentColumn.${key}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {assessment.checks?.map((check) => (
                  <tr key={check.name}>
                    <td className="p-2">
                      <Button
                        variant="link"
                        disabled={!check.dataset_id}
                        onClick={() =>
                          check.dataset_id && select(check.dataset_id)
                        }
                      >
                        {check.name}
                      </Button>
                    </td>
                    <td className="p-2">{check.units}</td>
                    <td className="p-2">{check.counts?.equal ?? 0}</td>
                    <td className="p-2">{check.counts?.different ?? 0}</td>
                    <td className="p-2">{check.counts?.uncompared ?? 0}</td>
                    <td className="p-2">{check.coverage_gaps ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <details>
        <summary>{t("business.sourceCompleteness")}</summary>
        <ul className="space-y-2">
          {assessment.sources?.map((source) => (
            <li key={source.dataset_id}>
              <Button variant="link" onClick={() => select(source.dataset_id)}>
                {source.node}
              </Button>
              {t(`business.completeness.${source.state}`, {
                defaultValue: source.state,
              })}{" "}
              · {t("business.totalRows", { count: source.received_rows })}
              {source.basis && (
                <p className="text-xs text-muted-foreground">{source.basis}</p>
              )}
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
