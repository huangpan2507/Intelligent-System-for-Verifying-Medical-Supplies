import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  type BusinessGraph,
  type Catalog,
  type Release,
  type Scheme,
  useBusinessMutation,
  useBusinessQuery,
} from "@/controllers/API/queries/business";
import { businessError } from "./errors";
import MaintenancePanel from "./MaintenancePanel";
import { SchemaForm } from "./SchemaForm";

export default function Schemes() {
  const { t } = useTranslation();
  const schemes = useBusinessQuery<Scheme[]>("schemes");
  const templates =
    useBusinessQuery<{ id: string; graph: BusinessGraph }[]>("templates");
  const catalog = useBusinessQuery<Catalog>("catalog");
  const mutation = useBusinessMutation<{ id: string }>();
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [template, setTemplate] = useState("compare");
  const [sources, setSources] = useState<string[]>([]);
  const [notice, setNotice] = useState("");
  return (
    <div className="space-y-6">
      <p className="text-muted-foreground">{t("business.schemeHint")}</p>
      <MaintenancePanel />
      <form
        className="space-y-4 rounded-lg border p-5"
        onSubmit={(e) => {
          e.preventDefault();
          const graph = templates.data?.find((x) => x.id === template)?.graph;
          if (!graph) return;
          mutation.mutate(
            {
              path: "schemes",
              body: { code, name, graph, allowed_sources: sources },
            },
            {
              onSuccess: () => {
                setName("");
                setCode("");
                setNotice(t("business.created"));
              },
              onError: (e) => setNotice(businessError(e)),
            },
          );
        }}
      >
        <div className="grid gap-4 md:grid-cols-3">
          <label>
            {t("business.field.name")}
            <Input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label>
            {t("business.field.code")}
            <Input
              required
              pattern="[A-Za-z][A-Za-z0-9_.-]*"
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          </label>
          <label>
            {t("business.template")}
            <select
              className="h-10 w-full rounded border bg-background px-2"
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
            >
              {templates.data?.map((item) => (
                <option key={item.id} value={item.id}>
                  {t(`business.template.${item.id}`, { defaultValue: item.id })}
                </option>
              ))}
            </select>
          </label>
        </div>
        <fieldset>
          <legend className="text-sm">{t("business.allowedSources")}</legend>
          <div className="mt-2 flex gap-4">
            {catalog.data?.sources.map((s) => (
              <label key={s} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={sources.includes(s)}
                  onChange={(e) =>
                    setSources(
                      e.target.checked
                        ? [...sources, s]
                        : sources.filter((v) => v !== s),
                    )
                  }
                />
                {s}
              </label>
            ))}
          </div>
        </fieldset>
        <Button disabled={mutation.isPending} type="submit">
          {t("business.createScheme")}
        </Button>
      </form>
      {notice && <p role="status">{notice}</p>}
      {schemes.error && <p role="alert">{String(schemes.error.message)}</p>}
      {schemes.data?.map((scheme) => (
        <SchemeCard key={scheme.code} scheme={scheme} />
      ))}
    </div>
  );
}
function SchemeCard({ scheme }: { scheme: Scheme }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const releases = useBusinessQuery<Release[]>(
    `schemes/${scheme.code}/releases`,
  );
  const mutation = useBusinessMutation<{ id: string }>();
  const [notice, setNotice] = useState("");
  const [parameters, setParameters] = useState<Record<string, unknown>>({});
  const [submitOpen, setSubmitOpen] = useState(false);
  const [externalTaskId, setExternalTaskId] = useState("");
  const active = releases.data?.find((r) => r.id === scheme.active_release_id);
  const action = (
    path: string,
    body: unknown,
    method: "PUT" | "POST" = "POST",
  ) =>
    mutation.mutate(
      { path, body, method },
      {
        onSuccess: () => setNotice(t("business.saved")),
        onError: (e) => setNotice(businessError(e)),
      },
    );
  return (
    <section className="space-y-4 rounded-lg border p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{scheme.name}</h2>
          <p className="text-sm text-muted-foreground">
            {scheme.code} ·{" "}
            {active
              ? t("business.activeVersion", { version: active.version })
              : t("business.inactive")}
          </p>
        </div>
        <Button asChild variant="outline">
          <Link to={`/flow/${scheme.flow_id}`}>{t("business.editCanvas")}</Link>
        </Button>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          disabled={mutation.isPending}
          onClick={() =>
            action(`schemes/${scheme.code}/releases`, {
              expected_revision: scheme.revision,
            })
          }
        >
          {t("business.publish")}
        </Button>
        <Button
          variant="outline"
          disabled={!active}
          onClick={() => {
            setSubmitOpen(!submitOpen);
            setExternalTaskId("");
            setParameters(
              Object.fromEntries(
                (active?.package.parameters ?? [])
                  .filter((p) => p.default !== undefined)
                  .map((p) => [p.name, p.default]),
              ),
            );
          }}
        >
          {t(
            active?.package.task_input
              ? "business.taskInput.testRequest"
              : "business.submitTask",
          )}
        </Button>
        {active && (
          <Button
            variant="outline"
            onClick={() =>
              action(
                `schemes/${scheme.code}/active`,
                { release_id: null, expected_revision: scheme.revision },
                "PUT",
              )
            }
          >
            {t("business.stopAccepting")}
          </Button>
        )}
      </div>
      {notice && (
        <p role="status" className="whitespace-pre-wrap break-words text-sm">
          {notice}
        </p>
      )}
      {submitOpen && active && (
        <div className="space-y-3 rounded border p-4">
          {active.package.task_input && (
            <>
              <p className="text-sm text-muted-foreground">
                {t("business.taskInput.testHint")}
              </p>
              <p>
                {t("business.taskInput.scheme")} · {scheme.code}
              </p>
              <label className="block space-y-1">
                <span>{t("business.taskInput.external_task_id")}</span>
                <Input
                  value={externalTaskId}
                  onChange={(e) => setExternalTaskId(e.target.value)}
                />
              </label>
            </>
          )}
          <SchemaForm
            schema={{
              type: "object",
              properties: Object.fromEntries(
                active.package.parameters.map((p) => [
                  p.name,
                  { type: p.type },
                ]),
              ),
              required: active.package.parameters
                .filter((p) => p.required)
                .map((p) => p.name),
            }}
            value={parameters}
            onChange={(value) =>
              setParameters(value as Record<string, unknown>)
            }
          />
          <Button
            disabled={mutation.isPending}
            onClick={() =>
              mutation.mutate(
                {
                  path: "tasks",
                  key: crypto.randomUUID(),
                  body: {
                    scheme: scheme.code,
                    parameters,
                    ...(active.package.task_input
                      ? { external_task_id: externalTaskId }
                      : {}),
                  },
                },
                {
                  onSuccess: (task) => navigate(`/business/tasks/${task.id}`),
                  onError: (e) => setNotice(businessError(e)),
                },
              )
            }
          >
            {t("business.run")}
          </Button>
        </div>
      )}
      {releases.data?.map((release) => (
        <div
          key={release.id}
          className="flex items-start justify-between gap-3 rounded border p-3"
        >
          <details className="min-w-0 flex-1">
            <summary className="cursor-pointer">
              {t("business.version", { version: release.version })}{" "}
              {release.note}
            </summary>
            <p className="my-2 text-sm text-muted-foreground">
              {t("business.immutableHint")}
            </p>
            <p className="font-medium">{t("business.releaseSummary")}</p>
            <pre className="max-h-80 overflow-auto text-xs">
              {JSON.stringify(release.package.summary ?? {}, null, 2)}
            </pre>
            <Button
              variant="outline"
              disabled={mutation.isPending}
              onClick={() =>
                action(`schemes/${scheme.code}/releases/from/${release.id}`, {
                  expected_revision: scheme.revision,
                })
              }
            >
              {t("business.republishVersion")}
            </Button>
            <pre className="max-h-80 overflow-auto text-xs">
              {JSON.stringify(
                {
                  parameters: release.package.parameters,
                  graph: release.package.graph,
                  schemas: release.package.schemas,
                  connections: release.package.connections,
                },
                null,
                2,
              )}
            </pre>
          </details>
          <Button
            size="sm"
            variant="outline"
            disabled={
              release.id === scheme.active_release_id || mutation.isPending
            }
            onClick={() =>
              action(
                `schemes/${scheme.code}/active`,
                { release_id: release.id, expected_revision: scheme.revision },
                "PUT",
              )
            }
          >
            {t(
              release.id === scheme.active_release_id
                ? "business.active"
                : "business.activate",
            )}
          </Button>
        </div>
      ))}
    </section>
  );
}
