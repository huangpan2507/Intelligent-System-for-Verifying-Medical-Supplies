import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { UnitResult } from "@/controllers/API/queries/verification/tasks";
import { JsonDetails, useResultFormat } from "./shared";

export default function ResultsTable({ results }: { results: UnitResult[] }) {
  const { t } = useTranslation();
  const format = useResultFormat();
  return (
    <div className="overflow-x-auto rounded-lg border">
      <Table aria-label={t("verificationTasks.resultDetails")}>
        <TableHeader>
          <TableRow>
            {[
              "category",
              "conclusion",
              "typeComparison",
              "quantityComparison",
              "feeComparison",
              "basis",
            ].map((key) => (
              <TableHead key={key}>{t(`verificationTasks.${key}`)}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {results.map((row) => {
            const reasons = [
              ...new Set([
                ...(row.reasons ?? []),
                ...(row.type?.reasons ?? []),
                ...(row.quantity?.reasons ?? []),
                ...(row.fee?.reasons ?? []),
              ]),
            ];
            return (
              <TableRow key={row.scope_id ?? row.detail_ids.join(",")}>
                <TableCell className="min-w-36 align-top font-medium">
                  {row.category
                    ? t(`verificationTasks.category.${row.category}`, {
                        defaultValue: row.category,
                      })
                    : t("verificationTasks.unknownCategory")}
                  <p className="mt-1 text-xs font-normal text-muted-foreground">
                    {t("verificationTasks.detailCount", {
                      count: row.detail_ids.length,
                    })}
                  </p>
                </TableCell>
                <TableCell className="align-top">
                  <Badge
                    variant={
                      row.conclusion === "difference"
                        ? "destructive"
                        : "secondary"
                    }
                  >
                    {t(`verificationTasks.conclusion.${row.conclusion}`, {
                      defaultValue: row.conclusion,
                    })}
                  </Badge>
                </TableCell>
                <TableCell className="align-top">
                  {t(
                    `verificationTasks.comparison.${row.type?.status ?? "not_compared"}`,
                    { defaultValue: row.type?.status },
                  )}
                </TableCell>
                <TableCell className="min-w-44 align-top">
                  <p>
                    {t(
                      `verificationTasks.comparison.${row.quantity?.status ?? "not_compared"}`,
                      { defaultValue: row.quantity?.status },
                    )}
                  </p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {t("verificationTasks.comparisonValues", {
                      source: format.number(row.quantity?.settlement),
                      recognized: format.number(row.quantity?.recognized),
                      delta: format.number(row.quantity?.delta),
                    })}
                  </p>
                  {row.quantity?.unit && (
                    <p className="text-xs text-muted-foreground">
                      {t("verificationTasks.unit", {
                        unit:
                          row.quantity.unit === "set"
                            ? t("verificationTasks.set")
                            : row.quantity.unit,
                      })}
                    </p>
                  )}
                </TableCell>
                <TableCell className="min-w-48 align-top">
                  <p>
                    {t(
                      `verificationTasks.comparison.${row.fee?.status ?? "not_compared"}`,
                      { defaultValue: row.fee?.status },
                    )}
                  </p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {t("verificationTasks.feeValues", {
                      source: format.number(row.fee?.source_amount),
                      converted: format.number(row.fee?.converted_amount),
                      delta: format.number(row.fee?.delta),
                    })}
                  </p>
                  {row.fee?.currency && (
                    <p className="text-xs text-muted-foreground">
                      {row.fee.currency}
                    </p>
                  )}
                </TableCell>
                <TableCell className="min-w-48 align-top">
                  <details>
                    <summary className="cursor-pointer text-primary">
                      {t("verificationTasks.inspectBasis")}
                    </summary>
                    <dl className="mt-3 space-y-2 break-all text-xs">
                      <div>
                        <dt className="font-medium">
                          {t("verificationTasks.settlementDetails")}
                        </dt>
                        <dd>{row.detail_ids.join(", ")}</dd>
                      </div>
                      <div>
                        <dt className="font-medium">
                          {t("verificationTasks.reviewEvidence")}
                        </dt>
                        <dd>
                          {row.review_evidence ??
                            t("verificationTasks.unavailable")}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-medium">
                          {t("verificationTasks.requestId")}
                        </dt>
                        <dd>
                          {row.request_id ?? t("verificationTasks.unavailable")}
                        </dd>
                      </div>
                    </dl>
                    {reasons.length > 0 && (
                      <ul className="mt-3 list-inside list-disc text-sm">
                        {reasons.map((reason) => (
                          <li key={reason}>
                            {t(`verificationTasks.reason.${reason}`, {
                              defaultValue: reason,
                            })}
                          </li>
                        ))}
                      </ul>
                    )}
                    <JsonDetails value={row} />
                  </details>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
