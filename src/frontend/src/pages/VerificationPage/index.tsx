import axios from "axios";
import { useContext, useState } from "react";
import { useTranslation } from "react-i18next";
import PageLayout from "@/components/common/pageLayout";
import { Button } from "@/components/ui/button";
import { AuthContext } from "@/contexts/authContext";
import {
  useVerificationRelease,
  useVerificationRules,
} from "@/controllers/API/queries/verification";
import { CustomLink } from "@/customization/components/custom-link";
import DraftRelease from "./DraftRelease";
import RegisterRule from "./RegisterRule";
import ReleaseHistory from "./ReleaseHistory";
import ReleasePreview from "./ReleasePreview";

export default function VerificationPage() {
  const { t } = useTranslation();
  const { userData } = useContext(AuthContext);
  const isAdmin = !!userData?.is_superuser;
  const rules = useVerificationRules({ enabled: isAdmin });
  const [selection, setSelection] = useState("");
  const selected =
    rules.data?.find((r) => r.code === selection) ?? rules.data?.[0];
  const [releaseId, setReleaseId] = useState("");
  const preview = useVerificationRelease({
    code: selected?.code ?? "",
    id: releaseId,
  });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  async function act(action: () => Promise<void>) {
    setError("");
    setNotice("");
    try {
      await action();
    } catch (error) {
      const detail = axios.isAxiosError(error)
        ? error.response?.data?.detail
        : null;
      setError(typeof detail === "string" ? detail : t("verification.error"));
    }
  }
  const feedback = { act, setError, setNotice };
  const selectRule = (code: string) => {
    setSelection(code);
    setReleaseId("");
    setNotice("");
  };
  return (
    <PageLayout
      title={t("verification.title")}
      description={t("verification.description")}
      button={
        <Button variant="outline" asChild>
          <CustomLink to="/verification/tasks">
            {t("verificationTasks.title")}
          </CustomLink>
        </Button>
      }
    >
      <main className="w-full space-y-6">
        {!isAdmin ? (
          <p role="alert">{t("verification.adminOnly")}</p>
        ) : (
          <>
            {(error || rules.error || preview.error) && (
              <div
                role="alert"
                className="rounded border border-destructive p-3 text-destructive"
              >
                {error || t("verification.loadError")}
              </div>
            )}
            {notice && (
              <p role="status" className="rounded border p-3">
                {notice}
              </p>
            )}
            <RegisterRule {...feedback} onCreated={selectRule} />
            <label htmlFor="verification-rule" className="block font-semibold">
              {t("verification.rule")}
            </label>
            <select
              id="verification-rule"
              className="h-10 w-full rounded border bg-background px-3"
              value={selected?.code ?? ""}
              onChange={(e) => selectRule(e.target.value)}
            >
              {!rules.data?.length && (
                <option value="">{t("verification.noRules")}</option>
              )}
              {rules.data?.map((r) => (
                <option key={r.code} value={r.code}>
                  {r.name}
                </option>
              ))}
            </select>
            {selected && (
              <>
                <DraftRelease
                  key={selected.code}
                  selected={selected}
                  {...feedback}
                  setReleaseId={setReleaseId}
                />
                <ReleaseHistory
                  selected={selected}
                  {...feedback}
                  setReleaseId={setReleaseId}
                />
              </>
            )}
            {preview.data && (
              <ReleasePreview key={preview.data.id} release={preview.data} />
            )}
          </>
        )}
      </main>
    </PageLayout>
  );
}
