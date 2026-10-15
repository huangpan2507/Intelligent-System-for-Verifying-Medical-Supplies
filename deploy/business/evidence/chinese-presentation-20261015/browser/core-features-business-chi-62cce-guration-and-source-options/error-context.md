# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: core/features/business-chinese-presentation.spec.ts >> Business Chinese presentation preserves all configuration and source options
- Location: tests/core/features/business-chinese-presentation.spec.ts:5:5

# Error details

```
Error: Channel closed
```

```
Error: page.goto: Target page, context or browser has been closed
Call log:
  - navigating to "http://127.0.0.1:3000/", waiting until "load"

```

```
Error: page.evaluate: Target page, context or browser has been closed
```

# Test source

```ts
  1  | // tests/playwrightCoverage.ts
  2  | 
  3  | import { test } from "@playwright/test";
  4  | import fs from "fs";
  5  | import path from "path";
  6  | 
  7  | test.afterEach(async ({ page }, testInfo) => {
> 8  |   const coverage = await page.evaluate(() => {
     |                               ^ Error: page.evaluate: Target page, context or browser has been closed
  9  |     return (window as unknown as { __coverage__?: Record<string, unknown> })
  10 |       .__coverage__;
  11 |   });
  12 | 
  13 |   if (!coverage) return;
  14 | 
  15 |   const dir = "coverage/playwright/individual-test";
  16 |   fs.mkdirSync(dir, { recursive: true });
  17 | 
  18 |   const safeTitle = testInfo.title.replace(/[^a-zA-Z0-9-_]/g, "_");
  19 |   const fileName = `coverage-${safeTitle}-${testInfo.testId}.json`;
  20 |   fs.writeFileSync(path.join(dir, fileName), JSON.stringify(coverage));
  21 | });
  22 | 
```