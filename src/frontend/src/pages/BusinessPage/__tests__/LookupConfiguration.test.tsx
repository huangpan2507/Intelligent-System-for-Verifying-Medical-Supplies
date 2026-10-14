import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import type { JsonSchema } from "@/controllers/API/queries/business";
import LookupConfiguration from "../LookupConfiguration";
import { type LookupConfig, managedLookup } from "../lookup-config";
import definition from "./lookup-schema.json";

const base: LookupConfig = {
  connection: "mysql",
  schema: "business_demo",
  table: "studies",
  keys: [{ left: "RPT_NO", right: "rpt_no" }],
  returns: [
    {
      field: "chk_dt",
      output: "checked_at",
      type: "datetime",
      timezone: "Asia/Shanghai",
    },
  ],
  source_identity: { keys: ["ris_study_id"] },
  source_required: ["chk_dt"],
  checks: {
    required: ["checked_at"],
    conditions: [{ field: "checked_at", op: "lt", right_field: "UPDATE_TIME" }],
  },
};
const options = {
  connections: [
    { id: "mysql", name: "Local MySQL", kind: "mysql", config: {} },
  ],
  databaseSchemas: ["business_demo", "other"],
  tables: ["studies", "other_studies"],
  fields: {
    data: ["RPT_NO", "UPDATE_TIME"].map((name) => ({ name, type: "text" })),
    database: ["rpt_no", "ris_study_id", "chk_dt"].map((name) => ({
      name,
      type: "text",
    })),
    result: ["RPT_NO", "UPDATE_TIME", "checked_at"].map((name) => ({
      name,
      type: "text",
    })),
  },
};
function Harness({ initial = base }: { initial?: LookupConfig }) {
  const [config, setConfig] = useState(initial);
  return (
    <>
      <LookupConfiguration
        nodeId="Lookup-A"
        value={config}
        onChange={setConfig}
        schema={definition as JsonSchema}
        options={options}
        upstream="Classification.Data"
      />
      <output data-testid="saved">{JSON.stringify(config)}</output>
    </>
  );
}
const saved = () => JSON.parse(screen.getByTestId("saved").textContent!);

test("manages identity once and preserves mappings through unrelated edits and reload", () => {
  const view = render(<Harness />);
  fireEvent.click(screen.getByText("Fields to bring back"));
  expect(saved().source_identity).toEqual({
    keys: ["ris_study_id"],
    name: "source",
    namespace: "lookup:Lookup-A",
  });
  expect(
    screen.queryByRole("textbox", { name: "Namespace" }),
  ).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole("textbox", { name: "Output" }), {
    target: { value: "exam_time" },
  });
  const persisted = saved();
  expect(persisted.returns[0]).toEqual({
    ...base.returns![0],
    output: "exam_time",
  });
  expect(managedLookup(persisted, "A-renamed-node").source_identity).toEqual(
    persisted.source_identity,
  );
  view.unmount();
  render(<Harness initial={persisted} />);
  expect(saved()).toEqual(persisted);
});

test("retains an existing template identity and separates upstream, remote and result choices", () => {
  render(
    <Harness
      initial={{
        ...base,
        source_identity: {
          ...base.source_identity!,
          name: "study",
          namespace: "core-study-v2",
        },
      }}
    />,
  );
  expect(saved().source_identity.namespace).toBe("core-study-v2");
  expect(
    within(screen.getByRole("combobox", { name: "Left" })).queryByRole(
      "option",
      { name: /rpt_no/ },
    ),
  ).not.toBeInTheDocument();
  expect(
    within(screen.getByRole("combobox", { name: "Right" })).queryByRole(
      "option",
      { name: /RPT_NO/ },
    ),
  ).not.toBeInTheDocument();
  expect(screen.getAllByTestId(/^lookup-section-/)).toHaveLength(6);
  expect(screen.queryAllByRole("alert")).toHaveLength(0);
});

test("keeps source changes pending across reload, even when column names still match", () => {
  const view = render(<Harness />);
  fireEvent.change(screen.getByRole("combobox", { name: "Table" }), {
    target: { value: "other_studies" },
  });
  expect(screen.getByRole("alert")).toHaveTextContent(
    "database source changed",
  );
  const pending = saved();
  expect(pending.keys).toEqual(base.keys);
  expect(pending.binding_source.table).toBe("studies");
  view.unmount();
  render(<Harness initial={pending} />);
  expect(screen.getByRole("alert")).toHaveTextContent(
    "database source changed",
  );
  fireEvent.click(
    screen.getByRole("button", {
      name: /I have reviewed these source bindings/i,
    }),
  );
  expect(saved().binding_source.table).toBe("other_studies");
  expect(screen.queryAllByRole("alert")).toHaveLength(0);
});

test("collapsed quality section still signals stale fields and retains their saved references", () => {
  render(<Harness initial={{ ...base, source_required: ["removed_field"] }} />);
  const section = screen.getByTestId("lookup-section-quality");
  fireEvent.click(within(section).getByText("Source record quality"));
  expect(within(section).getByRole("alert")).toHaveTextContent(
    "1 item needs attention",
  );
  expect(saved().source_required).toEqual(["removed_field"]);
});

test("changing identity fields uses real source choices and keeps the system identifiers", () => {
  render(<Harness />);
  const identity = saved().source_identity;
  fireEvent.click(screen.getByText("Source record quality"));
  const group = screen.getByRole("group", {
    name: "Fields identifying one source record",
  });
  fireEvent.click(within(group).getByText("Select fields"));
  fireEvent.click(within(group).getByRole("checkbox", { name: /rpt_no/ }));
  expect(saved().source_identity).toEqual({
    ...identity,
    keys: ["ris_study_id", "rpt_no"],
  });
  fireEvent.change(within(group).getByRole("textbox"), {
    target: { value: "chk_dt" },
  });
  expect(within(group).getByRole("checkbox", { name: /rpt_no/ })).toBeChecked();
  expect(
    within(group).queryByRole("checkbox", { name: /RPT_NO/ }),
  ).not.toBeInTheDocument();
});
