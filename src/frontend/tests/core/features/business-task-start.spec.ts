import fs from "node:fs";
import { expect, test } from "../../fixtures";
import { awaitBootstrapTest } from "../../utils/await-bootstrap-test";

test(
  "regulatory task entry displays the selected request without editing the canvas",
  { tag: ["@release", "@api", "@workspace"] },
  async ({ page }) => {
    test.skip(
      !process.env.BUSINESS_TASK_START_REPORT,
      "Requires local task-start acceptance tasks",
    );
    const report = JSON.parse(
      fs.readFileSync(process.env.BUSINESS_TASK_START_REPORT!, "utf8"),
    );
    await page.route(/\/api\/v1\/store\/tags(\?.*)?$/, (route) =>
      route.fulfill({ json: [] }),
    );
    await page.goto("/login", { waitUntil: "domcontentloaded" });
    await page
      .locator('input[name="username"], input[placeholder="Username"]')
      .first()
      .fill(process.env.BUSINESS_SMOKE_USER!);
    await page
      .locator('input[type="password"]')
      .fill(process.env.BUSINESS_SMOKE_PASSWORD!);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL((url) => !url.pathname.includes("login"));
    await awaitBootstrapTest(page, { skipModal: true, seedFlowIfEmpty: false });
    await page.goto(`/flow/${report.flow_id}`, {
      waitUntil: "domcontentloaded",
    });
    const panel = page.getByTestId("business-canvas-configuration");
    await expect(panel).toBeVisible({ timeout: 60_000 });
    await page.locator('.react-flow__node[data-id="Request"]').click();
    const input = page.getByTestId("business-task-input");
    await expect(input).toBeVisible();
    await expect(input.getByText("Not received", { exact: true })).toHaveCount(
      9,
    );
    await expect(input.getByRole("textbox")).toHaveCount(0);
    await expect(input.getByRole("checkbox")).toHaveCount(0);
    for (const entry of report.tasks) {
      await input
        .getByRole("combobox", { name: "View task" })
        .selectOption(entry.id);
      const values = input.getByTestId("business-task-input-values");
      await expect(
        values.getByText(entry.input.parameters.hospital_name, { exact: true }),
      ).toBeVisible();
      await expect(
        values.getByText(entry.input.parameters.start, { exact: true }),
      ).toBeVisible();
      await expect(
        values.getByText(entry.input.task.external_task_id, { exact: true }),
      ).toBeAttached();
    }
    await expect(
      input.getByText(report.tasks[0].input.parameters.hospital_name, {
        exact: true,
      }),
    ).toHaveCount(0);
    await page.screenshot({
      path: test.info().outputPath("task-input-selected.png"),
      fullPage: true,
    });
    // The source node still discovers its parameter names before a task is selected.
    await page.locator('.react-flow__node[data-id="Settlements"]').click();
    await expect(
      panel.getByRole("combobox", { name: "Parameter", exact: true }).first(),
    ).toHaveValue("hospital_name");
    const choices = await panel
      .getByRole("combobox", { name: "Parameter", exact: true })
      .first()
      .locator("option")
      .allTextContents();
    expect(choices).toEqual(
      expect.arrayContaining([
        "hospital_name",
        "start",
        "end",
        "external_task_id",
      ]),
    );
    await page.goto(`/business/tasks/${report.tasks[0].id}`, {
      waitUntil: "domcontentloaded",
    });
    await expect(
      page
        .getByTestId("business-task-input-values")
        .getByText("MOCK-REG-1", { exact: true }),
    ).toBeVisible({ timeout: 60_000 });
    // The migrated core canvas exposes the fixed contract; it has no accepted tasks yet.
    await page.goto("/flow/e55b03b0-7c7f-420b-b720-33b1a4cf5559", {
      waitUntil: "domcontentloaded",
    });
    await expect(panel).toBeVisible({ timeout: 60_000 });
    await page.getByTestId("canvas_controls_dropdown").click();
    await page.getByTestId("fit_view").click();
    await page.keyboard.press("Escape");
    await page.locator('.react-flow__node[data-id="Request"]').click();
    await expect(input).toBeVisible();
    await expect(input.getByText("Not received", { exact: true })).toHaveCount(
      9,
    );
    await expect(panel.getByText("Enum", { exact: true })).toHaveCount(0);
    await page.screenshot({
      path: test.info().outputPath("core-task-start.png"),
      fullPage: true,
    });
  },
);
