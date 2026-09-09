import { StrictMode } from "react";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/App";
import { setIdentity, type Schema } from "../src/client";
import { captureSetupAuthority } from "../src/setup-authority";

const guest: Schema<"SessionStatus"> = {
  authenticated: false,
  csrf_token: "synthetic-csrf",
  setup_required: true,
};
const adult: Schema<"SessionStatus"> = {
  authenticated: true,
  role: "adult",
  login_name: "Synthetic",
  csrf_token: "synthetic-adult-csrf",
  setup_required: false,
};
const available: Schema<"SetupStatus"> = {
  required: true,
  available: true,
  minimum_password_length: 6,
  maximum_password_length: 256,
  local_passwords_allowed: true,
};
const reply = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status }));
const syntheticToken = "synthetic-owner-setup-token-never-a-real-secret";

function install({
  status = available,
  initial = guest,
  failure,
  lostReceipt = false,
}: {
  status?: Schema<"SetupStatus">;
  initial?: Schema<"SessionStatus">;
  failure?: { code?: unknown; detail: string; status: number };
  lostReceipt?: boolean;
} = {}) {
  let session = initial;
  let permission = false;
  let setupFailure = failure;
  const fetcher = vi.fn((url: string, options: RequestInit) => {
    if (url.endsWith("/auth/session")) return reply(session);
    if (url.endsWith("/auth/setup") && options.method === "GET")
      return reply({ ...status, available: permission });
    if (url.endsWith("/auth/setup/session")) {
      if (options.method === "DELETE") permission = false;
      else if (status.available) permission = true;
      else return reply({ code: "setup_link_invalid" }, 403);
      return reply({ ...status, available: permission });
    }
    if (url.endsWith("/auth/setup") && options.method === "POST") {
      if (setupFailure) {
        const current = setupFailure;
        setupFailure = undefined;
        if (
          current.code === "setup_session_expired" ||
          current.code === "setup_unavailable"
        )
          permission = false;
        if (current.code === "setup_claimed")
          session = { ...guest, setup_required: false };
        return reply(
          { code: current.code, detail: current.detail },
          current.status,
        );
      }
      session = adult;
      if (lostReceipt)
        return Promise.reject(new TypeError("Synthetic lost response"));
      return reply(adult);
    }
    if (url.endsWith("/auth/login")) {
      session = adult;
      return reply(adult);
    }
    if (url.endsWith("/admin/providers"))
      return reply({
        routes: { tutor: "demo", vision: "demo" },
        providers: [],
        policy: {
          allow_cloud_inference: false,
          app_audience: "mixed",
          cloud_locked: false,
          audience_locked: false,
          demo_mode: false,
        },
      });
    return reply([]);
  });
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}
function mount(withToken = true) {
  window.history.replaceState(
    null,
    "",
    `/local?page=practice${withToken ? `#setup=${syntheticToken}` : ""}`,
  );
  const authority = captureSetupAuthority();
  const view = render(
    <StrictMode>
      <App setupAuthority={authority} />
    </StrictMode>,
  );
  return { ...view, authority };
}
async function fill(password = "simple", confirmation = password) {
  await screen.findByRole("button", { name: "Create account" });
  fireEvent.change(screen.getByLabelText("Username"), {
    target: { value: "Synthetic" },
  });
  fireEvent.change(screen.getByLabelText("Password", { exact: true }), {
    target: { value: password },
  });
  fireEvent.change(screen.getByLabelText("Confirm password"), {
    target: { value: confirmation },
  });
}
function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Create account" }));
}

