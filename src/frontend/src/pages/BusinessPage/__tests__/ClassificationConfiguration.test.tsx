import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import type { JsonSchema } from "@/controllers/API/queries/business";
import ClassificationConfiguration from "../ClassificationConfiguration";
import {
  type ClassificationConfig,
  classificationConfig,
} from "../classification-config";

const initial: ClassificationConfig = {
  classification_fields: [
    { field: "product", role: "evidence" },
    { field: "procedure", role: "context" },
  ],
  category_routes: [
    { category: "hip", continue: true },
    { category: "other", continue: false },
  ],
  rules: [
    { op: "contains_all", keywords: ["artificial", "hip"], category: "hip" },
  ],
  business_guidance: "Read material descriptions",
  model: "configured-model",
  path: "/chat",
  connection: "test",
};
const schema: JsonSchema = {
  type: "object",
  properties: {
    result_prefix: { type: "string" },
    dictionary: {
      type: "object",
      properties: {
        id: { type: "string", enum: ["wst364.8-2023-cv04.30.002"] },
        field: { type: "string", format: "field" },
      },
    },
    connection: { type: "string", format: "connection" },
    model: { type: "string" },
    path: { type: "string" },
    max_calls: { type: "integer" },
    conflicts: {
      type: "array",
      items: {
        type: "object",
        properties: {
          category: { type: "string" },
          field: { type: "string", format: "field" },
          contains: { type: "string" },
        },
      },
    },
  },
};
let saved: ClassificationConfig;
function Editor({ value = initial }: { value?: ClassificationConfig }) {
  const [config, setConfig] = useState(value);
  saved = config;
  return (
    <ClassificationConfiguration
      value={config}
      onChange={setConfig}
      schema={schema}
      fields={[
        { name: "product", type: "text", source: "Checks" },
        { name: "procedure", type: "text", source: "Checks" },
      ]}
      connections={[{ id: "test", name: "Test", kind: "http", config: {} }]}
      prompt="The actual inspected system message"
    />
  );
}
it("retains invalid custom field references after changing their role", () => {
  render(<Editor />);
  fireEvent.click(
    screen
      .getByTestId("configuration-section-classification-categories")
      .querySelector("summary")!,
  );
  expect(
    screen.getByText("Shared evidence fields: product"),
  ).toBeInTheDocument();
  expect(
    screen.getByText("The actual inspected system message"),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByText(/Additional scope/));
  fireEvent.click(
    screen.getByLabelText("Use an explicit subset of evidence fields"),
  );
  fireEvent.change(screen.getAllByRole("combobox", { name: "Role" })[0], {
    target: { value: "context" },
  });
  expect(saved.rules[0].fields).toEqual(["product"]);
  expect(screen.getAllByRole("alert").at(-1)!).toHaveTextContent(
    "References have not been removed",
  );
});
it("persists custom scope after reopening and keeps invalid category references visible", () => {
  const { unmount } = render(<Editor />);
  fireEvent.click(
    screen
      .getByTestId("configuration-section-classification-categories")
      .querySelector("summary")!,
  );
  expect(saved.rules[0]).not.toHaveProperty("fields");
  fireEvent.click(screen.getByText(/Additional scope/));
  fireEvent.click(
    screen.getByLabelText("Use an explicit subset of evidence fields"),
  );
  const stored = JSON.parse(JSON.stringify(saved));
  unmount();
  render(<Editor value={stored} />);
  expect(
    screen.getByLabelText("Use an explicit subset of evidence fields"),
  ).toBeChecked();
  fireEvent.click(
    screen
      .getByTestId("configuration-section-classification-categories")
      .querySelector("summary")!,
  );
  fireEvent.change(screen.getByRole("textbox", { name: "Category 1" }), {
    target: { value: "new hip" },
  });
  expect(saved.rules[0].category).toBe("hip");
  expect(screen.getAllByRole("alert").at(-1)!).toHaveTextContent("hip");
});
it("edits compact keywords without adding a duplicate field selection", () => {
  render(<Editor />);
  fireEvent.click(
    screen
      .getByTestId("configuration-section-classification-categories")
      .querySelector("summary")!,
  );
  fireEvent.change(
    screen.getByRole("textbox", { name: "Keywords (comma separated)" }),
    { target: { value: "人工, 髋关节" } },
  );
  expect(saved.rules[0]).toEqual({
    op: "contains_all",
    keywords: ["人工", "髋关节"],
    category: "hip",
  });
  fireEvent.change(screen.getByRole("combobox", { name: "Match" }), {
    target: { value: "contains" },
  });
  expect(saved.rules[0]).toEqual({
    op: "contains",
    value: "人工髋关节",
    category: "hip",
  });
});
it("provides one current configuration with fixed unknown status and editable guidance", () => {
  render(<Editor value={classificationConfig(initial)} />);
  expect(screen.getByText(/System state: Undetermined/)).toBeInTheDocument();
  fireEvent.click(
    screen
      .getByTestId("configuration-section-classification-model")
      .querySelector("summary")!,
  );
  expect(
    screen.getByRole("textbox", { name: "Business guidance" }),
  ).toHaveValue(initial.business_guidance);
  fireEvent.change(screen.getByRole("textbox", { name: "Business guidance" }), {
    target: { value: "Updated business guidance" },
  });
  expect(saved.business_guidance).toBe("Updated business guidance");
  expect(
    screen.queryByRole("textbox", { name: "Unknown category label" }),
  ).not.toBeInTheDocument();
});

it("offers dictionary-derived evidence and preserves upstream context in a second classification", () => {
  render(
    <Editor
      value={{
        ...initial,
        result_prefix: "study_relevance",
        dictionary: { id: "wst364.8-2023-cv04.30.002", field: "product" },
        classification_fields: [
          { field: "study_relevance_code_name", role: "evidence" },
          { field: "procedure", role: "context" },
        ],
        rules: [
          {
            op: "contains",
            value: "hip",
            category: "hip",
            when: [{ field: "procedure", value: "hip" }],
          },
        ],
      }}
    />,
  );
  fireEvent.click(
    screen
      .getByTestId("configuration-section-classification-output")
      .querySelector("summary")!,
  );
  expect(screen.getByRole("textbox", { name: "Result prefix" })).toHaveValue(
    "study_relevance",
  );
  const first = screen.getByRole("combobox", { name: "Field 1" });
  expect(first).toHaveValue("study_relevance_code_name");
  expect(
    first.querySelector('option[value="study_relevance_code_name"]'),
  ).not.toHaveTextContent(/unavailable/i);
  expect(saved.rules[0].when).toEqual([{ field: "procedure", value: "hip" }]);
  expect(saved.classification_fields[1]).toEqual({
    field: "procedure",
    role: "context",
  });
});
