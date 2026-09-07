import { expect, test } from "@playwright/test";
import { createActivity, createLearner, login, startTutor } from "./support";

// T25 supersedes template/exact-answer/manual-confirmation UI expectations.
// Preserve their auth, persistence, offline and request-recovery guarantees in
// the requested AI workflow, using the real disposable API, worker and database.
test("same-origin entry renders without external requests, templates, or overflow", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  const external: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== "http://127.0.0.1:4173") {
      external.push(url.origin);
      await route.abort();
    } else await route.continue();
  });
  expect((await request.get("/health/ready")).status()).toBe(200);
  await page.goto("/");
  await expect(page).toHaveTitle("Shepard Tutor");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Make room for understanding.",
  );
  await expect(
    page.getByRole("button", { name: "Sign in", exact: true }),
  ).toBeEnabled();
  await expect(
    page.getByText("Public offline practice pack", { exact: true }),
  ).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});

test("persisted tutoring survives disconnect and reload, then logout clears private content", async ({
  page,
  context,
}) => {
  const alias = await startTutor(
    page,
    "History: comparing evidence from two accounts",
  );
  await createActivity(page);
  await page
    .getByRole("textbox", { name: "Your work or question", exact: true })
    .fill(
      "I would compare which claims both accounts support and which depend on one witness.",
    );
  const submitted = page.waitForResponse(
    (response) =>
      response.url().includes("/submissions") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Share my work", exact: true })
    .click();
  expect((await submitted).status()).toBe(202);
  await context.setOffline(true);
  await page.reload();
  await expect(
    page.getByRole("alert").filter({ hasText: "The server is unavailable." }),
  ).toBeVisible();
  await context.setOffline(false);
  await page.reload();
  await page
    .getByRole("combobox", { name: "Learner", exact: true })
    .selectOption({ label: alias });
  await expect(page.locator(".tutor-feedback")).toHaveCount(1);
  const hash = await page.evaluate(() => location.hash);
  await page.reload();
  await page
    .getByRole("combobox", { name: "Learner", exact: true })
    .selectOption({ label: alias });
  await expect(page.locator(".tutor-feedback")).toHaveCount(1);
  expect(await page.evaluate(() => location.hash)).toBe(hash);
  await page.getByText("Session settings", { exact: true }).click();
  await page
    .getByRole("button", { name: "Finish tutoring session", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Your work or question", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Make room for understanding.",
  );
  await expect(page.locator(".tutor-feedback")).toHaveCount(0);
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([]);
});

test("offline shell does not cache private work or replace tutoring with templates", async ({
  page,
  context,
}) => {
  await page.goto("/");
  await page.evaluate(async () => {
    if ("serviceWorker" in navigator) await navigator.serviceWorker.ready;
  });
  await context.setOffline(true);
  await page.reload();
  await expect(
    page.getByRole("alert").filter({ hasText: "The server is unavailable." }),
  ).toBeVisible();
  await expect(
    page.getByText("Public offline practice pack", { exact: true }),
  ).toHaveCount(0);
  const cached = await page.evaluate(async () => {
    const urls: string[] = [];
    for (const key of await caches.keys())
      for (const request of await (await caches.open(key)).keys())
        urls.push(new URL(request.url).pathname);
    return urls;
  });
  expect(cached.length).toBeGreaterThan(0);
  expect(cached.every((path) => path.startsWith("/assets/"))).toBe(true);
  await context.setOffline(false);
});

test.describe("without JavaScript", () => {
  test.use({ javaScriptEnabled: false });
  test("has an honest fallback", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("noscript p")).toBeVisible();
    await expect(page.locator("noscript p")).toContainText("JavaScript");
  });
});

test("an installed update waits for the user before refreshing", async ({
  page,
}) => {
  await page.goto("/");
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
  });
  await page.reload();
  await page
    .getByLabel("Login name", { exact: true })
    .fill("unsent-synthetic-entry");
  await page.evaluate(async () => {
    await navigator.serviceWorker.register("/sw.js?synthetic-update=2");
  });
  await expect(
    page.getByRole("button", { name: "Refresh when ready" }),
  ).toBeVisible();
  await expect(page.getByLabel("Login name", { exact: true })).toHaveValue(
    "unsent-synthetic-entry",
  );
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Refresh when ready" }).click();
  await expect(page.getByLabel("Login name", { exact: true })).toHaveValue("");
});

