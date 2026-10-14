import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import type { JsonSchema } from "@/controllers/API/queries/business";
import DatabaseConfiguration from "../DatabaseConfiguration";

const schema: JsonSchema = {
  type: "object",
  properties: {
    connection: { type: "string", format: "connection" },
    schema: { type: "string", format: "database_schema" },
    table: { type: "string", format: "table" },
    sql: { type: "string", format: "multiline" },
    parameters: { type: "array", items: { type: "string" } },
    conditions: { type: "array", items: {} },
  },
};
const initial = {
  connection: "db",
  schema: "public",
  table: "records",
  conditions: [
    { field: "hospital", op: "eq", parameter: "hospital_name" },
    { field: "paid", op: "eq", value: "1" },
  ],
};
let saved: Record<string, unknown>;
function Editor() {
  const [value, setValue] = useState<Record<string, unknown>>(initial);
  saved = value;
  return (
    <DatabaseConfiguration
      value={value}
      onChange={(v) => setValue(v as Record<string, unknown>)}
      schema={schema}
      options={{
        tables: ["records"],
        databaseSchemas: ["public"],
        connections: [
          { id: "db", name: "Database", kind: "postgresql", config: {} },
        ],
        fields: { data: [{ name: "hospital", type: "text" }] },
      }}
    />
  );
}
it("folding and switching SQL back to table do not discard or retype table conditions", () => {
  render(<Editor />);
  expect(screen.queryByText("Parameters")).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Advanced reading settings"));
  fireEvent.change(screen.getByRole("textbox", { name: "Sql" }), {
    target: { value: "select hospital from records" },
  });
  expect(
    screen.queryByRole("combobox", { name: "Table" }),
  ).not.toBeInTheDocument();
  expect(saved.conditions).toEqual(initial.conditions);
  fireEvent.change(screen.getByRole("textbox", { name: "Sql" }), {
    target: { value: "" },
  });
  expect(screen.getByRole("combobox", { name: "Table" })).toHaveValue(
    "records",
  );
  expect(saved.conditions).toEqual(initial.conditions);
});
