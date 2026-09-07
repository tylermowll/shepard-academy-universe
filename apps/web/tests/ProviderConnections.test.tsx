import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProviderConnections } from "../src/ProviderConnections";
import { setIdentity, type Schema } from "../src/client";

const saved: Schema<"ProviderPublic"> = {
  id: "home-vision",
  adapter: "compatible",
  model: "installed-vision-model",
  base_url: "http://127.0.0.1:8081/v1",
  boundary: "local_network",
  audience: "mixed",
  enabled: true,
  image_input: true,
  tutor_probed: true,
  vision_probed: true,
  managed: true,
  key_configured: true,
  key_needs_replacement: false,
  requires_approval: false,
  eligibility_record: "Operator reviewed model terms.",
  configured_context_limit: 32768,
  structured_output_mode: "native",
};
const configuration: Schema<"ProvidersPublic"> = {
  routes: { tutor: "demo", vision: "demo" },
  providers: [saved],
  policy: {
    allow_cloud_inference: false,
    app_audience: "mixed",
    cloud_locked: false,
    audience_locked: false,
    demo_mode: false,
  },
};
const response = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status }));
const run = async (action: () => Promise<void>) => action();
const terms = () =>
  screen.getByRole("checkbox", {
    name: "I reviewed the model and provider terms for the users selected above.",
  });
const openDetails = () => {
  fireEvent.click(screen.getByText("Connection tests & provider details"));
  fireEvent.click(screen.getByText("Connection details"));
};

