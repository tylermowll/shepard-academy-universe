import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, newKey, type Schema } from "./client";
import { PhoneLink } from "./PhoneLink";
import { PhotoInput } from "./PhotoInput";
import { SafeText } from "./SafeText";

type Props = {
  learner: string;
  offline: boolean;
  act: (action: () => Promise<void>) => Promise<void>;
};
type Initiative = "tutor_led" | "balanced" | "learner_led";
type Source = "topic" | "reference_text" | "reference_photo";
type Command = {
  path: string;
  body: unknown;
  key: string;
  sessionId: string;
  kind: "session" | "activity" | "submission" | "settings" | "finish";
  ambiguous: boolean;
};
const activeStatuses = [
  "queued",
  "checking",
  "generating",
  "tutoring",
  "interpreting",
];

function InitiativeOptions() {
  return (
    <>
      <option value="tutor_led">Tutor leads: suggest the next step</option>
      <option value="balanced">Balanced: decide together</option>
      <option value="learner_led">I lead: follow my questions</option>
    </>
  );
}

export function Tutor({ learner, offline, act }: Props) {
  const [history, setHistory] = useState<Schema<"TutoringSessionPublic">[]>([]);
  const [session, setSession] =
    useState<Schema<"TutoringSessionPublic"> | null>(null);
  const [features, setFeatures] = useState<Schema<"Features"> | null>(null);
  const [topic, setTopic] = useState("");
  const [initiative, setInitiative] = useState<Initiative>("balanced");
  const [source, setSource] = useState<Source>("topic");
  const [reference, setReference] = useState("");
  const [text, setText] = useState("");
  const [working, setWorking] = useState(false);
  const [pending, setPending] = useState<Command | null>(null);
  const [photoPending, setPhotoPending] = useState(false);
  const [connectionError, setConnectionError] = useState("");
  const pendingCommand = useRef<Command | null>(null);
  const mounted = useRef(true);
  const selectedSession = useRef("");
  const loadSequence = useRef(0);
  const polling = useRef(false);
  const blocked = working || pending !== null || photoPending;

  const load = useCallback(
    async (id?: string) => {
      const sequence = ++loadSequence.current;
      if (id) selectedSession.current = id;
      const [sessions, capabilities, loaded] = await Promise.all([
        api<Schema<"TutoringSessionPublic">[]>("/tutor/sessions"),
        api<Schema<"Features">>(`/learners/${learner}/features`),
        id
          ? api<Schema<"TutoringSessionPublic">>(`/tutor/sessions/${id}`)
          : Promise.resolve(null),
      ]);
      if (!mounted.current || sequence !== loadSequence.current) return;
      setHistory(sessions.filter((item) => item.learner_id === learner));
      setFeatures(capabilities);
      setConnectionError("");
      if (loaded) {
        if (loaded.learner_id !== learner) {
          selectedSession.current = "";
          setSession(null);
          window.history.replaceState(null, "", window.location.pathname);
          return;
        }
        setSession(loaded);
        window.history.replaceState(null, "", `#tutor=${loaded.id}`);
      }
    },
    [learner],
  );

  useEffect(() => {
    mounted.current = true;
    const id = new URLSearchParams(window.location.hash.slice(1)).get("tutor");
    void act(() => load(id && /^[a-f0-9-]{36}$/.test(id) ? id : undefined));
    return () => {
      mounted.current = false;
      loadSequence.current += 1;
    };
  }, [act, load]);

  const sessionId = session?.id;
  useEffect(() => {
    if (!sessionId) return;
    const refresh = () => {
      if (
        polling.current ||
        !navigator.onLine ||
        document.visibilityState !== "visible"
      )
        return;
      polling.current = true;
      void load(selectedSession.current)
        .catch((cause: unknown) => {
          if (mounted.current)
            setConnectionError(
              cause instanceof Error
                ? cause.message
                : "Reconnect to recover your saved discussion.",
            );
        })
        .finally(() => {
          polling.current = false;
        });
    };
    const timer = window.setInterval(refresh, 2500);
    window.addEventListener("online", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("online", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [sessionId, load]);

  const refresh = useCallback(async () => {
    if (selectedSession.current) await load(selectedSession.current);
  }, [load]);
  const problem = session?.problems.find((item) => item.status === "assigned");
  const active =
    problem?.operations.some((operation) =>
      activeStatuses.includes(operation.status),
    ) ?? false;
  const disabled = blocked || active || offline;

  const sendCommand = async (request: Command) => {
    setWorking(true);
    try {
      let created: Schema<"TutoringSessionPublic"> | undefined;
      try {
        if (request.kind === "session")
          created = await api<Schema<"TutoringSessionPublic">>(
            request.path,
            "POST",
            request.body,
            request.key,
          );
        else await api(request.path, "POST", request.body, request.key);
      } catch (cause) {
        // Keep the original payload/key after an uncertain acknowledgement.
        if (
          !request.ambiguous &&
          cause instanceof ApiError &&
          cause.status < 500 &&
          cause.status !== 408
        ) {
          pendingCommand.current = null;
          setPending(null);
        } else request.ambiguous = true;
        throw cause;
      }
      pendingCommand.current = null;
      if (!mounted.current) return;
      setPending(null);
      if (request.kind === "submission") setText("");
      if (request.kind === "activity") setReference("");
      if (created) await load(created.id);
      else if (selectedSession.current === request.sessionId) await refresh();
    } finally {
      if (mounted.current) setWorking(false);
    }
  };
  const command = async (
    kind: Command["kind"],
    path: string,
    body: unknown,
  ) => {
    if (pendingCommand.current || photoPending) return;
    const request: Command = {
      kind,
      path,
      body,
      key: newKey(),
      sessionId: selectedSession.current,
      ambiguous: false,
    };
    pendingCommand.current = request;
    setPending(request);
    await sendCommand(request);
  };
  const activity = async (nextSource: Source = source) => {
    if (!session) return;
    const body: Schema<"TutorActivityInput"> = {
      source: nextSource,
      ...(nextSource === "reference_text" ? { reference_text: reference } : {}),
    };
    await command("activity", `/tutor/sessions/${session.id}/activities`, body);
  };
  const submit = async (kind: "answer" | "question" | "hint", level = 0) => {
    if (!problem) return;
    await command("submission", `/problems/${problem.id}/submissions`, {
      version: problem.version,
      kind,
      text: kind === "hint" ? "" : text,
      help_level: level,
      work_text: "",
    } satisfies Schema<"SubmissionInput">);
  };

  return (
    <section className="tutor" aria-label="AI tutor">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Think it through, together</p>
          <h2>Your work. A helpful next step.</h2>
        </div>
        <label>
          Saved tutoring sessions
          <select
            value={session?.id ?? ""}
            disabled={blocked}
            onChange={(event) => {
              const id = event.target.value;
              if (id) void act(() => load(id));
            }}
          >
            <option value="">Choose a session</option>
            {history.map((item) => (
              <option value={item.id} key={item.id}>
                {item.topic} · {item.status}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p>
        Choose any subject: writing, reading, history, social studies, science,
        math, or something else. Share your thinking and build understanding—not
        a finished homework answer.
      </p>
      <p className="fine">
        {features?.tutor_status ?? "Checking the configured tutor…"}{" "}
        {features &&
          ` Text and references are processed: ${features.text_processing}.`}
      </p>
      <form
        className="card"
        onSubmit={(event) => {
          event.preventDefault();
          void act(() =>
            command("session", "/tutor/sessions", {
              learner_id: learner,
              topic,
              initiative,
            } satisfies Schema<"TutoringSessionInput">),
          );
        }}
      >
        <label>
          Topic or learning goal
          <input
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            maxLength={500}
            required
            disabled={blocked}
            placeholder="e.g. photosynthesis, persuasive writing, or a book passage"
          />
        </label>
        <label>
          Tutor initiative
          <select
            value={initiative}
            onChange={(event) =>
              setInitiative(event.target.value as Initiative)
            }
            disabled={blocked}
          >
            <InitiativeOptions />
          </select>
        </label>
        <button
          className="primary"
          disabled={
            blocked || offline || !topic.trim() || !features?.tutoring_available
          }
        >
          Start tutoring
        </button>
      </form>
      {pending && !working && (
        <div role="status" className="notice">
          <p>
            The server has not acknowledged your request. Retry the saved
            request before continuing; it will not create a second activity or
            response.
          </p>
          <button
            disabled={offline}
            onClick={() => void act(() => sendCommand(pending))}
          >
            Retry saved request
          </button>
        </div>
      )}
      {connectionError && (
        <p role="status" className="error">
          {connectionError}
        </p>
      )}
      {session && (
        <>
          <div className="section-heading">
            <h3>{session.topic}</h3>
            <span className="pill">{session.status}</span>
          </div>
          {session.status === "open" && (
            <>
              <details>
                <summary>Session settings</summary>
                <form
                  key={`${session.id}-${session.initiative}`}
                  onSubmit={(event) => {
                    event.preventDefault();
                    const value = new FormData(event.currentTarget).get(
                      "initiative",
                    ) as Initiative;
                    void act(() =>
                      command(
                        "settings",
                        `/tutor/sessions/${session.id}/settings`,
                        {
                          initiative: value,
                        } satisfies Schema<"TutorSettingsInput">,
                      ),
                    );
                  }}
                >
                  <label>
                    Initiative for this session
                    <select
                      name="initiative"
                      defaultValue={session.initiative}
                      disabled={disabled}
                    >
                      <InitiativeOptions />
                    </select>
                  </label>
                  <button disabled={disabled}>Save tutor initiative</button>
                  <p className="fine">
                    This changes how much the tutor leads. It never enables
                    answers to supplied homework.
                  </p>
                </form>
                <button
                  disabled={disabled}
                  onClick={() =>
                    void act(() =>
                      command("finish", `/sessions/${session.id}/finish`, {}),
                    )
                  }
                >
                  Finish tutoring session
                </button>
              </details>
              <details open={!problem || undefined}>
                <summary>
                  {problem
                    ? "New activity or reference"
                    : "Choose your practice material"}
                </summary>
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    void act(() => activity());
                  }}
                >
                  <label>
                    Practice source
                    <select
                      value={source}
                      onChange={(event) =>
                        setSource(event.target.value as Source)
                      }
                      disabled={disabled}
                    >
                      <option value="topic">Generate from my topic</option>
                      <option value="reference_text">
                        Use pasted reference material
                      </option>
                      <option value="reference_photo">
                        Use a photo of reference material
                      </option>
                    </select>
                  </label>
                  {source !== "topic" && (
                    <p className="notice">
                      A supplied assignment is reference material, not something
                      the tutor will solve. It will create a distinct practice
                      activity using the same concepts. For reading, include the
                      passage; the tutor cannot retrieve or pretend to have read
                      your book.
                    </p>
                  )}
                  {source === "reference_text" && (
                    <label>
                      Reference material
                      <textarea
                        value={reference}
                        onChange={(event) => setReference(event.target.value)}
                        required
                        maxLength={8000}
                        rows={6}
                        disabled={disabled}
                      />
                    </label>
                  )}
                  {source === "reference_photo" && (
                    <p>
                      Create the activity, then use the phone link or upload the
                      reference photo. The reading is shown before analogous
                      practice is generated.
                    </p>
                  )}
                  <button
                    className="primary"
                    disabled={
                      disabled ||
                      (source === "reference_text" && !reference.trim()) ||
                      (source === "reference_photo" &&
                        !features?.photos_available)
                    }
                  >
                    Create practice activity
                  </button>
                </form>
              </details>
            </>
          )}
          {problem && (
            <article className="tutor-activity card">
              <p className="eyebrow">
                {problem.activity_state === "reference_capture"
                  ? "Reference material"
                  : "Your practice activity"}
              </p>
              <SafeText text={problem.problem_text} />
              {problem.concept_focus && (
                <p className="fine">Focus: {problem.concept_focus}</p>
              )}
              {problem.activity_state === "generating" && (
                <p role="status">
                  {active
                    ? "Preparing a practice activity… Creating different practice from the source, not requesting its answer."
                    : "No activity is ready yet. Retry the failed operation below, or choose new practice material."}
                </p>
              )}
              {problem.activity_state === "reference_capture" && (
                <p>
                  Photograph the source material. We will read it and create
                  different practice—not solve the supplied assignment.
                </p>
              )}
              {problem.activity_state === "ready" && (
                <>
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      void act(() => submit("answer"));
                    }}
                  >
                    <label>
                      Your work or question
                      <textarea
                        value={text}
                        onChange={(event) => setText(event.target.value)}
                        maxLength={8000}
                        rows={5}
                        readOnly={disabled}
                        placeholder="Explain your reasoning, share a draft, revise your work, or ask about the idea."
                      />
                    </label>
                    <div className="actions">
                      <button
                        className="primary"
                        disabled={disabled || !text.trim()}
                      >
                        Share my work
                      </button>
                      <button
                        type="button"
                        disabled={disabled || !text.trim()}
                        onClick={() => void act(() => submit("question"))}
                      >
                        Ask about this
                      </button>
                    </div>
                  </form>
                  <div className="actions">
                    <button
                      disabled={disabled}
                      onClick={() => void act(() => submit("hint", 1))}
                    >
                      Give me a hint
                    </button>
                    <button
                      disabled={disabled}
                      onClick={() => void act(() => submit("hint", 2))}
                    >
                      Explain the concept
                    </button>
                    <button
                      disabled={disabled}
                      onClick={() => void act(() => submit("hint", 3))}
                    >
                      Show a different example
                    </button>
                  </div>
                </>
              )}
              {(problem.activity_state !== "generating" || photoPending) && (
                <>
                  <p className="fine">{features?.photo_status}</p>
                  {features?.photos_available && (
                    <>
                      <PhoneLink
                        key={`phone-${problem.id}-${problem.version}`}
                        problem={problem.id}
                        version={problem.version}
                        disabled={disabled}
                        act={act}
                      />
                      <PhotoInput
                        key={problem.id}
                        problem={problem.id}
                        version={problem.version}
                        disabled={
                          active || working || pending !== null || offline
                        }
                        onPendingChange={setPhotoPending}
                        act={act}
                        onSaved={refresh}
                        reference={
                          problem.activity_state === "reference_capture"
                        }
                      />
                    </>
                  )}
                </>
              )}
              {active && (
                <p role="status">
                  Your tutor is working. You can return to this session if the
                  connection drops.
                </p>
              )}
              {problem.activity_state === "ready" && (
                <button
                  disabled={disabled}
                  onClick={() => void act(() => activity("topic"))}
                >
                  Next activity
                </button>
              )}
              <p className="fine">
                You can revise or discuss this activity as long as you need.
                “Next activity” uses the discussion so far; it does not certify
                mastery.
              </p>
            </article>
          )}
          <section aria-labelledby="tutor-history-heading">
            <h3 id="tutor-history-heading">Your learning conversation</h3>
            {session.problems.length === 0 && (
              <p>Create your first practice activity above.</p>
            )}
            {session.problems.map((item) => (
              <article className="card tutor-history" key={item.id}>
                <h4>
                  {item.status === "assigned"
                    ? "Current activity"
                    : "Earlier activity"}
                </h4>
                <SafeText text={item.problem_text} />
                {item.operations.map((operation) => (
                  <TutorOperation
                    key={operation.id}
                    operation={operation}
                    offline={offline}
                    disabled={blocked}
                    act={act}
                    refresh={refresh}
                  />
                ))}
              </article>
            ))}
          </section>
        </>
      )}
      <p className="fine">
        AI feedback can be mistaken. Ask for an explanation, challenge a
        reading, and keep revising. Guidance is not a certified grade.
      </p>
    </section>
  );
}

function TutorOperation({
  operation,
  offline,
  disabled,
  act,
  refresh,
}: {
  operation: Schema<"OperationPublic">;
  offline: boolean;
  disabled: boolean;
  act: Props["act"];
  refresh: () => Promise<void>;
}) {
  const reading = operation.reading;
  const feedback = operation.feedback;
  const canContinue =
    reading?.can_continue === true &&
    reading.quality === "clear" &&
    reading.confidence >= 0.85 &&
    !operation.ambiguities?.length;
  const rejected = reading && !canContinue;

  return (
    <section className="operation tutor-operation">
      {operation.text && operation.kind !== "generation" && (
        <>
          <p className="eyebrow">
            You ·{" "}
            {operation.kind === "answer"
              ? "shared work"
              : operation.kind === "hint"
                ? "requested guidance"
                : "discussion"}
          </p>
          <p className="user-text">{operation.text}</p>
        </>
      )}
      {operation.work_text && (
        <p className="user-text">{operation.work_text}</p>
      )}
      {reading && (
        <section className="photo-reading" aria-label="Reading from your photo">
          <h5>Reading from your photo</h5>
          <p className="user-text">
            {operation.interpretation ||
              "The writing could not be read reliably."}
          </p>
          {reading.organization_feedback.length > 0 && (
            <>
              <h6>Handwriting and organization</h6>
              <ul>
                {reading.organization_feedback.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </>
          )}
          {(operation.ambiguities ?? []).map((item, index) => (
            <p className="notice" key={index}>
              {item}
            </p>
          ))}
          {rejected && (
            <div role="status" className="error">
              <strong>Please organize or retake this work.</strong>
              <p>
                {reading.rejection_reason ??
                  "The tutor is not confident it can read this reliably. Write clearly, separate your steps or paragraphs, and take a well-lit, straight-on photo."}
              </p>
              <p>
                No tutoring will proceed from this uncertain reading. Submit a
                clearer photo, or write your work in the response box.
              </p>
            </div>
          )}
          {canContinue && (
            <p className="fine">
              This reading was clear enough to continue automatically. If you
              notice a mistake, tell the tutor in your next response.
            </p>
          )}
        </section>
      )}
      {feedback && !rejected ? (
        <section className="tutor-feedback" aria-label="Tutor guidance">
          <h5>Tutor guidance</h5>
          {feedback.strengths.length > 0 && (
            <>
              <h6>What is working</h6>
              <ul>
                {feedback.strengths.map((item, index) => (
                  <li key={index}>
                    <SafeText text={item} />
                  </li>
                ))}
              </ul>
            </>
          )}
          {feedback.guidance.map((item, index) => (
            <SafeText key={index} text={item} />
          ))}
          {feedback.concepts.length > 0 && (
            <p className="fine">Concepts: {feedback.concepts.join(" · ")}</p>
          )}
          <h6>Try this next</h6>
          <SafeText text={feedback.next_step} />
          {feedback.uncertainty_note && (
            <p className="notice">{feedback.uncertainty_note}</p>
          )}
          <p className="fine">
            {operation.source} · AI guidance, not a certified grade
          </p>
        </section>
      ) : (
        !rejected && operation.message && <SafeText text={operation.message} />
      )}
      {operation.safe_error && !rejected && (
        <p role="status" className="error">
          {operation.safe_error}
        </p>
      )}
      {operation.status === "failed" && !rejected && (
        <button
          disabled={disabled || offline}
          onClick={() =>
            void act(async () => {
              await api(`/operations/${operation.id}/retry`, "POST");
              await refresh();
            })
          }
        >
          Retry tutor response
        </button>
      )}
      {!["completed", "canceled"].includes(operation.status) && (
        <button
          disabled={disabled || offline}
          onClick={() =>
            void act(async () => {
              await api(`/operations/${operation.id}/cancel`, "POST");
              await refresh();
            })
          }
        >
          {rejected ? "Dismiss rejected reading" : "Cancel this operation"}
        </button>
      )}
    </section>
  );
}
