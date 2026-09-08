import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Tutor } from "../src/Tutor";
import { App } from "../src/App";

const learner = "911c9abc-4e8e-424d-a914-4338187ba00a";
const sessionId = "911c9abc-4e8e-424d-a914-4338187ba00b";
const problemId = "911c9abc-4e8e-424d-a914-4338187ba00c";
const capabilities = {
  photos_available: true,
  photo_status: "Photos are read by the local vision provider.",
  tutoring_available: true,
  tutor_status: "Synthetic test provider, not a live quality claim.",
  text_processing: "local",
  external_problems: false,
};
const activity = (operations: unknown[] = [], state = "ready") => ({
  id: problemId,
  status: "assigned",
  version: 1,
  skill_id: "tutor.generated",
  problem_text:
    "Write an argument for protecting a neighborhood wetland. Support your claim with evidence.",
  concept_focus: "Evidence and persuasion",
  activity_state: state,
  reference_source: "topic",
  assistance_level: 0,
  operations,
});
const session = (problems: unknown[] = []) => ({
  id: sessionId,
  learner_id: learner,
  topic: "Persuasive writing",
  initiative: "balanced",
  difficulty: "standard",
  status: "open",
  problems,
});
const guidance = {
  strengths: ["You stated a clear position."],
  guidance: [
    "What evidence would help your reader understand why the wetland matters?",
  ],
  next_step: "Add one observation and explain how it supports your claim.",
  concepts: ["Supporting evidence"],
  uncertainty_note: null,
};
const operation = (overrides: Record<string, unknown> = {}) => ({
  id: "911c9abc-4e8e-424d-a914-4338187ba00d",
  problem_id: problemId,
  kind: "answer",
  text: "",
  work_text: "",
  status: "completed",
  source: "synthetic",
  created_at: "2026-09-07T10:00:00Z",
  interpretation: "Protect the wetland because it gives birds a home.",
  interpretation_version: 1,
  ambiguities: [],
  reading: {
    quality: "clear",
    confidence: 0.97,
    can_continue: true,
    organization_feedback: [
      "Your line spacing makes the argument easy to read.",
    ],
    rejection_reason: null,
  },
  feedback: guidance,
  ...overrides,
});
const response = (value: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(value), { status }));
const run = async (action: () => Promise<void>) => action();

