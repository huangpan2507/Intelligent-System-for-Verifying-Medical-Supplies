import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  type Rule,
  useActivateVerification,
  useVerificationReleases,
} from "@/controllers/API/queries/verification";
import type { ActionFeedback } from "./types";
export default function ReleaseHistory({
  selected,
  act,
  setNotice,
  setReleaseId,
}: ActionFeedback & { selected: Rule; setReleaseId: (id: string) => void }) {
  const { t, i18n } = useTranslation();
  const code = selected.code;
  const releases = useVerificationReleases({ code });
  const activate = useActivateVerification();
  const busy = activate.isPending;
  return (
    <>
      {" "}
      {releases.error && <p role="alert">{t("verification.loadError")}</p>}
      <section className="space-y-3 rounded-lg border p-5">
        <h3 className="font-semibold">{t("verification.history")}</h3>
        {!releases.data?.length && <p>{t("verification.noReleases")}</p>}
        {releases.data?.map((r) => (
          <article
            key={r.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded border p-3"
          >
            <div>
              <p className="font-medium">
                {t("verification.version", { version: r.version })} ·{" "}
                {t(
                  r.simulated
                    ? "verification.simulation"
                    : "verification.production",
                )}
              </p>
              <p className="text-sm text-muted-foreground">
                {new Intl.DateTimeFormat(i18n.language, {
                  dateStyle: "medium",
                  timeStyle: "short",
                }).format(new Date(r.created_at))}
              </p>
              <p className="text-sm">{r.note}</p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setReleaseId(r.id)}>
                {t("verification.view")}
              </Button>
              <Button
                disabled={busy || r.id === selected.active_release_id}
                onClick={() =>
                  void act(async () => {
                    await activate.mutateAsync({
                      code,
                      release_id: r.id,
                      expected_revision: selected.revision,
                    });
                    setNotice(
                      t("verification.enabled", { version: r.version }),
                    );
                  })
                }
              >
                {t(
                  r.id === selected.active_release_id
                    ? "verification.active"
                    : "verification.activate",
                )}
              </Button>
            </div>
          </article>
        ))}
        <Button
          variant="outline"
          disabled={busy || !selected.active_release_id}
          onClick={() =>
            void act(async () => {
              await activate.mutateAsync({
                code,
                release_id: null,
                expected_revision: selected.revision,
              });
              setNotice(t("verification.disabled"));
            })
          }
        >
          {t("verification.deactivate")}
        </Button>
      </section>
    </>
  );
}