test("adult pairs a second browser and revocation clears its tutoring access", async ({
  page,
  browser,
}) => {
  await login(page);
  await createLearner(page);
  const device = await browser.newContext();
  try {
    const learner = await device.newPage();
    await learner.goto("http://127.0.0.1:4173/");
    await learner.getByRole("button", { name: "Pair this device" }).click();
    const requestId = await learner
      .getByLabel("Pairing request ID")
      .inputValue();
    await page
      .getByText("Manage learners and devices", { exact: true })
      .click();
    await page.getByLabel("Pairing request ID").fill(requestId);
    await page.getByRole("button", { name: "Approve this browser" }).click();
    await expect(
      learner.getByRole("button", { name: "Start tutoring", exact: true }),
    ).toBeVisible();
    await expect(
      learner.getByText("Manage learners and devices", { exact: true }),
    ).toHaveCount(0);
    await learner
      .getByRole("textbox", { name: "Topic or learning goal", exact: true })
      .fill("Science: testing a prediction");
    await learner
      .getByRole("button", { name: "Start tutoring", exact: true })
      .click();
    await createActivity(learner);
    await page.getByRole("button", { name: "Revoke learner devices" }).click();
    await expect(
      page.getByText("Learner devices revoked.", { exact: true }),
    ).toBeVisible();
    await expect(
      learner.getByRole("button", { name: "Pair this device" }),
    ).toBeEnabled();
    await expect(learner.locator(".tutor-activity")).toHaveCount(0);
    await expect(learner.getByRole("button", { name: "Sign out" })).toHaveCount(
      0,
    );
    expect(await learner.evaluate(() => location.hash)).toBe("");
  } finally {
    await device.close();
  }
});

test("changing learners clears the previous learner's tutoring and unsent work", async ({
  page,
}) => {
  await startTutor(page, "Writing: choosing evidence");
  await createActivity(page);
  await page
    .getByRole("textbox", { name: "Your work or question", exact: true })
    .fill("My evidence should support my paragraph's claim.");
  await page
    .getByRole("button", { name: "Share my work", exact: true })
    .click();
  await expect(page.locator(".tutor-feedback")).toHaveCount(1);
  await page
    .getByRole("textbox", { name: "Your work or question", exact: true })
    .fill("Unsent work must not appear for Delta.");
  const previousSession = await page.evaluate(() => location.hash);
  await page
    .getByRole("combobox", { name: "Learner", exact: true })
    .selectOption({ label: "Delta" });
  await expect(page.locator(".tutor-feedback")).toHaveCount(0);
  await expect(page.locator(".tutor-activity")).toHaveCount(0);
  await expect(
    page.getByRole("combobox", { name: "Saved tutoring sessions" }),
  ).toHaveValue("");
  expect(await page.evaluate(() => location.hash)).toBe("");
  await page
    .getByRole("textbox", { name: "Topic or learning goal", exact: true })
    .fill("Reading: compare two characters");
  await page
    .getByRole("button", { name: "Start tutoring", exact: true })
    .click();
  expect(await page.evaluate(() => location.hash)).not.toBe(previousSession);
});

