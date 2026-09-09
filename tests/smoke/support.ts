import { expect, test, type Page } from "@playwright/test";

export async function navigate(
  page: Page,
  name: "Practice" | "History" | "Learners" | "Settings" | "Help",
) {
  const link = page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name, exact: true });
  await link.click();
  await expect(link).toHaveAttribute("aria-current", "page");
}

export async function login(
  page: Page,
  username = "demo",
  password = "synthetic-demo-password-only",
) {
  await page.goto("/");
  await page.getByLabel("Username", { exact: true }).fill(username);
  await page.getByLabel("Password", { exact: true }).fill(password);
  const signIn = async () => {
    const response = page.waitForResponse(
      (result) =>
        result.url().endsWith("/auth/login") &&
        result.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    return response;
  };
  let response = await signIn();
  // Independent browser contexts share a loopback address. The expanded suite
  // honors the real ten-per-minute limit instead of disabling it for tests.
  if (response.status() === 429) {
    await expect(page.getByRole("alert")).toContainText(
      "Too many login attempts",
    );
    const retryAfter = Number(response.headers()["retry-after"]);
    expect(Number.isInteger(retryAfter)).toBe(true);
    expect(retryAfter).toBeGreaterThan(0);
    expect(retryAfter).toBeLessThanOrEqual(60);
    const delay = retryAfter * 1000 + 100;
    test.setTimeout(test.info().timeout + delay);
    await page.waitForTimeout(delay);
    response = await signIn();
  }
  expect(response.status()).toBe(200);
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
}

export async function createLearner(page: Page, signIn = true) {
  await navigate(page, "Learners");
  await page
    .getByRole("button", { name: "Add learner account", exact: true })
    .click();
  const alias = `Synthetic tutor ${Date.now()}`;
  await page.getByLabel("Learner username", { exact: true }).fill(alias);
  await page
    .getByLabel("Password", { exact: true })
    .fill("synthetic-demo-password-only");
  await page
    .getByRole("button", { name: "Create learner account", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Selected learner", exact: true }),
  ).toContainText(alias);
  if (signIn) {
    await page.getByRole("button", { name: "Sign out", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "Sign in", exact: true }),
    ).toBeVisible();
    await login(page, alias);
  }
  return alias;
}

export async function startTutor(page: Page, topic: string) {
  await login(page);
  const alias = await createLearner(page);
  await page
    .getByRole("textbox", { name: "Topic or learning goal", exact: true })
    .fill(topic);
  await page
    .getByRole("combobox", { name: "Tutor style", exact: true })
    .selectOption("balanced");
  await page
    .getByRole("button", { name: "Start session", exact: true })
    .click();
  // Starting now creates the first activity in the same transaction.
  await expect(page.locator(".tutor-activity")).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Your work or question", exact: true }),
  ).toBeEditable();
  return alias;
}

export async function createActivity(page: Page) {
  await openPracticeMaterial(page);
  await page
    .getByRole("button", { name: "Create practice activity", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Your work or question", exact: true }),
  ).toBeEditable();
  await expect(page.locator(".tutor-activity")).toBeVisible();
}

export async function openPracticeMaterial(page: Page) {
  await openSessionTools(page);
  const trigger = page.getByText("Use different practice material", {
    exact: true,
  });
  if ((await trigger.locator("..").getAttribute("open")) === null)
    await trigger.click();
}

export async function openAttachments(page: Page) {
  const trigger = page.getByRole("button", {
    name: "Attach photo",
    exact: true,
  });
  if (
    (await trigger.count()) &&
    (await trigger.getAttribute("aria-expanded")) === "false"
  )
    await trigger.click();
  await expect(page.getByText("Upload a photo", { exact: true })).toBeVisible();
}

export async function openSessionTools(page: Page) {
  const trigger = page.getByText("Session & material", { exact: true });
  if ((await trigger.locator("..").getAttribute("open")) === null)
    await trigger.click();
}
