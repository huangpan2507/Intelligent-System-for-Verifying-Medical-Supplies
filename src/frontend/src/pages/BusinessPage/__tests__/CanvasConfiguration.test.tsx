import { act, fireEvent, render, screen } from "@testing-library/react";
import type { JsonSchema } from "@/controllers/API/queries/business";
import useFlowStore from "@/stores/flowStore";
import type { AllNodeType } from "@/types/flow";
import CanvasConfiguration from "../CanvasConfiguration";

jest.mock("@/stores/flowStore", () => {
  const { create } = jest.requireActual("zustand");
  return {
    __esModule: true,
    default: create((set) => ({
      nodes: [],
      edges: [],
      setNode: (id, change) =>
        set((state) => ({
          nodes: state.nodes.map((node) =>
            node.id === id ? change(node) : node,
          ),
        })),
    })),
  };
});

const databaseSchema: JsonSchema = {
  type: "object",
  properties: {
    connection: { type: "string", format: "connection" },
    table: { type: "string", format: "table" },
    schema: { type: "string", format: "database_schema" },
    conditions: { type: "array", items: {} },
    sql: { type: "string", format: "multiline" },
    parameters: { type: "array", items: { type: "string" } },
    fields: { type: "array", items: {} },
  },
  required: ["connection"],
};
const mockInspect = jest.fn();
const mockMutate = jest.fn();
const mockQuery = jest.fn();
let mockDefaultSchema: string | undefined;
const lookupSchema: JsonSchema = {
  type: "object",
  properties: {
    connection: databaseSchema.properties!.connection,
    schema: databaseSchema.properties!.schema,
    table: databaseSchema.properties!.table,
    keys: {
      type: "array",
      items: {
        type: "object",
        properties: {
          left: { type: "string", format: "field" },
          right: { type: "string", format: "field:database" },
        },
      },
    },
  },
};

jest.mock("@/controllers/API/queries/business", () => ({
  useBusinessQuery: (path: string, enabled: boolean) => {
    mockQuery(path, enabled);
    return {
      data:
        path === "catalog"
          ? {
              nodes: {
                database: { schema: databaseSchema },
                databaselookup: { schema: lookupSchema },
              },
            }
          : path === "connections"
            ? [{ id: "postgres", name: "PostgreSQL", kind: "postgresql" }]
            : {
                default_schema: mockDefaultSchema,
                tables: ["payments", "orders"],
                schemas: ["public", "audit"],
                fields: [{ name: "rpt_no", type: "text" }],
              },
    };
  },
  useInspectBusiness: () => ({ mutate: mockInspect }),
  useBusinessUpload: () => ({ mutate: mockMutate }),
  useBusinessMutation: () => ({ mutate: mockMutate, isPending: false }),
}));

function databaseNode(id: string, config = {}, selected = false): AllNodeType {
  return {
    id,
    type: "genericNode",
    position: { x: 0, y: 0 },
    selected,
    data: {
      id,
      type: "ext:business:BusinessDatabase@extra",
      node: {
        display_name: "Business Database",
        description: "Persistent business datasets: database",
        documentation: "",
        template: {
          configuration: {
            type: "str",
            required: false,
            list: false,
            show: true,
            readonly: false,
            value: JSON.stringify(config),
          },
        },
      },
    },
  };
}

function selectNode(id: string | null) {
  act(() => {
    useFlowStore.setState((state) => ({
      nodes: state.nodes.map((node) => ({
        ...node,
        selected: node.id === id,
      })),
    }));
  });
}

function configureDatabase() {
  fireEvent.change(screen.getByRole("combobox", { name: "Connection" }), {
    target: { value: "postgres" },
  });
  fireEvent.change(screen.getByRole("combobox", { name: "Table" }), {
    target: { value: "payments" },
  });
}

