import { expect, test } from "@playwright/test";
import type { Schema } from "../../apps/web/src/client";
import { createActivity, startTutor } from "./support";

// These tests use the disposable same-origin API, database, worker, and synthetic
// provider. They establish orchestration and privacy, not live model quality.
test("the tutor continues from a phone photo through guidance, revision, discussion, and the next activity", async ({
  page,
  browser,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await startTutor(
    page,
    "Science: interpreting fractions of plants in an experiment",
  );
  const assigned = page.waitForResponse(
    (response) =>
      response.url().endsWith("/activities") &&
      response.request().method() === "POST",
  );
  await createActivity(page);
  const firstActivity = (await (
    await assigned
  ).json()) as Schema<"ProblemPublic">;
  expect(firstActivity.id).toMatch(/^[a-f0-9-]{36}$/);
  const approvals: string[] = [];
  page.on("request", (request) => {
    if (/\/(?:accept-reading|confirm)(?:\?|$)/.test(request.url()))
      approvals.push(request.url());
  });
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
    const external: string[] = [];
    const secret = link!.split("#capture=")[1]!;
    phone.on("request", (request) => {
      expect(request.url()).not.toContain(secret);
      if (new URL(request.url()).origin !== "http://127.0.0.1:4173")
        external.push(request.url());
    });
    await phone.goto(link!);
    await phone
      .getByLabel("Take or choose a photo")
      .setInputFiles("evals/fixtures/work.png");
    await expect(
      phone.getByAltText("Your photograph before submission"),
    ).toBeVisible();
    await phone
      .getByRole("button", { name: "Send to computer", exact: true })
      .click();
    await expect(phone.getByRole("heading", { level: 1 })).toHaveText(
      "Photo sent to your computer.",
    );
    await expect(page.locator(".tutor-feedback")).toHaveCount(1);
    await expect(page.locator(".tutor-feedback").first()).toContainText(
      /Synthetic/i,
    );
    await expect(
      page.getByRole("heading", {
        name: "Reading from your photo",
        exact: true,
      }),
    ).toBeVisible();
    const reading = page.getByRole("region", {
      name: "Reading from your photo",
      exact: true,
    });
    await expect(reading).toContainText("2/5");
    await expect(reading).toContainText("Handwriting and organization");
    expect(
      await reading.evaluate((element) => {
        const feedback = document.querySelector(".tutor-feedback");
        return (
          feedback !== null &&
          Boolean(
            element.compareDocumentPosition(feedback) &
            Node.DOCUMENT_POSITION_FOLLOWING,
          )
        );
      }),
    ).toBe(true);
    await expect(
      page.getByRole("button", { name: /confirm|approve|accept reading/i }),
    ).toHaveCount(0);
    await expect(page.locator(".verdict")).toHaveCount(0);
    expect(approvals).toEqual([]);
    expect(await phone.evaluate(() => location.hash)).toBe("#capture");
    expect(await phone.evaluate(() => Object.keys(localStorage))).toEqual([]);
    expect(
      (
        await mobile.request.get("http://127.0.0.1:4173/api/v1/sessions")
      ).status(),
    ).toBe(401);
    expect(external).toEqual([]);
  } finally {
    await mobile.close();
  }
  await page
    .getByRole("textbox", { name: "Your work or question", exact: true })
    .fill(
      "Revision: I counted two plants out of five and used the total number as the denominator.",
    );
  await page
    .getByRole("button", { name: "Share my work", exact: true })
    .click();
  await expect(page.locator(".tutor-feedback")).toHaveCount(2);
  await page
    .getByRole("textbox", { name: "Your work or question", exact: true })
    .fill(
      "Why should the denominator describe all plants rather than only the surviving ones?",
    );
  await page
    .getByRole("button", { name: "Ask about this", exact: true })
    .click();
  await expect(page.locator(".tutor-feedback")).toHaveCount(3);
  const next = page.waitForResponse(
    (response) =>
      response.url().endsWith("/activities") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Next activity", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Your work or question", exact: true }),
  ).toBeEditable();
  const nextActivity = (await (await next).json()) as Schema<"ProblemPublic">;
  expect(nextActivity.id).toMatch(/^[a-f0-9-]{36}$/);
  expect(nextActivity.id).not.toBe(firstActivity.id);
  await expect(page.locator(".tutor-history")).toHaveCount(2);
  await expect(page.locator(".tutor-feedback")).toHaveCount(3);
  expect(errors).toEqual([]);
});

