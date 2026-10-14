import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import type { JsonSchema } from "@/controllers/API/queries/business";
import { SchemaForm } from "../SchemaForm";

const condition: JsonSchema = {
  type: "object",
  format: "condition",
  properties: {
    field: { type: "string", format: "field" },
    op: { type: "string", enum: ["eq", "is_null"] },
    value: {},
    parameter: { type: "string", format: "parameter" },
    right_field: { type: "string", format: "field" },
  },
};

function Editor() {
  const [value, setValue] = useState<unknown>({
    field: "amount",
    op: "eq",
    value: 10,
  });
  return (
    <>
      <SchemaForm
        schema={condition}
        value={value}
        onChange={setValue}
        options={{
          fields: { data: [{ name: "amount", type: "number" }] },
          parameters: ["threshold"],
        }}
      />
      <output data-testid="saved-condition">{JSON.stringify(value)}</output>
    </>
  );
}

it("switches condition value sources without retaining a competing value", () => {
  render(<Editor />);
  fireEvent.change(screen.getByRole("combobox", { name: "Value source" }), {
    target: { value: "parameter" },
  });
  fireEvent.change(screen.getByRole("combobox", { name: "Parameter" }), {
    target: { value: "threshold" },
  });
  expect(
    JSON.parse(screen.getByTestId("saved-condition").textContent!),
  ).toEqual({ field: "amount", op: "eq", parameter: "threshold" });
  fireEvent.change(screen.getByRole("combobox", { name: "Value source" }), {
    target: { value: "right_field" },
  });
  fireEvent.change(screen.getByRole("combobox", { name: "Right field" }), {
    target: { value: "amount" },
  });
  expect(
    JSON.parse(screen.getByTestId("saved-condition").textContent!),
  ).toEqual({ field: "amount", op: "eq", right_field: "amount" });
  fireEvent.change(screen.getByRole("combobox", { name: "Op" }), {
    target: { value: "is_null" },
  });
  expect(
    JSON.parse(screen.getByTestId("saved-condition").textContent!),
  ).toEqual({ field: "amount", op: "is_null" });
  expect(
    screen.queryByRole("combobox", { name: "Value source" }),
  ).not.toBeInTheDocument();
});
