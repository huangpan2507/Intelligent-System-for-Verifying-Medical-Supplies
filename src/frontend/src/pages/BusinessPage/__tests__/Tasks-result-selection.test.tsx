import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Tasks from "../Tasks";

jest.mock("../RequestLog", () => () => null);
jest.mock("../AssessmentPanel", () => () => null);
jest.mock("@/controllers/API/queries/business", () => ({
  useBusinessQuery: (path: string) => ({
    data: path.includes("/datasets/")
      ? {
          total: 1,
          fields: [{ name: "label", type: "text" }],
          rows: [
            {
              label: path.includes("/final?")
                ? "MOCK-DETAIL-HIP"
                : "Coverage summary",
            },
          ],
        }
      : {
          scheme_code: "compact",
          version: 1,
          status: "completed",
          unresolved_rows: 0,
          progress: {},
          results: ["coverage", "final"],
          datasets: [
            { id: "coverage", node_id: "Assessment", port: "dispositions" },
            { id: "final", node_id: "Results", port: "data" },
          ],
        },
  }),
}));

it("opens the business output first and still allows viewing coverage", () => {
  render(
    <MemoryRouter initialEntries={["/business/tasks/task-a"]}>
      <Routes>
        <Route path="/business/tasks/:taskId" element={<Tasks />} />
      </Routes>
    </MemoryRouter>,
  );
  const selection = screen.getByRole("combobox", { name: "Inspect dataset" });
  expect(selection).toHaveValue("final");
  expect(screen.getByText("MOCK-DETAIL-HIP")).toBeInTheDocument();
  fireEvent.change(selection, { target: { value: "coverage" } });
  expect(screen.getByText("Coverage summary")).toBeInTheDocument();
  expect(screen.queryByText("MOCK-DETAIL-HIP")).not.toBeInTheDocument();
});
