import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import BusinessResultEvidence from "../BusinessResultEvidence";
import ResultEvidenceDialog from "../ResultEvidenceDialog";
import ResultStorage from "../ResultStorage";

const mockQuery = jest.fn();
jest.mock("@/controllers/API/queries/business", () => ({
  useBusinessQuery: (...args: unknown[]) => mockQuery(...args),
}));
const state = (data: unknown) => ({ data, isLoading: false, error: null });
afterEach(() => jest.clearAllMocks());

it("shows full evidence counts and reads the selected source in a dialog", async () => {
  mockQuery.mockImplementation((path: string, enabled = true) => {
    if (!enabled) return state(undefined);
    if (path.endsWith("/evidence/source-91/detail"))
      return state({
        kind: "source",
        record: { RPT_NO: "EXACT-ROW-91", CNT: "2" },
      });
    return state({
      counts: {
        settlement: 1,
        study: 24,
        series: 30,
        image: 77,
        recognition: 1,
        unlinked: 0,
      },
      total: path.includes("group=settlement") ? 1 : 0,
      items: path.includes("group=settlement")
        ? [
            {
              id: "source-91",
              kind: "settlement",
              title: ["Saved settlement"],
              details: {},
              available: true,
              sources: ["source-91"],
              children: 0,
            },
          ]
        : [],
    });
  });
  render(<BusinessResultEvidence taskId="task-a" resultId="result-a" />);
  expect(mockQuery.mock.calls.every(([, enabled]) => enabled === false)).toBe(
    true,
  );
  fireEvent.click(screen.getByText("Sources and evidence"));
  expect(
    await screen.findByText(
      "24 study records · 30 series records · 77 image addresses",
    ),
  ).toBeVisible();
  fireEvent.click(screen.getByText(/Settlement details · 1/));
  fireEvent.click(screen.getByText(/Saved settlement/));
  fireEvent.click(
    await screen.findByRole("button", { name: /View source record 1/i }),
  );
  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).getByText("EXACT-ROW-91")).toBeVisible();
  expect(mockQuery).toHaveBeenCalledWith(
    "tasks/task-a/results/result-a/evidence/source-91/detail",
    true,
    false,
    { staleTime: Infinity },
  );
  expect(
    mockQuery.mock.calls.some(([path]) => path.includes("offset=91")),
  ).toBe(false);
});

it("keeps loading and errors inside the recognition dialog", () => {
  mockQuery.mockReturnValue({ data: undefined, isLoading: true, error: null });
  const props = {
    base: "tasks/task-a/results/result-a",
    selection: { id: "call-a", kind: "recognition" },
    close: jest.fn(),
  };
  const { rerender } = render(<ResultEvidenceDialog {...props} />);
  expect(within(screen.getByRole("dialog")).getByRole("status")).toBeVisible();
  mockQuery.mockReturnValue({
    data: undefined,
    isLoading: false,
    error: new Error("Saved request unavailable"),
  });
  rerender(<ResultEvidenceDialog {...props} />);
  expect(
    within(screen.getByRole("dialog")).getByRole("alert"),
  ).toHaveTextContent("Saved request unavailable");
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  expect(props.close).toHaveBeenCalled();
});

it("counts the actual JSON-text image manifest in the saved recognition summary", () => {
  mockQuery.mockReturnValue(
    state({
      kind: "recognition",
      request: {
        payload: {
          hospital: "HOSP-1",
          evidence: '["image-a","image-b","image-c"]',
        },
        response: {
          recognized_category: "人工膝关节",
          recognized_quantity: 1,
          simulated: true,
        },
        transport: "responded",
        remote: "completed",
        validity: "valid",
      },
    }),
  );
  render(
    <ResultEvidenceDialog
      base="tasks/a/results/r"
      selection={{ id: "request-evidence", kind: "recognition" }}
      close={jest.fn()}
    />,
  );
  const dialog = screen.getByRole("dialog");
  expect(within(dialog).getByText("3", { exact: true })).toBeVisible();
  expect(within(dialog).getByText("HOSP-1")).toBeVisible();
});

it("distinguishes policy from saved task state and uses the frozen template", async () => {
  mockQuery.mockImplementation((_path: string, enabled: boolean) =>
    state(
      enabled
        ? {
            saved: 2,
            incomplete: 1,
            different: 1,
            task_status: "completed",
            assessment: null,
            templates: [
              {
                id: "hip_knee_v1",
                name: "Published template",
                version: 1,
                columns: ["RPT_NO"],
                obligation: { mode: "verification" },
              },
            ],
          }
        : undefined,
    ),
  );
  const template = {
    id: "hip_knee_v1",
    name: "Draft template",
    version: 2,
    columns: ["CNT"],
    obligation: {},
  };
  const { rerender } = render(<ResultStorage template={template} />);
  expect(screen.getByText(/No task selected/)).toBeVisible();
  expect(screen.queryByText(/Business results saved:/)).not.toBeInTheDocument();
  rerender(<ResultStorage taskId="task-a" template={template} />);
  expect(screen.getByText("Business results saved: 2")).toBeVisible();
  expect(
    screen.getByText(
      /Results with differences: 1; results with unfinished checks: 1/,
    ),
  ).toBeVisible();
  fireEvent.click(
    screen.getByRole("button", {
      name: /Retention fields and technical details/i,
    }),
  );
  const dialog = await screen.findByRole("dialog");
  await waitFor(() =>
    expect(within(dialog).getByText("Published template · v1")).toBeVisible(),
  );
  expect(within(dialog).queryByText(/Draft template/)).not.toBeInTheDocument();
});