describe("business canvas configuration", () => {
  const originalStructuredClone = global.structuredClone;

  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    mockDefaultSchema = undefined;
    // jsdom does not provide structuredClone; node data here is JSON only.
    global.structuredClone = (value) => JSON.parse(JSON.stringify(value));
    useFlowStore.setState({
      nodes: [databaseNode("Database-A", {}, true), databaseNode("Database-B")],
      edges: [],
    });
  });

  afterEach(() => {
    global.structuredClone = originalStructuredClone;
    jest.useRealTimers();
  });

  it("preselects only a reflected default schema and retains an existing selection", () => {
    mockDefaultSchema = "audit";
    render(<CanvasConfiguration />);
    configureDatabase();
    expect(
      screen.getByRole("combobox", {
        name: "Schema (namespace within the database)",
      }),
    ).toHaveValue("audit");
    fireEvent.change(
      screen.getByRole("combobox", {
        name: "Schema (namespace within the database)",
      }),
      { target: { value: "public" } },
    );
    selectNode("Database-B");
    selectNode("Database-A");
    expect(
      screen.getByRole("combobox", {
        name: "Schema (namespace within the database)",
      }),
    ).toHaveValue("public");
  });

  it("does not invent a schema when the reported default is unavailable", () => {
    mockDefaultSchema = "unavailable";
    render(<CanvasConfiguration />);
    configureDatabase();
    expect(
      screen.getByRole("combobox", {
        name: "Schema (namespace within the database)",
      }),
    ).toHaveValue("");
  });

  it("renders one set of fields through configuration edits and inspection updates", () => {
    render(<CanvasConfiguration />);
    configureDatabase();
    fireEvent.change(
      screen.getByRole("combobox", {
        name: "Schema (namespace within the database)",
      }),
      {
        target: { value: "public" },
      },
    );
    act(() => jest.advanceTimersByTime(700));
    act(() => {
      mockInspect.mock.calls.at(-1)[1].onSuccess({ schemas: {}, errors: {} });
    });

    for (const name of [
      "Connection",
      "Table",
      "Schema (namespace within the database)",
    ])
      expect(screen.getAllByRole("combobox", { name })).toHaveLength(1);
    for (const name of ["Sql"])
      expect(screen.getAllByRole("textbox", { name })).toHaveLength(1);
    expect(
      screen.getAllByTestId("configuration-section-database-range"),
    ).toHaveLength(1);
    expect(
      screen.queryByText("Parameters", { exact: true }),
    ).not.toBeInTheDocument();
    expect(screen.getAllByText("Fields", { exact: true })).toHaveLength(1);
    expect(
      screen.getByRole("combobox", {
        name: "Schema (namespace within the database)",
      }),
    ).toHaveValue("public");
  });

  it("switches between configured and empty database nodes without retaining old fields", () => {
    render(<CanvasConfiguration />);
    configureDatabase();
    selectNode("Database-B");

    const connections = screen.getAllByRole("combobox", { name: "Connection" });
    expect(connections).toHaveLength(1);
    expect(connections[0]).toHaveValue("");
    expect(screen.getByRole("combobox", { name: "Table" })).toHaveValue("");

    configureDatabase();
    fireEvent.change(screen.getByRole("combobox", { name: "Table" }), {
      target: { value: "orders" },
    });
    selectNode("Database-A");
    expect(screen.getByRole("combobox", { name: "Table" })).toHaveValue(
      "payments",
    );
    selectNode("Database-B");
    expect(screen.getByRole("combobox", { name: "Table" })).toHaveValue(
      "orders",
    );
  });

  it("clears configuration controls when a configured node is deselected", () => {
    render(<CanvasConfiguration />);
    configureDatabase();
    selectNode(null);
    expect(
      screen.queryAllByRole("combobox", { name: "Connection" }),
    ).toHaveLength(0);
    expect(screen.queryAllByRole("combobox", { name: "Table" })).toHaveLength(
      0,
    );
  });

  it("includes the selected schema in both metadata requests", () => {
    render(<CanvasConfiguration />);
    configureDatabase();
    fireEvent.change(
      screen.getByRole("combobox", {
        name: "Schema (namespace within the database)",
      }),
      {
        target: { value: "audit" },
      },
    );
    expect(mockQuery).toHaveBeenCalledWith(
      "connections/postgres/schema?schema=audit",
      true,
    );
    expect(mockQuery).toHaveBeenCalledWith(
      "connections/postgres/schema?table=payments&schema=audit",
      true,
    );
  });

  it("keeps upstream and database lookup field choices separate", () => {
    const source = databaseNode("Settlements");
    const lookup = databaseNode(
      "Lookup",
      {
        connection: "postgres",
        schema: "public",
        table: "orders",
        keys: [{ left: "RPT_NO", right: "rpt_no" }],
      },
      true,
    );
    lookup.data.type = "ext:business:BusinessDatabaselookup@extra";
    useFlowStore.setState({
      nodes: [source, lookup],
      edges: [{ id: "source-lookup", source: "Settlements", target: "Lookup" }],
    });
    render(<CanvasConfiguration />);
    act(() => jest.advanceTimersByTime(700));
    act(() =>
      mockInspect.mock.calls.at(-1)[1].onSuccess({
        schemas: { Settlements: { data: [{ name: "RPT_NO", type: "text" }] } },
        errors: {},
      }),
    );
    const left = screen.getByRole("combobox", { name: "Left" });
    const right = screen.getByRole("combobox", { name: "Right" });
    expect(left).toHaveValue("RPT_NO");
    expect(right).toHaveValue("rpt_no");
    expect(
      Array.from((left as HTMLSelectElement).options).map(
        (option) => option.value,
      ),
    ).not.toContain("rpt_no");
    expect(
      Array.from((right as HTMLSelectElement).options).map(
        (option) => option.value,
      ),
    ).not.toContain("RPT_NO");
    expect(mockQuery).toHaveBeenCalledWith(
      "connections/postgres/schema?table=orders&schema=public",
      true,
    );
  });

  it("ignores an older inspection after the graph configuration changes", () => {
    render(<CanvasConfiguration />);
    configureDatabase();
    act(() => jest.advanceTimersByTime(700));
    const previous = mockInspect.mock.calls.at(-1)[1];
    fireEvent.change(screen.getByRole("combobox", { name: "Table" }), {
      target: { value: "orders" },
    });
    act(() => jest.advanceTimersByTime(700));
    act(() =>
      mockInspect.mock.calls.at(-1)[1].onSuccess({ schemas: {}, errors: {} }),
    );
    act(() =>
      previous.onSuccess({
        schemas: {},
        errors: { "Database-A": "stale error" },
      }),
    );
    expect(screen.queryByText("stale error")).not.toBeInTheDocument();
  });

  it("discards database previews returned after switching source configuration", () => {
    render(<CanvasConfiguration />);
    configureDatabase();
    fireEvent.click(screen.getByText(/Preview up to 25 rows/i));
    const callback = mockMutate.mock.calls.at(-1)[1];
    fireEvent.change(screen.getByRole("combobox", { name: "Table" }), {
      target: { value: "orders" },
    });
    act(() =>
      callback.onSuccess({
        fields: [{ name: "old_column", type: "text" }],
        rows: [{ old_column: "stale" }],
      }),
    );
    expect(screen.queryByText("old_column")).not.toBeInTheDocument();
  });
});
