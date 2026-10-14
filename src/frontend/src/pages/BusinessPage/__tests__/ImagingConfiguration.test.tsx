import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import type { JsonSchema } from "@/controllers/API/queries/business";
import ImagingConfiguration from "../ImagingConfiguration";

const initial = {
  connection: "service",
  path: "/recognize",
  max_calls: 10,
  hospital_field: "hospital",
  patient_field: "patient",
  encounter_field: "encounter",
  category_field: "category",
  evidence_field: "images",
  evidence_context_field: "context",
  result_checks: { required: ["recognized_quantity"] },
};
const schema: JsonSchema = {
  type: "object",
  required: [
    "connection",
    "path",
    "hospital_field",
    "patient_field",
    "evidence_field",
    "category_field",
  ],
  properties: Object.fromEntries(
    Object.keys(initial).map((key) => [
      key,
      key.endsWith("_field")
        ? { type: "string", format: "field" }
        : key === "max_calls"
          ? { type: "integer" }
          : key === "result_checks"
            ? { type: "object" }
            : { type: "string" },
    ]),
  ),
};
let saved: Record<string, unknown>;
function Editor({ stale = false }: { stale?: boolean }) {
  const [value, setValue] = useState<Record<string, unknown>>({
    ...initial,
    ...(stale ? { patient_field: "missing_patient" } : {}),
  });
  saved = value;
  return (
    <ImagingConfiguration
      value={value}
      onChange={(v) => setValue(v as Record<string, unknown>)}
      schema={schema}
      options={{
        fields: {
          data: [
            "hospital",
            "patient",
            "encounter",
            "category",
            "images",
            "context",
            "other_patient",
          ].map((name) => ({ name, type: "text" })),
        },
      }}
    />
  );
}

it("groups the preset bindings and edits one without replacing hidden configuration", () => {
  render(<Editor />);
  expect(screen.getAllByTestId(/^configuration-section-imaging-/)).toHaveLength(
    5,
  );
  for (const key of ["quantity_field", "unit_field", "unit_value"])
    expect(
      screen.queryByTestId(`business-field-${key}`),
    ).not.toBeInTheDocument();
  const scope = screen.getByTestId("configuration-section-imaging-scope");
  expect(scope).toHaveTextContent("hospital");
  expect(scope).not.toHaveAttribute("open");
  fireEvent.click(within(scope).getByText("Who the images belong to"));
  fireEvent.click(within(scope).getByText("Edit field bindings"));
  fireEvent.change(
    within(scope).getByRole("combobox", { name: "Patient field" }),
    { target: { value: "other_patient" } },
  );
  expect(saved).toEqual({ ...initial, patient_field: "other_patient" });
});

it("reveals an invalid preset mapping without silently substituting a field", () => {
  render(<Editor stale />);
  const scope = screen.getByTestId("configuration-section-imaging-scope");
  expect(scope).toHaveAttribute("open");
  expect(within(scope).getByRole("alert")).toBeVisible();
  expect(
    within(scope).getByRole("combobox", { name: "Patient field" }),
  ).toHaveValue("missing_patient");
  expect(saved.patient_field).toBe("missing_patient");
});
