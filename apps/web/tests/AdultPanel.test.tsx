import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AdultPanel } from "../src/AdultPanel";
import { setIdentity, type Schema } from "../src/client";

const learner: Schema<"LearnerPublic"> = {
  id: "4a15f6fc-8866-468e-801c-1faedc9ae88b",
  alias: "Orbit",
  eligibility: "unknown",
  enabled: true,
};
const pairId = "c50a2621-21eb-4670-9269-d9c491479635";
const providers: Schema<"ProvidersPublic"> = {
  policy: {
    allow_cloud_inference: false,
    app_audience: "mixed",
    cloud_locked: false,
    audience_locked: false,
    demo_mode: false,
  },
  routes: { tutor: "demo", vision: "demo" },
  providers: [
    {
      id: "demo",
      adapter: "mock",
      model: "fixture-v1",
      boundary: "synthetic",
      audience: "mixed",
      enabled: true,
      image_input: true,
      tutor_probed: true,
      vision_probed: true,
      managed: false,
      key_configured: false,
      key_needs_replacement: false,
      requires_approval: false,
      eligibility_record: "Synthetic test fixture.",
      configured_context_limit: 8192,
      structured_output_mode: "native",
    },
    {
      id: "local-text",
      adapter: "ollama",
      model: "synthetic-model",
      boundary: "local_network",
      audience: "mixed",
      enabled: true,
      image_input: false,
      tutor_probed: true,
      vision_probed: false,
      managed: false,
      key_configured: false,
      key_needs_replacement: false,
      requires_approval: false,
      eligibility_record: "Synthetic test fixture.",
      configured_context_limit: 8192,
      structured_output_mode: "native",
    },
  ],
};
const response = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const failures: Error[] = [];
const run = async (action: () => Promise<void>) => {
  try {
    await action();
  } catch (cause) {
    failures.push(cause as Error);
  }
};
const props = () => ({
  learner: learner.id,
  learners: [learner],
  onLearner: vi.fn(),
  onRefresh: vi.fn(() => Promise.resolve()),
  page: "learners" as const,
  onNavigate: vi.fn(),
  onProvidersChanged: vi.fn(),
  act: run,
});

