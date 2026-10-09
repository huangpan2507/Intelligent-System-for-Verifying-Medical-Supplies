import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  type Candidate,
  type Rule,
  usePrepareVerification,
  usePublishVerification,
  useSaveVerificationDraft,
} from "@/controllers/API/queries/verification";
import { CustomLink } from "@/customization/components/custom-link";
import type { ActionFeedback } from "./types";
export default function DraftRelease({
  selected,
  act,
  setNotice,
  setError,
  setReleaseId,
}: ActionFeedback & { selected: Rule; setReleaseId: (id: string) => void }) {
  const { t } = useTranslation();
  const code = selected.code;
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [mapping, setMapping] = useState(() =>
    selected.draft_config.catalog_mapping
      ? Object.entries(selected.draft_config.catalog_mapping).map(
          ([code, category]) => ({ code, category }),
        )
      : [
          { code: "DEMO-HIP", category: "hip_prosthesis" },
          { code: "DEMO-KNEE", category: "knee_prosthesis" },
        ],
  );
  const [note, setNote] = useState(selected.draft_config.note ?? "");
  const save = useSaveVerificationDraft();
  const prepare = usePrepareVerification();
  const publish = usePublishVerification();
  const busy = prepare.isPending || publish.isPending || save.isPending;
  const draft = () => ({
    code,
    note,
    catalog_mapping: Object.fromEntries(
      mapping.map((r) => [r.code.trim(), r.category]),
    ),
  });
  return (
    <section className="space-y-4 rounded-lg border p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p>
          {selected.active_version
            ? t("verification.activeVersion", {
                version: selected.active_version,
              })
            : t("verification.inactive")}
        </p>
        <Button variant="outline" asChild>
          <CustomLink to={`/flow/${selected.flow_id}`}>
            {t("verification.editDraft")}
          </CustomLink>
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        {t("verification.lifecycle")}
      </p>
      <h3 className="font-medium">{t("verification.catalog")}</h3>
      <p className="text-sm text-muted-foreground">
        {t("verification.catalogHint")}
      </p>
      {mapping.map((row, index) => (
        <div key={index} className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
          <Input
            aria-label={t("verification.catalogCode", {
              index: index + 1,
            })}
            value={row.code}
            onChange={(e) => {
              setMapping(
                mapping.map((r, i) =>
                  i === index ? { ...r, code: e.target.value } : r,
                ),
              );
              setCandidate(null);
            }}
          />
          <select
            aria-label={t("verification.category", {
              index: index + 1,
            })}
            className="h-10 rounded border bg-background px-3"
            value={row.category}
            onChange={(e) => {
              setMapping(
                mapping.map((r, i) =>
                  i === index ? { ...r, category: e.target.value } : r,
                ),
              );
              setCandidate(null);
            }}
          >
            <option value="hip_prosthesis">{t("verification.hip")}</option>
            <option value="knee_prosthesis">{t("verification.knee")}</option>
          </select>
          <Button
            variant="outline"
            disabled={mapping.length === 1}
            onClick={() => {
              setMapping(mapping.filter((_, i) => i !== index));
              setCandidate(null);
            }}
          >
            {t("verification.remove")}
          </Button>
        </div>
      ))}
      <Button
        variant="outline"
        onClick={() => {
          setMapping([...mapping, { code: "", category: "hip_prosthesis" }]);
          setCandidate(null);
        }}
      >
        {t("verification.addMapping")}
      </Button>
      <label className="block space-y-1 text-sm">
        {t("verification.note")}
        <Textarea
          value={note}
          onChange={(e) => {
            setNote(e.target.value);
            setCandidate(null);
          }}
        />
      </label>
      <div className="flex flex-wrap gap-3">
        <Button
          variant="outline"
          disabled={
            busy ||
            mapping.some((r) => !r.code.trim()) ||
            new Set(mapping.map((r) => r.code.trim())).size !== mapping.length
          }
          onClick={() =>
            void act(async () => {
              await save.mutateAsync({
                ...draft(),
                expected_revision: selected.draft_revision,
              });
              setNotice(t("verification.draftSaved"));
            })
          }
        >
          {t("verification.saveDraft")}
        </Button>

        <Button
          variant="outline"
          disabled={busy}
          onClick={() =>
            void act(async () => {
              if (
                mapping.some((r) => !r.code.trim()) ||
                new Set(mapping.map((r) => r.code.trim())).size !==
                  mapping.length
              ) {
                setError(t("verification.invalidMapping"));
                return;
              }
              setCandidate(null);
              setCandidate(
                await prepare.mutateAsync({
                  code,
                  note,
                  catalog_mapping: Object.fromEntries(
                    mapping.map((r) => [r.code.trim(), r.category]),
                  ),
                }),
              );
              setNotice(t("verification.checked"));
            })
          }
        >
          {t("verification.check")}
        </Button>
        <Button
          disabled={busy || !candidate}
          onClick={() =>
            void act(async () => {
              if (!candidate) return;
              const release = await publish.mutateAsync({
                code,
                candidate_id: candidate.id,
                content_hash: candidate.content_hash,
              });
              setReleaseId(release.id);
              setCandidate(null);
              setNotice(
                t("verification.published", {
                  version: release.version,
                }),
              );
            })
          }
        >
          {t("verification.publish")}
        </Button>
      </div>
    </section>
  );
}
