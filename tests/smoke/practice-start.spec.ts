import { expect, test } from "@playwright/test";
import type { Schema } from "../../apps/web/src/client";
import { createLearner, login, startTutor } from "./support";

test("starting with reference text creates exactly one activity without a second prompt", async ({
  page,
}) => {
  await login(page);
  await createLearner(page);
  await page
    .getByLabel("Topic or learning goal", { exact: true })
    .fill("Synthetic supporting evidence");
  await page
    .getByRole("combobox", { name: "Practice source", exact: true })
    .selectOption("reference_text");
  await page
    .getByLabel("Reference material", { exact: true })
    .fill("Synthetic assignment: explain why a seedling grew taller.");
  const started = page.waitForResponse(
    (response) =>
      response.url().endsWith("/tutor/sessions") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Start session", exact: true })
    .click();
  const result = await started;
  expect(result.status()).toBe(201);
  const session = (await result.json()) as Schema<"TutoringSessionPublic">;
  expect(session.problems).toHaveLength(1);
  expect(session.problems[0]?.reference_source).toBe("reference_text");
  await expect(
    page.getByLabel("Your work or question", { exact: true }),
  ).toBeEditable();
  await expect(page.locator(".tutor-activity")).toContainText("Synthetic");
  await expect(page.locator(".tutor-activity")).not.toContainText(
    "explain why a seedling grew taller",
  );
});

test("composer menus close each other and dismiss on Escape, outside click and action", async ({
  page,
}) => {
  await startTutor(page, "Synthetic menu interaction");
  const helpToggle = page
    .locator(".composer-menu summary")
    .filter({ hasText: /^Help$/ });
  const nextToggle = page.getByText("Next activity options", { exact: true });
  const menus = page.locator(".composer-menu[open]");
  await helpToggle.click();
  await expect(menus).toHaveCount(1);
  await nextToggle.click();
  await expect(menus).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "Give me a hint", exact: true }),
  ).not.toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menus).toHaveCount(0);
  await expect(nextToggle).toBeFocused();
  await helpToggle.click();
  // On narrow screens the menu covers the textarea; click a visible point
  // outside the menu rather than trying to click through its buttons.
  await page
    .getByRole("heading", { level: 1, name: "Practice", exact: true })
    .click();
  await expect(menus).toHaveCount(0);
  await helpToggle.click();
  await page
    .getByRole("button", { name: "Give me a hint", exact: true })
    .click();
  await expect(menus).toHaveCount(0);
  await expect(page.locator(".tutor-feedback")).toHaveCount(1);
});
