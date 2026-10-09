import { expect, test } from "../../fixtures";
import { awaitBootstrapTest } from "../../utils/await-bootstrap-test";

test(
  "save a rule draft, validate, publish, activate and inspect its immutable version",
  {
    tag: ["@release", "@api", "@workspace"],
  },
  async ({ page }) => {
    test.skip(
      process.env.VERIFICATION_E2E !== "1",
      "Requires the opt-in verification simulation services",
    );
    const password = process.env.LANGFLOW_SUPERUSER_PASSWORD;
    const flowId = process.env.VERIFICATION_DRAFT_FLOW_ID;
    if (!password || !flowId)
      throw new Error(
        "Configure the simulation account and import a draft first",
      );
    // The public component store is unrelated to verification and unavailable locally.
    await page.route("**/api/v1/store/tags", (route) =>
      route.fulfill({ json: [] }),
    );
    await page.addInitScript(() =>
      localStorage.setItem("languagePreference", "en"),
    );
    await page.goto("/login");
    await page.locator("#login-username").fill("verification-admin");
    await page.locator("input[type=password]").fill(password);
    await page.getByRole("button", { name: /^Sign in$/i }).click();
    await page.waitForURL((url) => !url.pathname.includes("login"));
    await awaitBootstrapTest(page, {
      skipGoto: true,
      skipModal: true,
      seedFlowIfEmpty: false,
    });
    await page
      .getByRole("button", { name: "Verification Rules", exact: true })
      .click();
    const code = process.env.VERIFICATION_E2E_RULE_CODE ?? `ui_${Date.now()}`;
    const name = process.env.VERIFICATION_E2E_RULE_NAME ?? code;
    const exists = await page
      .getByLabel("Rule selection")
      .locator(`option[value="${code}"]`)
      .count();
    if (process.env.VERIFICATION_E2E_REUSE === "1" || exists) {
      await page.getByLabel("Rule selection").selectOption(code);
    } else {
      await page.getByLabel("Rule name", { exact: true }).fill(name);
      await page.getByLabel("Stable rule code").fill(code);
      await page.getByLabel("Draft flow", { exact: true }).selectOption(flowId);
      await page
        .getByRole("button", { name: "Register Rule", exact: true })
        .click();
    }
    await expect(page.getByLabel("Rule selection")).toHaveValue(code);
    await expect(
      page.getByRole("button", { name: "Publish Version", exact: true }),
    ).toBeDisabled();
    await page
      .getByLabel("Release note")
      .fill("Browser validated simulation version");
    await page.getByRole("button", { name: /^Save rule draft$/i }).click();
    await expect(page.getByRole("main").getByRole("status")).toContainText(
      "Rule catalog draft saved",
    );
    await page.reload();
    await page.getByLabel("Rule selection").selectOption(code);
    await expect(page.getByLabel("Release note")).toHaveValue(
      "Browser validated simulation version",
    );
    await page
      .getByRole("button", { name: "Check Saved Draft", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Publish Version", exact: true }),
    ).toBeEnabled();
    await page
      .getByRole("button", { name: "Publish Version", exact: true })
      .click();
    await expect(page.getByRole("main").getByRole("status")).toContainText(
      "v1 published",
    );
    await page
      .getByRole("button", { name: "Activate Version", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Active", exact: true }),
    ).toBeDisabled();
    const preview = page.getByRole("region", {
      name: "Published flow, read-only",
    });
    await expect(preview).toBeVisible();
    await expect(preview.locator(".react-flow__node")).toHaveCount(10);
    await preview
      .getByLabel("Node parameters")
      .selectOption({ label: "01 结算快照" });
    await expect(preview).toContainText("http://127.0.0.1:8090");
    await page.screenshot({
      path: "../../deploy/verification/.cache/release-ui-tests/rules-published.png",
      fullPage: true,
    });
  },
);
