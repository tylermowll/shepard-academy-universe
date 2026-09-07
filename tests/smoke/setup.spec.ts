import { spawn, type ChildProcess } from "node:child_process";
import { mkdtemp } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test } from "@playwright/test";

async function unusedPort() {
  const listener = createServer();
  await new Promise<void>((resolve) =>
    listener.listen(0, "127.0.0.1", resolve),
  );
  const address = listener.address();
  if (!address || typeof address === "string") throw new Error("No test port");
  await new Promise<void>((resolve, reject) =>
    listener.close((error) => (error ? reject(error) : resolve())),
  );
  return address.port;
}

async function stop(child: ChildProcess) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const pid = child.pid;
  if (!pid || pid <= 1)
    throw new Error("Missing isolated launcher process group");
  const exited = new Promise<void>((resolve) =>
    child.once("exit", () => resolve()),
  );
  process.kill(-pid, "SIGINT");
  let fallback: ReturnType<typeof setTimeout> | undefined;
  try {
    await Promise.race([
      exited,
      new Promise<void>((_, reject) => {
        fallback = setTimeout(() => {
          process.kill(-pid, "SIGKILL");
          reject(new Error("Isolated launcher did not stop cleanly"));
        }, 15_000);
      }),
    ]);
  } finally {
    clearTimeout(fallback);
  }
}

async function installation() {
  // Only generated synthetic state is used. Never inspect the real operator's
  // .env or database, or print the generated setup token in test diagnostics.
  const directory = await mkdtemp(join(tmpdir(), "shepard-browser-setup-"));
  const origin = `http://127.0.0.1:${await unusedPort()}`;
  const environment = { ...process.env };
  for (const name of [
    "SESSION_SECRET",
    "PROVIDER_CONFIG",
    "UV_ENV_FILE",
    "SHEPARD_SETUP_TOKEN",
  ])
    delete environment[name];
  Object.assign(environment, {
    DATABASE_URL: `sqlite+pysqlite:///${join(directory, "data", "test.sqlite3")}`,
    MATH_TUTOR_DATA_DIR: join(directory, "data"),
    APP_PUBLIC_ORIGIN: origin,
    APP_MODE: "private",
    APP_AUDIENCE: "mixed",
    ALLOW_CLOUD_INFERENCE: "false",
    UV_NO_ENV_FILE: "true",
  });
  return {
    origin,
    async start() {
      let output = "";
      let setupUrl = "";
      const child = spawn(
        "make",
        ["start", `ENV_FILE=${join(directory, ".env")}`],
        {
          cwd: process.cwd(),
          env: environment,
          detached: true,
          stdio: ["ignore", "pipe", "pipe"],
        },
      );
      const capture = (chunk: Buffer) => {
        output = (output + chunk.toString()).slice(-131_072);
        const match = output.match(
          /http:\/\/127\.0\.0\.1:\d+\/#setup=[A-Za-z0-9_-]+/,
        );
        if (match) setupUrl = match[0];
      };
      child.stdout?.on("data", capture);
      child.stderr?.on("data", capture);
      try {
        await expect
          .poll(
            async () => {
              if (child.exitCode !== null || child.signalCode !== null)
                throw new Error(
                  "Isolated native startup exited before readiness",
                );
              return fetch(`${origin}/health/ready`, {
                signal: AbortSignal.timeout(1000),
              })
                .then((response) => response.status)
                .catch(() => 0);
            },
            { timeout: 60_000, intervals: [200, 500] },
          )
          .toBe(200);
      } catch (error) {
        await stop(child);
        throw error;
      }
      return {
        setupUrl: () => setupUrl,
        promptedForPassword: () =>
          /New password:|Administrator login name:/.test(output),
        stop: () => stop(child),
      };
    },
  };
}

