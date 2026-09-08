import { openAttachments } from "./support";
import { expect, test } from "@playwright/test";
import { createActivity, login, startTutor } from "./support";

test("a signed-in phone opens and replaces photo links in its existing tab without signing out", async ({
  page,
  browser,
}) => {
  await startTutor(page, "Synthetic fraction models");
  await createActivity(page);
  await openAttachments(page);
  await page
    .getByRole("button", { name: "Take photo with phone", exact: true })
    .click();
  const link = await page
    .getByRole("link", { name: "Open photo page" })
    .getAttribute("href");
  expect(link).toContain("/#capture=");

  const mobile = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  try {
    const phone = await mobile.newPage();
    await login(phone);
    await phone.evaluate(() => {
      document.documentElement.dataset.qrDocument = "original";
    });
    const secrets = [new URL(link!).hash.slice("#capture=".length)];
    const signouts: string[] = [];
    phone.on("request", (request) => {
      for (const secret of secrets) expect(request.url()).not.toContain(secret);
      if (request.url().endsWith("/auth/logout")) signouts.push(request.url());
    });
    await phone.goto(link!);
    await expect(phone.getByRole("heading", { level: 1 })).toHaveText(
      "Photograph your work.",
    );
    expect(
      await phone.evaluate(() => document.documentElement.dataset.qrDocument),
    ).toBe("original");
    expect(await phone.evaluate(() => location.hash)).toBe("#capture");

    // An expired/revoked link must remain a photo error, without ending login.
    await page.getByRole("button", { name: "Cancel phone link" }).click();
    await expect(phone.getByRole("alert")).toContainText("photo link ended", {
      timeout: 10_000,
    });
    await openAttachments(page);
    await page
      .getByRole("button", { name: "Take photo with phone", exact: true })
      .click();
    const replacement = await page
      .getByRole("link", { name: "Open photo page" })
      .getAttribute("href");
    expect(replacement).not.toBe(link);
    secrets.push(new URL(replacement!).hash.slice("#capture=".length));
    await phone.goto(replacement!);
    await expect(phone.getByLabel("Take or choose a photo")).toBeVisible();
    await expect(phone.getByRole("alert")).toHaveCount(0);
    expect(await phone.evaluate(() => location.hash)).toBe("#capture");

    await phone
      .getByLabel("Take or choose a photo")
      .setInputFiles("evals/fixtures/work.png");
    await expect(
      phone.getByAltText("Your photograph before submission"),
    ).toBeVisible();
    const upload = phone.waitForRequest((request) =>
      request.url().endsWith("/phone-upload/photos"),
    );
    await phone
      .getByRole("button", { name: "Send to computer", exact: true })
      .click();
    const headers = await (await upload).allHeaders();
    expect(headers.cookie).toBeUndefined();
    expect(headers["x-csrf-token"]).toBeUndefined();
    expect(headers["x-photo-token"]).toBe(secrets[1]);
    await expect(phone.getByRole("heading", { level: 1 })).toHaveText(
      "Photo sent to your computer.",
    );
    await expect(page.locator(".tutor-feedback")).toHaveCount(1);
    expect(await phone.evaluate(() => Object.keys(localStorage))).toEqual([]);
    expect(signouts).toEqual([]);

    await phone.evaluate(() => {
      window.location.hash = "";
    });
    await expect(phone.getByRole("button", { name: "Sign out" })).toBeVisible();
    expect(
      await phone.evaluate(() => document.documentElement.dataset.qrDocument),
    ).toBe("original");
  } finally {
    await mobile.close();
  }
});