test("a lost work receipt retries the original submission through throttling without duplicate guidance", async ({
  page,
}) => {
  await startTutor(page, "Social studies: evaluating a source");
  await createActivity(page);
  const submissions: { key: string | undefined; body: string | null }[] = [];
  await page.route("**/api/v1/problems/*/submissions", async (route) => {
    const request = route.request();
    submissions.push({
      key: request.headers()["idempotency-key"],
      body: request.postData(),
    });
    if (submissions.length === 1) {
      expect((await route.fetch()).status()).toBe(202);
      await route.abort("connectionreset");
    } else if (submissions.length === 2)
      await route.fulfill({
        status: 429,
        json: { detail: "Synthetic retry throttle." },
      });
    else await route.continue();
  });
  await page
    .getByRole("textbox", { name: "Your work or question", exact: true })
    .fill("Synthetic original work remains bound to this entry.");
  await page
    .getByRole("button", { name: "Share my work", exact: true })
    .click();
  await expect(page.locator(".tutor-feedback")).toHaveCount(1);
  await expect(
    page.getByRole("textbox", { name: "Your work or question", exact: true }),
  ).not.toBeEditable();
  await expect(
    page.getByRole("button", { name: "Share my work", exact: true }),
  ).toBeDisabled();
  const throttled = page.waitForResponse(
    (response) =>
      response.url().endsWith("/submissions") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Retry saved request", exact: true })
    .click();
  expect((await throttled).status()).toBe(429);
  await expect(
    page.getByRole("button", { name: "Retry saved request", exact: true }),
  ).toBeEnabled();
  await expect(
    page.getByRole("textbox", { name: "Your work or question", exact: true }),
  ).not.toBeEditable();
  const recovered = page.waitForResponse(
    (response) =>
      response.url().endsWith("/submissions") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Retry saved request", exact: true })
    .click();
  expect((await recovered).status()).toBe(202);
  await expect(
    page.getByRole("textbox", { name: "Your work or question", exact: true }),
  ).toBeEditable();
  expect(submissions).toHaveLength(3);
  expect(submissions[1]).toEqual(submissions[0]);
  expect(submissions[2]).toEqual(submissions[0]);
  await expect(page.locator(".tutor-feedback")).toHaveCount(1);
  await page
    .getByRole("textbox", { name: "Your work or question", exact: true })
    .fill("A new revision gets its own operation.");
  await page
    .getByRole("button", { name: "Share my work", exact: true })
    .click();
  await expect(page.locator(".tutor-feedback")).toHaveCount(2);
  expect(submissions[3]?.key).not.toBe(submissions[0]?.key);
});

test("a lost photograph receipt retries the same bytes and purpose without duplicate reading or guidance", async ({
  page,
}) => {
  await startTutor(page, "Science: interpreting experiment results");
  await createActivity(page);
  const submissions: {
    key: string | undefined;
    url: string;
    body: Buffer | null;
  }[] = [];
  await page.route("**/api/v1/problems/*/photos?*", async (route) => {
    const request = route.request();
    submissions.push({
      key: request.headers()["idempotency-key"],
      url: request.url(),
      body: request.postDataBuffer(),
    });
    if (submissions.length === 1) {
      expect((await route.fetch()).status()).toBe(202);
      await route.abort("connectionreset");
    } else if (submissions.length === 2)
      await route.fulfill({
        status: 429,
        json: { detail: "Synthetic retry throttle." },
      });
    else await route.continue();
  });
  await page.getByText("Submit a photograph", { exact: true }).click();
  await page
    .getByLabel("Take or choose a photo")
    .setInputFiles("evals/fixtures/work.png");
  await page
    .getByRole("button", { name: "Submit this photograph", exact: true })
    .click();
  await expect(page.locator(".tutor-feedback")).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "Rotate 90°", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("combobox", { name: "Saved tutoring sessions" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("textbox", { name: "Your work or question", exact: true }),
  ).not.toBeEditable();
  const throttled = page.waitForResponse(
    (response) =>
      response.url().includes("/photos?") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Retry saved photograph", exact: true })
    .click();
  expect((await throttled).status()).toBe(429);
  await expect(
    page.getByRole("button", { name: "Retry saved photograph", exact: true }),
  ).toBeEnabled();
  const recovered = page.waitForResponse(
    (response) =>
      response.url().includes("/photos?") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Retry saved photograph", exact: true })
    .click();
  expect((await recovered).status()).toBe(202);
  expect(submissions).toHaveLength(3);
  expect(submissions[1]).toEqual(submissions[0]);
  expect(submissions[2]).toEqual(submissions[0]);
  await expect(page.locator(".tutor-feedback")).toHaveCount(1);
  await expect(
    page.getByRole("heading", { name: "Reading from your photo", exact: true }),
  ).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "Retry saved photograph", exact: true }),
  ).toHaveCount(0);
});

test("lost tutoring session and activity receipts retain their original topic, settings, source, and request identity", async ({
  page,
}) => {
  await login(page);
  await createLearner(page);
  const requests: {
    url: string;
    key: string | undefined;
    body: string | null;
  }[] = [];
  const acceptedPaths = new Set<string>();
  await page.route(
    /\/api\/v1\/tutor\/sessions(?:\/[^/]+\/activities)?$/,
    async (route) => {
      const request = route.request();
      if (request.method() !== "POST") {
        await route.continue();
        return;
      }
      requests.push({
        url: request.url(),
        key: request.headers()["idempotency-key"],
        body: request.postData(),
      });
      if (!acceptedPaths.has(request.url())) {
        acceptedPaths.add(request.url());
        expect((await route.fetch()).status()).toBe(201);
        await route.abort("connectionreset");
      } else await route.continue();
    },
  );
  await page
    .getByRole("textbox", { name: "Topic or learning goal", exact: true })
    .fill("Reading: support an interpretation with evidence");
  await page
    .getByRole("combobox", { name: "Tutor initiative", exact: true })
    .selectOption("learner_led");
  await page
    .getByRole("button", { name: "Start tutoring", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Retry saved request", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Topic or learning goal", exact: true }),
  ).not.toBeEditable();
  await expect(
    page.getByRole("button", { name: "Start tutoring", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Retry saved request", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Create practice activity", exact: true }),
  ).toBeEnabled();
  expect(requests).toHaveLength(2);
  expect(requests[1]).toEqual(requests[0]);
  await page
    .getByRole("combobox", { name: "Practice source", exact: true })
    .selectOption("reference_text");
  await page
    .getByRole("textbox", { name: "Reference material", exact: true })
    .fill(
      "Synthetic original homework prompt to use only for analogous practice.",
    );
  await page
    .getByRole("button", { name: "Create practice activity", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Retry saved request", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Practice source", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Retry saved request", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Your work or question", exact: true }),
  ).toBeEditable();
  expect(requests).toHaveLength(4);
  expect(requests[3]).toEqual(requests[2]);
});
