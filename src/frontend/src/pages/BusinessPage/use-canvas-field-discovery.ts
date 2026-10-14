import { useEffect, useMemo, useRef, useState } from "react";
import {
  type Field,
  type Inspection,
  type SourcePreview,
  useInspectBusiness,
} from "@/controllers/API/queries/business";
import type useFlowStore from "@/stores/flowStore";
import { businessError } from "./errors";

type CanvasState = ReturnType<typeof useFlowStore.getState>;
export const previewKey = (config: Record<string, unknown>) =>
  JSON.stringify(
    Object.fromEntries(
      Object.entries(config).filter(
        ([key]) => !["fields", "field_evidence"].includes(key),
      ),
    ),
  );

export function useCanvasFieldDiscovery(
  nodes: CanvasState["nodes"],
  edges: CanvasState["edges"],
  business: boolean,
  selectedId?: string,
) {
  const inspect = useInspectBusiness();
  const [result, setResult] = useState<{
    version: string;
    inspection: Inspection;
  }>();
  const [error, setError] = useState("");
  const [previews, setPreviews] = useState<
    Record<string, { key: string; result: SourcePreview }>
  >({});
  const serialized = useMemo(
    () =>
      JSON.stringify({
        nodes: nodes.map((node) => ({
          id: node.id,
          data: node.data,
          position: node.position,
        })),
        edges,
      }),
    [nodes, edges],
  );
  const latest = useRef(serialized);
  latest.current = serialized;
  useEffect(() => {
    if (!business) return;
    let active = true;
    const timer = setTimeout(
      () =>
        inspect.mutate(
          { canvas: JSON.parse(serialized) },
          {
            onSuccess: (inspection) => {
              if (!active || latest.current !== serialized) return;
              setResult({ version: serialized, inspection });
              setError("");
            },
            onError: (failure) => {
              if (active && latest.current === serialized)
                setError(businessError(failure));
            },
          },
        ),
      700,
    );
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [serialized, business]);
  const inspection =
    result?.version === serialized ? result.inspection : undefined;
  const fields: Record<string, Field[]> = {};
  const upstreamRows: { label: string; row: Record<string, unknown> }[] = [];
  for (const edge of edges.filter((edge) => edge.target === selectedId)) {
    const port = edge.data?.sourceHandle?.name ?? "data";
    const input = (edge.data?.targetHandle?.fieldName ?? "input_data").replace(
      "input_",
      "",
    );
    const node = nodes.find((node) => node.id === edge.source);
    const source = String(node?.data.node?.display_name ?? edge.source);
    const incoming = (inspection?.schemas[edge.source]?.[port] ?? []).map(
      (field) => ({ ...field, source }),
    );
    fields[input] = [...(fields[input] ?? []), ...incoming].filter(
      (field, index, all) =>
        all.findIndex((candidate) => candidate.name === field.name) === index,
    );
    const saved = previews[edge.source];
    if (!node || !saved || port !== "data") continue;
    try {
      if (
        saved.key !==
        previewKey(
          JSON.parse(node.data.node?.template.configuration?.value ?? "{}"),
        )
      )
        continue;
    } catch {
      continue;
    }
    upstreamRows.push(
      ...saved.result.rows.map((row, index) => ({
        label: `${source} · ${index + 1}`,
        row,
      })),
    );
  }
  const savePreview = (
    config: Record<string, unknown>,
    preview: SourcePreview,
  ) => {
    if (selectedId)
      setPreviews((old) => ({
        ...old,
        [selectedId]: { key: previewKey(config), result: preview },
      }));
  };
  return { inspection, error, fields, upstreamRows, savePreview };
}
