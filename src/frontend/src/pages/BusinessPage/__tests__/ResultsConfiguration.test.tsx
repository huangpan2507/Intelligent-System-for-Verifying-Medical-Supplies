import { fireEvent, render, screen, within } from "@testing-library/react";
import { BusinessResultCard, type SavedResult } from "../BusinessResults";
import ResultsConfiguration from "../ResultsConfiguration";

const mockQuery = jest.fn();
jest.mock("@/controllers/API/queries/business", () => ({
  useBusinessQuery: (...args: unknown[]) => mockQuery(...args),
}));
const example: SavedResult = {
  template_id: "hip_knee_v1",
  template_version: 1,
  status: "normal",
  complete: true,
  narrative: "示例中文结果",
  facts: { RPT_NO: "RPT-1", simulated: true },
  checks: [
    {
      name: "quantity",
      label: "数量",
      status: "equal",
      left: "1",
      right: "1",
      difference: "0",
    },
  ],
};
const saved = {
  ...example,
  id: "result-1",
  task_id: "task-1",
  narrative: "任务当时保存的中文说明",
};
beforeEach(() => {
  mockQuery.mockImplementation((path: string) => ({
    data:
      path === "result-templates"
        ? [
            {
              id: "hip_knee_v1",
              name: "髋膝耗材核验结果",
              version: 1,
              columns: ["RPT_NO", "_request_id"],
              obligation: { mode: "verification" },
              example,
            },
          ]
        : path.startsWith("tasks?")
          ? { items: [{ id: "task-1", status: "completed" }], total: 1 }
          : path.startsWith("tasks/task-1/results?")
            ? { items: [saved], total: 1 }
            : path.includes("evidence-view")
              ? undefined
              : path.includes("result-storage")
                ? {
                    templates: [],
                    saved: 1,
                    different: 0,
                    incomplete: 0,
                    task_status: "completed",
                  }
                : { items: [], total: 0 },
    isLoading: false,
    error: null,
  }));
});
afterEach(() => jest.clearAllMocks());
it("shows three groups and an example without editing or executing", () => {
  const change = jest.fn();
  render(
    <ResultsConfiguration
      value={{ result_template: "hip_knee_v1" }}
      onChange={change}
      flowId="flow-1"
      nodeId="Results"
    />,
  );
  expect(
    screen
      .getAllByTestId(/^configuration-section-results-/)
      .map((s) => s.getAttribute("data-testid")),
  ).toEqual([
    "configuration-section-results-template",
    "configuration-section-results-preview",
    "configuration-section-results-storage",
  ]);
  expect(screen.getByText("示例中文结果")).toBeVisible();
  expect(
    screen.getAllByText("Example (not executed or saved)").length,
  ).toBeGreaterThan(0);
  expect(screen.queryByText("Primary")).not.toBeInTheDocument();
  expect(screen.queryByText("Key fields")).not.toBeInTheDocument();
  expect(change).not.toHaveBeenCalled();
  expect(
    mockQuery.mock.calls.every(([path]) => !path.includes("requests/")),
  ).toBe(true);
});
it("reads the selected task's saved narrative instead of regenerating it", () => {
  const change = jest.fn();
  render(
    <ResultsConfiguration
      value={{ result_template: "hip_knee_v1" }}
      onChange={change}
      flowId="flow-1"
      nodeId="Results"
    />,
  );
  fireEvent.change(
    within(
      screen.getByTestId("configuration-section-results-preview"),
    ).getByRole("combobox"),
    { target: { value: "task-1" } },
  );
  expect(screen.getByText("任务当时保存的中文说明")).toBeVisible();
  expect(screen.queryByText("示例中文结果")).not.toBeInTheDocument();
  expect(
    screen.getByText("Saved in the platform result database"),
  ).toBeVisible();
  expect(change).not.toHaveBeenCalled();
});
it("shows known differences alongside unfinished checks and lazily reads evidence", () => {
  render(
    <BusinessResultCard
      result={{
        ...saved,
        status: "difference",
        complete: false,
        narrative: "类别存在差异；数量尚未完成。",
        checks: [
          {
            name: "category",
            label: "类别",
            status: "different",
            left: "髋",
            right: "膝",
            difference: null,
          },
          {
            name: "quantity",
            label: "数量",
            status: "unknown",
            left: "1",
            right: null,
            difference: null,
          },
        ],
      }}
    />,
  );
  expect(screen.getByText("Differences found")).toBeVisible();
  expect(screen.getByText("Undetermined")).toBeVisible();
  expect(mockQuery).toHaveBeenCalledWith(
    "tasks/task-1/results/result-1/evidence-view?group=settlement&limit=20&offset=0",
    false,
    false,
    { staleTime: Infinity },
  );
});

it("allows naming a new generic output without exposing internal coverage configuration", () => {
  const change = jest.fn();
  render(
    <ResultsConfiguration value={{}} onChange={change} nodeId="NewOutput" />,
  );
  fireEvent.change(screen.getByRole("textbox", { name: "Name" }), {
    target: { value: "Order results" },
  });
  expect(change).toHaveBeenCalledWith({ name: "Order results" });
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
});