beforeEach(() => {
  failures.length = 0;
  setIdentity("synthetic-csrf", true);
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(response(providers))),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("learner and device page", () => {
  it("keeps provider setup off this page and explains pairing versus camera-only use", () => {
    const handlers = props();
    render(<AdultPanel {...handlers} />);
    expect(fetch).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("combobox", { name: "Tutor" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/Copy the request ID shown on that device/),
    ).toBeVisible();
    fireEvent.click(screen.getByText("Only need the phone camera?"));
    expect(
      screen.getByText(/No pairing or phone sign-in is needed/),
    ).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: "How phone photos work" }),
    );
    expect(handlers.onNavigate).toHaveBeenCalledWith("help", "phone");
    expect(
      screen.getByRole("button", { name: "Delete learner", hidden: true }),
    ).not.toBeVisible();
  });

  it("adds the learner, refreshes the shared list, and selects it without forcing navigation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(response(learner))),
    );
    vi.spyOn(crypto, "randomUUID").mockReturnValue(pairId);
    const handlers = props();
    render(<AdultPanel {...handlers} learner="" learners={[]} />);
    fireEvent.change(screen.getByLabelText("Learner name"), {
      target: { value: learner.alias },
    });
    fireEvent.change(screen.getByLabelText("Age group"), {
      target: { value: "minor" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add learner" }));
    await screen.findByText("Orbit added. You can start practice now.");
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/admin/learners",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ alias: "Orbit", eligibility: "minor" }),
        headers: {
          "X-CSRF-Token": "synthetic-csrf",
          "Content-Type": "application/json",
          "Idempotency-Key": pairId,
        },
      }),
    );
    expect(handlers.onRefresh).toHaveBeenCalledOnce();
    expect(handlers.onLearner).toHaveBeenCalledWith(learner.id);
    expect(handlers.onNavigate).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Learner name")).toHaveValue("");
  });

  it("prefills an editable adult profile for the parent without creating it until submitted", async () => {
    const ownProfile = { ...learner, alias: "Me", eligibility: "adult" };
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(response(ownProfile))),
    );
    const handlers = props();
    render(<AdultPanel {...handlers} />);
    expect(
      screen.getByText(/Your adult sign-in manages this app/),
    ).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: "Add yourself (adult)" }),
    );
    const name = screen.getByLabelText("Learner name");
    expect(name).toHaveValue("Me");
    expect(name).toHaveFocus();
    expect(name).not.toHaveAttribute("readonly");
    expect(screen.getByLabelText("Age group")).toHaveValue("adult");
    expect(fetch).not.toHaveBeenCalled();
    expect(handlers.onLearner).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Add learner" }));
    await screen.findByText("Me added. You can start practice now.");
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/admin/learners",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ alias: "Me", eligibility: "adult" }),
      }),
    );
    expect(handlers.onLearner).toHaveBeenCalledWith(ownProfile.id);
  });

  it.each(["add", "delete"] as const)(
    "refreshes learners after a delayed %s finishes without changing selection after leaving the page",
    async (action) => {
      let finish: (value: Response) => void = () => {
        throw new Error("The request has not started.");
      };
      const pending = new Promise<Response>((resolve) => {
        finish = resolve;
      });
      vi.stubGlobal(
        "fetch",
        vi.fn(() => pending),
      );
      const handlers = props();
      const panel = render(<AdultPanel {...handlers} />);
      const form = screen.getByLabelText("Learner name").closest("form")!;
      const reset = vi.spyOn(form, "reset");
      if (action === "add") {
        fireEvent.change(screen.getByLabelText("Learner name"), {
          target: { value: "Delta" },
        });
        fireEvent.click(screen.getByRole("button", { name: "Add learner" }));
      } else {
        vi.spyOn(window, "confirm").mockReturnValue(true);
        fireEvent.click(screen.getByText("Saved data & device access"));
        fireEvent.click(screen.getByRole("button", { name: "Delete learner" }));
      }
      expect(fetch).toHaveBeenCalledOnce();
      panel.unmount();
      // App may now be showing another learner's unsent practice draft. A
      // callback from the old panel must not replace that current selection.
      await act(async () => {
        finish(
          response(
            action === "add" ? { ...learner, id: pairId, alias: "Delta" } : {},
          ),
        );
        await pending;
      });
      expect(handlers.onRefresh).toHaveBeenCalledOnce();
      expect(handlers.onLearner).not.toHaveBeenCalled();
      expect(reset).not.toHaveBeenCalled();
      expect(failures).toHaveLength(0);
    },
  );

  it("approves the request for the selected learner and preserves the request on rejection", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(
          response({ detail: "This request expired." }, 403),
        )
        .mockResolvedValueOnce(response({ approved: true })),
    );
    render(<AdultPanel {...props()} />);
    fireEvent.change(screen.getByLabelText("Pairing request ID"), {
      target: { value: pairId },
    });
    fireEvent.click(screen.getByRole("button", { name: "Approve device" }));
    await vi.waitFor(() => expect(failures).toHaveLength(1));
    expect(failures[0]?.message).toBe("This request expired.");
    expect(screen.getByLabelText("Pairing request ID")).toHaveValue(pairId);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Approve device" }));
    await screen.findByText(
      "Device approved for Orbit. The other browser will sign in automatically.",
    );
    expect(fetch).toHaveBeenLastCalledWith(
      `/api/v1/admin/pairing/${pairId}/approve`,
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ learner_id: learner.id }),
      }),
    );
    expect(screen.getByLabelText("Pairing request ID")).toHaveValue("");
  });

  it("requires a current learner for pairing and confirmation before deleting saved work", () => {
    const handlers = props();
    const { rerender } = render(
      <AdultPanel {...handlers} learner="stale-id" />,
    );
    expect(
      screen.getByRole("button", { name: "Approve device" }),
    ).toBeDisabled();
    rerender(<AdultPanel {...handlers} />);
    fireEvent.click(screen.getByText("Saved data & device access"));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    fireEvent.click(screen.getByRole("button", { name: "Delete learner" }));
    expect(confirm).toHaveBeenCalledWith(
      expect.stringContaining("Orbit's saved practice"),
    );
    expect(fetch).not.toHaveBeenCalled();
    expect(handlers.onRefresh).not.toHaveBeenCalled();
  });
});

