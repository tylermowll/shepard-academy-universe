import { StrictMode } from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Entry } from "../src/Entry";
import { setIdentity } from "../src/client";
import { capturePhotoToken } from "../src/photo-authority";
import { captureSetupAuthority } from "../src/setup-authority";

const firstToken = "a".repeat(64);
const secondToken = "b".repeat(64);
const fetcher =
  vi.fn<(path: string, options?: RequestInit) => Promise<Response>>();

function mountEntry() {
  const photoToken = capturePhotoToken();
  const setupAuthority = captureSetupAuthority();
  return render(
    <StrictMode>
      <Entry photoToken={photoToken} setupAuthority={setupAuthority} />
    </StrictMode>,
  );
}

beforeEach(() => {
  setIdentity("");
  window.history.replaceState(null, "", "/");
  vi.stubGlobal("scrollTo", vi.fn());
  fetcher.mockReset();
  fetcher.mockImplementation((path, options) => {
    if (path === "/api/v1/auth/session")
      return Promise.resolve(
        new Response(
          JSON.stringify({
            authenticated: true,
            role: "adult",
            csrf_token: "synthetic-csrf",
          }),
        ),
      );
    if (path === "/api/v1/admin/learners")
      return Promise.resolve(new Response("[]"));
    if (path === "/api/v1/phone-upload") {
      const token = new Headers(options?.headers).get("X-Photo-Token");
      return Promise.resolve(
        token
          ? new Response(
              JSON.stringify({
                received: token === firstToken,
                problem_text: token === firstToken ? "" : "Synthetic activity",
                processing: "Synthetic reader.",
                expires_at: new Date(Date.now() + 300_000).toISOString(),
              }),
            )
          : new Response(
              JSON.stringify({
                detail: "Open a new photo link from your computer.",
              }),
              { status: 401 },
            ),
      );
    }
    throw new Error(`Unexpected API request: ${path}`);
  });
  vi.stubGlobal("fetch", fetcher);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

it("captures a fresh link before StrictMode without bootstrapping login", async () => {
  window.history.replaceState(null, "", `/#capture=${secondToken}`);
  mountEntry();
  expect(window.location.hash).toBe("#capture");
  expect(await screen.findByText("Synthetic activity")).toBeVisible();
  expect(
    fetcher.mock.calls.every(([path]) => path === "/api/v1/phone-upload"),
  ).toBe(true);
  expect(localStorage.length).toBe(0);
});

it.each(["hashchange", "popstate"])(
  "opens a photo link from the signed-in app on %s and retains its secret across duplicate events",
  async (event) => {
    mountEntry();
    expect(
      await screen.findByRole("button", { name: "Sign out" }),
    ).toBeVisible();
    act(() => {
      window.history.pushState(null, "", `/#capture=${secondToken}`);
      window.dispatchEvent(new Event(event));
    });
    expect(window.location.hash).toBe("#capture");
    expect(await screen.findByText("Synthetic activity")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Sign out" }),
    ).not.toBeInTheDocument();
    act(() => {
      window.dispatchEvent(new Event("hashchange"));
    });
    expect(screen.getByLabelText("Take or choose a photo")).toBeVisible();
    expect(fetcher).toHaveBeenCalledWith("/api/v1/phone-upload", {
      headers: { "X-Photo-Token": secondToken },
      credentials: "omit",
      cache: "no-store",
    });
    expect(
      fetcher.mock.calls.some(([path]) => path.endsWith("/auth/logout")),
    ).toBe(false);
  },
);

it("clears the previous receipt when a replacement link opens in the same tab", async () => {
  window.history.replaceState(null, "", `/#capture=${firstToken}`);
  mountEntry();
  expect(await screen.findByText("Photo sent to your computer.")).toBeVisible();
  act(() => {
    window.history.pushState(null, "", `/#capture=${secondToken}`);
    window.dispatchEvent(new Event("hashchange"));
  });
  expect(await screen.findByText("Synthetic activity")).toBeVisible();
  expect(
    screen.queryByText("Photo sent to your computer."),
  ).not.toBeInTheDocument();
  expect(window.location.hash).toBe("#capture");
});

it("loses the secret on reload and asks for a new link without falling through to login", async () => {
  window.history.replaceState(null, "", `/#capture=${secondToken}`);
  const firstPage = mountEntry();
  expect(await screen.findByText("Synthetic activity")).toBeVisible();
  firstPage.unmount();
  mountEntry();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Open a new photo link",
  );
  expect(
    screen.queryByLabelText("Take or choose a photo"),
  ).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
});
