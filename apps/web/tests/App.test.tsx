import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/App";
import { checkOffline } from "../src/offline-math";
import { Tutor } from "../src/Tutor";
import { SafeText } from "../src/SafeText";

beforeEach(() => {
  vi.stubGlobal("scrollTo", vi.fn());
  window.history.replaceState(null, "", "/");
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          authenticated: false,
          csrf_token: "synthetic-csrf",
        }),
        { headers: { "Content-Type": "application/json" } },
      ),
    ),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
describe("entry and offline practice", () => {
  it("offers real sign-in and pairing with an authenticated CSRF bootstrap", async () => {
    render(<App />);
    expect(screen.getByRole("main")).toBeVisible();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Sign in",
    );
    await vi.waitFor(() =>
      expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled(),
    );
    expect(screen.getByLabelText("Password")).toHaveAttribute(
      "type",
      "password",
    );
    expect(
      screen.getByRole("button", { name: "Pair this device" }),
    ).toBeEnabled();
  });
  it("retains bounded arithmetic utilities without exposing a template practice UI", () => {
    expect(checkOffline("10/12", 5n, 6n)).toMatch("Correct value");
    expect(checkOffline("1/0", 5n, 6n)).toMatch("cannot be zero");
    expect(checkOffline("1+1", 2n, 1n)).toMatch("Use an integer");
    expect(checkOffline("999999999/999999998", 999999999n, 999999998n)).toMatch(
      "Correct value",
    );
  });
  it("renders untrusted output without HTML, external images, or links", () => {
    const { container } = render(
      <SafeText
        text={
          '<img src="https://evil.invalid/x"> **Hint** [click](javascript:alert(1)) $\\frac{1}{2}$'
        }
      />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(screen.getByText("Hint").tagName).toBe("STRONG");
    expect(container.querySelector("math")).not.toBeNull();
  });
});

it("keeps a newly created learner when an older list request finishes late", async () => {
  const row = {
    id: "4a15f6fc-8866-468e-801c-1faedc9ae88b",
    alias: "Synthetic",
    eligibility: "unknown",
    enabled: true,
  };
  let resolveOld: (response: Response) => void = () => {
    throw new Error("not initialized");
  };
  const oldResponse = new Promise<Response>((resolve) => {
    resolveOld = resolve;
  });
  let firstList = true;
  const response = (value: unknown) =>
    new Response(JSON.stringify(value), {
      headers: { "Content-Type": "application/json" },
    });
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, options: RequestInit) => {
      if (url.endsWith("/auth/session"))
        return Promise.resolve(
          response({
            authenticated: true,
            role: "adult",
            csrf_token: "synthetic-csrf",
          }),
        );
      if (url.endsWith("/admin/learners")) {
        if (options.method === "POST") return Promise.resolve(response(row));
        if (firstList) {
          firstList = false;
          return oldResponse;
        }
        return Promise.resolve(response([row]));
      }
      if (url.endsWith("/features"))
        return Promise.resolve(
          response({ tutoring_available: false, photos_available: false }),
        );
      return Promise.resolve(response([]));
    }),
  );
  render(<App />);
  fireEvent.click(
    await screen.findByRole("link", { name: "Learners & devices" }),
  );
  fireEvent.change(screen.getByLabelText("Learner name"), {
    target: { value: "Synthetic" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Add learner" }));
  await vi.waitFor(() =>
    expect(screen.getByRole("combobox", { name: "Learner" })).toHaveValue(
      row.id,
    ),
  );
  await act(async () => {
    resolveOld(response([]));
    await oldResponse;
  });
  expect(screen.getByRole("combobox", { name: "Learner" })).toHaveValue(row.id);
});

it("retries a failed learner list when the adult reconnects", async () => {
  let lists = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.endsWith("/auth/session"))
        return Promise.resolve(
          new Response(
            JSON.stringify({
              authenticated: true,
              role: "adult",
              csrf_token: "synthetic-csrf",
            }),
          ),
        );
      if (url.endsWith("/admin/learners")) {
        lists += 1;
        if (lists === 1)
          return Promise.reject(new TypeError("Synthetic connection loss"));
        return Promise.resolve(
          new Response(
            JSON.stringify([
              {
                id: "4a15f6fc-8866-468e-801c-1faedc9ae88b",
                alias: "Recovered learner",
                eligibility: "unknown",
                enabled: true,
              },
            ]),
          ),
        );
      }
      return Promise.resolve(new Response("[]"));
    }),
  );
  render(<App />);
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: "Reconnect" }));
  await screen.findByRole("option", { name: "Recovered learner" });
  expect(lists).toBe(2);
  expect(screen.queryByRole("alert")).toBeNull();
});

