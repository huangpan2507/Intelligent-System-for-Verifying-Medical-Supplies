import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { Locator } from "@playwright/test";
import { expect as baseExpect, test } from "../../fixtures";
import { awaitBootstrapTest } from "../../utils/await-bootstrap-test";
import { parameters, steps } from "./business-core-flow.recipe";
import english from "../../../src/locales/en.json";

const expect = baseExpect.configure({ timeout: 45_000 });
const label = (key: string) =>
  english[`business.field.${key}` as keyof typeof english] ?? key;

test(
  "build and execute the normal database and imaging core path from an empty canvas",
  { tag: ["@release", "@api", "@workspace", "@components", "@database"] },
  async ({ page }) => {
    test.skip(
      !process.env.BUSINESS_CORE_EVIDENCE,
      "Requires the dedicated local synthetic sources",
    );
    const directory = process.env.BUSINESS_CORE_EVIDENCE!;
    mkdirSync(directory, { recursive: true });
    const checkpoint = join(directory, "canvas-checkpoint.json");
    const state = existsSync(checkpoint)
      ? JSON.parse(readFileSync(checkpoint, "utf8"))
      : {
          code: `core.normal.${Date.now()}`,
          name: "髋膝关节正常核心流程（数据库＋API）",
          ids: {},
          completed: [],
        };
    const save = () =>
      writeFileSync(checkpoint, JSON.stringify(state, null, 2));
    const readApi = async (path: string) => {
      const response = await page.request.get(`/api/v1/business/${path}`, {
        headers: { Authorization: `Bearer ${process.env.BUSINESS_CORE_TOKEN}` },
      });
      expect(response.ok(), path).toBe(true);
      return response.json();
    };
    const browserErrors: string[] = [];
    page.on("pageerror", (error) => browserErrors.push(error.message));
    await page.route(/\/api\/v1\/store\/tags(\?.*)?$/, (route) =>
      route.fulfill({ json: [] }),
    );
    console.log("Opening login");
    await page.goto("/login", { waitUntil: "domcontentloaded" });
    console.log("Waiting for login form");
    await page
      .locator('input[name="username"], input[placeholder="Username"]')
      .first()
      .fill(process.env.BUSINESS_SMOKE_USER!);
    await page
      .locator('input[type="password"]')
      .fill(process.env.BUSINESS_SMOKE_PASSWORD!);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL((url) => !url.pathname.includes("login"));
    console.log("Signed in; waiting for application bootstrap");
    await awaitBootstrapTest(page, {
      skipGoto: true,
      skipModal: true,
      seedFlowIfEmpty: false,
    });
    const catalog = await readApi("catalog");
    console.log("Catalog loaded");
    await page.getByRole("button", { name: /^Schemes$/i }).click();
    if (!state.flow) {
      const form = page.locator("form");
      await form.getByLabel("Name", { exact: true }).fill(state.name);
      await form.getByLabel("Code", { exact: true }).fill(state.code);
      await form.getByLabel("Starting template").selectOption("empty");
      const created = page.waitForResponse(
        (r) =>
          r.url().endsWith("/business/schemes") &&
          r.request().method() === "POST",
      );
      await form.getByRole("button", { name: /^Create scheme$/i }).click();
      const response = await created;
      expect(response.ok()).toBe(true);
      state.flow = (await response.json()).flow_id;
      save();
    }
    await page.locator(`a[href="/flow/${state.flow}"]`).click();
    const panel = page.getByTestId("business-canvas-configuration");
    await expect(panel).toBeVisible();
    const fit = async () => {
      await page.getByTestId("canvas_controls_dropdown").click();
      await page.getByTestId("fit_view").click();
      await page.keyboard.press("Escape");
    };
    const select = async (name: string) => {
      const node = page.locator(
        `.react-flow__node[data-id="${state.ids[name]}"]`,
      );
      await node.focus();
      await node.press("Enter");
      await expect(node).toHaveClass(/selected/);
      if (await panel.getByRole("button", { name: /^Expand$/i }).isVisible())
        await panel.getByRole("button", { name: /^Expand$/i }).click();
    };
    const choose = async (element: Locator, value: string) => {
      await expect(
        element.locator("option").filter({ hasText: /./ }),
      ).not.toHaveCount(0);
      await expect
        .poll(async () =>
          element
            .locator("option")
            .evaluateAll(
              (options, v) =>
                options.some((o) => (o as HTMLOptionElement).value === v),
              value,
            ),
        )
        .toBe(true);
      await element.selectOption(value);
    };
    const bind = async (root: Locator, body: Record<string, any>) => {
      while (
        await root
          .getByRole("textbox", { name: "Request property name", exact: true })
          .count()
      ) {
        await root
          .getByRole("button", { name: /^Remove$/i })
          .last()
          .click();
      }
      for (const [key, value] of Object.entries(body)) {
        await root
          .getByRole("button", { name: /^Add request property$/i })
          .last()
          .click();
        const keyInput = root
          .getByRole("textbox", { name: "Request property name", exact: true })
          .last();
        await keyInput.fill(key);
        const row = root.locator(":scope > div > div.rounded.border").last();
        const mode =
          typeof value === "object" && value !== null
            ? Object.keys(value)[0]
            : "constant";
        await row
          .getByRole("combobox", { name: "Value source", exact: true })
          .selectOption(mode);
        if (mode === "constant")
          await row
            .getByRole("textbox", { name: "Constant (JSON)", exact: true })
            .fill(JSON.stringify(value));
        else
          await choose(
            row.getByRole("combobox", {
              name: mode === "field" ? "Upstream field" : "Task parameter",
              exact: true,
            }),
            value[mode],
          );
      }
    };
    const fill = async (
      root: Locator,
      schema: any,
      value: any,
      name = "configuration",
    ) => {
      if (schema.format === "condition") {
        await fill(
          root,
          {
            type: "object",
            properties: {
              field: schema.properties.field,
              op: schema.properties.op,
            },
          },
          { field: value.field, op: value.op },
        );
        const key =
          "parameter" in value
            ? "parameter"
            : "right_field" in value
              ? "right_field"
              : "value";
        if (!["is_null", "not_null"].includes(value.op)) {
          await root
            .getByRole("combobox", { name: "Value source", exact: true })
            .selectOption(key);
          await fill(root, schema.properties[key], value[key], key);
        }
      } else if (name === "body") {
        await bind(root, value);
      } else if (schema.type === "object" && schema.properties) {
        for (const [key, child] of Object.entries(value)) {
          const wrapper = root.getByTestId(`business-field-${key}`).first();
          await fill(wrapper, schema.properties[key], child, key);
        }
      } else if (schema.type === "array") {
        // Existing entries are only possible when resuming an interrupted UI edit.
        const rows = root.locator(":scope > div > div.rounded.border");
        while (await rows.count())
          await rows
            .last()
            .getByRole("button", { name: /^Remove$/i })
            .last()
            .click();
        for (let i = 0; i < value.length; i++) {
          await root
            .getByRole("button", { name: /^Add item$/i })
            .last()
            .click();
          await fill(rows.nth(i), schema.items, value[i], name);
        }
      } else if (schema.type === "boolean") {
        await root
          .getByRole("checkbox", { name: label(name), exact: true })
          .setChecked(value);
      } else if (
        schema.enum ||
        schema.format?.startsWith("field") ||
        [
          "connection",
          "table",
          "database_schema",
          "parameter",
          "node",
          "output_port",
        ].includes(schema.format)
      ) {
        await choose(
          root.getByRole("combobox", { name: label(name), exact: true }),
          String(value),
        );
      } else {
        const input =
          schema.type === "integer" || schema.type === "number"
            ? root.getByRole("spinbutton")
            : root.getByRole("textbox", { name: label(name), exact: true });
        await input.fill(schema.type ? String(value) : JSON.stringify(value));
      }
    };
    const resolve = (value: any): any =>
      typeof value === "string" && value.startsWith("@")
        ? state.ids[value.slice(1)]
        : Array.isArray(value)
          ? value.map(resolve)
          : value && typeof value === "object"
            ? Object.fromEntries(
                Object.entries(value).map(([k, v]) => [k, resolve(v)]),
              )
            : value;
    const arrange = async (name: string) => {
      if (state.arranged?.includes(name)) return;
      const node = page.locator(
        `.react-flow__node[data-id="${state.ids[name]}"]`,
      );
      await node.focus();
      await node.press("Enter");
      await expect(node).toHaveClass(/selected/);
      const position = await node.evaluate((element) => {
        const matrix = new DOMMatrix(getComputedStyle(element).transform);
        return { x: matrix.m41, y: matrix.m42 };
      });
      const index = steps.findIndex((step) => step.name === name);
      // Native keyboard movement preserves the same undo/save behavior as manual layout.
      for (const [delta, positive, negative] of [
        [(index % 6) * 500 - position.x, "ArrowRight", "ArrowLeft"],
        [Math.floor(index / 6) * 600 - position.y, "ArrowDown", "ArrowUp"],
      ] as const) {
        for (let i = 0; i < Math.round(Math.abs(delta) / 20); i++)
          await page.keyboard.press(
            `Shift+${delta >= 0 ? positive : negative}`,
          );
      }
      state.arranged = [...(state.arranged ?? []), name];
      save();
    };
    if (!state.ids.Request) {
      await expect(page.locator(".react-flow__node")).toHaveCount(1);
      state.ids.Request = await page
        .locator(".react-flow__node")
        .getAttribute("data-id");
      state.started_empty = true;
      save();
      await page.screenshot({ path: join(directory, "empty-canvas.png") });
    }
    for (const name of Object.keys(state.ids)) await arrange(name);
    for (const step of steps) {
      if (state.completed.includes(step.name)) continue;
      console.log(`Configuring ${step.name} (${step.kind})`);
      const display = `Business ${step.kind.charAt(0).toUpperCase() + step.kind.slice(1)}`;
      if (!state.ids[step.name]) {
        const candidate = page
          .locator(".react-flow__node")
          .filter({ has: page.getByTestId(`title-${display}`) })
          .last();
        if (!(await candidate.count())) {
          const count = await page.locator(".react-flow__node").count();
          await page.getByTestId("sidebar-search-input").fill(display);
          await page
            .getByTestId(
              `add-component-button-${display.toLowerCase().replaceAll(" ", "-")}`,
            )
            .click();
          await expect(page.locator(".react-flow__node")).toHaveCount(
            count + 1,
          );
        }
        await fit();
        state.ids[step.name] = await candidate.getAttribute("data-id");
        save();
      }
      const node = page.locator(
        `.react-flow__node[data-id="${state.ids[step.name]}"]`,
      );
      if (!(await node.getByTestId(`title-${step.name}`).count())) {
        await node.getByTestId(`title-${display}`).click({ force: true });
        await node
          .getByTestId("node-edit-name-description-button")
          .click({ force: true });
        await node.getByTestId(`input-title-${display}`).fill(step.name);
        await node.getByTestId(`input-title-${display}`).press("Enter");
        save();
      }
      await arrange(step.name);
      // Wire through the visible canvas handles, never through a store or graph API.
      if (step.from && !state.wired?.includes(step.name)) {
        if (
          await panel.getByRole("button", { name: /^Collapse$/i }).isVisible()
        )
          await panel.getByRole("button", { name: /^Collapse$/i }).click();
        await fit();
        const sources = Array.isArray(step.from) ? step.from : [step.from];
        for (let i = 0; i < sources.length; i++) {
          const source = page.locator(
            `.react-flow__node[data-id="${state.ids[sources[i]]}"]`,
          );
          const target = page.locator(
            `.react-flow__node[data-id="${state.ids[step.name]}"]`,
          );
          const input =
            step.kind === "join" ? (i === 0 ? "left" : "right") : "data";
          const previousEdges = await page.locator(".react-flow__edge").count();
          const outgoing = source.locator(".react-flow__handle.source");
          const sourceId = await outgoing.evaluateAll(
            (handles, port) =>
              handles
                .find((h) => {
                  const text = h.getAttribute("data-handleid") || "";
                  return text.includes(`œnameœ:œ${port}œ`);
                })
                ?.getAttribute("data-handleid"),
            step.port ?? "data",
          );
          expect(
            sourceId,
            `output ${sources[i]}.${step.port ?? "data"}`,
          ).toBeTruthy();
          const index = await outgoing.evaluateAll(
            (handles, id) =>
              handles.findIndex((h) => h.getAttribute("data-handleid") === id),
            sourceId,
          );
          await outgoing.nth(index).click({ force: true });
          const incoming = target.locator(".react-flow__handle.target");
          const targetIndex = await incoming.evaluateAll(
            (handles, field) =>
              handles.findIndex((h) =>
                (h.getAttribute("data-handleid") || "").includes(
                  `œfieldNameœ:œinput_${field}œ`,
                ),
              ),
            input,
          );
          expect(targetIndex).toBeGreaterThanOrEqual(0);
          await incoming.nth(targetIndex).click({ force: true });
          await expect(page.locator(".react-flow__edge")).toHaveCount(
            previousEdges + 1,
          );
        }
        state.wired = [...(state.wired ?? []), step.name];
        save();
      }
      await select(step.name);
      await fill(panel, catalog.nodes[step.kind].schema, resolve(step.config));
      if (step.contract) {
        const details = panel.locator("details").filter({
          has: page.locator("summary", { hasText: "Provider contract" }),
        });
        await details.locator("summary").click();
        await details
          .getByLabel("Document source and version")
          .fill(step.reference!);
        const schema = {
          type: "object",
          properties: {
            data: {
              type: "array",
              items: {
                type: "object",
                required: Object.keys(step.contract),
                properties: Object.fromEntries(
                  Object.entries(step.contract).map(([name, type]) => [
                    name,
                    { type },
                  ]),
                ),
              },
            },
          },
        };
        await details
          .getByLabel("Response JSON Schema or OpenAPI JSON")
          .fill(JSON.stringify(schema));
        await details
          .getByRole("button", { name: /^Import contract fields$/i })
          .click();
      }
      // Wait for schema propagation through the same inspection used by field dropdowns.
      await expect
        .poll(
          async () => {
            const alerts = await panel
              .locator('[role="alert"]')
              .allTextContents();
            return alerts.filter(Boolean);
          },
          { timeout: 60_000 },
        )
        .toEqual([]);
      state.completed.push(step.name);
      save();
    }
    await page.getByTestId("sidebar-search-input").fill("");
    if (await panel.getByRole("button", { name: /^Collapse$/i }).isVisible())
      await panel.getByRole("button", { name: /^Collapse$/i }).click();
    await fit();
    await page.keyboard.press("Control+s");
    let savedCanvas: any;
    await expect(async () => {
      const response = await page.request.get(`/api/v1/flows/${state.flow}`, {
        headers: { Authorization: `Bearer ${process.env.BUSINESS_CORE_TOKEN}` },
      });
      expect(response.ok()).toBe(true);
      savedCanvas = await response.json();
      expect(savedCanvas.data.nodes).toHaveLength(steps.length);
      for (const step of steps) {
        const node = savedCanvas.data.nodes.find(
          (node: any) => node.id === state.ids[step.name],
        );
        expect(
          JSON.parse(node.data.node.template.configuration.value),
        ).toMatchObject(resolve(step.config));
      }
    }).toPass({ timeout: 30_000 });
    const edgeKeys = (edges: any[]) =>
      edges.map((edge) => JSON.stringify(edge)).sort();
    const expectedEdges = steps.flatMap((step) => {
      const sources = step.from
        ? Array.isArray(step.from)
          ? step.from
          : [step.from]
        : [];
      return sources.map((source, index) => [
        state.ids[source],
        step.port ?? "data",
        state.ids[step.name],
        step.kind === "join" ? (index === 0 ? "left" : "right") : "data",
      ]);
    });
    expect(
      edgeKeys(
        savedCanvas.data.edges.map((edge: any) => [
          edge.source,
          edge.data.sourceHandle.name,
          edge.target,
          edge.data.targetHandle.fieldName.replace(/^input_/, ""),
        ]),
      ),
    ).toEqual(edgeKeys(expectedEdges));
    writeFileSync(
      join(directory, "saved-canvas.json"),
      JSON.stringify(savedCanvas, null, 2),
    );
    await page.screenshot({ path: join(directory, "configured-canvas.png") });
    await page.getByRole("button", { name: /^Schemes$/i }).click();
    const card = page
      .locator("section")
      .filter({
        has: page.getByRole("heading", { name: state.name, exact: true }),
      })
      .filter({ hasText: state.code });
    const published = page.waitForResponse(
      (r) =>
        r.url().endsWith(`/business/schemes/${state.code}/releases`) &&
        r.request().method() === "POST",
    );
    await card
      .getByRole("button", { name: /^Validate and publish saved canvas$/i })
      .click();
    const publication = await published;
    expect(publication.ok(), await publication.text()).toBe(true);
    state.release = (await publication.json()).id;
    save();
    await card
      .getByRole("button", { name: /^Activate$/i })
      .first()
      .click();
    await card.getByRole("button", { name: /^Submit test task$/i }).click();
    const submitted = page.waitForResponse(
      (r) =>
        r.url().endsWith("/business/tasks") && r.request().method() === "POST",
    );
    await card.getByRole("button", { name: /^Run task$/i }).click();
    const response = await submitted;
    expect(response.ok(), await response.text()).toBe(true);
    state.task = (await response.json()).id;
    save();
    let task: any;
    await expect
      .poll(
        async () => {
          task = await readApi(`tasks/${state.task}`);
          return task.status;
        },
        { timeout: 180_000, intervals: [1000, 2000] },
      )
      .toBe("completed");
    writeFileSync(join(directory, "task.json"), JSON.stringify(task, null, 2));
    expect(task.parameters).toEqual(parameters);
    expect(task.assessment.state).toBe("accounted");
    expect(task.assessment.received_records).toBe(2);
    const expectedCounts = {
      Settlements: 2,
      Studies: 2,
      Series: 2,
      Images: 4,
      Manifests: 2,
      Observation: 2,
      Results: 2,
    };
    for (const [name, count] of Object.entries(expectedCounts)) {
      const dataset = task.datasets.find(
        (d: any) => d.node_id === state.ids[name] && d.port === "data",
      );
      expect(dataset?.row_count, name).toBe(count);
    }
    const result = task.datasets.find(
      (d: any) => d.node_id === state.ids.Results && d.port === "data",
    );
    const output = await readApi(`tasks/${state.task}/datasets/${result.id}`);
    writeFileSync(
      join(directory, "results.json"),
      JSON.stringify(output, null, 2),
    );
    expect(output.rows).toHaveLength(2);
    for (const row of output.rows) {
      expect([
        row.category_status,
        row.quantity_status,
        row.amount_status,
      ]).toEqual(["equal", "equal", "equal"]);
      expect(Number(row.CNT)).toBe(1);
      expect(Number(row.recognized_quantity)).toBe(1);
      expect(Number(row.difference_0)).toBe(0);
      expect(Number(row.difference_1)).toBe(0);
      expect(JSON.parse(row.image_manifest)).toHaveLength(2);
      expect(row.simulated).toBe(true);
    }
    await page.goto(`/business/tasks/${state.task}`);
    await expect(
      page.getByRole("heading", {
        name: "Accountability and business results",
      }),
    ).toBeVisible();
    await page.screenshot({
      path: join(directory, "completed-task.png"),
      fullPage: true,
    });
    expect(browserErrors).toEqual([]);
    state.accepted = true;
    save();
  },
);
