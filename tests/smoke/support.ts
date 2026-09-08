import { expect, test, type Page } from "@playwright/test";

export async function navigate(
  page: Page,
  name: "Practice" | "History" | "Learners & devices" | "Settings" | "Help",
) {
  const link = page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name, exact: true });
  await link.click();
  await expect(link).toHaveAttribute("aria-current", "page");
}

export async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("Login name", { exact: true }).fill("demo");
  await page
    .getByLabel("Password", { exact: true })
    .fill("synthetic-demo-password-only");
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

export async function createLearner(page: Page) {
  await navigate(page, "Learners & devices");
  const alias = `Synthetic tutor ${Date.now()}`;
  await page.getByLabel("Learner name", { exact: true }).fill(alias);
  await page.getByRole("button", { name: "Add learner", exact: true }).click();
  await expect(
    page.getByRole("combobox", { name: "Learner", exact: true }),
  ).toHaveValue(/[a-f0-9-]{36}/);
  await navigate(page, "Practice");
  return alias;
}

export async function startTutor(page: Page, topic: string) {
  await login(page);
  const alias = await createLearner(page);
  await page
    .getByRole("textbox", { name: "Topic or learning goal", exact: true })
    .fill(topic);
  await page.getByText("Tutor options", { exact: true }).click();
  await page
    .getByRole("combobox", { name: "Tutor style", exact: true })
    .selectOption("balanced");
  await page
    .getByRole("button", { name: "Start session", exact: true })
    .click();
  await expect(
    page.getByRole("combobox", { name: "Practice source", exact: true }),
  ).toBeVisible();
  return alias;
}

export async function createActivity(page: Page) {
  await page
    .getByRole("button", { name: "Create practice activity", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Your work or question", exact: true }),
  ).toBeEditable();
  await expect(page.locator(".tutor-activity")).toBeVisible();
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
