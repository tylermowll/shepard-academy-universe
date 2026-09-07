import { expect, type Page } from "@playwright/test";

export async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("Login name", { exact: true }).fill("demo");
  await page
    .getByLabel("Password", { exact: true })
    .fill("synthetic-demo-password-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
}

export async function createLearner(page: Page) {
  await page.getByText("Manage learners and devices", { exact: true }).click();
  const alias = `Synthetic tutor ${Date.now()}`;
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

export async function startTutor(page: Page, topic: string) {
  await login(page);
  const alias = await createLearner(page);
  await page
    .getByRole("textbox", { name: "Topic or learning goal", exact: true })
    .fill(topic);
  await page
    .getByRole("combobox", { name: "Tutor initiative", exact: true })
    .selectOption("balanced");
  await page
    .getByRole("button", { name: "Start tutoring", exact: true })
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
