import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  useBusinessMutation,
  useBusinessQuery,
} from "@/controllers/API/queries/business";
import { useTranslation } from "./business-i18n";
import { businessError } from "./errors";

export default function MaintenancePanel() {
  const { t } = useTranslation();
  const [error, setError] = useState("");
  const query = useBusinessQuery<{
    status: string;
    pending_tasks: string[];
    safe_to_upgrade: boolean;
  }>("maintenance", true, true);
  const mutation = useBusinessMutation();
  const state = query.data;
  const act = (action: string) =>
    mutation.mutate(
      { path: "maintenance", body: { action } },
      {
        onSuccess: () => setError(""),
        onError: (e) => setError(businessError(e)),
      },
    );
  return (
    <section className="space-y-2 rounded border p-4">
      <h2 className="font-semibold">{t("business.maintenanceTitle")}</h2>
      <p className="text-sm">{t("business.maintenanceHint")}</p>
      {state && (
        <>
          <p>
            {t(
              state.status === "open"
                ? "business.intakeOpen"
                : "business.intakeClosed",
            )}{" "}
            ·{" "}
            {t("business.pendingTasks", { count: state.pending_tasks.length })}
          </p>
          {state.safe_to_upgrade && <p>{t("business.drained")}</p>}
          <Button
            variant="outline"
            disabled={
              mutation.isPending ||
              (state.status !== "open" && state.pending_tasks.length > 0)
            }
            onClick={() => act(state.status === "open" ? "close" : "open")}
          >
            {t(
              state.status === "open"
                ? "business.closeIntake"
                : "business.openIntake",
            )}
          </Button>
        </>
      )}
      {(error || query.error) && (
        <p role="alert">{error || query.error?.message}</p>
      )}
    </section>
  );
}