test("reading and history reference material produces analogous practice instead of directly solving the supplied assignment", async ({
  page,
}) => {
  const alias = await startTutor(
    page,
    "Reading and history: evaluating a narrator's evidence",
  );
  const source =
    "My assigned homework: explain why the invented narrator Mira distrusts the mayor in chapter three of The Copper Lantern. Write the final paragraph for me.";
  await page
    .getByRole("combobox", { name: "Practice source", exact: true })
    .selectOption("reference_text");
  await page
    .getByRole("textbox", { name: "Reference material", exact: true })
    .fill(source);
  const generated = page.waitForResponse(
    (response) =>
      response.url().includes("/activities") &&
      response.request().method() === "POST",
  );
  await createActivity(page);
  expect((await generated).status()).toBe(201);
  await expect(page.locator(".tutor-activity")).not.toContainText(
    "Write the final paragraph for me",
  );
  await expect(page.locator(".tutor-activity")).toContainText(/Synthetic/i);
  await page
    .getByRole("textbox", { name: "Your work or question", exact: true })
    .fill(
      "The narrator makes a claim, but I would look for a quoted action supporting that claim before accepting it.",
    );
  await page
    .getByRole("button", { name: "Share my work", exact: true })
    .click();
  await expect(page.locator(".tutor-feedback")).toHaveCount(1);
  await expect(page.locator(".verdict")).toHaveCount(0);
  await page.getByText("Session settings", { exact: true }).click();
  await page
    .getByRole("combobox", { name: "Initiative for this session", exact: true })
    .selectOption("learner_led");
  await page
    .getByRole("button", { name: "Save tutor initiative", exact: true })
    .click();
  await page.reload();
  await page
    .getByRole("combobox", { name: "Learner", exact: true })
    .selectOption({ label: alias });
  await page.getByText("Session settings", { exact: true }).click();
  await expect(
    page.getByRole("combobox", {
      name: "Initiative for this session",
      exact: true,
    }),
  ).toHaveValue("learner_led");
});

test("an uncertain photographed response requests clearer organized work and never starts tutoring", async ({
  page,
}) => {
  await startTutor(page, "Writing: organizing evidence into a paragraph");
  await createActivity(page);
  const acceptedReadings: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/accept-reading"))
      acceptedReadings.push(request.url());
  });
  await page.getByText("Submit a photograph", { exact: true }).click();
  // Original generated blur fixture; not a downloaded worksheet or learner photo.
  await page
    .getByLabel("Take or choose a photo")
    .setInputFiles("evals/fixtures/vision/04-ambiguous.png");
  await page
    .getByRole("button", { name: "Submit this photograph", exact: true })
    .click();
  await expect(
    page.getByText("Please organize or retake this work.", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".tutor-feedback")).toHaveCount(0);
  await expect(page.locator(".verdict")).toHaveCount(0);
  expect(acceptedReadings).toEqual([]);
  // Rejection must not strand the learner or count as an incorrect answer.
  await expect(
    page.getByRole("textbox", { name: "Your work or question", exact: true }),
  ).toBeEditable();
});

test("a source photograph is read only to create distinct practice, not reviewed as the student's solution", async ({
  page,
}) => {
  await startTutor(page, "Science: explain the evidence behind a comparison");
  await page
    .getByRole("combobox", { name: "Practice source", exact: true })
    .selectOption("reference_photo");
  await page
    .getByRole("button", { name: "Create practice activity", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Your work or question", exact: true }),
  ).toHaveCount(0);
  await expect(page.locator(".tutor-activity")).toContainText(
    "Reference material",
  );
  await page.getByText("Submit a photograph", { exact: true }).click();
  await page
    .getByLabel("Take or choose a photo")
    .setInputFiles("evals/fixtures/work.png");
  await page
    .getByRole("button", { name: "Submit this photograph", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Reading from your photo", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Your work or question", exact: true }),
  ).toBeEditable();
  await expect(page.locator(".tutor-activity")).toContainText(
    "Synthetic practice",
  );
  await expect(page.locator(".tutor-feedback")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: /confirm|accept reading/i }),
  ).toHaveCount(0);
  await page
    .getByRole("textbox", { name: "Your work or question", exact: true })
    .fill(
      "My own response to the new activity: compare an observation from each group before making a claim.",
    );
  await page
    .getByRole("button", { name: "Share my work", exact: true })
    .click();
  await expect(page.locator(".tutor-feedback")).toHaveCount(1);
  await expect(page.locator(".verdict")).toHaveCount(0);
});