describe("AI settings page", () => {
  it("separates the four setup purposes into keyboard-navigable tabs", async () => {
    render(<AdultPanel {...props()} page="settings" />);
    const connections = await screen.findByRole("tab", {
      name: /Connections.*Save model access/,
    });
    const permissions = screen.getByRole("tab", {
      name: /App permissions.*Allow data use/,
    });
    const tests = screen.getByRole("tab", {
      name: /Connection tests.*Check readiness/,
    });
    const roles = screen.getByRole("tab", {
      name: /Assign active connections.*Activate for the app/,
    });
    expect(screen.getAllByRole("tab")).toHaveLength(4);
    expect(connections).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "Connections" })).toBeVisible();

    fireEvent.click(permissions);
    expect(permissions).toHaveAttribute("aria-selected", "true");
    expect(
      screen.getByRole("heading", { name: "App permissions" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Add AI connection" }),
    ).not.toBeInTheDocument();

    fireEvent.keyDown(permissions, { key: "ArrowRight" });
    expect(tests).toHaveAttribute("aria-selected", "true");
    expect(
      screen.getByRole("heading", { name: "Connection tests" }),
    ).toBeVisible();
    expect(tests).toHaveFocus();

    fireEvent.keyDown(tests, { key: "End" });
    expect(roles).toHaveAttribute("aria-selected", "true");
    expect(
      screen.getByRole("heading", { name: "Assign active connections" }),
    ).toBeVisible();
    expect(roles).toHaveFocus();
  });

  it("keeps an untested connection selectable while blocking final app-wide activation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          response({
            ...providers,
            routes: { tutor: "local-text", vision: "demo" },
            providers: providers.providers.map((provider) =>
              provider.id === "local-text"
                ? { ...provider, tutor_probed: false }
                : provider,
            ),
          }),
        ),
      ),
    );
    render(<AdultPanel {...props()} page="settings" />);
    const rolesTab = await screen.findByRole("tab", {
      name: /Assign active connections/,
    });
    fireEvent.click(rolesTab);
    expect(
      screen.getByRole("heading", { name: "Assign active connections" }),
    ).toBeVisible();
    expect(
      screen.getByText(/used across this app for future learner work/i),
    ).toBeVisible();
    expect(
      screen.getByText(
        /Saving a connection never activates it; this final step does/i,
      ),
    ).toBeVisible();
    const tutor = screen.getByRole("combobox", { name: "Tutor connection" });
    expect(
      within(tutor).getByRole("option", { name: "local-text (setup needed)" }),
    ).toBeEnabled();
    expect(screen.getByText("Its tutor test has not passed.")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Open Connection tests" }),
    ).toBeVisible();
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "I authorize these app-wide connections to process future learner text and photos.",
      }),
    );
    expect(
      screen.getByRole("button", { name: "Save active connections" }),
    ).toBeDisabled();
    expect(fetch).toHaveBeenCalledOnce();
  });

  it("lets an adult explicitly reapprove a changed, successfully tested connection", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          response({
            ...providers,
            routes: { tutor: "local-text", vision: "demo" },
            providers: providers.providers.map((provider) =>
              provider.id === "local-text"
                ? { ...provider, requires_approval: true }
                : provider,
            ),
          }),
        ),
      ),
    );
    render(<AdultPanel {...props()} page="settings" />);
    fireEvent.click(
      await screen.findByRole("tab", { name: /Assign active connections/ }),
    );
    const tutor = screen.getByRole("combobox", { name: "Tutor connection" });
    expect(
      within(tutor).getByRole("option", { name: "local-text (ready)" }),
    ).toBeEnabled();
    expect(
      screen.getByText(/This connection changed. Saving below approves/),
    ).toBeVisible();
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "I authorize these app-wide connections to process future learner text and photos.",
      }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Save active connections" }),
    );
    await screen.findByText(
      "Active connections saved. Future learner work will use these app-wide choices.",
    );
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/admin/providers/routes",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("loads on Settings only, filters photo capability, and requires fresh consent after a selection change", async () => {
    const handlers = props();
    const { rerender } = render(<AdultPanel {...handlers} />);
    expect(fetch).not.toHaveBeenCalled();
    rerender(<AdultPanel {...handlers} page="settings" />);
    fireEvent.click(
      await screen.findByRole("tab", { name: /Assign active connections/ }),
    );
    const tutor = screen.getByRole("combobox", { name: "Tutor connection" });
    const photoReader = screen.getByRole("combobox", {
      name: "Photo reader connection",
    });
    expect(
      within(photoReader).getByRole("option", {
        name: "local-text (no photo input)",
      }),
    ).toBeDisabled();
    expect(
      within(tutor).getByRole("option", { name: "local-text (ready)" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Pairing request ID"),
    ).not.toBeInTheDocument();
    const save = screen.getByRole("button", {
      name: "Save active connections",
    });
    expect(save).toBeDisabled();
    const consent = screen.getByRole("checkbox", {
      name: "I authorize these app-wide connections to process future learner text and photos.",
    });
    fireEvent.click(consent);
    expect(save).toBeEnabled();
    fireEvent.change(tutor, { target: { value: "local-text" } });
    expect(consent).not.toBeChecked();
    expect(save).toBeDisabled();
    fireEvent.click(consent);
    fireEvent.click(save);
    await screen.findByText(
      "Active connections saved. Future learner work will use these app-wide choices.",
    );
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/admin/providers/routes",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          tutor: "local-text",
          vision: "demo",
          acknowledge_data_boundary: true,
        }),
      }),
    );
    expect(handlers.onProvidersChanged).toHaveBeenCalledOnce();
  });

  it("does not call a live provider without approving the individual test", async () => {
    render(<AdultPanel {...props()} page="settings" />);
    fireEvent.click(
      await screen.findByRole("tab", { name: /Connection tests/ }),
    );
    const card = screen
      .getByRole("heading", { name: "local-text" })
      .closest("article")!;
    expect(
      within(card).getByRole("button", { name: "Test photo reader" }),
    ).toBeDisabled();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    fireEvent.click(within(card).getByRole("button", { name: "Test tutor" }));
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("may charge"));
    confirm.mockReturnValue(true);
    fireEvent.click(within(card).getByRole("button", { name: "Test tutor" }));
    await screen.findByText("local-text: tutor test passed.");
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/admin/providers/local-text/probe",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          stage: "tutor",
          authorize_synthetic_call: true,
        }),
      }),
    );
  });

  it("provides a retry after settings fail to load instead of reporting empty settings", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(
          response({ detail: "Provider configuration unavailable." }, 503),
        )
        .mockResolvedValueOnce(response(providers)),
    );
    render(<AdultPanel {...props()} page="settings" />);
    const retry = await screen.findByRole("button", {
      name: "Retry AI settings",
    });
    expect(failures[0]?.message).toBe("Provider configuration unavailable.");
    expect(screen.queryByText("Loading AI settings…")).not.toBeInTheDocument();
    fireEvent.click(retry);
    await screen.findByRole("heading", { name: "Connections" });
    expect(
      screen.queryByRole("button", { name: "Retry AI settings" }),
    ).not.toBeInTheDocument();
  });
});
