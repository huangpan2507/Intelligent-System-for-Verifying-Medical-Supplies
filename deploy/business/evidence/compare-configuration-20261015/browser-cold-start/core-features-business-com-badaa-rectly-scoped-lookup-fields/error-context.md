# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: core/features/business-compact-core.spec.ts >> compact core canvas exposes reusable nodes and correctly scoped lookup fields
- Location: tests/core/features/business-compact-core.spec.ts:5:5

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByTestId('business-canvas-configuration')
Expected: visible
Timeout: 60000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 60000ms
  - waiting for getByTestId('business-canvas-configuration')

```

```yaml
- banner:
  - button "Go to home"
  - button "Starter Project"
  - text: /
  - button "Edit flow details and settings for 髋膝关节正常核心流程（数据库＋API，精简11节点）" [disabled]
  - button "Tasks And Results"
  - button "Schemes"
  - button "Go to GitHub repo"
  - button "Go to Discord server"
  - button "Notifications and errors"
  - button "User":
    - img "User"
- navigation "Components sidebar":
  - list:
    - listitem:
      - button "Components"
    - listitem:
      - button "MCP"
    - listitem:
      - button "Bundles"
    - listitem:
      - button "Versions"
    - listitem:
      - button "Agent"
    - listitem:
      - button "Memories"
    - listitem:
      - button "Traces"
  - searchbox "Components"
  - img /
  - button "New Custom Component" [disabled]
- main:
  - status: Loading...
- region "Notifications":
  - status
