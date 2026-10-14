import { fireEvent, render, screen, within } from "@testing-library/react";
import TaskInputPanel from "../TaskInputPanel";

const mockQuery = jest.fn();
jest.mock("@/controllers/API/queries/business", () => ({
  useBusinessQuery: (...args: unknown[]) => mockQuery(...args),
}));

const definition = {
  contract: "regulatory.v1",
  parameters: ["hospital_name", "start", "end"].map((name) => ({
    name,
    type: "string",
  })),
  context: ["scheme", "external_task_id", "task_id"].map((name) => ({
    name,
    type: "string",
  })),
};
const first = {
  id: "task-a",
  flow_id: "flow-a",
  task_input: {
    parameters: {
      hospital_name: "Hospital A",
      start: "2025-08-01 00:00:00",
      end: "2025-08-31 23:59:59",
    },
    task: { scheme: "rule-a", external_task_id: "REG-A", task_id: "task-a" },
  },
};
const second = {
  ...first,
  id: "task-b",
  task_input: {
    parameters: { ...first.task_input.parameters, hospital_name: "Hospital B" },
    task: {
      ...first.task_input.task,
      external_task_id: "REG-B",
      task_id: "task-b",
    },
  },
};

beforeEach(() => {
  mockQuery.mockImplementation((path: string) => ({
    data: path.startsWith("tasks?")
      ? { items: [first, second], total: 2 }
      : path === "tasks/task-a"
        ? first
        : path === "tasks/task-b"
          ? second
          : undefined,
  }));
});

it("shows fixed input definitions without editable parameter settings", () => {
  render(<TaskInputPanel flowId="flow-a" definition={definition} />);
  expect(
    screen.getByTestId("business-task-input-values").querySelectorAll("dd"),
  ).toHaveLength(12);
  expect(screen.getAllByText("Not received").length).toBeGreaterThanOrEqual(6);
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  expect(screen.queryByText("Hospital A")).not.toBeInTheDocument();
});

it("shows only the selected task and removes values when returning to the contract", () => {
  render(<TaskInputPanel flowId="flow-a" definition={definition} />);
  fireEvent.change(screen.getByRole("combobox", { name: "View task" }), {
    target: { value: "task-a" },
  });
  const values = screen.getByTestId("business-task-input-values");
  expect(within(values).getByText("Hospital A")).toBeInTheDocument();
  expect(within(values).getByText("REG-A")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox"), {
    target: { value: "task-b" },
  });
  expect(screen.queryByText("Hospital A")).not.toBeInTheDocument();
  expect(within(values).getByText("Hospital B")).toBeInTheDocument();
  expect(within(values).getByText("REG-B")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "" } });
  expect(screen.queryByText("Hospital B")).not.toBeInTheDocument();
  expect(
    screen.getByTestId("business-task-input-values").querySelectorAll("dd"),
  ).toHaveLength(12);
  expect(screen.getAllByText("Not received").length).toBeGreaterThanOrEqual(6);
});

it("never renders a stale response from the previously selected task", () => {
  render(<TaskInputPanel flowId="flow-a" definition={definition} />);
  fireEvent.change(screen.getByRole("combobox"), {
    target: { value: "task-a" },
  });
  mockQuery.mockImplementation((path: string) => ({
    data: path.startsWith("tasks?")
      ? { items: [first, second], total: 2 }
      : first,
  }));
  fireEvent.change(screen.getByRole("combobox"), {
    target: { value: "task-b" },
  });
  expect(screen.queryByText("Hospital A")).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Loading task input");
});

it("clears task selection when moving to another canvas", () => {
  const view = render(
    <TaskInputPanel flowId="flow-a" definition={definition} />,
  );
  fireEvent.change(screen.getByRole("combobox"), {
    target: { value: "task-a" },
  });
  view.rerender(<TaskInputPanel flowId="flow-b" definition={definition} />);
  expect(screen.getByRole("combobox")).toHaveValue("");
  expect(screen.queryByText("Hospital A")).not.toBeInTheDocument();
  expect(
    screen.getByTestId("business-task-input-values").querySelectorAll("dd"),
  ).toHaveLength(12);
  expect(screen.getAllByText("Not received").length).toBeGreaterThanOrEqual(6);
});
