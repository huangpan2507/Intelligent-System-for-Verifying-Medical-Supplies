import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  useVerificationRelease,
  useVerificationReleases,
  useVerificationRules,
} from "@/controllers/API/queries/verification";
import ReleasePreview from "@/pages/VerificationPage/ReleasePreview";

export default function History() {
  const { t } = useTranslation();
  const rules = useVerificationRules();
  const [code, setCode] = useState("");
  const selected = code || rules.data?.[0]?.code || "";
  const versions = useVerificationReleases({ code: selected });
  const [releaseId, setReleaseId] = useState("");
  const release = useVerificationRelease({ code: selected, id: releaseId });
  return (
    <section className="space-y-4">
      <p>{t("business.historyHint")}</p>
      <label className="block">
        {t("verification.rule")}
        <select
          className="block w-full rounded border bg-background p-2"
          value={selected}
          onChange={(e) => {
            setCode(e.target.value);
            setReleaseId("");
          }}
        >
          {rules.data?.map((r) => (
            <option key={r.code} value={r.code}>
              {r.name} ({r.code})
            </option>
          ))}
        </select>
      </label>
      {[rules.error, versions.error, release.error]
        .filter(Boolean)
        .map((e, i) => (
          <p role="alert" key={i}>
            {String(e?.message)}
          </p>
        ))}
      {versions.data?.map((v) => (
        <div
          className="flex items-center justify-between rounded border p-3"
          key={v.id}
        >
          <span>
            {t("business.version", { version: v.version })} · {v.note}
          </span>
          <Button variant="outline" onClick={() => setReleaseId(v.id)}>
            {t("verification.readonly")}
          </Button>
        </div>
      ))}
      {release.data && <ReleasePreview release={release.data} />}
    </section>
  );
}