it("keeps the selected session when a previous session response arrives late", async () => {
  const learner = "4a15f6fc-8866-468e-801c-1faedc9ae88b";
  const first = "4a15f6fc-8866-468e-801c-1faedc9ae881";
  const second = "4a15f6fc-8866-468e-801c-1faedc9ae882";
  window.location.hash = "";
  let resolveOld: (response: Response) => void = () => {
    throw new Error("not initialized");
  };
  const oldResponse = new Promise<Response>((resolve) => {
    resolveOld = resolve;
  });
  const response = (value: unknown) => new Response(JSON.stringify(value));
  const session = (id: string) => ({
    id,
    learner_id: learner,
    status: "completed",
    problems: [],
    topic: id === first ? "Old session" : "Chosen session",
    initiative: "balanced",
    difficulty: "standard",
  });
  const fetcher = vi.fn((url: string) => {
    if (url.endsWith(`/sessions/${first}`)) return oldResponse;
    if (url.endsWith(`/sessions/${second}`))
      return Promise.resolve(response(session(second)));
    if (url.endsWith("/sessions"))
      return Promise.resolve(response([first, second].map(session)));
    if (url.endsWith("/progress"))
      return Promise.resolve(
        response({
          checked_answers: 0,
          correct_without_help: 0,
          correct_with_help: 0,
          incorrect: 0,
        }),
      );
    if (url.endsWith("/features"))
      return Promise.resolve(
        response({ photos_available: false, external_problems: false }),
      );
    return Promise.resolve(response([]));
  });
  vi.stubGlobal("fetch", fetcher);
  const run = async (action: () => Promise<void>) => {
    await action();
  };
  render(<Tutor learner={learner} offline={false} act={run} page="history" />);
  await vi.waitFor(() =>
    expect(
      screen.getAllByRole("button", { name: "Review session" }),
    ).toHaveLength(2),
  );
  fireEvent.click(
    screen.getAllByRole("button", { name: "Review session" })[0]!,
  );
  fireEvent.click(
    screen.getAllByRole("button", { name: "Review session" })[1]!,
  );
  await vi.waitFor(() => expect(window.location.hash).toBe(`#tutor=${second}`));
  await act(async () => {
    resolveOld(response(session(first)));
    await oldResponse;
  });
  expect(
    screen.getAllByRole("heading", { name: "Chosen session", hidden: true }),
  ).toHaveLength(2);
  expect(window.location.hash).toBe(`#tutor=${second}`);
  window.location.hash = "";
});

it("rejects a URL session belonging to a different selected learner", async () => {
  const wrongSession = "4a15f6fc-8866-468e-801c-1faedc9ae883";
  const learner = "4a15f6fc-8866-468e-801c-1faedc9ae884";
  window.location.hash = `tutor=${wrongSession}`;
  const response = (body: unknown) =>
    Promise.resolve(new Response(JSON.stringify(body)));
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.endsWith(`/sessions/${wrongSession}`))
        return response({
          id: wrongSession,
          learner_id: "4a15f6fc-8866-468e-801c-1faedc9ae885",
          status: "completed",
          problems: [],
          topic: "Previous learner private profile",
          initiative: "balanced",
          difficulty: "standard",
        });
      if (url.endsWith("/progress"))
        return response({
          correct_without_help: 0,
          correct_with_help: 0,
          incorrect: 0,
        });
      if (url.endsWith("/features"))
        return response({ photos_available: false });
      return response([]);
    }),
  );
  const run = async (action: () => Promise<void>) => {
    await action();
  };
  render(<Tutor learner={learner} offline={false} act={run} />);
  await vi.waitFor(() => expect(window.location.hash).toBe(""));
  expect(screen.queryByText(/Previous learner private profile/)).toBeNull();
  expect(
    screen.queryByRole("heading", { name: "Current activity" }),
  ).toBeNull();
  expect(
    screen.getByRole("heading", { name: "Start a practice session" }),
  ).toBeVisible();
});

