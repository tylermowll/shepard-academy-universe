import { expect, test } from "@playwright/test";
import { createLearner, login, navigate } from "./support";

test("administrator prevents duplicate accounts and resets a learner's password without losing their identity", async ({
  page,
  browser,
}) => {
  await login(page);
  const username = await createLearner(page, false);
  await navigate(page, "Learners");
  await expect(
    page.getByRole("combobox", { name: "Learner", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Add learner account", exact: true })
    .click();
  await page
    .getByLabel("Learner username", { exact: true })
    .fill(` ${username.toUpperCase()} `);
  await page
    .getByLabel("Password", { exact: true })
    .fill("synthetic-demo-password-only");
  await page
    .getByRole("button", { name: "Create learner account", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "username is already in use",
  );
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  const context = await browser.newContext();
  try {
    const learner = await context.newPage();
    await login(learner, username);
    const signedIn = (await (
      await learner.request.get("/api/v1/auth/session")
    ).json()) as { learner_id: string };
    const learnerId = signedIn.learner_id;
    await expect(
      learner
        .getByRole("navigation", { name: "Main navigation" })
        .getByRole("link"),
    ).toHaveText(["Practice", "History", "Help"]);
    const replacement = "synthetic-account-replacement";
    const updatedName = `${username} updated`;
    await page
      .getByLabel("Learner username", { exact: true })
      .fill(updatedName);
    await page.getByLabel("New password", { exact: true }).fill(replacement);
    await page
      .getByRole("button", { name: "Save sign-in details", exact: true })
      .click();
    await expect(page.getByRole("status")).toContainText(
      "Previous learner sign-ins have ended",
    );
    await expect(page.getByLabel("New password", { exact: true })).toHaveValue(
      "",
    );
    expect((await learner.request.get("/api/v1/tutor/sessions")).status()).toBe(
      401,
    );
    await login(learner, updatedName, replacement);
    const identity = await learner.request.get("/api/v1/auth/session");
    expect(await identity.json()).toMatchObject({ learner_id: learnerId });
    expect((await learner.request.get("/api/v1/admin/learners")).status()).toBe(
      403,
    );
    await expect(
      page
        .getByRole("navigation", { name: "Main navigation" })
        .getByRole("link"),
    ).toHaveText(["Learners", "Settings", "Help"]);
    await page.screenshot({
      path: test.info().outputPath("learner-accounts.png"),
      fullPage: true,
    });
  } finally {
    await context.close();
  }
});