for (const lostReceipt of [false, true]) {
  test(`native browser setup recovers validation${lostReceipt ? " and a lost success receipt" : ""}, then keeps the login after restart`, async ({
    page,
    context,
  }) => {
    test.setTimeout(120_000);
    const app = await installation();
    let running = await app.start();
    try {
      expect(running.promptedForPassword()).toBe(false);
      expect(Boolean(running.setupUrl())).toBe(true);
      const ownerUrl = running.setupUrl();
      const token = new URL(ownerUrl).hash.slice("#setup=".length);
      const requestUrls: string[] = [];
      context.on("request", (request) => requestUrls.push(request.url()));

      // An ordinary visitor cannot claim the account by being the first to visit.
      await page.goto(app.origin);
      await expect(
        page.getByRole("heading", { name: "Create administrator account" }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Create account", exact: true }),
      ).toHaveCount(0);
      await page.goto(ownerUrl);
      await expect(
        page.getByLabel("Login name", { exact: true }),
      ).toBeEditable();
      await expect.poll(() => new URL(page.url()).hash).toBe("");
      await expect(page.locator("#setup-password-requirements")).toContainText(
        "6–256",
      );
      if (!lostReceipt)
        await page.screenshot({
          path: test.info().outputPath("account-setup.png"),
          fullPage: true,
        });
      await page
        .getByLabel("Login name", { exact: true })
        .fill("synthetic-owner");
      await page.getByLabel("Password", { exact: true }).fill("tiny");
      await page.getByLabel("Confirm password", { exact: true }).fill("tiny");
      await page
        .getByRole("button", { name: "Create account", exact: true })
        .click();
      await expect(page.getByRole("alert")).toContainText(/6–256 characters/);
      await expect(page.getByLabel("Login name", { exact: true })).toHaveValue(
        "synthetic-owner",
      );

      await page.getByLabel("Password", { exact: true }).fill("local6");
      await page
        .getByLabel("Confirm password", { exact: true })
        .fill("different");
      await page
        .getByRole("button", { name: "Create account", exact: true })
        .click();
      await expect(page.getByRole("alert")).toContainText(/match/i);
      expect(
        (await page.request.get(`${app.origin}/health/ready`)).status(),
      ).toBe(200);

      if (lostReceipt) {
        await page.route("**/auth/setup", async (route) => {
          if (route.request().method() !== "POST") return route.continue();
          const response = await route.fetch();
          expect(response.status()).toBe(200);
          // The session cookie arrives, but the successful receipt cannot be
          // decoded. Recover its session without attempting another owner claim.
          await route.fulfill({ response, body: "{" });
        });
      }
      await page.getByLabel("Confirm password", { exact: true }).fill("local6");
      await page
        .getByRole("button", { name: "Create account", exact: true })
        .click();
      await expect(
        page.getByRole("button", { name: "Sign out", exact: true }),
      ).toBeVisible();
      await expect(
        page
          .getByRole("navigation", { name: "Main navigation" })
          .getByRole("link", { name: "Settings", exact: true }),
      ).toHaveAttribute("aria-current", "page");
      expect(requestUrls.some((url) => url.includes(token))).toBe(false);
      expect(
        await page.evaluate(() =>
          JSON.stringify({
            local: { ...localStorage },
            session: { ...sessionStorage },
          }),
        ),
      ).not.toContain(token);

      // The same link cannot reset an existing account, even from another browser.
      const anonymous = await context.browser()!.newContext();
      try {
        const visitor = await anonymous.newPage();
        await visitor.goto(ownerUrl);
        await expect(
          visitor.getByRole("heading", { name: "Adult sign in", exact: true }),
        ).toBeVisible();
        await expect(
          visitor.getByRole("button", { name: "Create account", exact: true }),
        ).toHaveCount(0);
        await expect.poll(() => new URL(visitor.url()).hash).toBe("");
      } finally {
        await anonymous.close();
      }

      await running.stop();
      running = await app.start();
      expect(running.setupUrl()).toBe("");
      expect(running.promptedForPassword()).toBe(false);
      await page.reload();
      await expect(
        page.getByRole("button", { name: "Sign out", exact: true }),
      ).toBeVisible();
      await page.getByRole("button", { name: "Sign out", exact: true }).click();
      await page
        .getByLabel("Login name", { exact: true })
        .fill("synthetic-owner");
      await page.getByLabel("Password", { exact: true }).fill("local6");
      await page.getByRole("button", { name: "Sign in", exact: true }).click();
      await expect(
        page.getByRole("button", { name: "Sign out", exact: true }),
      ).toBeVisible();
      expect(requestUrls.some((url) => url.includes(token))).toBe(false);
    } finally {
      await running.stop();
    }
  });
}