it("does not restore an old learner's URL when its request completes after switching", async () => {
  const oldLearner = "4a15f6fc-8866-468e-801c-1faedc9ae885";
  const newLearner = "4a15f6fc-8866-468e-801c-1faedc9ae886";
  const oldSession = "4a15f6fc-8866-468e-801c-1faedc9ae887";
  window.location.hash = `tutor=${oldSession}`;
  let resolveOld!: (response: Response) => void;
  const oldResponse = new Promise<Response>((resolve) => {
    resolveOld = resolve;
  });
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.endsWith(`/sessions/${oldSession}`)) return oldResponse;
      if (url.endsWith("/progress"))
        return Promise.resolve(
          new Response(
            JSON.stringify({
              correct_without_help: 0,
              correct_with_help: 0,
              incorrect: 0,
            }),
          ),
        );
      if (url.endsWith("/features"))
        return Promise.resolve(
          new Response('{"photos_available":false,"tutoring_available":true}'),
        );
      return Promise.resolve(new Response("[]"));
    }),
  );
  const run = async (action: () => Promise<void>) => {
    await action();
  };
  const view = render(
    <Tutor key={oldLearner} learner={oldLearner} offline={false} act={run} />,
  );
  window.location.hash = "";
  view.rerender(
    <Tutor key={newLearner} learner={newLearner} offline={false} act={run} />,
  );
  await act(async () => {
    resolveOld(
      new Response(
        JSON.stringify({
          id: oldSession,
          learner_id: oldLearner,
          status: "completed",
          problems: [],
          topic: "Old private session",
          initiative: "balanced",
          difficulty: "standard",
        }),
      ),
    );
    await oldResponse;
  });
  expect(window.location.hash).toBe("");
  expect(screen.queryByText(/Old private session/)).toBeNull();
});

it("allows a corrected request after its first attempt is definitively rejected", async () => {
  window.location.hash = "";
  const learner = "4a15f6fc-8866-468e-801c-1faedc9ae884";
  const session = {
    id: "4a15f6fc-8866-468e-801c-1faedc9ae883",
    learner_id: learner,
    status: "open",
    problems: [],
    topic: "Persuasive writing",
    initiative: "balanced",
    difficulty: "standard",
  };
  const keys: unknown[] = [];
  const errors: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, options: RequestInit) => {
      if (url.endsWith("/sessions") && options.method === "POST") {
        keys.push(
          (options.headers as Record<string, string>)["Idempotency-Key"],
        );
        return Promise.resolve(
          keys.length === 1
            ? new Response('{"detail":"Synthetic first-attempt rejection."}', {
                status: 422,
              })
            : new Response(JSON.stringify(session), { status: 201 }),
        );
      }
      if (url.endsWith(`/sessions/${session.id}`))
        return Promise.resolve(new Response(JSON.stringify(session)));
      if (url.endsWith("/progress"))
        return Promise.resolve(
          new Response(
            JSON.stringify({
              correct_without_help: 0,
              correct_with_help: 0,
              incorrect: 0,
            }),
          ),
        );
      if (url.endsWith("/features"))
        return Promise.resolve(
          new Response('{"photos_available":false,"tutoring_available":true}'),
        );
      return Promise.resolve(new Response("[]"));
    }),
  );
  const run = async (action: () => Promise<void>) => {
    try {
      await action();
    } catch (cause) {
      errors.push(cause);
    }
  };
  render(<Tutor learner={learner} offline={false} act={run} />);
  fireEvent.change(screen.getByLabelText("Topic or learning goal"), {
    target: { value: "Persuasive writing" },
  });
  await vi.waitFor(() =>
    expect(screen.getByRole("button", { name: "Start session" })).toBeEnabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "Start session" }));
  await vi.waitFor(() => expect(errors).toHaveLength(1));
  expect(
    screen.queryByRole("button", { name: "Retry saved request" }),
  ).toBeNull();
  fireEvent.click(screen.getByText("Tutor options"));
  expect(screen.getByRole("combobox", { name: "Tutor style" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Start session" }));
  await vi.waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Create practice activity" }),
    ).toBeEnabled(),
  );
  expect(keys).toHaveLength(2);
  expect(keys[1]).not.toBe(keys[0]);
  window.location.hash = "";
});
