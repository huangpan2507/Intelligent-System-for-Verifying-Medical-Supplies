import fs from "node:fs";
import { expect, test } from "../../fixtures";
import { awaitBootstrapTest } from "../../utils/await-bootstrap-test";

test(
  "saved result evidence is readable from the canvas and task page without executing",
  {
    tag: ["@release", "@api", "@workspace"],
  },
  async ({ page }) => {
    test.skip(
      !process.env.BUSINESS_EVIDENCE_REPORT,
      "Requires saved local core results",
    );
    const report = JSON.parse(
      fs.readFileSync(process.env.BUSINESS_EVIDENCE_REPORT!, "utf8"),
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
    await page.getByTestId("canvas_controls_dropdown").click();
    await page.getByTestId("fit_view").click();
    await page.keyboard.press("Escape");
    await expect(page.locator(".react-flow__node")).toHaveCount(11);
    await panel.getByRole("button", { name: "Collapse", exact: true }).click();
    await page.getByTestId("rf__node-Results").click();
    await panel.getByRole("button", { name: "Expand", exact: true }).click();
    const storage = panel.getByTestId("configuration-section-results-storage");
    await storage.locator(":scope > summary").click();
    await expect(storage.getByText(/No task selected/)).toBeVisible();
    const choice = panel.getByRole("combobox", {
      name: "View task",
      exact: true,
    });
    await expect(
      choice.locator(`option[value="${report.task_id}"]`),
    ).toHaveCount(1);
    await choice.selectOption(report.task_id);
    await expect(panel.getByTestId("business-result-card")).toHaveCount(2);
    await expect(storage.getByText("Business results saved: 2")).toBeVisible();
    await expect(storage.getByText("Coverage policy (technical)")).toHaveCount(
      0,
    );
    const mutations: string[] = [];
    page.on("request", (request) => {
      if (
        request.url().includes("/api/v1/business/") &&
        request.method() !== "GET"
      )
        mutations.push(
          request.method() + " " + new URL(request.url()).pathname,
        );
    });
    const hip = panel
      .getByTestId("business-result-card")
      .filter({ hasText: "MOCK-RPT-HIP" });
    await hip.getByText("Sources and evidence", { exact: true }).click();
    await expect(
      hip.getByText("3 study records · 3 series records · 7 image addresses"),
    ).toBeVisible();
    await hip.getByText(/^Settlement details ·/).click();
    await hip
      .locator("summary")
      .filter({ hasText: /^Settlement detail ·/ })
      .click();
    const sourceButton = hip
      .getByRole("button", { name: /View source record 1/i })
      .first();
    await sourceButton.click();
    const dialog = page.getByTestId("result-evidence-dialog");
    await expect(
      dialog.getByText("MOCK-DETAIL-HIP", { exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: test.info().outputPath("settlement-snapshot.png"),
      fullPage: true,
    });
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(sourceButton).toBeFocused();
    await hip.getByText(/^Related studies and images ·/).click();
    await hip
      .locator("summary")
      .filter({ hasText: /^Study ·/ })
      .first()
      .click();
    await hip
      .locator("summary")
      .filter({ hasText: /^Series ·/ })
      .first()
      .click();
    const image = hip
      .locator("details")
      .filter({
        has: page.locator(":scope > summary", { hasText: /^Image ·/ }),
      })
      .first();
    await image.locator(":scope > summary").click();
    await image.getByRole("button", { name: /View source record 1/i }).click();
    await expect(dialog.getByText("file_path", { exact: true })).toBeVisible();
    await page.screenshot({
      path: test.info().outputPath("image-source.png"),
      fullPage: true,
    });
    await expect(storage).toHaveCount(1);
    await dialog.getByRole("button", { name: "Close", exact: true }).click();
    await expect(dialog).toBeHidden();
    await expect(storage).toHaveCount(1);
    await hip.getByText(/^Recognition calls ·/).click();
    await hip
      .locator("summary")
      .filter({ hasText: /^Recognition call$/ })
      .click();
    const requestButton = hip.getByRole("button", {
      name: /View saved recognition request and response/i,
    });
    await requestButton.click();
    await expect(
      dialog.getByRole("tab", { name: /Returned result/i }),
    ).toBeVisible();
    await expect(
      dialog.getByText("人工髋关节", { exact: true }).first(),
    ).toBeVisible();
    await dialog.getByRole("tab", { name: /Sent content/i }).click();
    await expect(
      dialog.getByRole("tab", { name: /Sent content/i }),
    ).toHaveAttribute("aria-selected", "true");
    await expect(dialog.getByText(/^MOCKHOSP\d+$/).first()).toBeVisible();
    await page.screenshot({
      path: test.info().outputPath("recognition-dialog.png"),
      fullPage: true,
    });
    await dialog.getByRole("button", { name: "Close", exact: true }).click();
    await expect(dialog).toBeHidden();
    await expect(requestButton).toBeFocused();
    await panel.getByRole("button", { name: /^Widen editor$/i }).click();
    await hip
      .getByText("Sources and evidence", { exact: true })
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: test.info().outputPath("evidence-wide.png"),
      fullPage: true,
    });
    await storage
      .getByRole("button", { name: /Retention fields and technical details/i })
      .click();
    await expect(
      page.getByRole("dialog").getByText(/^Settlement facts ·/),
    ).toBeVisible();
    await page.screenshot({
      path: test.info().outputPath("storage-details.png"),
      fullPage: true,
    });
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Close", exact: true })
      .click();
    const knee = panel
      .getByTestId("business-result-card")
      .filter({ hasText: "MOCK-RPT-KNEE" });
    await knee.getByText("Sources and evidence", { exact: true }).click();
    await expect(
      knee.getByText("2 study records · 2 series records · 5 image addresses"),
    ).toBeVisible();
    await choice.selectOption("");
    await expect(panel.getByText(/No task selected/)).toBeVisible();
    await expect(panel.getByText(/Business results saved:/)).toHaveCount(0);
    await page.evaluate(() =>
      localStorage.setItem("languagePreference", "zh-Hans"),
    );
    await page.goto(`/business/tasks/${report.task_id}`, {
      waitUntil: "domcontentloaded",
    });
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("business-result-card")).toHaveCount(2, {
      timeout: 60_000,
    });
    const taskHip = page
      .getByTestId("business-result-card")
      .filter({ hasText: "MOCK-RPT-HIP" });
    await taskHip.getByText("来源与证据", { exact: true }).click();
    await expect(
      taskHip.getByText("检查记录 3 条 · 序列记录 3 条 · 影像地址 7 个"),
    ).toBeVisible();
    await taskHip.getByText(/^关联检查与影像/).click();
    const studies = taskHip.locator("summary").filter({ hasText: /^检查 ·/ });
    await expect(studies).toHaveCount(3);
    await expect(studies.first()).toBeVisible();
    await expect(taskHip.getByRole("alert")).toHaveCount(0);
    await page.screenshot({
      path: test.info().outputPath("task-evidence-zh.png"),
      fullPage: true,
    });
    expect(mutations).toEqual([]);
    await page.goto("about:blank");
  },
);
