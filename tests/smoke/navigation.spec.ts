import { expect, test, type Page } from "@playwright/test";
import {
  createActivity,
  createLearner,
  login,
  navigate,
  openAttachments,
  openSessionTools,
  startTutor,
} from "./support";

async function expectPageFits(page: Page) {
  await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
}

test("guests can open and reload Help without exposing account controls", async ({
  page,
}) => {
  await page.goto("/?page=help");
  const navigation = page.getByRole("navigation", { name: "Main navigation" });
  await expect(navigation.getByRole("link")).toHaveText(["Sign in", "Help"]);
  await expect(
    navigation.getByRole("link", { name: "Help", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Help");
  await expect(page.getByRole("button", { name: "Add learner" })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("button", { name: "Approve device" }),
  ).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Test tutor" })).toHaveCount(0);
  await expectPageFits(page);

  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Help");
  await page
    .getByRole("navigation", { name: "Help topics" })
    .getByRole("link", { name: "Phone setup", exact: true })
    .click();
  await expect(page).toHaveURL(/page=help&help=phone/);
  await expect(
    page.getByRole("heading", {
      name: "Send a photo while you work on the computer",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Use the whole tutor on the phone",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("This address works only on this computer.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText(/No sign-in or device pairing is needed for this photo/),
  ).toBeVisible();
  await expectPageFits(page);
  await navigation.getByRole("link", { name: "Sign in", exact: true }).click();
  await expect(page.getByLabel("Login name", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Pair this device" }),
  ).toBeVisible();
});

test("adult pages isolate each job and browser navigation preserves a new session draft", async ({
  page,
}) => {
  const external: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).origin !== "http://127.0.0.1:4173")
      external.push(request.url());
  });
  await login(page);
  const navigation = page.getByRole("navigation", { name: "Main navigation" });
  await expect(navigation.getByRole("link")).toHaveText([
    "Practice",
    "History",
    "Learners & devices",
    "Settings",
    "Help",
  ]);
  await createLearner(page);
  const topic = page.getByRole("textbox", {
    name: "Topic or learning goal",
    exact: true,
  });
  await topic.fill("Synthetic draft: comparing two scientific explanations");
  const practiceHelp = page.getByText("What can I practice?", { exact: true });
  const practiceHelpDetails = practiceHelp.locator("..");
  await expect(practiceHelpDetails).not.toHaveAttribute("open", "");
  await practiceHelp.focus();
  await page.keyboard.press("Enter");
  await expect(practiceHelpDetails).toHaveAttribute("open", "");
  await expect(practiceHelpDetails).toContainText("reference material");
  await page.keyboard.press("Enter");
  await expect(practiceHelpDetails).not.toHaveAttribute("open", "");
  await expect(page.getByRole("button", { name: "Add learner" })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("button", { name: "Approve device" }),
  ).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Test tutor" })).toHaveCount(0);
  await expectPageFits(page);

  await navigate(page, "Help");
  await expect(topic).not.toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Help");
  await expectPageFits(page);
  await navigate(page, "History");
  await expect(topic).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Start session" })).toHaveCount(
    0,
  );
  await expectPageFits(page);
  await page.goBack();
  await expect(
    navigation.getByRole("link", { name: "Help", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await page.goBack();
  await expect(
    navigation.getByRole("link", { name: "Practice", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await expect(topic).toHaveValue(
    "Synthetic draft: comparing two scientific explanations",
  );

  await navigate(page, "Settings");
  await page.getByRole("tab", { name: /Connection tests/ }).click();
  await expect(page.getByRole("button", { name: "Test tutor" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Approve device" }),
  ).toHaveCount(0);
  await expect(topic).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: "Download and load experiment" }),
  ).toHaveCount(0);
  await expectPageFits(page);
  await navigate(page, "Learners & devices");
  await expect(page.getByRole("button", { name: "Add learner" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Approve device" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Test tutor" })).toHaveCount(0);
  await expect(topic).not.toBeVisible();
  await expectPageFits(page);
  await navigate(page, "Practice");
  await expect(topic).toHaveValue(
    "Synthetic draft: comparing two scientific explanations",
  );
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([]);
  expect(external).toEqual([]);
});

test("Help and History preserve unsent work and saved sessions reopen through History", async ({
  page,
}) => {
  const topic = "Synthetic navigation: supporting a claim with evidence";
  await startTutor(page, topic);
  await createActivity(page);
  const response = page.getByRole("textbox", {
    name: "Your work or question",
    exact: true,
  });
  await response.fill(
    "A source should contain observations supporting the claim.",
  );
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.locator(".tutor-feedback")).toHaveCount(1);
  const sessionHash = await page.evaluate(() => location.hash);
  const draft = "Unsent revision: I also need to compare another source.";
  await response.fill(draft);
  await openAttachments(page);
  await page.getByText("How do I use my phone?", { exact: true }).click();
  await page.evaluate(() =>
    window.scrollTo(0, document.documentElement.scrollHeight),
  );
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
  await page
    .getByRole("button", { name: "Phone setup help", exact: true })
    .click();
  await expect(page).toHaveURL(/page=help&help=phone/);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  await expect(
    page.getByRole("heading", { level: 1, name: "Help", exact: true }),
  ).toBeInViewport();
  await expect(response).not.toBeVisible();
  await navigate(page, "History");
  await expect(
    page.getByRole("heading", { name: topic, exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Continue session", exact: true })
    .click();
  await expect(response).toHaveValue(draft);
  expect(await page.evaluate(() => location.hash)).toBe(sessionHash);
  await response.fill("");
  await navigate(page, "History");
  await page
    .getByRole("button", { name: "Continue session", exact: true })
    .click();
  await expect(
    page
      .getByRole("navigation", { name: "Main navigation" })
      .getByRole("link", { name: "Practice", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await expect(page.locator(".tutor-feedback")).toHaveCount(1);
  expect(await page.evaluate(() => location.hash)).toBe(sessionHash);
  await openSessionTools(page);
  await page.getByText("Session settings", { exact: true }).click();
  await page
    .getByRole("button", { name: "Finish session", exact: true })
    .click();
  await navigate(page, "History");
  await page
    .getByRole("button", { name: "Review session", exact: true })
    .click();
  await expect(page.locator(".tutor-feedback")).toHaveCount(1);
  await expect(response).toHaveCount(0);
});

test("an adult practices with their own learner profile and browser Back restores the selected saved session", async ({
  page,
}) => {
  await login(page);
  await navigate(page, "Learners & devices");
  await page
    .getByRole("button", { name: "Create my practice profile", exact: true })
    .click();
  const learnerName = page.getByLabel("Learner name", { exact: true });
  await expect(learnerName).toHaveValue("demo");
  await expect(learnerName).toBeEditable();
  await expect(
    page.getByRole("combobox", { name: "Age group", exact: true }),
  ).toHaveValue("adult");
  const alias = `Synthetic adult ${Date.now()}`;
  await learnerName.fill(alias);
  const created = page.waitForResponse(
    (response) =>
      response.url().endsWith("/admin/learners") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Add learner", exact: true }).click();
  const createdResponse = await created;
  expect(createdResponse.status()).toBe(201);
  expect(await createdResponse.json()).toMatchObject({
    alias,
    eligibility: "adult",
  });
  await expect(
    page.getByRole("region", { name: "Selected learner", exact: true }),
  ).toContainText(alias);
  await page
    .getByRole("button", { name: "Start practice", exact: true })
    .click();

  const topicA = "Synthetic adult practice: compare scientific explanations";
  const topicB = "Synthetic adult practice: evaluate a historical source";
  const topicField = page.getByRole("textbox", {
    name: "Topic or learning goal",
    exact: true,
  });
  await topicField.fill(topicA);
  await page
    .getByRole("button", { name: "Start session", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: topicA, level: 2, exact: true }),
  ).toBeVisible();
  const hashA = await page.evaluate(() => location.hash);
  expect(hashA).toMatch(/^#tutor=[a-f0-9-]{36}$/);
  await page.getByRole("button", { name: "New session", exact: true }).click();
  await topicField.fill(topicB);
  await page
    .getByRole("button", { name: "Start session", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: topicB, level: 2, exact: true }),
  ).toBeVisible();
  const hashB = await page.evaluate(() => location.hash);
  expect(hashB).toMatch(/^#tutor=[a-f0-9-]{36}$/);
  expect(hashB).not.toBe(hashA);

  await navigate(page, "History");
  await page
    .getByRole("article")
    .filter({ has: page.getByRole("heading", { name: topicA, exact: true }) })
    .getByRole("button", { name: "Continue session", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: topicA, level: 2, exact: true }),
  ).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`page=practice${hashA}$`));
  await navigate(page, "History");
  await page
    .getByRole("article")
    .filter({ has: page.getByRole("heading", { name: topicB, exact: true }) })
    .getByRole("button", { name: "Continue session", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: topicB, level: 2, exact: true }),
  ).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`page=practice${hashB}$`));
  await page.goBack();
  await expect(
    page
      .getByRole("navigation", { name: "Main navigation" })
      .getByRole("link", { name: "History", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await page.goBack();
  await expect(
    page.getByRole("heading", { name: topicA, level: 2, exact: true }),
  ).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`page=practice${hashA}$`));
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }).getByRole("link"),
  ).toHaveText([
    "Practice",
    "History",
    "Learners & devices",
    "Settings",
    "Help",
  ]);
  await expect(
    page.getByRole("button", { name: "Sign out", exact: true }),
  ).toBeVisible();
});
