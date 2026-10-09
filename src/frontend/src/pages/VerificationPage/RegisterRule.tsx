import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useGetRefreshFlowsQuery } from "@/controllers/API/queries/flows/use-get-refresh-flows-query";
import { useCreateVerificationRule } from "@/controllers/API/queries/verification";
import type { ActionFeedback } from "./types";
export default function RegisterRule({
  act,
  setNotice,
  onCreated,
}: ActionFeedback & { onCreated: (code: string) => void }) {
  const { t } = useTranslation();
  const flows = useGetRefreshFlowsQuery({ get_all: true });
  const flowItems = Array.isArray(flows.data) ? flows.data : [];
  const create = useCreateVerificationRule();
  const busy = create.isPending;
  const [name, setName] = useState("");
  const [newCode, setNewCode] = useState("");
  const [flowId, setFlowId] = useState("");
  return (
    <>
      {flows.error && <p role="alert">{t("verification.loadError")}</p>}
      <section className="rounded-lg border p-5">
        <h3 className="mb-3 font-semibold">{t("verification.register")}</h3>
        <form
          className="grid gap-3 md:grid-cols-4"
          onSubmit={(e) => {
            e.preventDefault();
            void act(async () => {
              const rule = await create.mutateAsync({
                code: newCode,
                name,
                flow_id: flowId,
              });
              onCreated(rule.code);

              setNotice(t("verification.registered"));
            });
          }}
        >
          <label className="space-y-1 text-sm">
            {t("verification.name")}
            <Input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            {t("verification.code")}
            <Input
              required
              value={newCode}
              onChange={(e) => setNewCode(e.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            {t("verification.draft")}
            <select
              aria-label={t("verification.draft")}
              required
              className="h-10 w-full rounded border bg-background px-2"
              value={flowId}
              onChange={(e) => setFlowId(e.target.value)}
            >
              <option value="">{t("verification.chooseDraft")}</option>
              {flowItems.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
          </label>
          <Button type="submit" className="self-end" disabled={busy}>
            {t("verification.register")}
          </Button>
        </form>
      </section>
    </>
  );
}