beforeEach(() => {
  setIdentity("");
  vi.stubGlobal("scrollTo", vi.fn());
  window.history.replaceState(null, "", "/");
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("browser first-account setup", () => {
  it("refreshes expired anonymous CSRF before submitting the filled form", async () => {
    const fetcher = install();
    mount();
    await fill();
    const serve = fetcher.getMockImplementation();
    let renewed = false;
    let accountCreated = false;
    fetcher.mockImplementation((url, options) => {
      if (url.endsWith("/auth/session") && !accountCreated) {
        renewed = true;
        return reply({ ...guest, csrf_token: "renewed-synthetic-csrf" });
      }
      if (
        url.endsWith("/auth/setup") &&
        options.method === "POST" &&
        (!renewed ||
          (options.headers as Record<string, string>)["X-CSRF-Token"] !==
            "renewed-synthetic-csrf")
      )
        return reply({ detail: "CSRF validation failed." }, 403);
      if (url.endsWith("/auth/setup") && options.method === "POST")
        accountCreated = true;
      if (!serve) throw new Error("Missing synthetic handler");
      return serve(url, options);
    });
    setIdentity("expired-synthetic-csrf");
    submit();
    await screen.findByRole("heading", { name: "Settings", level: 1 });
    expect(renewed).toBe(true);
  });

  it("recovers a lost link exchange response using the browser permission", async () => {
    const fetcher = install();
    const serve = fetcher.getMockImplementation();
    fetcher.mockImplementation((url, options) => {
      if (!serve) throw new Error("Missing synthetic handler");
      const result = serve(url, options);
      if (url.endsWith("/auth/setup/session") && options.method === "POST")
        return result.then(() => {
          throw new Error("Synthetic lost exchange response");
        });
      return result;
    });
    const { authority } = mount();
    fireEvent.click(
      await screen.findByRole("button", { name: "Retry setup check" }),
    );
    await screen.findByRole("button", { name: "Create account" });
    expect(authority.token).toBe("");
    expect(
      fetcher.mock.calls.filter(
        ([url, options]) =>
          url.endsWith("/auth/setup/session") && options.method === "POST",
      ),
    ).toHaveLength(1);
  });

  it("captures once before StrictMode, strips history, preserves Help drafts and signs into Settings without model calls or storage", async () => {
    const fetcher = install();
    const storage = vi.spyOn(Storage.prototype, "setItem");
    const { authority } = mount();
    expect(window.location.hash).toBe("");
    expect(window.location.pathname + window.location.search).toBe(
      "/local?page=practice",
    );
    await fill();
    expect(screen.getByText(/Use 6–256 characters/)).toBeVisible();
    expect(screen.getByLabelText("Password", { exact: true })).toHaveAttribute(
      "type",
      "password",
    );
    fireEvent.click(screen.getByRole("link", { name: "Help" }));
    expect(screen.queryByRole("button", { name: "Create account" })).toBeNull();
    fireEvent.click(screen.getByRole("link", { name: "Set up account" }));
    expect(screen.getByLabelText("Username")).toHaveValue("Synthetic");
    expect(screen.getByLabelText("Password", { exact: true })).toHaveValue(
      "simple",
    );
    submit();
    await screen.findByRole("heading", { name: "Settings", level: 1 });
    expect(authority.token).toBe("");
    expect(window.location.search).toBe("?page=settings");
    const posts = fetcher.mock.calls.filter(
      ([url, options]) =>
        url.endsWith("/auth/setup") && options.method === "POST",
    );
    const exchanges = fetcher.mock.calls.filter(
      ([url, options]) =>
        url.endsWith("/auth/setup/session") && options.method === "POST",
    );
    expect(exchanges).toHaveLength(1);
    expect(JSON.parse(exchanges[0]?.[1].body as string)).toEqual({
      setup_token: syntheticToken,
    });
    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0]?.[1].body as string)).toEqual({
      login_name: "Synthetic",
      password: "simple",
      password_confirmation: "simple",
    });
    expect(posts[0]?.[1].headers).toMatchObject({
      "X-CSRF-Token": "synthetic-csrf",
    });
    expect(
      fetcher.mock.calls.some(([url]) => /probe|tutor\/|profiles/.test(url)),
    ).toBe(false);
    expect(
      fetcher.mock.calls.every(([url]) => !url.includes(syntheticToken)),
    ).toBe(true);
    expect(document.querySelector(`a[href*="${syntheticToken}"]`)).toBeNull();
    expect(storage).not.toHaveBeenCalled();
  });
  it("validates required, short, mismatched and overlong passwords inline, preserving the login and making no POST", async () => {
    const fetcher = install();
    mount();
    await screen.findByRole("button", { name: "Create account" });
    submit();
    expect(screen.getByText("Enter a login name.")).toBeVisible();
    expect(screen.getByText("Enter a password.")).toBeVisible();
    expect(screen.getByText("Enter the password again.")).toBeVisible();
    await fill("short");
    submit();
    expect(
      screen.getByText("Use 6–256 characters for your password."),
    ).toBeVisible();
    await fill("simple", "different");
    submit();
    expect(screen.getByText("The passwords do not match.")).toBeVisible();
    await fill("x".repeat(257));
    submit();
    expect(screen.getByLabelText("Password", { exact: true })).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(screen.getByLabelText("Username")).toHaveValue("Synthetic");
    expect(
      fetcher.mock.calls.some(
        ([url, options]) =>
          url.endsWith("/auth/setup") && options.method === "POST",
      ),
    ).toBe(false);
  });
  it("uses the server's network password policy before entry", async () => {
    const fetcher = install({
      status: {
        ...available,
        minimum_password_length: 12,
        local_passwords_allowed: false,
      },
    });
    mount();
    await fill();
    submit();
    expect(
      screen.getByText("Use 12–256 characters for your password."),
    ).toBeVisible();
    expect(
      screen.getByText(/HTTPS or network setup requires at least 12/),
    ).toBeVisible();
    expect(
      fetcher.mock.calls.some(
        ([url, options]) =>
          url.endsWith("/auth/setup") && options.method === "POST",
      ),
    ).toBe(false);
  });
  it("explains blank and control-character input without posting credentials", async () => {
    const fetcher = install();
    mount();
    await fill("      ");
    submit();
    expect(
      screen.getByText("Your password cannot be only spaces."),
    ).toBeVisible();
    await fill("abc\u200bdef");
    fireEvent.change(screen.getByLabelText("Username"), {
      target: { value: "Syn\u200bthetic" },
    });
    submit();
    expect(
      screen.getByText(
        "Remove invisible or control characters from the password.",
      ),
    ).toBeVisible();
    expect(
      screen.getByText(
        "Remove invisible or control characters from the login name.",
      ),
    ).toBeVisible();
    expect(
      fetcher.mock.calls.some(
        ([url, options]) =>
          url.endsWith("/auth/setup") && options.method === "POST",
      ),
    ).toBe(false);
  });
  it("counts Unicode characters like the server, not UTF-16 code units", async () => {
    const fetcher = install();
    mount();
    await fill("🌱".repeat(5));
    submit();
    expect(screen.getByLabelText("Password", { exact: true })).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(
      fetcher.mock.calls.some(
        ([url, options]) =>
          url.endsWith("/auth/setup") && options.method === "POST",
      ),
    ).toBe(false);
    await fill("🌱".repeat(6));
    submit();
    await screen.findByRole("heading", { name: "Settings", level: 1 });
  });
  it("retries an unavailable status check without exposing its error or losing the token", async () => {
    const fetcher = install();
    const serve = fetcher.getMockImplementation();
    let offline = true;
    fetcher.mockImplementation((url, options) => {
      if (url.endsWith("/auth/setup") && options.method === "GET" && offline)
        return Promise.reject(new Error(`unsafe ${syntheticToken}`));
      if (!serve) throw new Error("Missing synthetic handler");
      return serve(url, options);
    });
    const { authority } = mount();
    await screen.findByRole("button", { name: "Retry setup check" });
    expect(document.body.textContent).not.toContain(syntheticToken);
    expect(authority.token).toBe(syntheticToken);
    offline = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry setup check" }));
    await screen.findByRole("button", { name: "Create account" });
  });
  it.each([undefined, "unexpected_code", "toString", { unsafe: "code" }])(
    "never echoes an unknown error (%s), and keeps credentials for retry",
    async (code) => {
      install({
        failure: {
          code,
          detail: `malicious ${syntheticToken} simple`,
          status: 500,
        },
      });
      mount();
      await fill();
      submit();
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Could not create the account.",
      );
      expect(document.body.textContent).not.toContain(syntheticToken);
      expect(document.body.textContent).not.toContain("malicious");
      expect(screen.getByLabelText("Username")).toHaveValue("Synthetic");
      expect(screen.getByLabelText("Password", { exact: true })).toHaveValue(
        "simple",
      );
      submit();
      await screen.findByRole("heading", { name: "Settings", level: 1 });
    },
  );
  it("shows a fixed server mismatch error while retaining browser setup permission", async () => {
    install({
      failure: {
        code: "password_mismatch",
        detail: "unsafe response",
        status: 422,
      },
    });
    const { authority } = mount();
    await fill();
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Enter the same password in both fields.",
    );
    expect(authority.token).toBe("");
    expect(screen.getByLabelText("Username")).toHaveValue("Synthetic");
  });
  it.each(["setup_session_expired", "setup_unavailable"])(
    "clears the rejected authority for %s and explains how to restart without terminal credentials",
    async (code) => {
      install({ failure: { code, detail: "unsafe response", status: 403 } });
      const { authority } = mount();
      await fill();
      submit();
      await screen.findByRole("heading", {
        name: "Open the setup link from your terminal",
      });
      expect(authority.token).toBe("");
      expect(
        screen.queryByRole("button", { name: "Create account" }),
      ).toBeNull();
      expect(screen.getByText(/press Ctrl\+C/)).toHaveTextContent("make start");
    },
  );
  it("requires the private terminal link, not just a visit to the public page", async () => {
    install();
    mount(false);
    await screen.findByRole("heading", {
      name: "Open the setup link from your terminal",
    });
    expect(screen.queryByRole("button", { name: "Create account" })).toBeNull();
    expect(screen.queryByLabelText("Password", { exact: true })).toBeNull();
  });
  it("recovers browser permission after a reload without restoring the owner token or password", async () => {
    install();
    const first = mount();
    await fill();
    fireEvent.click(screen.getByRole("link", { name: "Help" }));
    await act(async () => {
      window.history.back();
      await new Promise((resolve) => window.setTimeout(resolve, 20));
    });
    expect(window.location.hash).toBe("");
    expect(screen.getByLabelText("Password", { exact: true })).toHaveValue(
      "simple",
    );
    first.unmount();
    const authority = captureSetupAuthority();
    expect(authority.token).toBe("");
    render(<App setupAuthority={authority} />);
    await screen.findByRole("button", { name: "Create account" });
    expect(screen.getByLabelText("Password", { exact: true })).toHaveValue("");
  });
  it("clears the holder and removes credential inputs on cancel", async () => {
    install();
    const { authority } = mount();
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Cancel setup" }));
    await screen.findByRole("heading", {
      name: "Open the setup link from your terminal",
    });
    expect(authority.token).toBe("");
    expect(screen.queryByLabelText("Password", { exact: true })).toBeNull();
    expect(
      screen.getByRole("heading", {
        name: "Open the setup link from your terminal",
      }),
    ).toBeVisible();
  });
  it.each([false, true])(
    "never offers setup for an existing account, authenticated=%s",
    async (authenticated) => {
      const fetcher = install({
        initial: authenticated ? adult : { ...guest, setup_required: false },
      });
      const { authority } = mount();
      await screen.findByRole(authenticated ? "link" : "button", {
        name: authenticated ? "Settings" : "Sign in",
      });
      expect(
        screen.queryByRole("button", { name: "Create account" }),
      ).toBeNull();
      await vi.waitFor(() => expect(authority.token).toBe(""));
      expect(
        fetcher.mock.calls.some(([url]) => url.endsWith("/auth/setup")),
      ).toBe(false);
      if (!authenticated) {
        fireEvent.change(screen.getByLabelText("Username"), {
          target: { value: "Synthetic" },
        });
        fireEvent.change(screen.getByLabelText("Password"), {
          target: { value: "existing-password" },
        });
        fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
        await screen.findByRole("button", { name: "Sign out" });
      }
    },
  );
  it("handles another browser claiming setup by returning to existing sign-in", async () => {
    install({
      failure: {
        code: "setup_claimed",
        detail: "unsafe response",
        status: 409,
      },
    });
    const { authority } = mount();
    await fill();
    submit();
    await screen.findByRole("button", { name: "Sign in" });
    expect(authority.token).toBe("");
    expect(screen.queryByRole("button", { name: "Create account" })).toBeNull();
  });
  it("recovers a committed account after losing its response without repeating account creation", async () => {
    const fetcher = install({ lostReceipt: true });
    const { authority } = mount();
    await fill();
    submit();
    await screen.findByRole("heading", { name: "Settings", level: 1 });
    expect(authority.token).toBe("");
    expect(
      fetcher.mock.calls.filter(
        ([url, options]) =>
          url.endsWith("/auth/setup") && options.method === "POST",
      ),
    ).toHaveLength(1);
    expect(screen.queryByRole("alert")).toBeNull();
  });
  it("captures a reopened link after cancellation and scrubs the new fragment before links render", async () => {
    install();
    const { authority } = mount();
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Cancel setup" }));
    await screen.findByRole("heading", {
      name: "Open the setup link from your terminal",
    });
    act(() => {
      window.history.pushState(null, "", `/#setup=${syntheticToken}`);
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    await screen.findByRole("button", { name: "Create account" });
    expect(window.location.hash).toBe("");
    expect(authority.token).toBe("");
    expect(screen.getByLabelText("Password", { exact: true })).toHaveValue("");
  });
  it("rechecks an expired server permission after a fresh link is opened in the same tab", async () => {
    const status = { ...available, available: false };
    const fetcher = install({ status });
    const { authority } = mount();
    await screen.findByRole("heading", {
      name: "Open the setup link from your terminal",
    });
    expect(authority.token).toBe("");
    status.available = true;
    act(() => {
      window.history.pushState(null, "", `/#setup=${syntheticToken}`);
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    await screen.findByRole("button", { name: "Create account" });
    expect(window.location.hash).toBe("");
    expect(authority.token).toBe("");
    expect(
      fetcher.mock.calls.filter(
        ([url, options]) =>
          url.endsWith("/auth/setup") && options.method === "GET",
      ).length,
    ).toBeGreaterThan(1);
  });
  it("does not offer the form when the server has no active setup permission", async () => {
    install({ status: { ...available, available: false } });
    const { authority } = mount();
    await screen.findByRole("heading", {
      name: "Open the setup link from your terminal",
    });
    expect(authority.token).toBe("");
    expect(screen.queryByRole("button", { name: "Create account" })).toBeNull();
  });
});
