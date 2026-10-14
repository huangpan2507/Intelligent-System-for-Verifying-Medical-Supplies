import type { APIClassType, InputFieldType } from "@/types/api";

export function createInput(
  overrides: Partial<InputFieldType> = {},
): InputFieldType {
  return {
    type: "str",
    required: false,
    list: false,
    show: true,
    readonly: false,
    ...overrides,
  };
}

export function createComponent(
  overrides: Partial<APIClassType> = {},
): APIClassType {
  return {
    display_name: "Test component",
    description: "",
    documentation: "",
    template: {},
    ...overrides,
  };
}
