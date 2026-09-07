import { createServer } from "node:http";
import { expect, test, type Page } from "@playwright/test";
import { createActivity, createLearner, login, navigate } from "./support";

const syntheticKey = "synthetic-connection-browser-fixture-only";

async function modelFixture() {
  let calls = 0;
  let authenticatedCalls = 0;
  let rejectAuthentication = false;
  const server = createServer((request, response) => {
    let text = "";
    request.on("data", (part: Buffer) => {
      text += part.toString();
    });
    request.on("end", () => {
      calls += 1;
      if (request.headers.authorization === `Bearer ${syntheticKey}`)
        authenticatedCalls += 1;
      if (rejectAuthentication) {
        response.writeHead(401, { "Content-Type": "application/json" });
        response.end(JSON.stringify({ error: { message: syntheticKey } }));
        return;
      }
      const wire = JSON.parse(text) as {
        format?: { properties?: Record<string, unknown> };
        response_format?: {
          json_schema?: { schema?: { properties?: Record<string, unknown> } };
        };
      };
      const properties =
        wire.format?.properties ??
        wire.response_format?.json_schema?.schema?.properties ??
        {};
      const payload =
        "problem_text" in properties
          ? {
              problem_text:
                "Synthetic connected-model activity: Describe two observations you could make when comparing plants grown in light and shade.",
              concept_focus: "Synthetic comparison of observations",
            }
          : "strengths" in properties
            ? {
                strengths: ["Synthetic review received."],
                guidance: ["Compare observations from both groups."],
                next_step: "Describe another observation.",
                concepts: ["Observations"],
                uncertainty_note: null,
              }
            : "quality" in properties
              ? {
                  transcription: "1/2",
                  quality: "clear",
                  confidence: 1,
                  ambiguities: [],
                  organization_feedback: [],
                  rejection_reason: null,
                }
              : {
                  schema_version: "1",
                  message_kind: "question_response",
                  message_markdown: "Synthetic connection test response.",
                  suggested_next_action: "continue",
                  uncertainty_note: null,
                };
      const content = JSON.stringify(payload);
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(
        JSON.stringify(
          request.url === "/api/chat"
            ? {
                done: true,
                done_reason: "stop",
                message: { role: "assistant", content },
                prompt_eval_count: 1,
                eval_count: 1,
              }
            : {
                choices: [
                  {
                    message: { role: "assistant", content },
                    finish_reason: "stop",
                  },
                ],
                usage: { prompt_tokens: 1, completion_tokens: 1 },
              },
        ),
      );
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string")
    throw new Error("No fixture port");
  return {
    url: `http://127.0.0.1:${address.port}`,
    calls: () => calls,
    authenticatedCalls: () => authenticatedCalls,
    rejectAuthentication: (reject: boolean) => {
      rejectAuthentication = reject;
    },
    close: () =>
      new Promise<void>((resolve, reject) =>
        server.close((error) => (error ? reject(error) : resolve())),
      ),
  };
}

async function restoreDemoRoutes(page: Page) {
  const session = await page.request.get("/api/v1/auth/session");
  const identity = (await session.json()) as { csrf_token: string };
  const response = await page.request.post("/api/v1/admin/providers/routes", {
    headers: { "X-CSRF-Token": identity.csrf_token },
    data: {
      tutor: "demo",
      vision: "demo",
      acknowledge_data_boundary: true,
    },
  });
  expect(response.status()).toBe(200);
}

for (const adapter of ["vllm", "ollama", "compatible"] as const) {
  test(`adult configures ${adapter} with a write-only key, probes it, and uses it without a restart`, async ({
    page,
  }) => {
    const fixture = await modelFixture();
    const id = `synthetic-${adapter}-${Date.now()}`;
    const failedCalls = adapter === "compatible" ? 1 : 0;
    try {
      await login(page);
      await navigate(page, "Settings");
      await page
        .getByRole("button", { name: "Add AI connection", exact: true })
        .click();
      await page.getByLabel("Connection name", { exact: true }).fill(id);
      await page
        .getByRole("combobox", { name: "Connection type", exact: true })
        .selectOption(adapter);
      if (adapter === "compatible") {
        await expect(page.getByLabel("API key", { exact: true })).toBeVisible();
      }
      await page
        .getByRole("combobox", { name: "Where this model runs", exact: true })
        .selectOption("local_network");
      await page
        .getByLabel("Server address", { exact: true })
        .fill(adapter === "ollama" ? fixture.url : `${fixture.url}/v1`);
      await page
        .getByLabel("Model name", { exact: true })
        .fill("synthetic-model-v1");
      await page
        .getByLabel("This model supports photo input", { exact: true })
        .check();
      await page
        .getByRole("combobox", { name: "API key action", exact: true })
        .selectOption("replace");
      await page.getByLabel("API key", { exact: true }).fill(syntheticKey);
      await page
        .getByLabel(
          "I reviewed the model and provider terms for the users selected above.",
          { exact: true },
        )
        .check();
      await page
        .getByRole("button", { name: "Save connection", exact: true })
        .click();
      const card = page
        .getByRole("article")
        .filter({ has: page.getByRole("heading", { name: id, exact: true }) });
      await expect(card).toBeVisible();
      expect(fixture.calls()).toBe(0);
      await expect(page.getByLabel("API key", { exact: true })).toHaveCount(0);
      const settings = await page.request.get("/api/v1/admin/providers");
      expect(settings.headers()["cache-control"]).toBe("no-store");
      expect(await settings.text()).not.toContain(syntheticKey);
      expect(
        await page.evaluate(() =>
          JSON.stringify({
            local: { ...localStorage },
            session: { ...sessionStorage },
          }),
        ),
      ).not.toContain(syntheticKey);

      // Cancel really means no synthetic call (and no charge).
      page.once("dialog", (dialog) => dialog.dismiss());
      await card
        .getByRole("button", { name: "Test tutor", exact: true })
        .click();
      expect(fixture.calls()).toBe(0);
      if (adapter === "compatible") {
        fixture.rejectAuthentication(true);
        page.once("dialog", (dialog) => dialog.accept());
        await card
          .getByRole("button", { name: "Test tutor", exact: true })
          .click();
        await expect(page.getByRole("alert")).toContainText(
          "Edit this connection and replace the key",
        );
        await expect(page.getByRole("alert")).not.toContainText(syntheticKey);
        await expect(card).toContainText("Tutor: not tested");
        expect(fixture.calls()).toBe(1);
        fixture.rejectAuthentication(false);
      }
      page.once("dialog", (dialog) => dialog.accept());
      await card
        .getByRole("button", { name: "Test tutor", exact: true })
        .click();
      await expect(card).toContainText("Tutor: test recorded");
      page.once("dialog", (dialog) => dialog.accept());
      await card
        .getByRole("button", { name: "Test photo reader", exact: true })
        .click();
      await expect(card).toContainText("Photo reader: test recorded");
      expect(fixture.calls()).toBe(3 + failedCalls);
      expect(fixture.authenticatedCalls()).toBe(3 + failedCalls);
      await page
        .getByRole("combobox", { name: "Tutor", exact: true })
        .selectOption(id);
      await page
        .getByRole("combobox", { name: "Photo reader", exact: true })
        .selectOption(id);
      await page
        .getByLabel(
          "I authorize sending text and photos to the providers selected above.",
          { exact: true },
        )
        .check();
      await page
        .getByRole("button", { name: "Save AI settings", exact: true })
        .click();
      await expect(
        page.getByRole("status").filter({ hasText: "AI settings saved" }),
      ).toBeVisible();

      await page.reload();
      await expect(
        page.getByRole("combobox", { name: "Tutor", exact: true }),
      ).toHaveValue(id);
      await expect(
        page.getByRole("combobox", { name: "Photo reader", exact: true }),
      ).toHaveValue(id);
      await createLearner(page);
      await page
        .getByLabel("Topic or learning goal", { exact: true })
        .fill("Synthetic connection workflow");
      await page
        .getByRole("button", { name: "Start session", exact: true })
        .click();
      await createActivity(page);
      await expect(page.locator(".tutor-activity")).toContainText(
        "Synthetic connected-model activity",
      );
      expect(fixture.calls()).toBe(4 + failedCalls);
      expect(fixture.authenticatedCalls()).toBe(4 + failedCalls);

      await restoreDemoRoutes(page);
      await navigate(page, "Settings");
      await page
        .getByText("Connection tests & provider details", { exact: true })
        .click();
      await card.getByText("Connection details", { exact: true }).click();
      await card
        .getByRole("button", { name: "Edit connection", exact: true })
        .click();
      await expect(
        page.getByRole("combobox", { name: "API key action", exact: true }),
      ).toHaveValue("keep");
      await expect(page.getByLabel("API key", { exact: true })).toHaveCount(0);
      await page
        .getByRole("combobox", { name: "API key action", exact: true })
        .selectOption("remove");
      await page
        .getByLabel(
          "I reviewed the model and provider terms for the users selected above.",
          { exact: true },
        )
        .check();
      await page
        .getByRole("button", { name: "Save connection", exact: true })
        .click();
      await expect(card).toContainText("Tutor: not tested");
      await expect(card).toContainText("Photo reader: not tested");
      expect(fixture.calls()).toBe(4 + failedCalls);
      // Editing persisted settings doesn't redisplay the saved secret.
      const edited = await page.request.get("/api/v1/admin/providers");
      expect(await edited.text()).not.toContain(syntheticKey);
      const details = card.getByText("Connection details", { exact: true });
      if (
        !(await details
          .locator("..")
          .evaluate((node) => node.hasAttribute("open")))
      )
        await details.click();
      await expect(card).toContainText("No API key saved");
      page.once("dialog", (dialog) => dialog.accept());
      await card
        .getByRole("button", { name: "Delete connection", exact: true })
        .click();
      await expect(card).toHaveCount(0);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    } finally {
      try {
        await restoreDemoRoutes(page);
      } finally {
        await fixture.close();
      }
    }
  });
}
