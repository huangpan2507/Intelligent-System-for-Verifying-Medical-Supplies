import fs from "node:fs";
import { expect, test } from "../../fixtures";
import { awaitBootstrapTest } from "../../utils/await-bootstrap-test";

test(
  "Business Chinese presentation preserves all configuration and source options",
  { tag: ["@release", "@workspace", "@components"] },
  async ({ page }) => {
    test.skip(
      !process.env.BUSINESS_SMOKE_PASSWORD,
      "Requires the existing local core flow and login",
    );
    await page.route(/\/api\/v1\/store\/tags(\?.*)?$/, (route) =>
      route.fulfill({ json: [] }),
    );
    await page.addInitScript(() =>
      localStorage.setItem("languagePreference", "en"),
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
    await page.goto(`/flow/${process.env.BUSINESS_FLOW_ID}`, {
      waitUntil: "domcontentloaded",
    });
    const panel = page.getByTestId("business-canvas-configuration");
    await expect(panel).toBeVisible({ timeout: 60_000 });
    await page.getByTestId("canvas_controls_dropdown").click();
    await page.getByTestId("fit_view").click();
    await page.keyboard.press("Escape");
    await expect(page.locator(".react-flow__node")).toHaveCount(11);
    const names = {
      Request: "任务入参",
      Settlements: "结算读取",
      SettlementChecks: "结算质量检查",
      Classification: "耗材分类",
      Studies: "检查关联",
      StudyRelevance: "检查适用性判断",
      Series: "序列关联",
      Images: "影像清单",
      Observation: "影像识别",
      Compare: "耗材核验",
      Results: "结果输出",
    };
    const evidence: unknown[] = [];
    for (const [id, title] of Object.entries(names)) {
      const node = page.getByTestId(`rf__node-${id}`);
      await expect(node.getByTestId("node-name")).toHaveText(title);
      const collapse = panel.getByRole("button", { name: "收起", exact: true });
      if (await collapse.isVisible()) await collapse.click();
      await node.click();
      await panel.getByRole("button", { name: "展开", exact: true }).click();
      await expect(
        panel.getByText(title, { exact: true }).first(),
      ).toBeVisible();
      if (id === "Settlements") {
        await expect(
          panel.getByRole("combobox", { name: "表或视图" }),
        ).toHaveValue("core_flow_settlement_v1");
        await expect(
          panel.locator('option[value="ORGAN_NAME"]').first(),
        ).toHaveText(/ORGAN_NAME/);
        await expect(
          panel.locator('option[value="hospital_name"]').first(),
        ).toHaveText("hospital_name");
      }
      if (
        [
          "Classification",
          "Studies",
          "Images",
          "Observation",
          "Compare",
          "Results",
        ].includes(id)
      )
        await page.screenshot({
          path: test.info().outputPath(`${id}.png`),
          fullPage: true,
        });
      evidence.push({
        id,
        title,
        controls: await panel
          .locator("input, textarea, select")
          .evaluateAll((els) =>
            els.map((el) => ({
              value: (el as HTMLInputElement).value,
              options:
                el.tagName === "SELECT"
                  ? Array.from((el as HTMLSelectElement).options).map((o) => ({
                      value: o.value,
                      text: o.textContent,
                    }))
                  : undefined,
            })),
          ),
      });
    }
    // Chinese names must also be discoverable without changing palette payloads.
    await page.getByTestId("sidebar-search-input").fill("数据质量检查");
    await expect(
      page.getByTestId("display-name").filter({ hasText: "数据质量检查" }),
    ).toBeVisible({ timeout: 15_000 });
    await page.screenshot({
      path: test.info().outputPath("palette.png"),
      fullPage: true,
    });
    expect(
      await page.evaluate(() => localStorage.getItem("languagePreference")),
    ).toBe("en");
    fs.writeFileSync(
      test.info().outputPath("controls.json"),
      JSON.stringify(evidence, null, 2),
    );
  },
);
