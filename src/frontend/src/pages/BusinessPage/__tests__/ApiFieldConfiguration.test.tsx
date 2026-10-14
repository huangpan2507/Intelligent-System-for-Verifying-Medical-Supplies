import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import ApiFieldConfiguration from "../ApiFieldConfiguration";
import RequestBodyEditor from "../RequestBodyEditor";

const mockMutate = jest.fn();
jest.mock("@/controllers/API/queries/business", () => ({
  useBusinessMutation: () => ({ mutate: mockMutate, isPending: false }),
}));
const config = {
  connection: "api",
  path: "/lookup",
  items_path: "items",
  fields: [{ name: "code", type: "text" }],
};
const evidence = {
  kind: "sample",
  source: {},
  fields: [{ name: "code", type: "text" }],
  proof: "server-proof",
};
const onApply = jest.fn();
const onPreview = jest.fn();
const props = { config, onApply, onPreview, upstreamRows: [] };

beforeEach(() => jest.clearAllMocks());

it("does not request the API while editing and adopts documented fields explicitly", () => {
  render(<ApiFieldConfiguration {...props} />);
  expect(mockMutate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("Provider contract"));
  fireEvent.change(screen.getByLabelText("Document source and version"), {
    target: { value: "Provider manual v1" },
  });
  expect(mockMutate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText(/Apply documented fields/i));
  expect(mockMutate.mock.calls[0][0]).toMatchObject({
    path: "connections/api/contract",
    body: { reference: "Provider manual v1", fields: config.fields },
  });
  act(() =>
    mockMutate.mock.calls[0][1].onSuccess({
      fields: config.fields,
      field_evidence: { ...evidence, kind: "document" },
    }),
  );
  expect(onApply).toHaveBeenCalledWith(
    config.fields,
    expect.objectContaining({ kind: "document" }),
  );
});

it("keeps a contract when the API returns an empty record array", () => {
  render(<ApiFieldConfiguration {...props} />);
  fireEvent.click(screen.getByText("Test request and discover fields"));
  fireEvent.click(screen.getByText(/Send one test request/i));
  act(() =>
    mockMutate.mock.calls[0][1].onSuccess({
      fields: [],
      rows: [],
      field_evidence: { ...evidence, fields: [] },
    }),
  );
  expect(screen.getByText(/No sample records/)).toBeInTheDocument();
  expect(
    screen.getByText(/Confirm types and adopt sample fields/i),
  ).toBeDisabled();
  expect(onApply).not.toHaveBeenCalled();
});

it("uses an existing preview row only as test input and locks discovered field names", () => {
  render(
    <ApiFieldConfiguration
      {...props}
      upstreamRows={[{ label: "Database · 1", row: { patient_id: "P001" } }]}
    />,
  );
  fireEvent.click(screen.getByText("Test request and discover fields"));
  fireEvent.change(
    screen.getByLabelText("Choose an existing upstream preview row"),
    { target: { value: "0" } },
  );
  fireEvent.click(screen.getByText(/Send one test request/i));
  expect(mockMutate.mock.calls[0][0].body.record).toEqual({
    patient_id: "P001",
  });
  expect(mockMutate.mock.calls[0][0].body.config).toEqual(config);
  act(() =>
    mockMutate.mock.calls[0][1].onSuccess({
      fields: evidence.fields,
      rows: [{ code: "A" }],
      field_evidence: evidence,
    }),
  );
  const names = screen.getAllByLabelText("Name") as HTMLInputElement[];
  expect(names.some((input) => input.value === "code" && input.readOnly)).toBe(
    true,
  );
  fireEvent.click(screen.getByText(/Confirm types and adopt sample fields/i));
  expect(onApply).toHaveBeenCalledWith(evidence.fields, evidence);
});

it("ignores API discovery returned for an older configuration", () => {
  const view = render(<ApiFieldConfiguration {...props} />);
  fireEvent.click(screen.getByText("Test request and discover fields"));
  fireEvent.click(screen.getByText(/Send one test request/i));
  const callback = mockMutate.mock.calls[0][1];
  view.rerender(
    <ApiFieldConfiguration
      {...props}
      config={{ ...config, path: "/different" }}
    />,
  );
  act(() =>
    callback.onSuccess({
      fields: evidence.fields,
      rows: [{ code: "stale" }],
      field_evidence: evidence,
    }),
  );
  expect(onPreview).not.toHaveBeenCalled();
  expect(onApply).not.toHaveBeenCalled();
  expect(screen.queryByText(/stale/)).not.toBeInTheDocument();
});

it("binds nested API request values using available upstream fields", () => {
  function Body() {
    const [body, setBody] = useState<unknown>({
      patient: { field: "missing" },
    });
    return (
      <>
        <RequestBodyEditor
          value={body}
          onChange={setBody}
          fields={[{ name: "patient_id", type: "text" }]}
          parameters={[]}
        />
        <pre>{JSON.stringify(body)}</pre>
      </>
    );
  }
  render(<Body />);
  expect(
    screen.getByText("missing (unavailable; reselect)"),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Upstream field"), {
    target: { value: "patient_id" },
  });
  expect(
    screen.getByText('{"patient":{"field":"patient_id"}}'),
  ).toBeInTheDocument();
});