beforeEach(() => {
  setIdentity("synthetic-csrf", true);
  vi.stubGlobal(
    "fetch",
    vi.fn(() => response({ acknowledged: true })),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function show(value = configuration) {
  const onChanged = vi.fn(async () => {});
  const onNavigate = vi.fn();
  const view = render(
    <ProviderConnections
      configuration={value}
      act={run}
      onChanged={onChanged}
      onNavigate={onNavigate}
    />,
  );
  return { ...view, onChanged, onNavigate };
}

function fillNew() {
  fireEvent.click(screen.getByRole("button", { name: "Add AI connection" }));
  fireEvent.change(screen.getByLabelText("Connection name"), {
    target: { value: "local-tutor" },
  });
  fireEvent.change(screen.getByLabelText("Model name"), {
    target: { value: "installed-text-model" },
  });
}

describe("adult connection setup", () => {
  it("shows the API key field immediately for hosted APIs while local servers default to no key", () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: "Add AI connection" }));
    expect(screen.getByLabelText("API key action")).toHaveValue("keep");
    expect(screen.queryByLabelText("API key")).toBeNull();
    fireEvent.change(screen.getByLabelText("Connection type"), {
      target: { value: "compatible" },
    });
    expect(screen.getByLabelText("Where this model runs")).toHaveValue("cloud");
    expect(screen.getByLabelText("API key action")).toHaveValue("replace");
    expect(screen.getByLabelText("API key")).toHaveAttribute(
      "type",
      "password",
    );
    fireEvent.change(screen.getByLabelText("Connection type"), {
      target: { value: "vllm" },
    });
    expect(screen.getByLabelText("API key action")).toHaveValue("keep");
    expect(screen.queryByLabelText("API key")).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each([
    ["authentication", "Edit this connection and replace the key"],
    [
      "unavailable",
      "Check Server address, make sure the model server is running",
    ],
    ["malformed_output", "Structured output under Advanced connection options"],
    ["probe_reading_failed", "selected model and server support images"],
    ["unknown-provider-error", "No successful test was confirmed"],
    ["toString", "No successful test was confirmed"],
  ])(
    "shows fixed actionable test guidance for %s without echoing provider error text",
    async (code, expected) => {
      vi.stubGlobal(
        "fetch",
        vi.fn(() =>
          response(
            { detail: "Provider echoed synthetic-secret-do-not-display", code },
            422,
          ),
        ),
      );
      const { onChanged } = show();
      fireEvent.click(screen.getByText("Connection tests & provider details"));
      vi.spyOn(window, "confirm").mockReturnValue(true);
      fireEvent.click(
        screen.getByRole("button", {
          name:
            code === "probe_reading_failed"
              ? "Test photo reader"
              : "Test tutor",
        }),
      );
      const error = await screen.findByRole("alert");
      expect(error).toHaveTextContent(expected);
      expect(error).not.toHaveTextContent("synthetic-secret-do-not-display");
      expect(onChanged).not.toHaveBeenCalled();
      expect(screen.queryByText(/test passed/)).toBeNull();
    },
  );

  it("saves an exact local model without calling it or changing practice routes", async () => {
    const { onChanged } = show();
    fillNew();
    const save = screen.getByRole("button", { name: "Save connection" });
    expect(save).toBeDisabled();
    fireEvent.click(terms());
    fireEvent.click(save);
    expect(
      await screen.findByText(/local-tutor saved. No model request was sent/),
    ).toBeVisible();
    expect(fetch).toHaveBeenCalledOnce();
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/admin/providers/connections",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          adapter: "ollama",
          model: "installed-text-model",
          base_url: "http://127.0.0.1:11434",
          enabled: true,
          boundary: "local_network",
          audience: "mixed",
          eligibility_record:
            "Operator confirmed the model and provider terms permit mixed-age use.",
          image_input: false,
          configured_context_limit: 32768,
          structured_output_mode: "native",
          api_key_action: "keep",
          id: "local-tutor",
        }),
      }),
    );
    expect(onChanged).toHaveBeenCalledOnce();
    expect(screen.queryByLabelText("Model name")).toBeNull();
  });

  it("requires model, connection name, valid address and explicit reviewed terms", () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: "Add AI connection" }));
    fireEvent.click(terms());
    expect(
      screen.getByRole("button", { name: "Save connection" }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Connection name"), {
      target: { value: "bad name" },
    });
    fireEvent.change(screen.getByLabelText("Model name"), {
      target: { value: "installed-model" },
    });
    fireEvent.change(screen.getByLabelText("Server address"), {
      target: { value: "not an address" },
    });
    expect(
      screen.getByLabelText("Connection name").closest("form")!.checkValidity(),
    ).toBe(false);
    expect(terms()).not.toBeChecked();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("sends a new key only in the save request and clears it after save or cancel", async () => {
    const localStore = vi.spyOn(Storage.prototype, "setItem");
    show();
    fillNew();
    fireEvent.change(screen.getByLabelText("API key action"), {
      target: { value: "replace" },
    });
    const input = screen.getByLabelText("API key");
    expect(input).toHaveAttribute("type", "password");
    fireEvent.change(input, { target: { value: "synthetic-key-not-valid" } });
    fireEvent.click(terms());
    fireEvent.click(screen.getByRole("button", { name: "Save connection" }));
    await screen.findByText(/local-tutor saved/);
    const request = vi.mocked(fetch).mock.calls[0]![1]!;
    expect(JSON.parse(request.body as string)).toMatchObject({
      api_key_action: "replace",
      api_key: "synthetic-key-not-valid",
    });
    expect(screen.queryByLabelText("API key")).toBeNull();
    expect(localStore).not.toHaveBeenCalled();
    fillNew();
    fireEvent.change(screen.getByLabelText("API key action"), {
      target: { value: "replace" },
    });
    expect(screen.getByLabelText("API key")).toHaveValue("");
    fireEvent.change(screen.getByLabelText("API key"), {
      target: { value: "another-synthetic-key" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Cancel connection" }));
    fillNew();
    fireEvent.change(screen.getByLabelText("API key action"), {
      target: { value: "replace" },
    });
    expect(screen.getByLabelText("API key")).toHaveValue("");
    expect(fetch).toHaveBeenCalledOnce();
  });

  it.each([422, 403, 500])(
    "keeps failed-save entries without echoing credential-bearing errors (%s)",
    async (status) => {
      vi.stubGlobal(
        "fetch",
        vi.fn(() =>
          response({ detail: "Rejected synthetic-key-not-valid" }, status),
        ),
      );
      show();
      fillNew();
      fireEvent.change(screen.getByLabelText("API key action"), {
        target: { value: "replace" },
      });
      fireEvent.change(screen.getByLabelText("API key"), {
        target: { value: "synthetic-key-not-valid" },
      });
      fireEvent.click(terms());
      fireEvent.click(screen.getByRole("button", { name: "Save connection" }));
      const error = await screen.findByRole("alert");
      expect(error).not.toHaveTextContent("synthetic-key-not-valid");
      expect(screen.getByLabelText("API key")).toHaveValue(
        "synthetic-key-not-valid",
      );
      expect(screen.getByLabelText("Model name")).toHaveValue(
        "installed-text-model",
      );
      expect(
        screen.getByRole("button", { name: "Save connection" }),
      ).toBeEnabled();
    },
  );

  it("edits a stored connection without fetching or resubmitting its key", async () => {
    show();
    openDetails();
    fireEvent.click(screen.getByRole("button", { name: "Edit connection" }));
    expect(screen.getByLabelText("Connection name")).toHaveAttribute(
      "readonly",
    );
    expect(screen.getByLabelText("API key action")).toHaveValue("keep");
    expect(screen.queryByLabelText("API key")).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Model name"), {
      target: { value: "another-installed-model" },
    });
    fireEvent.click(terms());
    fireEvent.click(screen.getByRole("button", { name: "Save connection" }));
    await screen.findByText(/home-vision saved/);
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/admin/providers/connections/home-vision",
      expect.objectContaining({ method: "PUT" }),
    );
    const body: unknown = JSON.parse(
      vi.mocked(fetch).mock.calls[0]![1]!.body as string,
    );
    expect(body).toMatchObject({
      model: "another-installed-model",
      api_key_action: "keep",
    });
    expect(body).not.toHaveProperty("api_key");
    expect(body).not.toHaveProperty("id");
  });

  it("requires replacing or removing the key when changing its destination", async () => {
    show();
    openDetails();
    fireEvent.click(screen.getByRole("button", { name: "Edit connection" }));
    fireEvent.change(screen.getByLabelText("Server address"), {
      target: { value: "http://127.0.0.1:8082/v1" },
    });
    fireEvent.click(terms());
    expect(
      screen.getByRole("button", { name: "Save connection" }),
    ).toBeDisabled();
    expect(
      screen.getByText(/Replace or remove the saved key before saving/),
    ).toBeVisible();
    fireEvent.change(screen.getByLabelText("API key action"), {
      target: { value: "remove" },
    });
    fireEvent.click(terms());
    fireEvent.click(screen.getByRole("button", { name: "Save connection" }));
    await screen.findByText(/home-vision saved/);
    const body: unknown = JSON.parse(
      vi.mocked(fetch).mock.calls[0]![1]!.body as string,
    );
    expect(body).toMatchObject({
      api_key_action: "remove",
      base_url: "http://127.0.0.1:8082/v1",
    });
    expect(body).not.toHaveProperty("api_key");
  });

  it("clears typed keys when changing API key action or connection type", () => {
    show();
    fillNew();
    fireEvent.change(screen.getByLabelText("API key action"), {
      target: { value: "replace" },
    });
    fireEvent.change(screen.getByLabelText("API key"), {
      target: { value: "synthetic-before-change" },
    });
    fireEvent.change(screen.getByLabelText("API key action"), {
      target: { value: "keep" },
    });
    fireEvent.change(screen.getByLabelText("API key action"), {
      target: { value: "replace" },
    });
    expect(screen.getByLabelText("API key")).toHaveValue("");
    fireEvent.change(screen.getByLabelText("API key"), {
      target: { value: "synthetic-before-provider-change" },
    });
    fireEvent.change(screen.getByLabelText("Connection type"), {
      target: { value: "meta" },
    });
    expect(screen.getByLabelText("API key")).toHaveValue("");
    expect(screen.getByLabelText("Where this model runs")).toHaveValue("cloud");
    expect(screen.getByLabelText("Allowed users")).toHaveValue("adult_only");
    expect(screen.getByLabelText("Allowed users")).toBeDisabled();
  });

  it("disables a managed connection and requires confirmation for deletion", async () => {
    const { onChanged } = show();
    openDetails();
    fireEvent.click(screen.getByRole("button", { name: "Disable connection" }));
    await screen.findByText(/home-vision disabled/);
    expect(
      JSON.parse(vi.mocked(fetch).mock.calls[0]![1]!.body as string),
    ).toMatchObject({ enabled: false, api_key_action: "keep" });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    fireEvent.click(screen.getByRole("button", { name: "Delete connection" }));
    expect(fetch).toHaveBeenCalledOnce();
    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Delete connection" }));
    await screen.findByText("home-vision deleted.");
    expect(fetch).toHaveBeenLastCalledWith(
      "/api/v1/admin/providers/connections/home-vision",
      expect.objectContaining({ method: "DELETE" }),
    );
    expect(onChanged).toHaveBeenCalledTimes(2);
  });

  it("shows file-managed connections as read-only and prevents deleting a selected connection", () => {
    const view = show({
      ...configuration,
      providers: [{ ...saved, managed: false }],
    });
    openDetails();
    expect(screen.getByText(/read-only here/)).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Edit connection" }),
    ).toBeNull();
    view.rerender(
      <ProviderConnections
        configuration={{
          ...configuration,
          routes: { tutor: saved.id, vision: saved.id },
        }}
        act={run}
        onChanged={view.onChanged}
        onNavigate={view.onNavigate}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Delete connection" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Disable connection" }),
    ).toBeDisabled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("prevents demo connection/key writes and live probes", () => {
    const { onNavigate } = show({
      ...configuration,
      policy: { ...configuration.policy, demo_mode: true },
    });
    expect(
      screen.getByRole("button", { name: "Add AI connection" }),
    ).toBeDisabled();
    expect(screen.queryByLabelText("API key")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Private setup help" }));
    expect(onNavigate).toHaveBeenCalledWith("help", "setup");
    openDetails();
    expect(
      screen.getByRole("button", { name: "Edit connection" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "Test tutor" })).toBeDisabled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("requires explicit cloud/audience consent and displays server locks", async () => {
    const view = show({
      ...configuration,
      providers: [{ ...saved, boundary: "cloud", audience: "adult_only" }],
    });
    fireEvent.click(screen.getByText("Connection tests & provider details"));
    expect(screen.getByRole("button", { name: "Test tutor" })).toBeDisabled();
    fireEvent.click(screen.getByText("App privacy & audience"));
    fireEvent.change(screen.getByLabelText("Who uses this app?"), {
      target: { value: "adult_only" },
    });
    fireEvent.click(screen.getByLabelText("Allow cloud AI for this app"));
    expect(
      screen.getByRole("button", { name: "Save app policy" }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByLabelText(
        "I confirm this audience and authorize the selected data boundary.",
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "Save app policy" }));
    await screen.findByText(/App policy saved/);
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/admin/providers/policy",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          allow_cloud_inference: true,
          app_audience: "adult_only",
          acknowledge_data_boundary: true,
        }),
      }),
    );
    view.rerender(
      <ProviderConnections
        configuration={{
          ...configuration,
          policy: {
            ...configuration.policy,
            cloud_locked: true,
            audience_locked: true,
          },
        }}
        act={run}
        onChanged={view.onChanged}
        onNavigate={view.onNavigate}
      />,
    );
    expect(screen.getByLabelText("Allow cloud AI for this app")).toBeDisabled();
    expect(screen.getByLabelText("Who uses this app?")).toBeDisabled();
    expect(screen.getByText(/locked cloud access/)).toBeVisible();
  });

  it("offers an explicit enable action for disabled connections", async () => {
    show({ ...configuration, providers: [{ ...saved, enabled: false }] });
    openDetails();
    expect(screen.getByRole("button", { name: "Test tutor" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Enable connection" }));
    await screen.findByText(/home-vision enabled/);
    expect(
      JSON.parse(vi.mocked(fetch).mock.calls[0]![1]!.body as string),
    ).toMatchObject({ enabled: true, api_key_action: "keep" });
  });
});
