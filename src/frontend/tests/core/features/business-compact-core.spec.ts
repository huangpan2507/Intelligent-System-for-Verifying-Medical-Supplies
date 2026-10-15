import fs from "node:fs";
import { expect, test } from "../../fixtures";
import { awaitBootstrapTest } from "../../utils/await-bootstrap-test";

test(
  "compact core canvas exposes reusable nodes and correctly scoped lookup fields",
  { tag: ["@release", "@api", "@workspace"] },
  async ({ page }) => {
    test.skip(
      !process.env.BUSINESS_COMPACT_REPORT,
      "Requires the local compact core acceptance task",
    );
    const report = JSON.parse(
      fs.readFileSync(process.env.BUSINESS_COMPACT_REPORT!, "utf8"),
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
    const selectNode = async (id: string) => {
      // Collapse the overlay to reach nodes behind the right-hand configuration panel.
      await panel
        .getByRole("button", { name: "Collapse", exact: true })
        .click();
      await page.getByTestId(`rf__node-${id}`).click();
      await panel.getByRole("button", { name: "Expand", exact: true }).click();
    };
    for (const display of [
      "Business Classification",
      "Business Database Lookup",
    ]) {
      await page.getByTestId("sidebar-search-input").fill(display);
      await expect(
        page.getByTestId(
          `add-component-button-${display.toLowerCase().replaceAll(" ", "-")}`,
        ),
      ).toBeVisible();
    }
    await page.getByTestId("sidebar-search-input").fill("");
    await page.getByTestId("canvas_controls_dropdown").click();
    await page.getByTestId("fit_view").click();
    await page.keyboard.press("Escape");
    await expect(page.locator(".react-flow__node")).toHaveCount(11);
    const expandSection = async (id: string) => {
      const section = panel.getByTestId(`configuration-section-${id}`);
      if ((await section.getAttribute("open")) === null)
        await section.locator(":scope > summary").click();
    };
    await selectNode("Request");
    await expect(panel.getByRole("textbox")).toHaveCount(0);
    await expect(
      panel.getByTestId("configuration-section-task-business"),
    ).toContainText("Hospital name");
    await panel.getByRole("button", { name: /^Widen view$/i }).click();
    await expect(panel).toHaveClass(/w-\[56rem\]/);
    await page.screenshot({
      path: test.info().outputPath("task-start-wide.png"),
      fullPage: true,
    });
    await panel.getByRole("button", { name: /^Narrow view$/i }).click();
    const taskChoice = panel.getByRole("combobox", {
      name: "View task",
      exact: true,
    });
    await expect(
      taskChoice.locator(`option[value="${report.task_id}"]`),
    ).toHaveCount(1);
    await taskChoice.selectOption(report.task_id);
    await expect(
      panel
        .getByTestId("configuration-section-task-business")
        .getByText("核心流程模拟医院", { exact: true }),
    ).toBeVisible();
    await expandSection("task-trace");
    await expect(
      panel
        .getByTestId("configuration-section-task-trace")
        .getByText(report.task_id, { exact: true }),
    ).toBeVisible();
    await taskChoice.selectOption("");
    await expect(
      panel.getByText("核心流程模拟医院", { exact: true }),
    ).toHaveCount(0);
    await selectNode("Settlements");
    await expect(
      panel.getByRole("combobox", {
        name: "Schema (namespace within the database)",
        exact: true,
      }),
    ).toHaveValue("public");
    await expect(
      panel.getByRole("combobox", { name: "Table", exact: true }),
    ).toHaveValue("core_flow_settlement_v1");
    await expect(
      panel
        .getByTestId("configuration-section-database-range")
        .getByRole("combobox", { name: "Field", exact: true }),
    ).toHaveCount(6);
    await expect(
      panel.getByRole("textbox", { name: "Sql", exact: true }),
    ).not.toBeVisible();
    await panel.getByRole("button", { name: /Widen Editor/i }).click();
    await page.screenshot({
      path: test.info().outputPath("settlements-wide.png"),
      fullPage: true,
    });
    await selectNode("SettlementChecks");
    await expect(
      panel.getByRole("textbox", { name: "Namespace", exact: true }),
    ).toHaveCount(0);
    await expect(
      panel.getByTestId("configuration-section-identity"),
    ).toContainText("ORGAN_CODE + DATA_SOURCE + SETL_FEE_LIST_ID");
    await panel
      .getByText("System-managed identity details (read-only)", { exact: true })
      .click();
    await expect(
      panel.getByText("core-flow-v1", { exact: true }),
    ).toBeVisible();
    await expandSection("quality");
    const qualityOps = panel
      .getByTestId("configuration-section-quality")
      .getByRole("combobox", { name: "Op", exact: true });
    await expect(qualityOps).toHaveCount(2);
    await expect(qualityOps.first()).toHaveValue("ge");
    await expect(qualityOps.last()).toHaveValue("ge");
    await page.screenshot({
      path: test.info().outputPath("settlement-checks-wide.png"),
      fullPage: true,
    });
    await panel.getByRole("button", { name: /Narrow Editor/i }).click();
    await selectNode("Classification");
    await expandSection("classification-categories");

    await expect(
      panel.getByText("Classification", { exact: true }),
    ).toBeVisible();
    await expect(
      panel
        .getByTestId("configuration-section-classification-input")
        .locator(":scope > summary"),
    ).toBeVisible();
    await expect(
      panel.getByRole("combobox", { name: /^Field [1-5]$/ }),
    ).toHaveCount(5);
    await expect(
      panel.getByRole("group", { name: /^Rule [1-2]$/ }),
    ).toHaveCount(2);
    await expect(
      panel.getByText(
        "Shared evidence fields: PRODNAME · HOS_PROJ_NAME · MEDINS_LIST_NAME",
      ),
    ).toBeVisible();
    await expect(
      panel.getByRole("textbox", {
        name: "Unknown category label",
        exact: true,
      }),
    ).toHaveCount(0);
    await expect(
      panel.getByRole("textbox", { name: "Category 1", exact: true }),
    ).toHaveValue("人工髋关节");
    await expect(
      panel
        .getByRole("textbox", {
          name: "Keywords (comma separated)",
          exact: true,
        })
        .first(),
    ).toHaveValue("人工, 髋关节");
    await expect(panel.getByRole("alert")).toHaveCount(0);
    await page.screenshot({
      path: test.info().outputPath("classification-fields.png"),
      fullPage: true,
    });
    await expandSection("classification-model");
    await panel
      .getByText("Preview the complete system message", { exact: true })
      .click();
    await expect(
      panel.locator("pre").filter({ hasText: "allowed_categories" }),
    ).toContainText("model_evidence_text");
    await panel
      .getByRole("group", { name: "Rule 1", exact: true })
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: test.info().outputPath("classification-rules.png"),
      fullPage: true,
    });
    await panel.getByRole("button", { name: /Widen Editor/i }).click();
    await page.screenshot({
      path: test.info().outputPath("classification-wide.png"),
      fullPage: true,
    });
    await panel.getByRole("button", { name: /Narrow Editor/i }).click();
    await selectNode("StudyRelevance");
    await expandSection("classification-output");
    await expect(
      panel.getByRole("textbox", { name: "Result prefix", exact: true }),
    ).toHaveValue("study_relevance");
    await expect(
      panel.getByRole("combobox", { name: "Field 1", exact: true }),
    ).toHaveValue("study_relevance_code_name");
    await expect(
      panel.getByRole("group", { name: /^Rule [1-4]$/ }),
    ).toHaveCount(4);
    await expect(panel.getByRole("alert")).toHaveCount(0);
    await page.screenshot({
      path: test.info().outputPath("study-relevance.png"),
      fullPage: true,
    });
    for (const [id, table, left, right] of [
      ["Studies", "INSPECTION_INFO_RECORD", "RPT_NO", "rpt_no"],
      ["Series", "SERIES_INFO", "study_ris_study_id", "ris_study_id"],
    ]) {
      await selectNode(id);
      await expect(
        panel.getByRole("combobox", { name: "Table", exact: true }),
      ).toHaveValue(table);
      const keys = panel.getByTestId("business-field-keys").first();
      await expect(
        keys.getByRole("combobox", { name: "Left", exact: true }).nth(2),
      ).toHaveValue(left);
      await expect(
        keys.getByRole("combobox", { name: "Right", exact: true }).nth(2),
      ).toHaveValue(right);
      await expect(
        keys
          .getByRole("combobox", { name: "Right", exact: true })
          .nth(2)
          .locator(`option[value="${right}"]`),
      ).not.toHaveText(/unavailable/i);
      await expect(panel.getByRole("alert")).toHaveCount(0);
      await expect(panel.getByTestId(/^lookup-section-/)).toHaveCount(6);
      await expect(
        panel.getByRole("combobox", { name: "Database", exact: true }),
      ).toHaveValue("business_demo");
      await expect(
        panel.getByRole("textbox", { name: "Namespace", exact: true }),
      ).toHaveCount(0);
      if (id === "Studies") {
        await panel
          .getByTestId("lookup-section-returns")
          .locator(":scope > summary")
          .click();
        const fields = panel
          .getByTestId("business-field-returns")
          .getByRole("combobox", { name: "Field", exact: true });
        await expect(
          fields.locator("option:checked").filter({ hasText: "EXAM_PART" }),
        ).toHaveCount(1);
        await expect(
          panel.getByTestId("business-field-category_match"),
        ).toHaveCount(0);
        await panel
          .getByTestId("lookup-section-returns")
          .locator(":scope > summary")
          .click();
        await panel.getByRole("button", { name: /Widen Editor/i }).click();
        await expect(panel).toHaveClass(/w-\[56rem\]/);
        await page.screenshot({
          path: test.info().outputPath("studies-grouped-wide.png"),
          fullPage: true,
        });
        await panel
          .getByTestId("lookup-section-quality")
          .locator(":scope > summary")
          .click();
        await panel
          .getByText("System-managed identity details (read-only)", {
            exact: true,
          })
          .click();
        await expect(
          panel.getByText("core-study-v2", { exact: true }),
        ).toBeVisible();
        await page.screenshot({
          path: test.info().outputPath("studies-identity.png"),
          fullPage: true,
        });
        await panel.getByRole("button", { name: /Narrow Editor/i }).click();
      }
    }
    await page.screenshot({
      path: test.info().outputPath("compact-lookup.png"),
      fullPage: true,
    });
    await selectNode("Images");
    for (const group of [
      "service",
      "request",
      "validity",
      "collection",
      "contract",
      "test",
    ]) {
      await expect(
        panel.getByTestId(`configuration-section-api-${group}`),
      ).toBeVisible();
    }
    await panel.getByRole("button", { name: /Widen Editor/i }).click();
    await expect(panel).toHaveClass(/w-\[56rem\]/);
    await expect(panel.getByTestId("business-field-cursor_path")).toHaveCount(
      0,
    );
    await expect(
      panel.getByTestId("business-field-page_parameter"),
    ).toHaveCount(0);
    const collection = panel.getByTestId(
      "configuration-section-api-collection",
    );
    await expect(collection).toContainText("51 source fields + 7 derived");
    await collection.locator(":scope > summary").click();
    await collection
      .getByText("Addresses, item identifiers and per-item context", {
        exact: true,
      })
      .click();
    await expect(collection).toContainText("RPT_NO");
    await expect(
      collection.getByRole("textbox", { name: "Output", exact: true }),
    ).toHaveValue("image_manifest");
    await page.screenshot({
      path: test.info().outputPath("images-wide.png"),
      fullPage: true,
    });
    await panel.getByRole("button", { name: /Narrow Editor/i }).click();
    await page.screenshot({
      path: test.info().outputPath("images-narrow.png"),
      fullPage: true,
    });
    await selectNode("Observation");
    for (const group of [
      "service",
      "evidence",
      "scope",
      "validity",
      "output",
    ]) {
      await expect(
        panel.getByTestId(`configuration-section-imaging-${group}`),
      ).toBeVisible();
    }
    for (const key of ["quantity_field", "unit_field", "unit_value"]) {
      await expect(panel.getByTestId(`business-field-${key}`)).toHaveCount(0);
    }
    const scope = panel.getByTestId("configuration-section-imaging-scope");
    await expect(scope).toContainText("ORGAN_CODE");
    await expect(scope).toContainText("PSN_NO");
    await expect(scope).toContainText("OP_EM_NO");
    await scope.locator(":scope > summary").click();
    await scope.getByText("Edit field bindings", { exact: true }).click();
    await expect(
      scope.getByRole("combobox", { name: "Patient field", exact: true }),
    ).toHaveValue("PSN_NO");
    await expect(panel.getByRole("alert")).toHaveCount(0);
    await expect
      .poll(() => panel.evaluate((el) => el.scrollWidth <= el.clientWidth + 1))
      .toBe(true);
    await page.screenshot({
      path: test.info().outputPath("observation-narrow.png"),
      fullPage: true,
    });
    await panel.getByRole("button", { name: /Widen Editor/i }).click();
    await expect(panel).toHaveClass(/w-\[56rem\]/);
    await page.screenshot({
      path: test.info().outputPath("observation-wide.png"),
      fullPage: true,
    });
    await panel.getByRole("button", { name: /Narrow Editor/i }).click();
    await selectNode("Compare");
    await expect(
      panel.locator('[data-testid^="configuration-section-compare-"]'),
    ).toHaveCount(4);
    expect(
      await panel
        .locator('[data-testid^="configuration-section-compare-"]')
        .evaluateAll((elements) =>
          elements.map((el) => el.getAttribute("data-testid")),
        ),
    ).toEqual([
      "configuration-section-compare-source",
      "configuration-section-compare-calculations",
      "configuration-section-compare-comparisons",
      "configuration-section-compare-output",
    ]);
    await expect(panel.getByTestId("business-field-tolerance")).toHaveCount(0);
    await expect(panel.getByRole("alert")).toHaveCount(0);
    await expect(
      panel.getByTestId("configuration-section-compare-calculations"),
    ).toContainText("CNT * PRIC");
    await expect(
      panel.getByTestId("configuration-section-compare-comparisons"),
    ).toContainText("Numeric equality");
    await expect
      .poll(() => panel.evaluate((el) => el.scrollWidth <= el.clientWidth + 1))
      .toBe(true);
    await page.screenshot({
      path: test.info().outputPath("compare-narrow.png"),
      fullPage: true,
    });
    await panel.getByRole("button", { name: /Widen Editor/i }).click();
    await expect(panel).toHaveClass(/w-\[56rem\]/);
    const calculation = panel
      .getByText(/^Settlement-side calculated amount = CNT \* PRIC(?: \+ 0)?$/)
      .locator("..");
    await calculation.locator(":scope > summary").click();
    const expression = calculation.getByRole("textbox", {
      name: "Expression",
      exact: true,
    });
    try {
      await expression.fill("CNT * PRIC + 0");
      await expect(expression).toHaveValue("CNT * PRIC + 0");
    } finally {
      await expression.fill("CNT * PRIC");
    }
    await expect(
      calculation.getByRole("combobox", { name: "Field", exact: true }),
    ).toHaveCount(0);
    await page.screenshot({
      path: test.info().outputPath("compare-wide.png"),
      fullPage: true,
    });
    await panel.getByRole("button", { name: /Narrow Editor/i }).click();
    await page.keyboard.press("Control+s");
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(panel).toBeVisible({ timeout: 60_000 });
    await selectNode("Compare");
    await expect(
      panel.getByTestId("configuration-section-compare-calculations"),
    ).toContainText("CNT * PRIC");
    await expect(
      panel.getByTestId("configuration-section-compare-calculations"),
    ).not.toContainText("CNT * PRIC + 0");
    await selectNode("SettlementChecks");
    await panel
      .getByText("System-managed identity details (read-only)", { exact: true })
      .click();
    await expect(
      panel.getByText("core-flow-v1", { exact: true }),
    ).toBeVisible();
    await page.evaluate(() =>
      localStorage.setItem("languagePreference", "zh-Hans"),
    );
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(panel).toBeVisible({ timeout: 60_000 });
    await page.getByTestId("canvas_controls_dropdown").click();
    await page.getByTestId("fit_view").click();
    await page.keyboard.press("Escape");
    await panel.getByRole("button", { name: "收起", exact: true }).click();
    await page.getByTestId("rf__node-Classification").click();
    await panel.getByRole("button", { name: "展开", exact: true }).click();
    await expect(
      panel.getByTestId("configuration-section-classification-rules"),
    ).toContainText("判断规则与复核");
    await expect(panel).toContainText("上游数据集：SettlementChecks", {
      timeout: 60_000,
    });
    await expect
      .poll(() =>
        panel.evaluate(
          (element) => element.scrollWidth <= element.clientWidth + 1,
        ),
      )
      .toBe(true);
    await page.screenshot({
      path: test.info().outputPath("classification-zh-narrow.png"),
      fullPage: true,
    });
    await panel.getByRole("button", { name: "收起", exact: true }).click();
    await page.getByTestId("rf__node-Observation").click();
    await panel.getByRole("button", { name: "展开", exact: true }).click();
    await expect(
      panel.getByTestId("configuration-section-imaging-service"),
    ).toContainText("识别服务");
    await expect(
      panel.getByTestId("configuration-section-imaging-scope"),
    ).toContainText("影像属于谁");
    await expect(
      panel.getByTestId("configuration-section-imaging-validity"),
    ).toContainText("不做件／套换算");
    await expect(
      panel
        .getByTestId("configuration-section-imaging-validity")
        .locator(":scope > summary"),
    ).toContainText("识别数量 ≥ 0");
    await expect(panel.getByRole("alert")).toHaveCount(0);
    await expect
      .poll(() => panel.evaluate((el) => el.scrollWidth <= el.clientWidth + 1))
      .toBe(true);
    await page.screenshot({
      path: test.info().outputPath("observation-zh-narrow.png"),
      fullPage: true,
    });
    await panel.getByRole("button", { name: "收起", exact: true }).click();
    await page.getByTestId("rf__node-Compare").click();
    await panel.getByRole("button", { name: "展开", exact: true }).click();
    await expect(
      panel.getByTestId("configuration-section-compare-calculations"),
    ).toContainText("比较前计算");
    await expect(
      panel.getByTestId("configuration-section-compare-comparisons"),
    ).toContainText("数值相等");
    await expect(panel.getByRole("alert")).toHaveCount(0);
    await expect
      .poll(() => panel.evaluate((el) => el.scrollWidth <= el.clientWidth + 1))
      .toBe(true);
    await page.screenshot({
      path: test.info().outputPath("compare-zh-narrow.png"),
      fullPage: true,
    });
    await panel.getByRole("button", { name: "收起", exact: true }).click();
    await page.getByTestId("rf__node-Results").click();
    await panel.getByRole("button", { name: "展开", exact: true }).click();
    for (const id of ["template", "preview", "storage"]) {
      await expect(
        panel.getByTestId(`configuration-section-results-${id}`),
      ).toBeVisible();
    }
    await expect(panel.getByTestId("business-result-card")).toHaveCount(1);
    await expect(panel.getByTestId("business-result-card")).toContainText(
      "示例（未执行、未保存）",
    );
    await panel
      .getByTestId("configuration-section-results-preview")
      .getByRole("combobox")
      .selectOption(report.task_id);
    await expect(panel.getByTestId("business-result-card")).toHaveCount(2);
    await expect(
      panel.getByTestId("business-result-card").first(),
    ).toContainText("已保存至平台结果库");
    await expect(panel.getByRole("textbox")).toHaveCount(0);
    await expect(panel.getByRole("alert")).toHaveCount(0);
    await expect
      .poll(() => panel.evaluate((el) => el.scrollWidth <= el.clientWidth + 1))
      .toBe(true);
    await page.screenshot({
      path: test.info().outputPath("results-zh-narrow.png"),
      fullPage: true,
    });
    await panel.getByRole("button", { name: "宽编辑" }).click();
    await expect(panel).toHaveClass(/w-\[56rem\]/);
    await page.screenshot({
      path: test.info().outputPath("results-zh-wide.png"),
      fullPage: true,
    });
    await page.evaluate(() => localStorage.setItem("languagePreference", "en"));
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.goto(`/business/tasks/${report.task_id}`, {
      waitUntil: "domcontentloaded",
    });
    await expect(
      page.getByText("Execution status: Completed", { exact: true }),
    ).toBeVisible({ timeout: 60_000 });
    await page
      .getByText("Original and intermediate datasets (technical view)", {
        exact: true,
      })
      .click();
    await expect(
      page.getByText("MOCK-DETAIL-HIP", { exact: true }).first(),
    ).toBeVisible();
    await expect(
      page.getByText("MOCK-DETAIL-KNEE", { exact: true }).first(),
    ).toBeVisible();
    await page.screenshot({
      path: test.info().outputPath("compact-results.png"),
      fullPage: true,
    });
    await expect(page.getByTestId("business-result-card")).toHaveCount(2);
    const card = page.getByTestId("business-result-card").first();
    await card.getByText("Sources and evidence", { exact: true }).click();
    await expect(card.getByText(/Related studies and images/)).toBeVisible();
    await page.screenshot({
      path: test.info().outputPath("saved-result-evidence.png"),
      fullPage: true,
    });
    // Stop task polling before the fixture verifies that all requests settled.
    await page.goto("about:blank");
  },
);