function installSession(value: ReturnType<typeof session>) {
  window.location.hash = `tutor=${sessionId}`;
  const fetcher = vi.fn((url: string, options: RequestInit) => {
    if (url.endsWith("/features")) return response(capabilities);
    if (url.endsWith(`/tutor/sessions/${sessionId}`)) return response(value);
    if (url.endsWith("/tutor/sessions")) return response([value]);
    if (options.method === "POST") return response({});
    throw new Error(`Unexpected request: ${url}`);
  });
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

beforeEach(() => {
  window.history.replaceState(null, "", "/");
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("AI learning conversation", () => {
  it("requests easier practice directly and keeps response controls before next steps", async () => {
    const fetcher = installSession(session([activity()]));
    render(<Tutor learner={learner} offline={false} act={run} />);
    const easier = await screen.findByRole("button", {
      name: "Easier next activity",
    });
    const reply = screen.getByLabelText("Your work or question");
    const photo = screen.getByText("Upload a photo");
    const help = screen.getByText("Get help with this activity");
    expect(
      reply.compareDocumentPosition(photo) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      photo.compareDocumentPosition(help) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    fireEvent.click(easier);
    await vi.waitFor(() => {
      const sent = fetcher.mock.calls.find(([url]) =>
        url.endsWith("/activities"),
      );
      expect(sent).toBeDefined();
      expect(JSON.parse(sent![1].body as string)).toEqual({
        source: "topic",
        difficulty: "introductory",
      });
    });
  });

  it("starts a non-math topic with no level, templates, or solution controls", async () => {
    const fetcher = vi.fn((url: string, options: RequestInit) => {
      if (url.endsWith("/features")) return response(capabilities);
      if (url.endsWith(`/tutor/sessions/${sessionId}`))
        return response(session());
      if (url.endsWith("/tutor/sessions"))
        return response(options.method === "POST" ? session() : []);
      throw new Error(url);
    });
    vi.stubGlobal("fetch", fetcher);
    render(<Tutor learner={learner} offline={false} act={run} />);
    fireEvent.change(screen.getByLabelText("Topic or learning goal"), {
      target: { value: "Persuasive writing" },
    });
    fireEvent.click(screen.getByText("Tutor options"));
    fireEvent.change(screen.getByLabelText("Tutor style"), {
      target: { value: "learner_led" },
    });
    fireEvent.change(screen.getByLabelText("Activity difficulty"), {
      target: { value: "challenge" },
    });
    await vi.waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Start session" }),
      ).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Start session" }));
    expect(
      await screen.findByRole("button", { name: "Create practice activity" }),
    ).toBeEnabled();
    const sent = fetcher.mock.calls.find(
      ([url, options]) =>
        url.endsWith("/tutor/sessions") && options.method === "POST",
    );
    expect(JSON.parse(sent![1].body as string)).toEqual({
      learner_id: learner,
      topic: "Persuasive writing",
      initiative: "learner_led",
      difficulty: "challenge",
    });
    expect(screen.queryByLabelText(/level|skill|grade/i)).toBeNull();
    expect(screen.queryByText("Full solution")).toBeNull();
  });

  it("uses pasted assignments only as reference for distinct practice", async () => {
    const fetcher = installSession(session());
    render(<Tutor learner={learner} offline={false} act={run} />);
    fireEvent.change(await screen.findByLabelText("Practice source"), {
      target: { value: "reference_text" },
    });
    expect(screen.getByText(/The tutor uses your material/)).toHaveTextContent(
      "create different practice",
    );
    expect(screen.getByText(/The tutor uses your material/)).toHaveTextContent(
      "cannot access a book from its title",
    );
    fireEvent.change(screen.getByLabelText("Reference material"), {
      target: {
        value: "Homework: argue whether a historical decision was justified.",
      },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Create practice activity" }),
    );
    await vi.waitFor(() =>
      expect(
        fetcher.mock.calls.some(([url]) => url.endsWith("/activities")),
      ).toBe(true),
    );
    const sent = fetcher.mock.calls.find(([url]) =>
      url.endsWith("/activities"),
    )!;
    expect(JSON.parse(sent[1].body as string)).toEqual({
      source: "reference_text",
      reference_text:
        "Homework: argue whether a historical decision was justified.",
    });
  });

  it("offers the phone capture route for a source photo without solving it", async () => {
    installSession(session([activity([], "reference_capture")]));
    render(<Tutor learner={learner} offline={false} act={run} />);
    expect(
      await screen.findByRole("button", { name: "Take photo with phone" }),
    ).toBeEnabled();
    fireEvent.click(screen.getByText("Upload a photo"));
    expect(
      screen.getByText(/Photograph the reference material/),
    ).toHaveTextContent("not solve the original assignment");
    expect(screen.getByLabelText("Take or choose a photo")).toHaveAttribute(
      "capture",
      "environment",
    );
    expect(screen.queryByRole("combobox", { name: "Purpose" })).toBeNull();
    expect(screen.queryByLabelText("Your work or question")).toBeNull();
  });

  it("shows the reading before specific guidance with no approval request or button", async () => {
    const fetcher = installSession(session([activity([operation()])]));
    const { container } = render(
      <Tutor learner={learner} offline={false} act={run} />,
    );
    const reading = await screen.findByRole("region", {
      name: "Reading from your photo",
    });
    const feedback = screen.getByRole("region", { name: "Tutor guidance" });
    expect(
      reading.compareDocumentPosition(feedback) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(within(reading).getByText(/Protect the wetland/)).toBeVisible();
    expect(within(reading).getByText(/line spacing/)).toBeVisible();
    expect(within(feedback).getByText(guidance.guidance[0]!)).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /confirm|approve|accept/i }),
    ).toBeNull();
    expect(screen.queryByLabelText(/transcription/i)).toBeNull();
    expect(container.querySelector(".verdict")).toBeNull();
    expect(
      fetcher.mock.calls.filter(([, options]) => options.method === "POST"),
    ).toHaveLength(0);
  });

  it("rejects low-confidence readings and offers clearer work without tutoring guessed text", async () => {
    const uncertain = operation({
      status: "failed",
      ambiguities: ["The second sentence overlaps the first."],
      reading: {
        quality: "uncertain",
        confidence: 0.46,
        can_continue: false,
        organization_feedback: ["Put each sentence on a separate line."],
        rejection_reason: "Overlapping writing makes the argument unclear.",
      },
      // Even inconsistent server data must not present feedback on rejected text.
      feedback: guidance,
    });
    const fetcher = installSession(session([activity([uncertain])]));
    render(<Tutor learner={learner} offline={false} act={run} />);
    expect(
      await screen.findByText("Please organize or retake this work."),
    ).toBeVisible();
    expect(
      screen.getByText("Put each sentence on a separate line."),
    ).toBeVisible();
    expect(screen.queryByRole("region", { name: "Tutor guidance" })).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Retry tutor response" }),
    ).toBeNull();
    expect(
      screen.getByRole("button", { name: "Take photo with phone" }),
    ).toBeEnabled();
    expect(screen.getByLabelText("Your work or question")).not.toHaveAttribute(
      "readonly",
    );
    expect(
      fetcher.mock.calls.filter(([, options]) => options.method === "POST"),
    ).toHaveLength(0);
  });

  it("shares full written work and continues discussion instead of demanding a final answer", async () => {
    const fetcher = installSession(session([activity([operation()])]));
    render(<Tutor learner={learner} offline={false} act={run} />);
    fireEvent.change(await screen.findByLabelText("Your work or question"), {
      target: {
        value:
          "I added an observation about nesting birds. Does it support my claim?",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Share my work" }));
    await vi.waitFor(() =>
      expect(
        fetcher.mock.calls.some(([url]) => url.endsWith("/submissions")),
      ).toBe(true),
    );
    const sent = fetcher.mock.calls.find(([url]) =>
      url.endsWith("/submissions"),
    )!;
    expect(JSON.parse(sent[1].body as string)).toMatchObject({
      kind: "answer",
      text: "I added an observation about nesting birds. Does it support my claim?",
      work_text: "",
      version: 1,
    });
    expect(screen.queryByText("Check answer")).toBeNull();
    await vi.waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Next activity" }),
      ).toBeEnabled(),
    );
  });

  it("changes tutor initiative without introducing a homework solution setting", async () => {
    const fetcher = installSession(session([activity()]));
    render(<Tutor learner={learner} offline={false} act={run} />);
    fireEvent.click(await screen.findByText("Session settings"));
    fireEvent.change(screen.getByLabelText("Tutor style for this session"), {
      target: { value: "tutor_led" },
    });
    fireEvent.change(screen.getByLabelText("Activity difficulty"), {
      target: { value: "introductory" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save session settings" }),
    );
    await vi.waitFor(() =>
      expect(
        fetcher.mock.calls.some(([url]) => url.endsWith("/settings")),
      ).toBe(true),
    );
    const sent = fetcher.mock.calls.find(([url]) => url.endsWith("/settings"))!;
    expect(JSON.parse(sent[1].body as string)).toEqual({
      initiative: "tutor_led",
      difficulty: "introductory",
    });
    expect(
      screen.getByText(/Supplied homework is used for related practice only/),
    ).toBeVisible();
    expect(screen.queryByRole("button", { name: /Full solution/ })).toBeNull();
  });

  it("blocks competing work while a reading is being processed", async () => {
    installSession(
      session([
        activity([
          operation({
            status: "interpreting",
            reading: null,
            feedback: null,
            interpretation: null,
          }),
        ]),
      ]),
    );
    render(<Tutor learner={learner} offline={false} act={run} />);
    expect(
      await screen.findByText(
        "Reading your photograph… Your session is saved.",
      ),
    ).toBeVisible();
    expect(document.querySelector(".spinner")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "AI tutor" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
    expect(
      await screen.findByRole("button", { name: "Share my work" }),
    ).toBeDisabled();
    expect(screen.getByLabelText("Your work or question")).toHaveAttribute(
      "readonly",
    );
    expect(
      screen.getByRole("button", { name: "Next activity" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Take photo with phone" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Cancel this operation" }),
    ).toBeEnabled();
  });

  it("shows the persisted provider code and only offers valid retries", async () => {
    const failure = operation({
      status: "failed",
      reading: null,
      feedback: null,
      interpretation: null,
      safe_error:
        "The photo reader rejected the request. Ask an adult to check the model and connection settings. Your work is saved.",
      error_code: "invalid_request",
      retryable: false,
    });
    installSession(session([activity([failure])]));
    render(<Tutor learner={learner} offline={false} act={run} />);
    expect(
      await screen.findByText("Diagnostic code: invalid_request"),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Retry tutor response" }),
    ).toBeNull();
  });

  it("keeps the original session request and key when its acknowledgement is lost", async () => {
    const errors: unknown[] = [];
    let attempts = 0;
    const fetcher = vi.fn((url: string, options: RequestInit) => {
      if (url.endsWith("/features")) return response(capabilities);
      if (url.endsWith(`/tutor/sessions/${sessionId}`))
        return response(session());
      if (url.endsWith("/tutor/sessions") && options.method === "POST") {
        attempts += 1;
        if (attempts === 1)
          return Promise.reject(new TypeError("Lost acknowledgement"));
        return response(session());
      }
      if (url.endsWith("/tutor/sessions")) return response([]);
      throw new Error(url);
    });
    vi.stubGlobal("fetch", fetcher);
    render(
      <Tutor
        learner={learner}
        offline={false}
        act={async (action) => {
          try {
            await action();
          } catch (cause) {
            errors.push(cause);
          }
        }}
      />,
    );
    fireEvent.change(screen.getByLabelText("Topic or learning goal"), {
      target: { value: "Persuasive writing" },
    });
    await vi.waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Start session" }),
      ).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Start session" }));
    const retry = await screen.findByRole("button", {
      name: "Retry saved request",
    });
    expect(screen.getByLabelText("Topic or learning goal")).toBeDisabled();
    fireEvent.click(retry);
    expect(
      await screen.findByRole("button", { name: "Create practice activity" }),
    ).toBeEnabled();
    const sent = fetcher.mock.calls.filter(
      ([url, options]) =>
        url.endsWith("/tutor/sessions") && options.method === "POST",
    );
    expect(sent).toHaveLength(2);
    expect(sent[1]![1].body).toBe(sent[0]![1].body);
    expect(
      (sent[1]![1].headers as Record<string, string>)["Idempotency-Key"],
    ).toBe((sent[0]![1].headers as Record<string, string>)["Idempotency-Key"]);
    expect(errors).toHaveLength(1);
  });

  it("makes AI tutoring the only private practice interface", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.endsWith("/auth/session"))
          return response({
            authenticated: true,
            role: "learner",
            learner_id: learner,
            csrf_token: "synthetic",
          });
        if (url.endsWith("/features")) return response(capabilities);
        if (url.endsWith("/tutor/sessions")) return response([]);
        throw new Error(url);
      }),
    );
    render(<App />);
    expect(
      await screen.findByLabelText("Topic or learning goal"),
    ).toBeVisible();
    expect(
      screen.queryByText(
        /Built-in math|offline practice pack|Tutor profiles|Full solution/,
      ),
    ).toBeNull();
    expect(
      screen.getByRole("link", { name: "Shepard Academy Universe" }),
    ).toBeVisible();
  });

  it("shows one current activity and keeps the response draft across page changes", async () => {
    installSession(session([activity([operation()])]));
    const draftChanged = vi.fn();
    const props = {
      learner,
      offline: false,
      act: run,
      onDraftChange: draftChanged,
    };
    const view = render(<Tutor {...props} />);
    const input = await screen.findByLabelText("Your work or question");
    expect(screen.getAllByText(activity().problem_text)).toHaveLength(1);
    expect(screen.queryByLabelText("Topic or learning goal")).toBeNull();
    fireEvent.change(input, {
      target: { value: "An unsent observation about birds." },
    });
    expect(screen.getByRole("button", { name: "New session" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Next activity" }),
    ).toBeDisabled();
    expect(draftChanged).toHaveBeenLastCalledWith(true);
    view.rerender(<Tutor {...props} page="history" />);
    expect(
      screen.getByRole("heading", { name: "Saved sessions" }),
    ).toBeVisible();
    expect(input).not.toBeVisible();
    expect(
      screen.getByRole("button", { name: "Continue session" }),
    ).toBeEnabled();
    view.rerender(<Tutor {...props} active={false} />);
    view.rerender(<Tutor {...props} active />);
    expect(screen.getByLabelText("Your work or question")).toBe(input);
    expect(input).toHaveValue("An unsent observation about birds.");
    fireEvent.change(input, { target: { value: "" } });
    expect(draftChanged).toHaveBeenLastCalledWith(false);
    fireEvent.click(screen.getByRole("button", { name: "New session" }));
    expect(screen.getByLabelText("Topic or learning goal")).toBeVisible();
    expect(input).not.toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: "Back to current session" }),
    );
    expect(input).toBeVisible();
  });

  it("opens an owned history session and preserves page query parameters", async () => {
    const navigate = vi.fn();
    const own = session([activity()]);
    const other = {
      ...own,
      id: "another-session",
      learner_id: "another-learner",
      topic: "Private other learner work",
    };
    window.history.replaceState(null, "", "/?page=history");
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.endsWith("/features")) return response(capabilities);
        if (url.endsWith(`/tutor/sessions/${sessionId}`)) return response(own);
        if (url.endsWith("/tutor/sessions")) return response([own, other]);
        throw new Error(url);
      }),
    );
    render(
      <Tutor
        learner={learner}
        offline={false}
        act={run}
        page="history"
        onNavigate={navigate}
      />,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Continue session" }),
    );
    await vi.waitFor(() => expect(navigate).toHaveBeenCalledWith("practice"));
    expect(window.location.search).toBe("?page=history");
    expect(window.location.hash).toBe(`#tutor=${sessionId}`);
    expect(screen.queryByText(other.topic)).toBeNull();
  });

  it("keeps an unsent response when asking for a hint", async () => {
    const fetcher = installSession(session([activity()]));
    render(<Tutor learner={learner} offline={false} act={run} />);
    const input = await screen.findByLabelText("Your work or question");
    fireEvent.change(input, { target: { value: "An unfinished argument." } });
    fireEvent.click(screen.getByText("Get help with this activity"));
    fireEvent.click(screen.getByRole("button", { name: "Give me a hint" }));
    await vi.waitFor(() =>
      expect(
        fetcher.mock.calls.some(([url]) => url.endsWith("/submissions")),
      ).toBe(true),
    );
    await vi.waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Give me a hint" }),
      ).toBeEnabled(),
    );
    expect(input).toHaveValue("An unfinished argument.");
    const request = fetcher.mock.calls.find(([url]) =>
      url.endsWith("/submissions"),
    )!;
    expect(JSON.parse(request[1].body as string)).toMatchObject({
      kind: "hint",
      text: "",
      help_level: 1,
    });
  });

  it("restores the session in the URL when the browser goes back", async () => {
    const secondId = "911c9abc-4e8e-424d-a914-4338187ba00e";
    const first = session([activity()]);
    const second = { ...first, id: secondId, topic: "Photosynthesis" };
    window.history.pushState(null, "", `/?page=practice#tutor=${sessionId}`);
    window.history.pushState(null, "", `/?page=practice#tutor=${secondId}`);
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.endsWith("/features")) return response(capabilities);
        if (url.endsWith(`/tutor/sessions/${sessionId}`))
          return response(first);
        if (url.endsWith(`/tutor/sessions/${secondId}`))
          return response(second);
        if (url.endsWith("/tutor/sessions")) return response([first, second]);
        throw new Error(url);
      }),
    );
    render(<Tutor learner={learner} offline={false} act={run} />);
    expect(
      await screen.findByRole("heading", { name: "Photosynthesis" }),
    ).toBeVisible();
    window.history.back();
    expect(
      await screen.findByRole("heading", { name: "Persuasive writing" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "Photosynthesis" }),
    ).toBeNull();
    expect(window.location.hash).toBe(`#tutor=${sessionId}`);
    expect(window.location.search).toBe("?page=practice");
  });

  it("preserves the current session and draft when browser Back targets another session", async () => {
    const secondId = "911c9abc-4e8e-424d-a914-4338187ba00e";
    const first = session([activity()]);
    const second = { ...first, id: secondId, topic: "Photosynthesis" };
    window.history.pushState(null, "", `/?page=practice#tutor=${sessionId}`);
    window.history.pushState(null, "", `/?page=history#tutor=${secondId}`);
    const fetcher = vi.fn((url: string) => {
      if (url.endsWith("/features")) return response(capabilities);
      if (url.endsWith(`/tutor/sessions/${secondId}`)) return response(second);
      if (url.endsWith("/tutor/sessions")) return response([first, second]);
      throw new Error(url);
    });
    vi.stubGlobal("fetch", fetcher);
    render(<Tutor learner={learner} offline={false} act={run} />);
    const input = await screen.findByLabelText("Your work or question");
    fireEvent.change(input, {
      target: { value: "Keep my unfinished response." },
    });
    window.history.back();
    expect(
      await screen.findByText(
        "Send or clear your draft in Practice before switching sessions.",
      ),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Photosynthesis" }),
    ).toBeVisible();
    expect(input).toHaveValue("Keep my unfinished response.");
    expect(window.location.hash).toBe(`#tutor=${secondId}`);
    expect(window.location.search).toBe("?page=practice");
    expect(
      fetcher.mock.calls.some(([url]) =>
        url.endsWith(`/tutor/sessions/${sessionId}`),
      ),
    ).toBe(false);
  });

  it("keeps an uncertain submission and its retry identity while History is open", async () => {
    const value = session([activity()]);
    let attempts = 0;
    const busyChanged = vi.fn();
    const fetcher = vi.fn((url: string, options: RequestInit) => {
      if (url.endsWith("/features")) return response(capabilities);
      if (url.endsWith(`/tutor/sessions/${sessionId}`)) return response(value);
      if (url.endsWith("/tutor/sessions")) return response([value]);
      if (url.endsWith("/submissions") && options.method === "POST") {
        attempts += 1;
        if (attempts === 1)
          return Promise.reject(new TypeError("Lost receipt"));
        return response({});
      }
      throw new Error(url);
    });
    window.location.hash = `tutor=${sessionId}`;
    vi.stubGlobal("fetch", fetcher);
    const caught: unknown[] = [];
    const props = {
      learner,
      offline: false,
      onBusyChange: busyChanged,
      act: async (action: () => Promise<void>) => {
        try {
          await action();
        } catch (error) {
          caught.push(error);
        }
      },
    };
    const view = render(<Tutor {...props} />);
    fireEvent.change(await screen.findByLabelText("Your work or question"), {
      target: { value: "Keep this draft." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Share my work" }));
    await screen.findByRole("button", { name: "Retry saved request" });
    expect(busyChanged).toHaveBeenLastCalledWith(true);
    view.rerender(<Tutor {...props} page="history" />);
    expect(
      screen.getByRole("button", { name: "Continue session" }),
    ).toBeDisabled();
    view.rerender(<Tutor {...props} />);
    expect(screen.getByLabelText("Your work or question")).toHaveValue(
      "Keep this draft.",
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Retry saved request" }),
    );
    await vi.waitFor(() => expect(busyChanged).toHaveBeenLastCalledWith(false));
    const sent = fetcher.mock.calls.filter(([url]) =>
      url.endsWith("/submissions"),
    );
    expect(sent).toHaveLength(2);
    expect(sent[1]![1].body).toBe(sent[0]![1].body);
    expect(
      (sent[1]![1].headers as Record<string, string>)["Idempotency-Key"],
    ).toBe((sent[0]![1].headers as Record<string, string>)["Idempotency-Key"]);
    expect(caught).toHaveLength(1);
    expect(screen.getByLabelText("Your work or question")).toHaveValue("");
  });

  it("explains unavailable tutoring and refreshes capabilities after setup", async () => {
    let available = false;
    const navigate = vi.fn();
    const fetcher = vi.fn((url: string) => {
      if (url.endsWith("/features"))
        return response({
          ...capabilities,
          tutoring_available: available,
          tutor_status: available
            ? "Local tutor ready."
            : "This demo does not accept personal work.",
        });
      if (url.endsWith("/tutor/sessions")) return response([]);
      throw new Error(url);
    });
    vi.stubGlobal("fetch", fetcher);
    const props = {
      learner,
      offline: false,
      act: run,
      isAdult: true,
      onNavigate: navigate,
    };
    const view = render(<Tutor {...props} />);
    expect(
      await screen.findByText("Tutoring is not available yet"),
    ).toBeVisible();
    fireEvent.change(screen.getByLabelText("Topic or learning goal"), {
      target: { value: "Photosynthesis" },
    });
    expect(
      screen.getByRole("button", { name: "Start session" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Open Settings" }));
    expect(navigate).toHaveBeenLastCalledWith("settings");
    fireEvent.click(screen.getByRole("button", { name: "Setup help" }));
    expect(navigate).toHaveBeenLastCalledWith("help", "setup");
    view.rerender(<Tutor {...props} active={false} />);
    available = true;
    view.rerender(<Tutor {...props} active settingsVersion={1} />);
    await vi.waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Start session" }),
      ).toBeEnabled(),
    );
    expect(screen.getByLabelText("Topic or learning goal")).toHaveValue(
      "Photosynthesis",
    );
    expect(
      fetcher.mock.calls.filter(([url]) => url.endsWith("/features")),
    ).toHaveLength(2);
  });
});
