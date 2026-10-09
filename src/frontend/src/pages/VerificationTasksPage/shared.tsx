import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  return (
    <Badge
      variant={
        status === "failed" ||
        status === "partial_failed" ||
        status === "needs_confirmation"
          ? "destructive"
          : "secondary"
      }
    >
      {t(`verificationTasks.status.${status}`, { defaultValue: status })}
    </Badge>
  );
}

export function Pagination({
  offset,
  limit,
  total,
  hasNext,
  busy,
  onChange,
}: {
  offset: number;
  limit: number;
  total?: number;
  hasNext?: boolean;
  busy?: boolean;
  onChange: (offset: number) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 pt-3">
      <p className="text-sm text-muted-foreground">
        {total === undefined
          ? t("verificationTasks.page", {
              page: Math.floor(offset / limit) + 1,
            })
          : t("verificationTasks.pagination", {
              page: Math.floor(offset / limit) + 1,
              total,
            })}
      </p>
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={busy || offset === 0}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          {t("verificationTasks.previous")}
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={busy || !(hasNext ?? offset + limit < (total ?? 0))}
          onClick={() => onChange(offset + limit)}
        >
          {t("verificationTasks.next")}
        </Button>
      </div>
    </div>
  );
}

export function QueryError({ retry }: { retry: () => void }) {
  const { t } = useTranslation();
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center gap-3 rounded-lg border border-destructive p-4 text-destructive"
    >
      <p>{t("verificationTasks.loadError")}</p>
      <Button variant="outline" onClick={retry}>
        {t("verificationTasks.refresh")}
      </Button>
    </div>
  );
}

export function JsonDetails({ value }: { value: unknown }) {
  const { t } = useTranslation();
  return (
    <details className="mt-2">
      <summary className="cursor-pointer text-sm text-muted-foreground">
        {t("verificationTasks.rawData")}
      </summary>
      <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-all rounded bg-muted p-3 text-xs">
        {JSON.stringify(value, null, 2)}
      </pre>
    </details>
  );
}

export function useResultFormat() {
  const { t, i18n } = useTranslation();
  return {
    date: (value: string | null | undefined) =>
      value
        ? new Intl.DateTimeFormat(i18n.language, {
            dateStyle: "medium",
            timeStyle: "medium",
          }).format(new Date(value))
        : t("verificationTasks.unavailable"),
    number: (value: string | number | null | undefined) =>
      value === undefined || value === null
        ? t("verificationTasks.unavailable")
        : new Intl.NumberFormat(i18n.language, {
            maximumFractionDigits: 6,
          }).format(Number(value)),
    stage: (value: string | null) =>
      value
        ? t(`verificationTasks.stage.${value}`, { defaultValue: value })
        : t("verificationTasks.notStarted"),
  };
}
