import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  type Connection,
  useBusinessMutation,
  useBusinessQuery,
} from "@/controllers/API/queries/business";
import DatabasePreview from "./DatabasePreview";
import { businessError } from "./errors";

export default function Connections() {
  const { t } = useTranslation();
  const query = useBusinessQuery<Connection[]>("connections");
  const mutation = useBusinessMutation();
  const [kind, setKind] = useState("postgresql");
  const [name, setName] = useState("");
  const [config, setConfig] = useState<Record<string, string>>({});
  const [secret, setSecret] = useState("");
  const [notice, setNotice] = useState("");
  const database = ["postgresql", "mysql"].includes(kind);
  return (
    <div className="space-y-6">
      <p className="text-muted-foreground">{t("business.connectionHint")}</p>
      <form
        className="grid gap-4 rounded-lg border p-5 md:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate(
            { path: "connections", body: { name, kind, config, secret } },
            {
              onSuccess: () => {
                setSecret("");
                setNotice(t("business.saved"));
              },
              onError: (e) => setNotice(businessError(e)),
            },
          );
        }}
      >
        <label>
          {t("business.field.name")}
          <Input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          {t("business.field.type")}
          <select
            className="h-10 w-full rounded border bg-background px-2"
            value={kind}
            onChange={(e) => {
              setKind(e.target.value);
              setConfig({});
            }}
          >
            {["postgresql", "mysql", "api", "model"].map((k) => (
              <option key={k} value={k}>
                {t(`business.value.${k}`, { defaultValue: k })}
              </option>
            ))}
          </select>
        </label>
        {[
          ...(database
            ? (["host", "port", "database", "username"] as const)
            : (["base_url", "auth_header", "auth_prefix"] as const)),
        ].map((key) => (
          <label key={key}>
            {t(`business.field.${key}`)}
            <Input
              required={!["port", "auth_header", "auth_prefix"].includes(key)}
              value={config[key] ?? ""}
              onChange={(e) => setConfig({ ...config, [key]: e.target.value })}
            />
          </label>
        ))}
        <label>
          {t("business.field.secret")}
          <Input
            type="password"
            autoComplete="new-password"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
          />
        </label>
        <div className="self-end">
          <Button disabled={mutation.isPending} type="submit">
            {t("business.saveConnection")}
          </Button>
        </div>
      </form>
      {notice && <p role="status">{notice}</p>}
      {query.error && <p role="alert">{String(query.error.message)}</p>}
      <div className="space-y-3">
        {query.data?.map((c) => (
          <div key={c.id} className="rounded border p-4">
            <p className="font-medium">
              {c.name}{" "}
              <span className="ml-2 text-sm text-muted-foreground">
                {c.kind}
              </span>
            </p>
            <p className="text-sm text-muted-foreground">
              {c.config.host ?? c.config.base_url} {c.config.database}
            </p>
            <ConnectionTables connection={c} />
          </div>
        ))}
      </div>
    </div>
  );
}
function ConnectionTables({ connection }: { connection: Connection }) {
  const { t } = useTranslation();
  const [inspect, setInspect] = useState(false);
  const [table, setTable] = useState("");
  const query = useBusinessQuery<{ tables: string[] }>(
    `connections/${connection.id}/schema`,
    inspect,
  );
  if (!["mysql", "postgresql"].includes(connection.kind)) return null;
  return (
    <div className="mt-2">
      <Button variant="outline" size="sm" onClick={() => setInspect(true)}>
        {t("business.inspectConnection")}
      </Button>
      {query.data && (
        <label className="block my-3">
          {t("business.field.table")}
          <select
            className="w-full rounded border bg-background p-2"
            value={table}
            onChange={(e) => setTable(e.target.value)}
          >
            <option value="">{t("business.choose")}</option>
            {query.data.tables.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
      )}
      {table && (
        <DatabasePreview
          key={table}
          connection={connection.id}
          config={{ table }}
        />
      )}
      {query.error && <p role="alert">{t("business.connectionFailed")}</p>}
    </div>
  );
}
