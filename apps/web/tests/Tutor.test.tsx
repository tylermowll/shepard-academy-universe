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
  window.location.hash = "";
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = "";
});

describe("AI learning conversation", () => {
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
    fireEvent.change(screen.getByLabelText("Tutor initiative"), {
      target: { value: "learner_led" },
    });
    await vi.waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Start tutoring" }),
      ).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Start tutoring" }));
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
    expect(
      screen.getByText(/A supplied assignment is reference material/),
    ).toHaveTextContent("distinct practice activity");
    expect(
      screen.getByText(/A supplied assignment is reference material/),
    ).toHaveTextContent("cannot retrieve or pretend to have read your book");
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
    fireEvent.click(screen.getByText("Submit a photograph"));
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
    fireEvent.change(screen.getByLabelText("Initiative for this session"), {
      target: { value: "tutor_led" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save tutor initiative" }),
    );
    await vi.waitFor(() =>
      expect(
        fetcher.mock.calls.some(([url]) => url.endsWith("/settings")),
      ).toBe(true),
    );
    const sent = fetcher.mock.calls.find(([url]) => url.endsWith("/settings"))!;
    expect(JSON.parse(sent[1].body as string)).toEqual({
      initiative: "tutor_led",
    });
    expect(
      screen.getByText(/It never enables answers to supplied homework/),
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
        screen.getByRole("button", { name: "Start tutoring" }),
      ).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Start tutoring" }));
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
    expect(screen.getByText("Shepard Tutor")).toBeVisible();
  });
});
