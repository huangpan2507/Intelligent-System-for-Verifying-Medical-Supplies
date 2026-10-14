import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  type ExternalRequest,
  useBusinessQuery,
} from "@/controllers/API/queries/business";

export default function RequestLog({ taskId }: { taskId: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const query = useBusinessQuery<{ total: number; items: ExternalRequest[] }>(
    `tasks/${taskId}/requests?limit=20&offset=${offset}`,
    open,
    open,
  );
  return (
    <details onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>{t("business.requestLog")}</summary>
      <p className="my-2 text-sm text-muted-foreground">
        {t("business.requestUnknownHint")}
      </p>
      {query.error && <p role="alert">{query.error.message}</p>}
      {query.data?.items.map((request) => (
        <details key={request.id} className="my-2 rounded border p-3">
          <summary>
            {request.node_id} · {request.id} ·{" "}
            {t(`business.requestState.${request.remote}`, {
              defaultValue: request.remote,
            })}
          </summary>
          <p>
            {t("business.requestStates", {
              transport: request.transport,
              remote: request.remote,
              validity: request.validity,
            })}
          </p>
          <p className="text-xs">
            {request.input_dataset_id} · {request.input_row_id}
          </p>
          {request.error && <p>{request.error}</p>}
          <p className="font-medium">{t("business.requestPayload")}</p>
          <pre className="max-h-64 overflow-auto text-xs">
            {JSON.stringify(request.payload, null, 2)}
          </pre>
          <p className="font-medium">{t("business.requestResponse")}</p>
          <pre className="max-h-64 overflow-auto text-xs">
            {JSON.stringify(request.response, null, 2)}
          </pre>
        </details>
      ))}
      {query.data?.total === 0 && <p>{t("business.noRequests")}</p>}
      <div className="flex gap-2">
        <Button
          variant="outline"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 20))}
        >
          {t("business.previous")}
        </Button>
        <Button
          variant="outline"
          disabled={offset + 20 >= (query.data?.total ?? 0)}
          onClick={() => setOffset(offset + 20)}
        >
          {t("business.next")}
        </Button>
      </div>
    </details>
  );
}
