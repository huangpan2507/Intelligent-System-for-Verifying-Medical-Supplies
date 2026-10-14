import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Tasks from "../Tasks";

jest.mock("../RequestLog", () => () => null);
jest.mock("../AssessmentPanel", () => () => null);
jest.mock("@/controllers/API/queries/business", () => ({
  useBusinessQuery: (path: string) => ({
    data: path.includes("/datasets/")
      ? {
          total: 2,
          fields: [{ name: "_issue_severity", type: "text" }],
          rows: [{ _issue_severity: "info" }, { _issue_severity: "error" }],
        }
      : {
          scheme_code: "test",
          version: 1,
          status: "completed",
          unresolved_rows: 1,
          progress: {},
          results: [],
          datasets: [{ id: "issues", node_id: "Checks", port: "issues" }],
        },
  }),
}));

it("distinguishes a merged duplicate notice from a validation error", () => {
  render(
    <MemoryRouter initialEntries={["/business/tasks/task-a"]}>
      <Routes>
        <Route path="/business/tasks/:taskId" element={<Tasks />} />
      </Routes>
    </MemoryRouter>,
  );
  expect(screen.getByText("Validation issue type")).toBeInTheDocument();
  expect(screen.getByText("Merged duplicate (notice)")).toBeInTheDocument();
  expect(screen.getByText("Data error")).toBeInTheDocument();
});
