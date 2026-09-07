import { defineConfig, devices } from "@playwright/test";
import { randomBytes, randomUUID } from "node:crypto";
import { tmpdir } from "node:os";
import { join } from "node:path";

export default defineConfig({
  testDir: "./tests/smoke",
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? {
          launchOptions: {
            executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
          },
        }
      : {}),
  },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chromium", use: { ...devices["Pixel 7"] } },
  ],
  webServer: [
    {
      command: "pnpm --filter @math-tutor/web preview",
      url: "http://127.0.0.1:4173",
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command:
        "uv run --directory apps/api --locked uvicorn math_tutor.api.app:app --host 127.0.0.1 --port 18000 --no-proxy-headers",
      env: {
        SESSION_SECRET: randomBytes(48).toString("base64url"),
        APP_PUBLIC_ORIGIN: "http://127.0.0.1:18000",
        DATABASE_URL: `sqlite+pysqlite:///${join(tmpdir(), `math-tutor-smoke-${randomUUID()}`, "test.sqlite3")}`,
      },
      url: "http://127.0.0.1:18000/health",
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});
