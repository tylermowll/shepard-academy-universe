import { expect, test } from "@playwright/test";
import {
  createActivity,
  navigate,
  openAttachments,
  startTutor,
} from "./support";

test("one composer keeps photo problems, follow-ups and subsequent activities in a bounded conversation", async ({
  page,
}) => {
  await startTutor(page, "Synthetic explanation and observations");
  await createActivity(page);
  const composer = page.getByRole("textbox", {
    name: "Your work or question",
    exact: true,
  });
  const send = page.getByRole("button", { name: "Send", exact: true });
  const log = page.getByRole("log", { name: "Learning conversation" });
  await expect(send).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Ask about this" }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Upload a photo", { exact: true }),
  ).not.toBeVisible();
  await openAttachments(page);
  await page
    .getByLabel("Take or choose a photo")
    .setInputFiles("evals/fixtures/vision/04-ambiguous.png");
  await page
    .getByRole("button", { name: "Submit this photograph", exact: true })
    .click();
  await expect(
    log.getByText("This photo needs clarification.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Dismiss rejected reading" }),
  ).toHaveCount(0);
  // Clicking Send can scroll the outer page on a phone. Measure the composer
  // inside its chat frame so normal page scrolling is not mistaken for drift.
  const composerPosition = () =>
    composer.evaluate((node) => {
      const frame = node.closest(".chat-column");
      if (!frame) throw new Error("Composer has no chat frame");
      return (
        node.getBoundingClientRect().top - frame.getBoundingClientRect().top
      );
    });
  const initial = await composerPosition();
  await composer.fill("Which part of my photo could the reader not identify?");
  await send.click();
  await expect(log.locator(".tutor-feedback")).toHaveCount(1);
  await expect(
    log.getByText("This photo needs clarification.", { exact: true }),
  ).toBeVisible();
  for (let index = 0; index < 5; index++) {
    await composer.fill(
      `Synthetic follow-up ${index}: explain how the evidence supports the claim.`,
    );
    await send.click();
    await expect(log.locator(".tutor-feedback")).toHaveCount(index + 2);
  }
  const final = await composerPosition();
  expect(Math.abs(final - initial)).toBeLessThan(5);
  const sendBounds = await send.boundingBox();
  const chatBounds = await page.locator(".chat-column").boundingBox();
  expect(sendBounds).not.toBeNull();
  expect(chatBounds).not.toBeNull();
  expect(sendBounds!.y + sendBounds!.height).toBeLessThan(
    chatBounds!.y + chatBounds!.height - 5,
  );
  expect(
    await log.evaluate((node) => node.scrollHeight > node.clientHeight),
  ).toBe(true);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBe(true);
  await log.evaluate((node) => {
    node.scrollTop = 0;
    node.dispatchEvent(new Event("scroll"));
  });
  await expect(
    page.getByRole("button", { name: "Latest messages ↓" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Latest messages ↓" }).click();
  await composer.fill("Keep this draft while opening Help.");
  await navigate(page, "Help");
  await navigate(page, "Practice");
  await expect(composer).toHaveValue("Keep this draft while opening Help.");
  await composer.fill("");
  await page.getByText("Next activity options", { exact: true }).click();
  await page
    .getByRole("button", { name: "Harder next activity", exact: true })
    .click();
  await expect(
    page.getByText("Saved automatically · Harder difficulty", { exact: true }),
  ).toBeVisible();
  await expect(log.locator(".tutor-feedback")).toHaveCount(6);
  await expect(
    log.getByText("Earlier activity 1", { exact: true }),
  ).toBeVisible();
  await expect(composer).toBeEditable();
  await expect(send).toBeVisible();
  await page.screenshot({
    path: test.info().outputPath("conversation.png"),
    fullPage: true,
  });
});
