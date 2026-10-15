import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useBusinessQuery } from "@/controllers/API/queries/business";
import { useTranslation } from "./business-i18n";
import { FieldTable, resultText } from "./ResultFields";

type Detail = {
  kind: "source" | "recognition";
  name?: string;
  record?: Record<string, unknown>;
  original_record?: Record<string, unknown>;
  request?: {
    payload: Record<string, unknown>;
    response: Record<string, unknown>;
    transport: string;
    remote: string;
    validity: string;
    error?: string;
  };
};

function manifestCount(value: unknown): number | null {
  try {
    const manifest = typeof value === "string" ? JSON.parse(value) : value;
    return Array.isArray(manifest) ? manifest.length : null;
  } catch {
    return null;
  }
}

export default function ResultEvidenceDialog({
  base,
  selection,
  close,
}: {
  base: string;
  selection: { id: string; kind: string } | null;
  close: () => void;
}) {
  const { t } = useTranslation();
  const query = useBusinessQuery<Detail>(
    `${base}/evidence/${selection?.id ?? ""}/detail`,
    !!selection,
    false,
    { staleTime: Infinity },
  );
  return (
    <Dialog
      open={!!selection}
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <DialogContent
        className="max-h-[90vh] w-[min(56rem,95vw)] max-w-none overflow-y-auto"
        data-testid="result-evidence-dialog"
      >
        <DialogHeader>
          <DialogTitle>
            {t(
              selection?.kind === "recognition"
                ? "business.resultEvidence.recognitionTitle"
                : "business.resultEvidence.snapshotTitle",
            )}
          </DialogTitle>
          <DialogDescription>
            {t("business.resultEvidence.snapshotHint")}
          </DialogDescription>
        </DialogHeader>
        {query.isLoading && (
          <p role="status">{t("business.taskInput.loading")}</p>
        )}
        {query.error && (
          <p role="alert" className="text-destructive">
            {query.error.message}
          </p>
        )}
        {query.data && (
          <DetailContents key={selection?.id} detail={query.data} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function DetailContents({ detail }: { detail: Detail }) {
  const { t } = useTranslation();
  const [all, setAll] = useState(false);
  const request = detail.request;
  const record = detail.original_record ?? detail.record ?? {};
  const visible = Object.fromEntries(
    Object.entries(record).filter(
      ([k, v]) => !k.startsWith("_") && (all || (v !== null && v !== "")),
    ),
  );
  return (
    <div className="space-y-4">
      {request ? (
        <>
          <FieldTable
            values={{
              hospital: request.payload.hospital,
              patient: request.payload.patient,
              encounter: request.payload.encounter,
              image_count: manifestCount(request.payload.evidence),
              transport: request.transport,
              remote: request.remote,
              validity: request.validity,
              recognized_category: request.response?.recognized_category,
              recognized_quantity: request.response?.recognized_quantity,
              simulated: request.response?.simulated,
            }}
          />
          {request.error && <p role="alert">{request.error}</p>}
          <Tabs defaultValue="response">
            <TabsList>
              <TabsTrigger value="payload">
                {t("business.resultEvidence.sent")}
              </TabsTrigger>
              <TabsTrigger value="response">
                {t("business.resultEvidence.received")}
              </TabsTrigger>
            </TabsList>
            <TabsContent value="payload">
              <FieldTable values={request.payload} />
            </TabsContent>
            <TabsContent value="response">
              {Object.keys(request.response ?? {}).length ? (
                <FieldTable values={request.response} />
              ) : (
                <p>{t("business.resultEvidence.noResponse")}</p>
              )}
            </TabsContent>
          </Tabs>
        </>
      ) : (
        <>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={all}
              onChange={(e) => setAll(e.target.checked)}
            />
            {t("business.resultEvidence.showEmpty")}
          </label>
          <FieldTable values={visible} />
        </>
      )}
      <details>
        <summary className="cursor-pointer text-sm">
          {t("business.layout.technical")}
        </summary>
        <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-all rounded bg-muted p-3 text-xs">
          {resultText(detail)}
        </pre>
      </details>
    </div>
  );
}
