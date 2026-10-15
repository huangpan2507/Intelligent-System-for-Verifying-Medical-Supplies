import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { businessI18n } from "../business-i18n";
import {
  businessNodeDescription,
  businessNodeName,
} from "../business-node-presentation";
import { SchemaForm } from "../SchemaForm";

jest.unmock("react-i18next");

it("renders Chinese labels while preserving source options, bound values and edits", () => {
  const initial = {
    field: "ORGAN_NAME",
    op: "eq",
    parameter: "hospital_name",
    description: "Do not translate 人工髋关节",
  };
  function Editor() {
    const [value, setValue] = useState<unknown>(initial);
    return (
      <>
        <SchemaForm
          schema={{
            type: "object",
            properties: {
              field: { type: "string", format: "field" },
              op: { type: "string", enum: ["eq", "ge"] },
              parameter: { type: "string", format: "parameter" },
              description: { type: "string", format: "multiline" },
            },
          }}
          value={value}
          onChange={setValue}
          options={{
            fields: {
              data: [
                { name: "ORGAN_NAME", type: "TEXT", source: "Settlements" },
                {
                  name: "target_category",
                  type: "text",
                  source: "Classification",
                },
              ],
            },
            parameters: ["hospital_name"],
          }}
        />
        <output data-testid="saved">{JSON.stringify(value)}</output>
      </>
    );
  }
  render(<Editor />);
  expect(screen.getByRole("combobox", { name: "字段" })).toHaveValue(
    "ORGAN_NAME",
  );
  expect(
    screen.getByRole("option", { name: "Settlements.ORGAN_NAME · TEXT" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("option", {
      name: "Classification.target_category · text",
    }),
  ).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Eq" })).toHaveValue("eq");
  expect(screen.getByDisplayValue(initial.description)).toBeInTheDocument();
  expect(JSON.parse(screen.getByTestId("saved").textContent!)).toEqual(initial);
  fireEvent.change(screen.getByRole("combobox", { name: "字段" }), {
    target: { value: "target_category" },
  });
  expect(JSON.parse(screen.getByTestId("saved").textContent!)).toEqual({
    ...initial,
    field: "target_category",
  });
});

it("localizes only known Business presentation and preserves custom labels", () => {
  expect(businessNodeName("business:BusinessDatabaseLookup@1", "Studies")).toBe(
    "检查关联",
  );
  expect(businessNodeName("BusinessClassification", "StudyRelevance")).toBe(
    "检查适用性判断",
  );
  expect(businessNodeName("BusinessApi", "Business Api")).toBe("接口读取");
  expect(businessNodeName("BusinessApi", "My custom API")).toBe(
    "My custom API",
  );
  expect(businessNodeName("Other", "Studies")).toBe("Studies");
  expect(
    businessNodeDescription("BusinessApi", "Persistent business datasets: api"),
  ).toMatch(/调用业务接口/);
  expect(businessNodeDescription("BusinessApi", "Custom description")).toBe(
    "Custom description",
  );
  expect(businessI18n.language).toBe("zh-Hans");
});
