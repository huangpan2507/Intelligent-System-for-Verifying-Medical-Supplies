import { expect as baseExpect, test } from "../../fixtures";
import { awaitBootstrapTest } from "../../utils/await-bootstrap-test";

const expect = baseExpect.configure({ timeout: 60_000 });

test(
  "published business obligations and request receipts are visible",
  { tag: ["@release", "@api", "@workspace"] },
  async ({ page }) => {
    test.skip(
      !process.env.BUSINESS_REFACTORING_TASK,
      "Requires the dedicated local business acceptance task",
    );
    // The external template store is outside this local business acceptance scope.
    await page.route(/\/api\/v1\/store\/tags(\?.*)?$/, (route) =>
      route.fulfill({ json: [] }),
    );
    const browserErrors: string[] = [];
    page.on("pageerror", (error) => browserErrors.push(error.message));
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
    await page.goto("/business", { waitUntil: "domcontentloaded" });
    await expect(
      page.getByRole("heading", { name: "Task maintenance window" }),
    ).toBeVisible();
    await expect(page.getByText(/^Accepting new tasks ·/)).toBeVisible();

    const taskId = process.env.BUSINESS_REFACTORING_TASK!;
    const receipt = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/api/v1/business/tasks/${taskId}`) &&
        response.status() === 200,
    );
    await page.goto(`/business/tasks/${taskId}`, {
      waitUntil: "domcontentloaded",
    });
    const task = await (await receipt).json();
    expect(task.assessment.state).toBe("accounted");
    await expect(
      page.getByRole("heading", {
        name: "Accountability and business results",
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("columnheader", { name: "Uncompared", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /^category$/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /^quantity$/i }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /^fee$/i })).toBeVisible();
    await expect(page.locator("table").last().locator("tbody tr")).toHaveCount(
      task.assessment.received_records,
    );
    await page
      .getByText("Model and professional service requests", { exact: true })
      .click();
    const request = page
      .locator("details details")
      .filter({ hasText: "Imaging" })
      .first();
    await expect(request).toBeVisible();
    await request.locator("summary").click();
    await expect(
      request.getByText("Business input sent", { exact: true }),
    ).toBeVisible();
    await expect(request).toContainText("synthetic://");
    await page.screenshot({
      path: test.info().outputPath("results-and-requests.png"),
      fullPage: true,
    });

    await page.goto(`/flow/${process.env.BUSINESS_REFACTORING_FLOW}`, {
      waitUntil: "domcontentloaded",
    });
    const panel = page.getByTestId("business-canvas-configuration");
    await expect(panel).toBeVisible({ timeout: 60_000 });
    await page.getByTestId("canvas_controls_dropdown").click();
    await page.getByTestId("fit_view").click();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("fit_view")).not.toBeVisible();
    const resultNode = page.locator('.react-flow__node[data-id="Results"]');
    await resultNode.getByText("Results", { exact: true }).click();
    await expect(resultNode).toHaveClass(/selected/);
    await expect(panel.getByText("Obligation", { exact: true })).toBeVisible();
    await expect(
      panel.getByRole("combobox", { name: "Node", exact: true }).first(),
    ).toHaveValue("Settlements");
    await expect(
      panel.getByRole("combobox", { name: "Identity", exact: true }),
    ).toHaveValue("SettlementChecks");
    await panel
      .getByText("Obligation", { exact: true })
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: test.info().outputPath("canvas-obligation.png"),
      fullPage: true,
    });
    expect(browserErrors).toEqual([]);
  },
);
