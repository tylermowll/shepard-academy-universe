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

test("Meta hosted policy is explicit while local model controls remain usable", async ({
  page,
}) => {
  await login(page);
  await navigate(page, "Settings");
  await page
    .getByRole("button", { name: "Add AI connection", exact: true })
    .click();
  const connectionType = page.getByRole("combobox", {
    name: "Connection type",
    exact: true,
  });
  await expect(
    connectionType.getByRole("option", {
      name: "Meta hosted API",
      exact: true,
    }),
  ).toHaveCount(1);
  await connectionType.selectOption("meta");
  await expect(
    page.getByRole("combobox", {
      name: "Where this model runs",
      exact: true,
    }),
  ).toHaveCount(0);
  const fixedLocation = page.getByRole("group", {
    name: "Where this model runs",
    exact: true,
  });
  await expect(fixedLocation).toContainText("Cloud service Fixed");
  const metaAudience = page.getByRole("combobox", {
    name: "Allowed users",
    exact: true,
  });
  await expect(metaAudience).toBeEnabled();
  await expect(metaAudience).toHaveValue("mixed");
  await metaAudience.selectOption("adult_only");
  await expect(metaAudience).toHaveValue("adult_only");
  await expect(page.locator("#meta-policy-help")).toContainText(
    "records your decision; it is not a certification from this app",
  );
  await expect(page.locator("#meta-policy-help")).toContainText(
    "choose Ollama or vLLM instead",
  );

  await connectionType.selectOption("vllm");
  const boundary = page.getByRole("combobox", {
    name: "Where this model runs",
    exact: true,
  });
  const audience = page.getByRole("combobox", {
    name: "Allowed users",
    exact: true,
  });
  await expect(boundary).toBeEnabled();
  await expect(audience).toBeEnabled();
  await boundary.selectOption("cloud");
  await audience.selectOption("adult_only");
  await expect(boundary).toHaveValue("cloud");
  await expect(audience).toHaveValue("adult_only");
});

