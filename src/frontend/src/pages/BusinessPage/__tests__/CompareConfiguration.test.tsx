import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import type { JsonSchema } from "@/controllers/API/queries/business";
import CompareConfiguration from "../CompareConfiguration";

const field: JsonSchema = { type: "string", format: "field" };
const text: JsonSchema = { type: "string" };
const schema: JsonSchema = {
  type: "object",
  properties: {
    calculations: {
      type: "array",
      items: {
        type: "object",
        properties: {
          operation: {
            type: "string",
            enum: ["copy", "cast", "map", "expression"],
          },
          output: text,
          field,
          expression: text,
          type: text,
          precision: { type: "integer" },
          scale: { type: "integer" },
          mapping: { type: "object" },
        },
        required: ["operation", "output"],
      },
    },
    comparisons: {
      type: "array",
      minItems: 1,
      items: {
        type: "object",
        properties: {
          left: field,
          right: field,
          output: text,
          mode: {
            type: "string",
            enum: ["exact", "numeric", "case_insensitive"],
          },
          null_equal: { type: "boolean" },
        },
        required: ["left", "right"],
      },
    },
  },
};
const initial = {
  calculations: [
    {
      operation: "copy",
      field: "_representative_row_id",
      output: "unit_row_id",
    },
    {
      operation: "expression",
      expression: "CNT * PRIC",
      output: "settled_amount",
    },
    {
      operation: "expression",
      expression: "recognized_quantity * PRIC",
      output: "observed_amount",
    },
  ],
  comparisons: [
    {
      left: "settled_amount",
      right: "observed_amount",
      mode: "numeric",
      output: "amount_status",
    },
  ],
};
let saved: typeof initial;
function Editor({ stale = false }: { stale?: boolean }) {
  const [value, setValue] = useState({
    ...initial,
    comparisons: stale
      ? [{ ...initial.comparisons[0], left: "missing" }]
      : initial.comparisons,
  });
  saved = value;
  return (
    <CompareConfiguration
      value={value}
      onChange={(v) => setValue(v as typeof initial)}
      schema={schema}
      options={{
        fields: {
          upstream: [
            "CNT",
            "PRIC",
            "recognized_quantity",
            "_representative_row_id",
          ].map((name) => ({ name, type: "number", source: "Observation" })),
        },
      }}
    />
  );
}
it("orders calculations before comparisons and preserves hidden traceability when editing", () => {
  render(<Editor />);
  expect(
    screen
      .getAllByTestId(/^configuration-section-compare-/)
      .map((s) => s.getAttribute("data-testid")),
  ).toEqual([
    "configuration-section-compare-source",
    "configuration-section-compare-calculations",
    "configuration-section-compare-comparisons",
    "configuration-section-compare-output",
  ]);
  const section = screen.getByTestId(
    "configuration-section-compare-calculations",
  );
  const editor = within(section)
    .getByText("Settlement-side calculated amount = CNT * PRIC")
    .closest("details")!;
  fireEvent.click(
    within(editor).getByText("Settlement-side calculated amount = CNT * PRIC"),
  );
  expect(
    within(editor).queryByRole("combobox", { name: "Field" }),
  ).not.toBeInTheDocument();
  expect(
    within(editor).queryByRole("textbox", { name: "Type" }),
  ).not.toBeInTheDocument();
  fireEvent.change(
    within(editor).getByRole("textbox", { name: "Expression" }),
    { target: { value: "CNT * PRIC + 1" } },
  );
  expect(saved.calculations[0]).toEqual(initial.calculations[0]);
  expect(saved.calculations[1].expression).toBe("CNT * PRIC + 1");
  expect(saved.comparisons).toEqual(initial.comparisons);
  expect(screen.queryByText("Tolerance")).not.toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "Left" })).toHaveValue(
    "settled_amount",
  );
});
it("preserves stale fields and reveals errors without selecting replacements", () => {
  render(<Editor stale />);
  const section = screen.getByTestId(
    "configuration-section-compare-comparisons",
  );
  expect(within(section).getByRole("alert")).toBeVisible();
  expect(within(section).getByRole("combobox", { name: "Left" })).toHaveValue(
    "missing",
  );
  fireEvent.change(within(section).getByRole("combobox", { name: "Left" }), {
    target: { value: "CNT" },
  });
  expect(saved.comparisons[0]).toEqual({
    ...initial.comparisons[0],
    left: "CNT",
  });
  expect(saved.calculations).toEqual(initial.calculations);
});
it("shows only the chosen calculation operation inputs", () => {
  render(<Editor />);
  const section = screen.getByTestId(
    "configuration-section-compare-calculations",
  );
  const editor = within(section)
    .getByText("Settlement-side calculated amount = CNT * PRIC")
    .closest("details")!;
  fireEvent.click(
    within(editor).getByText("Settlement-side calculated amount = CNT * PRIC"),
  );
  fireEvent.change(
    within(editor).getByRole("combobox", { name: "Operation" }),
    { target: { value: "copy" } },
  );
  expect(
    within(editor).queryByRole("textbox", { name: "Expression" }),
  ).not.toBeInTheDocument();
  expect(within(editor).getByRole("combobox", { name: "Field" })).toBeVisible();
  expect(saved.calculations[1]).toEqual({
    operation: "copy",
    output: "settled_amount",
  });
});
