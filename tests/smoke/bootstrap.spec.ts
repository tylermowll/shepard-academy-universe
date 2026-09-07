import { expect, test, type Page } from "@playwright/test";

async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("Login name", { exact: true }).fill("demo");
  await page
    .getByLabel("Password", { exact: true })
    .fill("synthetic-demo-password-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
}
async function createLearner(page: Page) {
  await page.getByText("Manage learners and devices", { exact: true }).click();
  const alias = `Synthetic ${Date.now()}`;
  await page.getByLabel("Alias", { exact: true }).fill(alias);
  await page
    .getByRole("button", { name: "Create learner", exact: true })
    .click();
  await expect(
    page.getByRole("combobox", { name: "Learner", exact: true }),
  ).toHaveValue(/[a-f0-9-]{36}/);
  await page.getByText("Manage learners and devices", { exact: true }).click();
  return alias;
}
function answer(text: string) {
  const parts = text.split(" + ");
  const rational = (part: string) => {
    const [n, d] = part.split("/").map(Number);
    return [n ?? 0, d ?? 1] as const;
  };
  const [a, b] = rational(parts[0] ?? "");
  const [c, d] = rational(parts[1] ?? "");
  let n = a * d + c * b,
    den = b * d;
  let x = n,
    y = den;
  while (y) {
    [x, y] = [y, x % y];
  }
  n /= x;
  den /= x;
  return den === 1 ? String(n) : `${n}/${den}`;
}

test("same-origin entry renders without external requests or overflow", async ({
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
  await expect(page).toHaveTitle("Math Practice Tutor");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Make room for a little math.",
  );
  await expect(
    page.getByRole("button", { name: "Sign in", exact: true }),
  ).toBeEnabled();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});

