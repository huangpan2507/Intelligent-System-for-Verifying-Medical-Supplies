import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import type { JsonSchema } from "@/controllers/API/queries/business";
import ApiConfiguration from "../ApiConfiguration";

const schema: JsonSchema = {
  type: "object",
  properties: {
    connection: { type: "string", format: "connection" },
    path: { type: "string" },
    body: { type: "object" },
    pagination: { type: "string", enum: ["none", "cursor", "page"] },
    cursor_path: { type: "string" },
    cursor_parameter: { type: "string" },
    page_parameter: { type: "string" },
    collection: {
      type: "object",
      properties: {
        retain_fields: {
          type: "array",
          items: { type: "string", format: "field" },
        },
        output: { type: "string" },
      },
    },
  },
};
const initial = {
  connection: "api",
  path: "/images",
  body: { series_id: { field: "series_id" }, url_type: "3", numeric: 3 },
  pagination: "none",
  cursor_path: "next",
  cursor_parameter: "after",
  page_parameter: "page_no",
  collection: {
    group_by: ["identity"],
    retain_fields: ["RPT_NO"],
    item_context: ["RPT_NO"],
    output: "images",
  },
};
let saved: Record<string, unknown>;
function Editor() {
  const [value, setValue] = useState<Record<string, unknown>>(initial);
  saved = value;
  return (
    <ApiConfiguration
      value={value}
      onChange={(v) => setValue(v as Record<string, unknown>)}
      schema={schema}
      options={{
        fields: {
          data: ["identity", "RPT_NO", "series_id", "new_field"].map(
            (name) => ({ name, type: "text" }),
          ),
        },
      }}
    >
      <div />
    </ApiConfiguration>
  );
}
it("shows only applicable pagination fields, preserving hidden settings and typed request bindings", () => {
  render(<Editor />);
  expect(
    screen.queryByTestId("business-field-cursor_path"),
  ).not.toBeInTheDocument();
  fireEvent.change(
    screen.getByRole("combobox", { name: "Pagination", hidden: true }),
    { target: { value: "cursor" } },
  );
  expect(screen.getByTestId("business-field-cursor_path")).toBeInTheDocument();
  expect(
    screen.queryByTestId("business-field-page_parameter"),
  ).not.toBeInTheDocument();
  fireEvent.change(
    screen.getByRole("combobox", { name: "Pagination", hidden: true }),
    { target: { value: "page" } },
  );
  expect(
    screen.getByTestId("business-field-page_parameter"),
  ).toBeInTheDocument();
  fireEvent.change(
    screen.getByRole("combobox", { name: "Pagination", hidden: true }),
    { target: { value: "none" } },
  );
  expect(saved).toEqual(initial);
});
it("edits an explicit retained list without adding new upstream fields or losing item context", () => {
  render(<Editor />);
  const group = screen.getByTestId("configuration-section-api-collection");
  fireEvent.click(within(group).getByText("Organize the business result"));
  fireEvent.click(within(group).getByText("Edit retained fields"));
  const fields = within(group).getByText("Edit retained fields").parentElement!;
  fireEvent.click(within(fields).getByText("Select fields"));
  expect(
    within(fields).getByRole("checkbox", { name: "new_field · text" }),
  ).not.toBeChecked();
  fireEvent.click(
    within(fields).getByRole("checkbox", { name: "series_id · text" }),
  );
  expect(saved.collection).toEqual({
    ...initial.collection,
    retain_fields: ["RPT_NO", "series_id"],
  });
  expect(saved.body).toEqual(initial.body);
});

it("restores the explicit collection settings when temporarily toggled off", () => {
  render(<Editor />);
  const group = screen.getByTestId("configuration-section-api-collection");
  fireEvent.click(within(group).getByText("Organize the business result"));
  const toggle = within(group).getByRole("checkbox", {
    name: "Collect by source record (optional)",
  });
  fireEvent.click(toggle);
  expect(saved.collection).toBeUndefined();
  fireEvent.click(toggle);
  expect(saved.collection).toEqual(initial.collection);
});
