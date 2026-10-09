import path from "node:path";
import { defineConfig } from "@playwright/test";
import { config } from "dotenv";

config({
  path: path.resolve(__dirname, "../../deploy/verification/.env"),
  quiet: true,
});

// Opt-in live simulation environment; no global teardown of user flows or databases.
export default defineConfig({
  testDir: "./tests/live/verification",
  workers: 1,
  retries: 0,
  timeout: 180_000,
  expect: { timeout: 90_000 },
  reporter: "list",
  outputDir: "../../deploy/verification/.cache/release-ui-tests",
  use: {
    actionTimeout: 20000,
    navigationTimeout: 30000,
    baseURL: process.env.VERIFICATION_UI_URL ?? "http://127.0.0.1:3000",
    viewport: { width: 1440, height: 1050 },
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
      args: ["--no-sandbox"],
    },
  },
});
