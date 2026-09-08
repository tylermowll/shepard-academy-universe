import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  api,
  imageRequest,
  onAuthenticationLost,
  setIdentity,
} from "../src/client";

beforeEach(() => setIdentity(""));
afterEach(() => vi.unstubAllGlobals());

it("keeps photo-link authorization failures independent of the signed-in session", async () => {
  const lost = vi.fn();
  const unsubscribe = onAuthenticationLost(lost);
  setIdentity("synthetic-authenticated-csrf", true);
  const fetcher = vi
    .fn()
    .mockImplementation(() =>
      Promise.resolve(
        new Response('{"detail":"Open a new photo link."}', { status: 401 }),
      ),
    );
  vi.stubGlobal("fetch", fetcher);
  try {
    await expect(
      imageRequest(
        "/phone-upload/preview",
        new Blob(["synthetic"]),
        undefined,
        "a".repeat(64),
      ),
    ).rejects.toThrow("Open a new photo link.");
    expect(lost).not.toHaveBeenCalled();
    expect(fetcher).toHaveBeenLastCalledWith(
      "/api/v1/phone-upload/preview",
      expect.objectContaining({
        credentials: "omit",
        headers: {
          "X-Photo-Token": "a".repeat(64),
          "Content-Type": "application/octet-stream",
        },
      }),
    );
    fetcher.mockResolvedValue(new Response("{}"));
    await api("/auth/session");
    expect(fetcher).toHaveBeenLastCalledWith(
      "/api/v1/auth/session",
      expect.objectContaining({
        credentials: "same-origin",
        headers: { "X-CSRF-Token": "synthetic-authenticated-csrf" },
      }),
    );
  } finally {
    unsubscribe();
  }
});

it.each(["json", "photo"])(
  "invalidates authenticated state when a %s request reports revocation",
  async (kind) => {
    const lost = vi.fn();
    const unsubscribe = onAuthenticationLost(lost);
    setIdentity("synthetic-authenticated-csrf", true);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status: 401 })),
    );
    try {
      const request =
        kind === "json"
          ? api("/sessions")
          : imageRequest("/images/preview", new Blob(["synthetic"]));
      await expect(request).rejects.toThrow("Your session ended");
      expect(lost).toHaveBeenCalledOnce();
      await expect(api("/auth/session")).rejects.toThrow();
      expect(lost).toHaveBeenCalledOnce();
    } finally {
      unsubscribe();
    }
  },
);

it("does not treat anonymous bootstrap or failed login as revocation", async () => {
  const lost = vi.fn();
  const unsubscribe = onAuthenticationLost(lost);
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockImplementation(() =>
        Promise.resolve(
          new Response('{"detail":"Invalid credentials"}', { status: 401 }),
        ),
      ),
  );
  try {
    setIdentity("synthetic-anonymous-csrf");
    await expect(api("/auth/session")).rejects.toThrow("Invalid credentials");
    await expect(api("/auth/login", "POST", {})).rejects.toThrow(
      "Invalid credentials",
    );
    setIdentity("synthetic-authenticated-csrf", true);
    await expect(api("/auth/login", "POST", {})).rejects.toThrow(
      "Invalid credentials",
    );
    expect(lost).not.toHaveBeenCalled();
  } finally {
    unsubscribe();
  }
});

it("discards a late revocation response from a previous identity", async () => {
  const lost = vi.fn();
  const unsubscribe = onAuthenticationLost(lost);
  let respond!: (response: Response) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn().mockReturnValue(
      new Promise<Response>((resolve) => {
        respond = resolve;
      }),
    ),
  );
  try {
    setIdentity("synthetic-old-csrf", true);
    const request = api("/sessions");
    setIdentity("synthetic-new-csrf", true);
    respond(new Response("{}", { status: 401 }));
    await expect(request).rejects.toThrow("Session changed");
    expect(lost).not.toHaveBeenCalled();
  } finally {
    unsubscribe();
  }
});

it("discards private response data if identity changes while its body is read", async () => {
  let respond!: (body: unknown) => void;
  const reading = new Promise<unknown>((resolve) => {
    respond = resolve;
  });
  const bodyStarted = vi.fn(() => reading);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, status: 200, json: bodyStarted }),
  );
  setIdentity("synthetic-old-csrf", true);
  const request = api("/sessions");
  await vi.waitFor(() => expect(bodyStarted).toHaveBeenCalled());
  setIdentity("synthetic-new-csrf", true);
  respond([{ id: "previous-learner-session" }]);
  await expect(request).rejects.toThrow("Session changed");
});

it.each(["json", "photo"])(
  "preserves structured error codes from a failed %s request",
  async (kind) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              detail: "Safe authentication error.",
              code: "authentication",
            }),
            { status: 422 },
          ),
        ),
      ),
    );
    const request =
      kind === "json"
        ? api("/admin/providers/local/probe", "POST", {})
        : imageRequest("/images/preview", new Blob(["synthetic"]));
    await expect(request).rejects.toMatchObject({
      status: 422,
      code: "authentication",
      message: "Safe authentication error.",
    });
  },
);

it.each([null, 12, ["unavailable"], { name: "authentication" }])(
  "ignores a non-string API error code (%j)",
  async (code) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({ detail: "Safe request error.", code }),
            { status: 422 },
          ),
        ),
      ),
    );
    await expect(
      api("/admin/providers/local/probe", "POST", {}),
    ).rejects.toMatchObject({ status: 422, code: undefined });
  },
);
