import { expect, test } from "../../fixtures";
import { awaitBootstrapTest } from "../../utils/await-bootstrap-test";

test(
  "inspect a completed simulation in the task list, results and evidence",
  { tag: ["@release", "@api", "@workspace"] },
  async ({ page, request }) => {
    test.skip(
      process.env.VERIFICATION_E2E !== "1",
      "Requires the opt-in verification simulation services",
    );
    const password = process.env.LANGFLOW_SUPERUSER_PASSWORD;
    const clients = JSON.parse(process.env.VERIFICATION_CLIENTS ?? "{}");
    if (!password || !clients["demo-regulator"])
      throw new Error("Configure the simulation account and source first");
    const api = `http://127.0.0.1:${process.env.VERIFICATION_SOURCE_API_PORT ?? "8081"}`;
    const reference = `task-ui-${Date.now()}`;
    const sourceHeaders = {
      Authorization: `Bearer ${clients["demo-regulator"]}`,
    };
    const accepted = await request.post(`${api}/api/v1/verification/tasks`, {
      headers: { ...sourceHeaders, "Idempotency-Key": reference },
      data: {
        hospital_scope: "常州市第一人民医院",
        settlement_time_range: {
          start_inclusive: "2024-06-01T00:00:00+08:00",
          end_exclusive: "2025-09-01T00:00:00+08:00",
        },
        rule: "高值耗材智能体",
      },
    });
    expect(accepted.status()).toBe(202);
    const task = await accepted.json();
    await expect
      .poll(
        async () => {
          const response = await request.get(
            `${api}/api/v1/verification/tasks/${task.task_id}`,
            { headers: sourceHeaders },
          );
          return (await response.json()).status;
        },
        { timeout: 90_000 },
      )
      .toBe("completed");

    await page.route("**/api/v1/store/tags", (route) =>
      route.fulfill({ json: [] }),
    );
    await page.addInitScript(() =>
      localStorage.setItem("languagePreference", "zh-Hans"),
    );
    await page.goto("/login", {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });
    await page
      .locator("#login-username")
      .fill("verification-admin", { timeout: 60000 });
    await page.locator('input[type="password"]').fill(password);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL((url) => !url.pathname.includes("/login"));
    await awaitBootstrapTest(page, {
      skipGoto: true,
      skipModal: true,
      seedFlowIfEmpty: false,
    });
    await page.getByRole("button", { name: "核验任务", exact: true }).click();
    await page.getByLabel("查找任务").fill(reference);
    await page.getByRole("button", { name: "查询", exact: true }).click();
    const taskRow = page.getByRole("row").filter({ hasText: reference });
    await expect(taskRow).toContainText("已完成");
    await taskRow.getByRole("link", { name: reference, exact: true }).click();
    await expect(page).toHaveURL(
      new RegExp(`/verification/tasks/${task.task_id}\\?run_id=${task.run_id}`),
    );
    const results = page.getByRole("table", { name: "结果明细" });
    await expect(results).toBeVisible();
    await expect(
      results.getByRole("row").filter({ hasText: "人工髋关节" }),
    ).toContainText("存在差异");
    await expect(
      results.getByRole("row").filter({ hasText: "人工髋关节" }),
    ).toContainText("-10,000");
    await expect(
      results.getByRole("row").filter({ hasText: "人工膝关节" }),
    ).toContainText("一致");
    await page.screenshot({
      path: "../../deploy/verification/.cache/release-ui-tests/task-results.png",
      fullPage: true,
    });
    await page.getByRole("tab", { name: "证据", exact: true }).click();
    await expect(
      page.getByText("本次运行已保存 11 份阶段证据、2 次识别请求。", {
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "结算快照", exact: true }),
    ).toBeVisible();
    await page.getByText("查看原始数据", { exact: true }).first().click();
    await expect(
      page
        .getByRole("tabpanel")
        .getByText(/synthetic-model-v1/)
        .first(),
    ).toBeVisible();
    await page.reload({ waitUntil: "domcontentloaded", timeout: 60000 });
    await expect(page.getByRole("table", { name: "结果明细" })).toBeVisible();
    const saved = await request.get(
      `${api}/api/v1/verification/tasks/${task.task_id}/evidence`,
      { headers: sourceHeaders, params: { run_id: task.run_id } },
    );
    expect((await saved.json()).model_requests).toHaveLength(2);
    await page.getByRole("link", { name: "返回任务列表", exact: true }).click();
    await page.getByLabel("查找任务").fill(`missing-${reference}`);
    await page.getByRole("button", { name: "查询", exact: true }).click();
    await expect(
      page.getByText("没有符合查询条件的任务。", { exact: true }),
    ).toBeVisible();
  },
);
