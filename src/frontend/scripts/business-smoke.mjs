import path from "node:path";
import { expect as baseExpect, chromium } from "@playwright/test";

const expect = baseExpect.configure({ timeout: 60000 });
const base = process.env.BUSINESS_SMOKE_BASE_URL || "http://127.0.0.1:13001";
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.BUSINESS_CHROMIUM_EXECUTABLE,
});
const context = await browser.newContext();
const page = await context.newPage();
page.setDefaultTimeout(60000);
page.setDefaultNavigationTimeout(120000);
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
try {
  await page.goto(`${base}/login`, { waitUntil: "domcontentloaded" });
  await page
    .locator('input[name="username"], input[placeholder="Username"]')
    .first()
    .fill(process.env.BUSINESS_SMOKE_USER);
  await page
    .locator('input[type="password"]')
    .fill(process.env.BUSINESS_SMOKE_PASSWORD);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((url) => !url.pathname.includes("/login"));
  await page.goto(`${base}/business`, { waitUntil: "domcontentloaded" });
  await expect(
    page.getByText(process.env.BUSINESS_SMOKE_SCHEME || "Smoke consumables", {
      exact: true,
    }),
  ).toBeVisible();
  await page.goto(`${base}/business/tasks/${process.env.BUSINESS_SMOKE_TASK}`, {
    waitUntil: "domcontentloaded",
  });
  await expect(page.locator("table").first()).toBeVisible();
  await expect(page.locator("table").last().locator("tbody tr")).toHaveCount(
    Number(process.env.BUSINESS_SMOKE_RECORDS || 6),
  );
  await page.screenshot({
    path: path.join(process.env.BUSINESS_SMOKE_OUTPUT, "task.png"),
    fullPage: true,
  });
  await page.goto(`${base}/flow/${process.env.BUSINESS_SMOKE_FLOW}`, {
    waitUntil: "domcontentloaded",
  });
  await expect(page.getByTestId("business-canvas-configuration")).toBeVisible({
    timeout: 30000,
  });
  await expect(page.locator(".react-flow__edge")).toHaveCount(
    Number(process.env.BUSINESS_SMOKE_EDGES),
  );
  await page.locator('.react-flow__node[data-id="Facts"]').click();
  const panel = page.getByTestId("business-canvas-configuration");
  const field = panel
    .getByRole("combobox", { name: "Field", exact: true })
    .first();
  await expect(
    field.locator('option[value="insurance_paid"]'),
  ).not.toContainText("unavailable");
  const saved = page.waitForResponse(
    (response) =>
      response
        .url()
        .includes(`/api/v1/flows/${process.env.BUSINESS_SMOKE_FLOW}`) &&
      response.request().method() === "PATCH" &&
      response.status() === 200,
  );
  await field.selectOption("medical_consumable");
  await field.selectOption("insurance_paid");
  await saved;
  await expect(panel).toBeVisible();
  await expect(panel).toBeInViewport();
  await expect(field).toHaveValue("insurance_paid");
  await expect(
    field.locator('option[value="insurance_paid"]'),
  ).not.toContainText("unavailable");
  await expect(page.locator(".react-flow__edge")).toHaveCount(
    Number(process.env.BUSINESS_SMOKE_EDGES),
  );
  await expect(
    page.getByText("Some connections were removed because they were invalid:", {
      exact: true,
    }),
  ).toHaveCount(0);
  await page.evaluate(
    () =>
      new Promise((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(resolve)),
      ),
  );
  await page.screenshot({
    path: path.join(process.env.BUSINESS_SMOKE_OUTPUT, "canvas.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
  console.log(
    "Browser login, results, edge retention, field choices and canvas autosave passed",
  );
} catch (error) {
  await page.screenshot({
    path: path.join(process.env.BUSINESS_SMOKE_OUTPUT, "failure.png"),
    fullPage: true,
  });
  console.error(
    "Browser failure",
    page.url(),
    errors,
    (await page.locator("body").innerText()).slice(0, 1800),
  );
  throw error;
} finally {
  await browser.close();
}
