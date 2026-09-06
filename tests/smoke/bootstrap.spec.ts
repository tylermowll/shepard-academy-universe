import { expect, test } from "@playwright/test";

test("built preview renders with a live API and no external requests", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  const externalRequests: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== "http://127.0.0.1:4173") {
      externalRequests.push(url.origin);
      await route.abort();
      return;
    }
    await route.continue();
  });

  const health = await request.get("http://127.0.0.1:18000/health");
  expect(health.status()).toBe(200);
  expect(await health.json()).toEqual({ status: "ok" });

  await page.goto("/");
  await expect(page).toHaveTitle("Math Practice Tutor");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Make room for a little math.",
  );
  await expect(
    page.getByText(/Practice sessions are not available yet/),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
  expect(externalRequests).toEqual([]);
});

test.describe("without JavaScript", () => {
  test.use({ javaScriptEnabled: false });

  test("has an honest fallback", async ({ page }) => {
    await page.goto("/");
    // Playwright's text selector excludes noscript elements.
    const fallback = page.locator("noscript p");
    await expect(fallback).toBeVisible();
    await expect(fallback).toHaveText(
      "This preview needs JavaScript to display the app.",
    );
  });
});
