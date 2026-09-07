import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { AdultPanel } from "../src/AdultPanel";
import { App } from "../src/App";
import { OfflinePractice } from "../src/OfflinePractice";
import { checkOffline } from "../src/offline-math";
import { Practice } from "../src/Practice";
import { SafeText } from "../src/SafeText";

beforeEach(() =>
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
  ),
);
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
describe("entry and offline practice", () => {
  it("offers real sign-in and pairing with an authenticated CSRF bootstrap", async () => {
    render(<App />);
    expect(screen.getByRole("main")).toBeVisible();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Make room for a little math.",
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
  it("uses exact bounded client arithmetic and labels its result", () => {
    expect(checkOffline("10/12", 5n, 6n)).toMatch("Correct value");
    expect(checkOffline("1/0", 5n, 6n)).toMatch("cannot be zero");
    expect(checkOffline("1+1", 2n, 1n)).toMatch("Use an integer");
    expect(checkOffline("999999999/999999998", 999999999n, 999999998n)).toMatch(
      "Correct value",
    );
    render(<OfflinePractice />);
    fireEvent.click(screen.getByText("Public offline practice pack"));
    fireEvent.change(screen.getByLabelText("Offline answer"), {
      target: { value: "5/6" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Check on this device" }),
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "checked on this device",
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
      if (url.endsWith("/admin/learners")) {
        if (options.method === "POST") return Promise.resolve(response(row));
        if (firstList) {
          firstList = false;
          return oldResponse;
        }
        return Promise.resolve(response([row]));
      }
      if (url.endsWith("/admin/tutor-profiles"))
        return Promise.resolve(response([]));
      return Promise.resolve(
        response({ providers: [], routes: { tutor: "demo", vision: "demo" } }),
      );
    }),
  );
  const run = async (action: () => Promise<void>) => {
    await action();
  };
  function Workspace() {
    const [learner, setLearner] = useState("");
    return <AdultPanel learner={learner} onLearner={setLearner} act={run} />;
  }
  render(<Workspace />);
  fireEvent.click(screen.getByText("Manage learners and devices"));
  fireEvent.change(screen.getByLabelText("Alias"), {
    target: { value: "Synthetic" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create learner" }));
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
    profile: {
      name: id === first ? "Old session" : "Chosen session",
      topics: ["fractions.add"],
      session_problem_limit: 5,
    },
  });
  const fetcher = vi.fn((url: string) => {
    if (url.endsWith(`/sessions/${first}`)) return oldResponse;
    if (url.endsWith(`/sessions/${second}`))
      return Promise.resolve(response(session(second)));
    if (url.endsWith("/sessions"))
      return Promise.resolve(
        response(
          [first, second].map((id) => ({
            id,
            learner_id: learner,
            status: "completed",
            created_at: "2026-09-06T00:00:00Z",
          })),
        ),
      );
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
  render(<Practice learner={learner} offline={false} act={run} />);
  await vi.waitFor(() =>
    expect(
      screen.getByRole("combobox", { name: "Saved sessions" }).children,
    ).toHaveLength(3),
  );
  fireEvent.change(screen.getByRole("combobox", { name: "Saved sessions" }), {
    target: { value: first },
  });
  fireEvent.change(screen.getByRole("combobox", { name: "Saved sessions" }), {
    target: { value: second },
  });
  await vi.waitFor(() =>
    expect(
      screen.getByRole("combobox", { name: "Saved sessions" }),
    ).toHaveValue(second),
  );
  await act(async () => {
    resolveOld(response(session(first)));
    await oldResponse;
  });
  expect(screen.getByRole("combobox", { name: "Saved sessions" })).toHaveValue(
    second,
  );
  expect(window.location.hash).toBe(`#${second}`);
  window.location.hash = "";
});