```

# Test source

```ts
  1   | import fs from "node:fs";
  2   | import { expect, test } from "../../fixtures";
  3   | import { awaitBootstrapTest } from "../../utils/await-bootstrap-test";
  4   | 
  5   | test(
  6   |   "compact core canvas exposes reusable nodes and correctly scoped lookup fields",
  7   |   { tag: ["@release", "@api", "@workspace"] },
  8   |   async ({ page }) => {
  9   |     test.skip(
  10  |       !process.env.BUSINESS_COMPACT_REPORT,
  11  |       "Requires the local compact core acceptance task",
  12  |     );
  13  |     const report = JSON.parse(
  14  |       fs.readFileSync(process.env.BUSINESS_COMPACT_REPORT!, "utf8"),
  15  |     );
  16  |     await page.route(/\/api\/v1\/store\/tags(\?.*)?$/, (route) =>
  17  |       route.fulfill({ json: [] }),
  18  |     );
  19  |     await page.goto("/login", { waitUntil: "domcontentloaded" });
  20  |     await page
  21  |       .locator('input[name="username"], input[placeholder="Username"]')
  22  |       .first()
  23  |       .fill(process.env.BUSINESS_SMOKE_USER!);
  24  |     await page
  25  |       .locator('input[type="password"]')
  26  |       .fill(process.env.BUSINESS_SMOKE_PASSWORD!);
  27  |     await page.locator('button[type="submit"]').click();
  28  |     await page.waitForURL((url) => !url.pathname.includes("login"));
  29  |     await awaitBootstrapTest(page, { skipModal: true, seedFlowIfEmpty: false });
  30  |     await page.goto(`/flow/${report.flow_id}`, {
  31  |       waitUntil: "domcontentloaded",
  32  |     });
  33  |     const panel = page.getByTestId("business-canvas-configuration");
> 34  |     await expect(panel).toBeVisible({ timeout: 60_000 });
      |                         ^ Error: expect(locator).toBeVisible() failed
  35  |     const selectNode = async (id: string) => {
  36  |       // Collapse the overlay to reach nodes behind the right-hand configuration panel.
  37  |       await panel
  38  |         .getByRole("button", { name: "Collapse", exact: true })
  39  |         .click();
  40  |       await page.getByTestId(`rf__node-${id}`).click();
  41  |       await panel.getByRole("button", { name: "Expand", exact: true }).click();
  42  |     };
  43  |     for (const display of [
  44  |       "Business Classification",
  45  |       "Business Database Lookup",
  46  |     ]) {
  47  |       await page.getByTestId("sidebar-search-input").fill(display);
  48  |       await expect(
  49  |         page.getByTestId(
  50  |           `add-component-button-${display.toLowerCase().replaceAll(" ", "-")}`,
  51  |         ),
  52  |       ).toBeVisible();
  53  |     }
  54  |     await page.getByTestId("sidebar-search-input").fill("");
  55  |     await page.getByTestId("canvas_controls_dropdown").click();
  56  |     await page.getByTestId("fit_view").click();
  57  |     await page.keyboard.press("Escape");
  58  |     await expect(page.locator(".react-flow__node")).toHaveCount(11);
  59  |     const expandSection = async (id: string) => {
  60  |       const section = panel.getByTestId(`configuration-section-${id}`);
  61  |       if ((await section.getAttribute("open")) === null)
  62  |         await section.locator(":scope > summary").click();
  63  |     };
  64  |     await selectNode("Request");
  65  |     await expect(panel.getByRole("textbox")).toHaveCount(0);
  66  |     await expect(
  67  |       panel.getByTestId("configuration-section-task-business"),
  68  |     ).toContainText("Hospital name");
  69  |     await panel.getByRole("button", { name: /^Widen view$/i }).click();
  70  |     await expect(panel).toHaveClass(/w-\[56rem\]/);
  71  |     await page.screenshot({
  72  |       path: test.info().outputPath("task-start-wide.png"),
  73  |       fullPage: true,
  74  |     });
  75  |     await panel.getByRole("button", { name: /^Narrow view$/i }).click();
  76  |     const taskChoice = panel.getByRole("combobox", {
  77  |       name: "View task",
  78  |       exact: true,
  79  |     });
  80  |     await expect(
  81  |       taskChoice.locator(`option[value="${report.task_id}"]`),
  82  |     ).toHaveCount(1);
  83  |     await taskChoice.selectOption(report.task_id);
  84  |     await expect(
  85  |       panel
  86  |         .getByTestId("configuration-section-task-business")
  87  |         .getByText("核心流程模拟医院", { exact: true }),
  88  |     ).toBeVisible();
  89  |     await expandSection("task-trace");
  90  |     await expect(
  91  |       panel
  92  |         .getByTestId("configuration-section-task-trace")
  93  |         .getByText(report.task_id, { exact: true }),
  94  |     ).toBeVisible();
  95  |     await taskChoice.selectOption("");
  96  |     await expect(
  97  |       panel.getByText("核心流程模拟医院", { exact: true }),
  98  |     ).toHaveCount(0);
  99  |     await selectNode("Settlements");
  100 |     await expect(
  101 |       panel.getByRole("combobox", {
  102 |         name: "Schema (namespace within the database)",
  103 |         exact: true,
  104 |       }),
  105 |     ).toHaveValue("public");
  106 |     await expect(
  107 |       panel.getByRole("combobox", { name: "Table", exact: true }),
  108 |     ).toHaveValue("core_flow_settlement_v1");
  109 |     await expect(
  110 |       panel
  111 |         .getByTestId("configuration-section-database-range")
  112 |         .getByRole("combobox", { name: "Field", exact: true }),
  113 |     ).toHaveCount(6);
  114 |     await expect(
  115 |       panel.getByRole("textbox", { name: "Sql", exact: true }),
  116 |     ).not.toBeVisible();
  117 |     await panel.getByRole("button", { name: /Widen Editor/i }).click();
  118 |     await page.screenshot({
  119 |       path: test.info().outputPath("settlements-wide.png"),
  120 |       fullPage: true,
  121 |     });
  122 |     await selectNode("SettlementChecks");
  123 |     await expect(
  124 |       panel.getByRole("textbox", { name: "Namespace", exact: true }),
  125 |     ).toHaveCount(0);
  126 |     await expect(
  127 |       panel.getByTestId("configuration-section-identity"),
  128 |     ).toContainText("ORGAN_CODE + DATA_SOURCE + SETL_FEE_LIST_ID");
  129 |     await panel
  130 |       .getByText("System-managed identity details (read-only)", { exact: true })
  131 |       .click();
  132 |     await expect(
  133 |       panel.getByText("core-flow-v1", { exact: true }),
  134 |     ).toBeVisible();
```