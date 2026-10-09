import { Background, Controls, ReactFlow } from "@xyflow/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ReleaseDetail } from "@/controllers/API/queries/verification";

export default function ReleasePreview({
  release,
}: {
  release: ReleaseDetail;
}) {
  const { t } = useTranslation();
  const graph = release.package.graph;
  const [selected, setSelected] = useState("");
  const node = graph.nodes.find((n) => n.id === selected) ?? graph.nodes[0];
  return (
    <section
      className="space-y-4 rounded-lg border p-4"
      aria-label={t("verification.readonly")}
    >
      <h3 className="font-semibold">
        {t("verification.readonlyVersion", { version: release.version })}
      </h3>
      <p className="text-sm text-muted-foreground">
        {t("verification.readonlyHint")}
      </p>
      <div className="h-72 rounded border">
        <ReactFlow
          fitView
          minZoom={0.1}
          nodesDraggable={false}
          nodesConnectable={false}
          edgesReconnectable={false}
          deleteKeyCode={null}
          nodes={graph.nodes.map((n) => ({
            id: n.id,
            position: n.position,
            data: { label: n.data.node.display_name },
          }))}
          edges={graph.edges.map((e) => ({
            id: e.id,
            source: e.source,
            target: e.target,
          }))}
          onNodeClick={(_, n) => setSelected(n.id)}
        >
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      <label className="block text-sm" htmlFor="release-node">
        {t("verification.nodeParameters")}
      </label>
      <select
        id="release-node"
        className="h-10 w-full rounded border bg-background px-3"
        value={node?.id ?? ""}
        onChange={(e) => setSelected(e.target.value)}
      >
        {graph.nodes.map((n) => (
          <option key={n.id} value={n.id}>
            {n.data.node.display_name}
          </option>
        ))}
      </select>
      <dl className="grid gap-3 text-sm md:grid-cols-2">
        {Object.entries(node?.data.node.template ?? {})
          .filter(
            ([key, field]) =>
              !["code", "_type", "context", "input_value"].includes(key) &&
              field.display_name,
          )
          .map(([key, field]) => (
            <div key={key} className="min-w-0 rounded bg-muted p-3">
              <dt className="font-medium">{field.display_name}</dt>
              <dd className="mt-1 whitespace-pre-wrap break-all">
                {typeof field.value === "string"
                  ? field.value
                  : JSON.stringify(field.value, null, 2)}
              </dd>
            </div>
          ))}
      </dl>
      <details>
        <summary className="cursor-pointer text-sm">
          {t("verification.traceability")}
        </summary>
        <dl className="mt-3 space-y-2 break-all text-xs">
          <dt>{t("verification.contentHash")}</dt>
          <dd>{release.content_hash}</dd>
          <dt>{t("verification.runtimeHash")}</dt>
          <dd>{release.runtime_digest}</dd>
        </dl>
      </details>
    </section>
  );
}
