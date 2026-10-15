import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  type Assessment,
  useBusinessQuery,
} from "@/controllers/API/queries/business";
import { useTranslation } from "./business-i18n";
import { RetainedFields, resultText } from "./ResultFields";

export type StorageTemplate = {
  id: string;
  version: number;
  name: string;
  columns: string[];
  obligation: unknown;
  node_id?: string;
};
type Storage = {
  task_status: string;
  release_version: number;
  saved: number;
  incomplete: number;
  different: number;
  assessment: Assessment | null;
  templates: StorageTemplate[];
};

export default function ResultStorage({
  taskId,
  nodeId,
  template,
}: {
  taskId?: string;
  nodeId?: string;
  template?: StorageTemplate;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const query = useBusinessQuery<Storage>(
    `tasks/${taskId ?? ""}/result-storage${nodeId ? `?node_id=${encodeURIComponent(nodeId)}` : ""}`,
    !!taskId,
    true,
  );
  const profiles = taskId
    ? (query.data?.templates ?? [])
    : template
      ? [template]
      : [];
  const assessment = query.data?.assessment;
  return (
    <div className="space-y-3 text-sm" data-testid="result-storage-summary">
      <p>{t("business.resultEvidence.storageScope")}</p>
      {!taskId && (
        <p className="text-muted-foreground">
          {t("business.resultEvidence.policyOnly")}
        </p>
      )}
      {taskId && query.isLoading && (
        <p role="status">{t("business.taskInput.loading")}</p>
      )}
      {query.error && <p role="alert">{query.error.message}</p>}
      {taskId && query.data && (
        <div className="space-y-2 rounded border p-3">
          <p>
            {t("business.resultEvidence.savedCount", {
              count: query.data.saved,
            })}
          </p>
          <p>
            {t("business.executionStatus")}:{" "}
            {t(`business.status.${query.data.task_status}`, {
              defaultValue: query.data.task_status,
            })}
          </p>
          <p>
            {t("business.resultEvidence.resultCounts", {
              incomplete: query.data.incomplete,
              different: query.data.different,
            })}
          </p>
          <p>
            {assessment
              ? t(`business.assessment.${assessment.state}`, {
                  defaultValue: assessment.state,
                })
              : t("business.assessmentPending")}
          </p>
          {assessment?.mode === "verification" && (
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
            </>
          )}
          <p className="text-xs text-muted-foreground">
            {t("business.resultEvidence.statusHint")}
          </p>
        </div>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger asChild>
          <Button variant="outline" size="sm">
            {t("business.resultEvidence.storageDetails")}
          </Button>
        </DialogTrigger>
        <DialogContent className="max-h-[90vh] w-[min(56rem,95vw)] max-w-none overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {t("business.resultEvidence.storageDetails")}
            </DialogTitle>
            <DialogDescription>
              {t("business.resultEvidence.storageDetailsHint")}
            </DialogDescription>
          </DialogHeader>
          {profiles.map((profile) => (
            <div
              key={`${profile.node_id ?? ""}-${profile.id}`}
              className="space-y-3"
            >
              <p className="font-semibold">
                {profile.name} · v{profile.version}
              </p>
              <RetainedFields columns={profile.columns} />
              <details>
                <summary className="cursor-pointer text-sm">
                  {t("business.resultEvidence.coveragePolicy")}
                </summary>
                <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-all rounded bg-muted p-3 text-xs">
                  {resultText(profile.obligation)}
                </pre>
              </details>
            </div>
          ))}
          {query.data && (
            <details>
              <summary className="cursor-pointer text-sm">
                {t("business.resultEvidence.actualAssessment")}
              </summary>
              <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all text-xs">
                {resultText(query.data)}
              </pre>
            </details>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