test("a saved connection stays selectable while setup blockers point to their exact steps", async ({
  page,
}) => {
  const fixture = await modelFixture();
  const id = `synthetic-pending-${Date.now()}`;
  try {
    await login(page);
    await navigate(page, "Settings");
    await page
      .getByRole("button", { name: "Add AI connection", exact: true })
      .click();
    await page.getByLabel("Connection name", { exact: true }).fill(id);
    await page
      .getByRole("combobox", { name: "Connection type", exact: true })
      .selectOption("compatible");
    await page
      .getByRole("combobox", { name: "Where this model runs", exact: true })
      .selectOption("local_network");
    await page
      .getByLabel("Server address", { exact: true })
      .fill(`${fixture.url}/v1`);
    await page
      .getByLabel("Model name", { exact: true })
      .fill("synthetic-million-context-model");
    await page
      .getByLabel("This model supports photo input", { exact: true })
      .check();
    await page
      .getByRole("combobox", { name: "Allowed users", exact: true })
      .selectOption("adult_only");
    await page.getByLabel("API key", { exact: true }).fill(syntheticKey);
    await page
      .getByText("Advanced connection options", { exact: true })
      .click();
    const contextLimit = page.getByLabel("Model context limit", {
      exact: true,
    });
    await contextLimit.fill("1000000");
    await expect(contextLimit).toHaveValue("1000000");
    expect(
      await contextLimit.evaluate(
        (input) => input instanceof HTMLInputElement && input.checkValidity(),
      ),
    ).toBe(true);
    await page
      .getByLabel(
        "I reviewed the model and provider terms for the users selected above.",
        { exact: true },
      )
      .check();
    await page
      .getByRole("button", { name: "Save connection", exact: true })
      .click();
    expect(fixture.calls()).toBe(0);

    await page.getByRole("tab", { name: /Connections/ }).click();
    const card = page
      .getByRole("article")
      .filter({ has: page.getByRole("heading", { name: id, exact: true }) });
    await expect(card).toContainText("Saved, but blocked by App permissions.");
    await expect(
      card.getByRole("button", { name: "Open App permissions", exact: true }),
    ).toBeVisible();

    await page.getByRole("tab", { name: /Assign active connections/ }).click();
    await expect(
      page.getByRole("heading", {
        name: "Assign active connections",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByText(/used across this app for future learner work/i),
    ).toBeVisible();
    await expect(
      page.getByText(
        /Saving a connection never activates it; this final step does/i,
      ),
    ).toBeVisible();
    const tutor = page.getByRole("combobox", {
      name: "Tutor connection",
      exact: true,
    });
    const photoReader = page.getByRole("combobox", {
      name: "Photo reader connection",
      exact: true,
    });
    await expect(tutor.locator(`option[value="${id}"]`)).toBeEnabled();
    await expect(photoReader.locator(`option[value="${id}"]`)).toBeEnabled();
    await tutor.selectOption(id);
    await photoReader.selectOption(id);
    await expect(tutor).toHaveValue(id);
    await expect(photoReader).toHaveValue(id);
    await expect(
      page.getByText(
        "Its Allowed users setting does not match the app-wide audience.",
      ),
    ).toHaveCount(2);
    await expect(
      page.getByText("Its tutor test has not passed.", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Its photo-reader test has not passed.", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Open App permissions", exact: true }),
    ).toHaveCount(2);
    await expect(
      page.getByRole("button", { name: "Open Connection tests", exact: true }),
    ).toHaveCount(2);
    await page
      .getByLabel(
        "I authorize these app-wide connections to process future learner text and photos.",
        { exact: true },
      )
      .check();
    await expect(
      page.getByRole("button", {
        name: "Save active connections",
        exact: true,
      }),
    ).toBeDisabled();

    await page
      .getByRole("button", { name: "Open App permissions", exact: true })
      .first()
      .click();
    const permissionsHeading = page.getByRole("heading", {
      name: "App permissions",
      exact: true,
    });
    await expect(permissionsHeading).toBeVisible();
    await expect(permissionsHeading).toBeFocused();
    await expect(
      page.getByText(
        /one app-wide permission gate for every connection and learner/i,
      ),
    ).toBeVisible();
    const appAudience = page.getByRole("combobox", {
      name: "Who uses this app?",
      exact: true,
    });
    await expect(appAudience).toHaveValue("mixed");
    await expect(appAudience).toBeDisabled();
    await expect(page.getByText(/locked the app audience/i)).toBeVisible();

    const settings = await page.request.get("/api/v1/admin/providers");
    const body = (await settings.json()) as {
      routes: { tutor: string; vision: string };
      providers: Array<{
        id: string;
        tutor_probed: boolean;
        vision_probed: boolean;
        configured_context_limit: number;
      }>;
    };
    expect(body.routes).toEqual({ tutor: "demo", vision: "demo" });
    expect(body.providers.find((provider) => provider.id === id)).toMatchObject(
      {
        tutor_probed: false,
        vision_probed: false,
        configured_context_limit: 1_000_000,
      },
    );
    expect(fixture.calls()).toBe(0);

    await page.getByRole("tab", { name: /Connections/ }).click();
    await card
      .getByText("Technical details and actions", { exact: true })
      .click();
    page.once("dialog", (dialog) => dialog.accept());
    await card
      .getByRole("button", { name: "Delete connection", exact: true })
      .click();
    await expect(card).toHaveCount(0);
  } finally {
    await fixture.close();
  }
});

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
      const tutorStatus = card
        .locator("dl.readiness-list > div")
        .filter({ hasText: "Tutor test" });
      const photoReaderStatus = card
        .locator("dl.readiness-list > div")
        .filter({ hasText: "Photo-reader test" });
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
        await expect(tutorStatus).toContainText("Not run");
        expect(fixture.calls()).toBe(1);
        fixture.rejectAuthentication(false);
      }
      page.once("dialog", (dialog) => dialog.accept());
      await card
        .getByRole("button", { name: "Test tutor", exact: true })
        .click();
      await expect(tutorStatus).toContainText("Passed");
      page.once("dialog", (dialog) => dialog.accept());
      await card
        .getByRole("button", { name: "Test photo reader", exact: true })
        .click();
      await expect(photoReaderStatus).toContainText("Passed");
      expect(fixture.calls()).toBe(3 + failedCalls);
      expect(fixture.authenticatedCalls()).toBe(3 + failedCalls);
      await page
        .getByRole("tab", { name: /Assign active connections/ })
        .click();
      await page
        .getByRole("combobox", { name: "Tutor connection", exact: true })
        .selectOption(id);
      await page
        .getByRole("combobox", {
          name: "Photo reader connection",
          exact: true,
        })
        .selectOption(id);
      await page
        .getByLabel(
          "I authorize these app-wide connections to process future learner text and photos.",
          { exact: true },
        )
        .check();
      await page
        .getByRole("button", {
          name: "Save active connections",
          exact: true,
        })
        .click();
      await expect(
        page
          .getByRole("status")
          .filter({ hasText: "Active connections saved" }),
      ).toBeVisible();

      await page.reload();
      await page
        .getByRole("tab", { name: /Assign active connections/ })
        .click();
      await expect(
        page.getByRole("combobox", {
          name: "Tutor connection",
          exact: true,
        }),
      ).toHaveValue(id);
      await expect(
        page.getByRole("combobox", {
          name: "Photo reader connection",
          exact: true,
        }),
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
      await page.getByRole("tab", { name: /Connections/ }).click();
      const editConnection = card.getByRole("button", {
        name: "Edit connection",
        exact: true,
      });
      await expect(editConnection).toBeVisible();
      await editConnection.click();
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
      await expect(tutorStatus).toContainText("Not run");
      await expect(photoReaderStatus).toContainText("Not run");
      expect(fixture.calls()).toBe(4 + failedCalls);
      // Editing persisted settings doesn't redisplay the saved secret.
      const edited = await page.request.get("/api/v1/admin/providers");
      expect(await edited.text()).not.toContain(syntheticKey);
      await page.getByRole("tab", { name: /Connections/ }).click();
      const details = card.getByText("Technical details and actions", {
        exact: true,
      });
      if (
        !(await details
          .locator("..")
          .evaluate((node) => node.hasAttribute("open")))
      )
        await details.click();
      await expect(card).toContainText("API key: not saved");
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
