import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import type { JsonSchema } from "@/controllers/API/queries/business";
import {
  managedValidation,
  type ValidateConfig,
} from "../configuration-layout";
import ValidateConfiguration from "../ValidateConfiguration";

const field = { type: "string", format: "field" };
const schema: JsonSchema = {
  type: "object",
  properties: {
    required: { type: "array", items: field },
    unique: { type: "array", items: field },
    identity: {
      type: "object",
      properties: {
        name: { type: "string" },
        namespace: { type: "string" },
        keys: { type: "array", items: field, minItems: 1 },
      },
      required: ["name", "namespace", "keys"],
    },
    conditions: { type: "array", items: { type: "object" } },
  },
};
let saved: ValidateConfig;
function Editor({
  initial = {},
  id = "Checks",
}: {
  initial?: ValidateConfig;
  id?: string;
}) {
  const [config, setConfig] = useState(initial);
  saved = config;
  return (
    <ValidateConfiguration
      value={config}
      onChange={setConfig}
      nodeId={id}
      schema={schema}
      options={{
        fields: {
          data: [
            { name: "hospital", type: "text" },
            { name: "detail", type: "text" },
          ],
        },
      }}
    />
  );
}
it("leaves identity optional and creates persistent identifiers when enabled", () => {
  const view = render(<Editor />);
  expect(saved.identity).toBeUndefined();
  fireEvent.click(screen.getByRole("checkbox", { name: /Merge identical/ }));
  const fields = screen.getByRole("group", {
    name: "Fields identifying one detail",
  });
  fireEvent.click(within(fields).getByText("Select fields"));
  fireEvent.click(within(fields).getByRole("checkbox", { name: /hospital/ }));
  expect(saved.identity).toEqual({
    name: "detail",
    namespace: "validate:Checks",
    keys: ["hospital"],
  });
  fireEvent.click(within(fields).getByRole("checkbox", { name: /hospital/ }));
  expect(saved.identity?.namespace).toBe("validate:Checks");
  expect(
    screen.getByTestId("configuration-section-identity"),
  ).toHaveTextContent("1 item needs attention");
  fireEvent.click(within(fields).getByRole("checkbox", { name: /detail/ }));
  const stored = JSON.parse(JSON.stringify(saved));
  view.unmount();
  render(<Editor initial={stored} />);
  expect(saved).toEqual(stored);
  expect(
    screen.queryByRole("textbox", { name: "Namespace" }),
  ).not.toBeInTheDocument();
  expect(managedValidation(stored, "renamed-node")).toEqual(stored);
});
it("retains valid existing identifiers and flags missing source fields without dropping them", () => {
  render(
    <Editor
      initial={{
        required: ["removed"],
        identity: {
          name: "settlement_detail",
          namespace: "core-flow-v1",
          keys: ["detail"],
        },
      }}
    />,
  );
  expect(saved.identity?.namespace).toBe("core-flow-v1");
  expect(saved.required).toEqual(["removed"]);
  expect(
    screen.getByTestId("configuration-section-required"),
  ).toHaveTextContent("1 item needs attention");
  fireEvent.click(
    screen.getByText("System-managed identity details (read-only)"),
  );
  expect(screen.getByText("core-flow-v1")).toBeVisible();
});