test("persisted practice, assistance, reload, progress and logout", async ({
  page,
  context,
}) => {
  await login(page);
  const alias = await createLearner(page);
  await page.getByRole("button", { name: "Start a new session" }).click();
  await page.getByRole("button", { name: "Assign next problem" }).click();
  const problem = page.locator(".math-problem");
  await expect(problem).toBeVisible();
  const value = answer(await problem.innerText());
  await page.getByLabel("Your answer or question").fill("-999");
  await page.getByRole("button", { name: "Check answer", exact: true }).click();
  await expect(page.locator(".verdict").first()).toContainText("incorrect");
  await page.getByRole("button", { name: "Hint", exact: true }).click();
  await expect(
    page.getByText("Help used: level 1", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Your answer or question").fill(value);
  const submitted = page.waitForResponse(
    (response) =>
      response.url().includes("/submissions") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Check answer", exact: true }).click();
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
  await expect(page.locator(".verdict.correct")).toHaveCount(1);
  if (
    process.env.CAPTURE_SYNTHETIC_SCREENSHOT &&
    test.info().project.name === "desktop-chromium"
  )
    await page.screenshot({
      path: "/tmp/math-tutor-practice.png",
      fullPage: true,
    });
  const hash = await page.evaluate(() => location.hash);
  await page.reload();
  // Adult selection is explicit after reload; select the session's learner again.
  await page
    .getByRole("combobox", { name: "Learner", exact: true })
    .selectOption({ label: alias });
  await expect(page.locator(".verdict.correct")).toHaveCount(1);
  expect(await page.evaluate(() => location.hash)).toBe(hash);
  await page.getByRole("button", { name: "Finish session" }).click();
  await expect(
    page.locator(".practice").getByText(/Guided practice · completed/),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Make room for a little math.",
  );
  await expect(page.locator(".operation")).toHaveCount(0);
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([]);
});

test("public offline pack remains distinct from saved tutoring", async ({
  page,
  context,
}) => {
  await page.goto("/");
  await page.evaluate(async () => {
    if ("serviceWorker" in navigator) await navigator.serviceWorker.ready;
  });
  await context.setOffline(true);
  await page.reload();
  await page.getByText("Public offline practice pack", { exact: true }).click();
  await page.getByLabel("Offline answer", { exact: true }).fill("5/6");
  await page.getByRole("button", { name: "Check on this device" }).click();
  await expect(
    page.getByText("Correct value (checked on this device)."),
  ).toBeVisible();
  const cached = await page.evaluate(async () => {
    const keys = await caches.keys();
    const urls: string[] = [];
    for (const key of keys)
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

test("photo preview and explicit confirmation preserve work before checking", async ({
  page,
}) => {
  await login(page);
  await createLearner(page);
  await page.getByRole("button", { name: "Start a new session" }).click();
  await page.getByRole("button", { name: "Assign next problem" }).click();
  await page.getByText("Submit a photograph", { exact: true }).click();
  await page
    .getByLabel("Take or choose a photo")
    .setInputFiles("evals/fixtures/work.png");
  await expect(
    page.getByRole("img", { name: "Your photograph before submission" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Rotate 90°" }).click();
  await page.getByRole("button", { name: "Submit this photograph" }).click();
  await expect(
    page.getByRole("button", { name: "Confirm this interpretation" }),
  ).toBeVisible();
  await expect(page.locator(".verdict")).toHaveCount(0);
  await page
    .getByLabel("Confirm or edit the transcription")
    .fill("My work says 2/5.");
  await page.getByLabel("Final answer from this work").fill("2/5");
  await page
    .getByRole("button", { name: "Confirm this interpretation" })
    .click();
  await expect(page.locator(".verdict")).toHaveCount(1);
  await expect(
    page.getByText("Transcription: My work says 2/5."),
  ).toBeVisible();
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

test("adult pairs a second browser and revocation clears learner access", async ({
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
      learner.getByRole("button", { name: "Start a new session" }),
    ).toBeVisible();
    await expect(
      learner.getByText("Manage learners and devices", { exact: true }),
    ).toHaveCount(0);
    await learner.getByRole("button", { name: "Start a new session" }).click();
    await learner.getByRole("button", { name: "Assign next problem" }).click();
    await expect(learner.locator(".math-problem")).toBeVisible();
    await page.getByRole("button", { name: "Revoke learner devices" }).click();
    await expect(
      page.getByText("Learner devices revoked.", { exact: true }),
    ).toBeVisible();
    await expect(
      learner.getByRole("button", { name: "Pair this device" }),
    ).toBeEnabled();
    await expect(learner.locator(".math-problem")).toHaveCount(0);
    await expect(learner.getByRole("button", { name: "Sign out" })).toHaveCount(
      0,
    );
    expect(await learner.evaluate(() => location.hash)).toBe("");
  } finally {
    await device.close();
  }
});

test("changing learners clears the previous learner's session and entries", async ({
  page,
}) => {
  await login(page);
  await createLearner(page);
  await page.getByRole("button", { name: "Start a new session" }).click();
  await page.getByRole("button", { name: "Assign next problem" }).click();
  await page.getByLabel("Your answer or question").fill("-999");
  await page.getByRole("button", { name: "Check answer", exact: true }).click();
  await expect(page.locator(".verdict.incorrect")).toHaveCount(1);
  const previousSession = await page.evaluate(() => location.hash);
  await page
    .getByRole("combobox", { name: "Learner", exact: true })
    .selectOption({ label: "Delta" });
  await expect(page.locator(".operation")).toHaveCount(0);
  await expect(page.locator(".math-problem")).toHaveCount(0);
  await expect(
    page.getByRole("combobox", { name: "Saved sessions" }),
  ).toHaveValue("");
  expect(await page.evaluate(() => location.hash)).toBe("");
  await page.getByRole("button", { name: "Start a new session" }).click();
  await expect(
    page.getByRole("button", { name: "Assign next problem" }),
  ).toBeVisible();
  expect(await page.evaluate(() => location.hash)).not.toBe(previousSession);
});

test("a lost submission acknowledgement retries the original entry without duplicate grading", async ({
  page,
}) => {
  await login(page);
  await createLearner(page);
  await page.getByRole("button", { name: "Start a new session" }).click();
  await page.getByRole("button", { name: "Assign next problem" }).click();
  const submissions: { key: string | undefined; body: string | null }[] = [];
  await page.route("**/api/v1/problems/*/submissions", async (route) => {
    const request = route.request();
    submissions.push({
      key: request.headers()["idempotency-key"],
      body: request.postData(),
    });
    if (submissions.length === 1) {
      const accepted = await route.fetch();
      expect(accepted.status()).toBe(202);
      await route.abort("connectionreset");
    } else if (submissions.length === 2)
      await route.fulfill({
        status: 429,
        json: { detail: "Synthetic retry throttle." },
      });
    else await route.continue();
  });
  await page.getByLabel("Your answer or question").fill("-999");
  await page
    .getByLabel("Steps (optional; reasoning is not checked)")
    .fill("Synthetic steps stay with this entry.");
  await page.getByRole("button", { name: "Check answer", exact: true }).click();
  await expect(page.locator(".verdict.incorrect")).toHaveCount(1);
  await expect(page.getByLabel("Your answer or question")).not.toBeEditable();
  await expect(
    page.getByRole("button", { name: "Check answer", exact: true }),
  ).toBeDisabled();
  const throttled = page.waitForResponse(
    (response) =>
      response.url().endsWith("/submissions") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Retry saved submission" }).click();
  expect((await throttled).status()).toBe(429);
  await expect(
    page.getByRole("button", { name: "Retry saved submission" }),
  ).toBeEnabled();
  await expect(page.getByLabel("Your answer or question")).not.toBeEditable();
  const recovered = page.waitForResponse(
    (response) =>
      response.url().endsWith("/submissions") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Retry saved submission" }).click();
  expect((await recovered).status()).toBe(202);
  await expect(page.getByLabel("Your answer or question")).toBeEditable();
  expect(submissions).toHaveLength(3);
  expect(submissions[1]).toEqual(submissions[0]);
  expect(submissions[2]).toEqual(submissions[0]);
  await expect(page.locator(".operation")).toHaveCount(1);
  await expect(
    page
      .locator(".progress .stats > div")
      .filter({ hasText: "Incorrect answers" })
      .locator("strong"),
  ).toHaveText("1");
  await page.getByLabel("Your answer or question").fill("-998");
  await page.getByRole("button", { name: "Check answer", exact: true }).click();
  await expect(page.locator(".verdict.incorrect")).toHaveCount(2);
  expect(submissions[3]?.key).not.toBe(submissions[0]?.key);
});

test("a lost photograph acknowledgement retries the same bytes and purpose after polling", async ({
  page,
}) => {
  await login(page);
  await createLearner(page);
  await page.getByRole("button", { name: "Start a new session" }).click();
  await page.getByRole("button", { name: "Assign next problem" }).click();
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
      const accepted = await route.fetch();
      expect(accepted.status()).toBe(202);
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
  await page.getByRole("button", { name: "Submit this photograph" }).click();
  await expect(
    page.getByRole("button", { name: "Confirm this interpretation" }),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Purpose", exact: true }),
  ).toBeDisabled();
  await expect(page.getByRole("button", { name: "Rotate 90°" })).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Start a new session" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("combobox", { name: "Saved sessions" }),
  ).toBeDisabled();
  await expect(page.getByLabel("Your answer or question")).not.toBeEditable();
  await expect(
    page.getByRole("button", { name: "Confirm this interpretation" }),
  ).toBeDisabled();
  const throttled = page.waitForResponse(
    (response) =>
      response.url().includes("/photos?") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Retry saved photograph" }).click();
  expect((await throttled).status()).toBe(429);
  await expect(
    page.getByRole("button", { name: "Retry saved photograph" }),
  ).toBeEnabled();
  await expect(
    page.getByRole("button", { name: "Start a new session" }),
  ).toBeDisabled();
  const recovered = page.waitForResponse(
    (response) =>
      response.url().includes("/photos?") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Retry saved photograph" }).click();
  expect((await recovered).status()).toBe(202);
  expect(submissions).toHaveLength(3);
  expect(submissions[1]).toEqual(submissions[0]);
  expect(submissions[2]).toEqual(submissions[0]);
  await expect(page.locator(".operation")).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "Retry saved photograph" }),
  ).toHaveCount(0);
  await page
    .getByLabel("Confirm or edit the transcription")
    .fill("My synthetic work says -999.");
  await page.getByLabel("Final answer from this work").fill("-999");
  await page
    .getByRole("button", { name: "Confirm this interpretation" })
    .click();
  await expect(page.locator(".verdict.incorrect")).toHaveCount(1);
});

test("lost session and problem receipts retain their original configuration", async ({
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
    /\/api\/v1\/sessions(?:\/[^/]+\/problems)?$/,
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
    .getByRole("combobox", { name: "Tutor profile", exact: true })
    .selectOption({ label: "All supported skills · v1" });
  await page.getByRole("button", { name: "Start a new session" }).click();
  await expect(
    page.getByRole("button", { name: "Retry session creation" }),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Tutor profile", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Start a new session" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Retry session creation" }).click();
  await expect(
    page.getByRole("button", { name: "Assign next problem" }),
  ).toBeEnabled();
  await expect(
    page.getByRole("combobox", { name: "Saved sessions" }).locator("option"),
  ).toHaveCount(2);
  expect(requests).toHaveLength(2);
  expect(requests[1]).toEqual(requests[0]);
  await page
    .getByRole("combobox", { name: "Skill", exact: true })
    .selectOption("fractions.add");
  await page.getByRole("button", { name: "Assign next problem" }).click();
  await expect(
    page.getByRole("button", { name: "Retry problem assignment" }),
  ).toBeVisible();
  await expect(page.locator(".math-problem")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Skip problem" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Retry problem assignment" }).click();
  await expect(
    page.getByRole("button", { name: "Skip problem" }),
  ).toBeEnabled();
  expect(requests).toHaveLength(4);
  expect(requests[3]).toEqual(requests[2]);
  await expect(page.locator(".history.card")).toHaveCount(1);
});
