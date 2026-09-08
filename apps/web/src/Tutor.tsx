import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, newKey, type Schema } from "./client";
import { BusyStatus } from "./BusyStatus";
import { ContextHelp } from "./Help";
import { PhoneLink } from "./PhoneLink";
import { PhotoInput } from "./PhotoInput";
import { SafeText } from "./SafeText";
import { TutorConversation } from "./TutorConversation";

type Props = {
  learner: string;
  offline: boolean;
  act: (action: () => Promise<void>) => Promise<void>;
  page?: "practice" | "history";
  active?: boolean;
  isAdult?: boolean;
  settingsVersion?: number;
  onBusyChange?: (busy: boolean) => void;
  onDraftChange?: (draft: boolean) => void;
  onNavigate?: (
    page: "practice" | "history" | "learners" | "settings" | "help",
    help?: string,
  ) => void;
};
type Initiative = "tutor_led" | "balanced" | "learner_led";
type Difficulty = "introductory" | "standard" | "challenge";
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
      <option value="tutor_led">Suggest what to do next</option>
      <option value="balanced">Decide together</option>
      <option value="learner_led">Follow my questions</option>
    </>
  );
}

function DifficultyOptions() {
  return (
    <>
      <option value="introductory">Easier</option>
      <option value="standard">Standard</option>
      <option value="challenge">Harder</option>
    </>
  );
}

function difficultyLabel(value: Difficulty) {
  return {
    introductory: "Easier",
    standard: "Standard",
    challenge: "Harder",
  }[value];
}

export function Tutor({
  learner,
  offline,
  act,
  page = "practice",
  active: pageActive = true,
  isAdult = false,
  settingsVersion = 0,
  onBusyChange,
  onDraftChange,
  onNavigate,
}: Props) {
  const [history, setHistory] = useState<Schema<"TutoringSessionPublic">[]>([]);
  const [session, setSession] =
    useState<Schema<"TutoringSessionPublic"> | null>(null);
  const [features, setFeatures] = useState<Schema<"Features"> | null>(null);
  const [topic, setTopic] = useState("");
  const [initiative, setInitiative] = useState<Initiative>("balanced");
  const [difficulty, setDifficulty] = useState<Difficulty>("standard");
  const [source, setSource] = useState<Source>("topic");
  const [reference, setReference] = useState("");
  const [text, setText] = useState("");
  const [working, setWorking] = useState(false);
  const [pending, setPending] = useState<Command | null>(null);
  const [photoPending, setPhotoPending] = useState(false);
  const [photoDraft, setPhotoDraft] = useState(false);
  const [attachmentsOpen, setAttachmentsOpen] = useState(false);
  const [newSession, setNewSession] = useState(false);
  const [connectionError, setConnectionError] = useState("");
  const [navigationNotice, setNavigationNotice] = useState("");
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
          window.history.replaceState(
            null,
            "",
            `${window.location.pathname}${window.location.search}`,
          );
          return;
        }
        setSession(loaded);
        window.history.replaceState(
          null,
          "",
          `${window.location.pathname}${window.location.search}#tutor=${loaded.id}`,
        );
      }
    },
    [learner],
  );

  useEffect(() => {
    mounted.current = true;
    const id = new URLSearchParams(window.location.hash.slice(1)).get("tutor");
    selectedSession.current = id && /^[a-f0-9-]{36}$/.test(id) ? id : "";
    return () => {
      mounted.current = false;
      loadSequence.current += 1;
    };
  }, [learner]);

  useEffect(() => {
    if (pageActive && !offline)
      void act(() => load(selectedSession.current || undefined));
  }, [act, load, offline, page, pageActive, settingsVersion]);

  const sessionId = session?.id;
  useEffect(() => {
    if (!sessionId || !pageActive) return;
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
  }, [sessionId, load, pageActive]);

  const refresh = useCallback(async () => {
    if (selectedSession.current) await load(selectedSession.current);
  }, [load]);
  const problem = session?.problems.find((item) => item.status === "assigned");
  const activeOperation = problem?.operations.find((operation) =>
    activeStatuses.includes(operation.status),
  );
  const active = Boolean(activeOperation);
  const disabled =
    blocked ||
    active ||
    offline ||
    Boolean(session && session.status !== "open");
  const hasResponseDraft = Boolean(
    text.trim() || reference.trim() || photoDraft,
  );
  const hasDraft =
    hasResponseDraft || Boolean((newSession || !session) && topic.trim());
  const changingSessionDisabled = blocked || active || offline || hasDraft;
  useEffect(() => {
    const restoreSession = () => {
      const requested = new URLSearchParams(window.location.hash.slice(1)).get(
        "tutor",
      );
      const target =
        requested && /^[a-f0-9-]{36}$/.test(requested) ? requested : "";
      if (target === selectedSession.current) return;
      if (changingSessionDisabled) {
        window.history.replaceState(
          null,
          "",
          `${window.location.pathname}${window.location.search}${selectedSession.current ? `#tutor=${selectedSession.current}` : ""}`,
        );
        setNavigationNotice(
          blocked
            ? "Finish or retry your pending request in Practice before switching sessions."
            : hasDraft
              ? "Send or clear your draft in Practice before switching sessions."
              : offline
                ? "Reconnect before opening another session. Your current work is still here."
                : "Wait for the tutor to finish before switching sessions.",
        );
        return;
      }
      setNavigationNotice("");
      setNewSession(false);
      if (target) void act(() => load(target));
      else {
        loadSequence.current += 1;
        selectedSession.current = "";
        setSession(null);
      }
    };
    window.addEventListener("popstate", restoreSession);
    return () => window.removeEventListener("popstate", restoreSession);
  }, [act, blocked, changingSessionDisabled, hasDraft, load, offline]);
  useEffect(() => {
    onBusyChange?.(blocked);
  }, [blocked, onBusyChange]);
  useEffect(() => {
    onDraftChange?.(hasResponseDraft || Boolean(topic.trim()));
  }, [hasResponseDraft, topic, onDraftChange]);
  useEffect(
    () => () => {
      onBusyChange?.(false);
      onDraftChange?.(false);
    },
    [onBusyChange, onDraftChange],
  );

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
      if (
        request.kind === "submission" &&
        (request.body as Schema<"SubmissionInput">).kind !== "hint"
      )
        setText("");
      if (
        request.kind === "activity" &&
        (request.body as Schema<"TutorActivityInput">).source ===
          "reference_text"
      )
        setReference("");
      if (created) {
        await load(created.id);
        setNewSession(false);
        setTopic("");
      } else if (selectedSession.current === request.sessionId) await refresh();
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
  const activity = async (
    nextSource: Source = source,
    nextDifficulty?: Difficulty,
  ) => {
    if (!session) return;
    const body: Schema<"TutorActivityInput"> = {
      source: nextSource,
      ...(nextDifficulty ? { difficulty: nextDifficulty } : {}),
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

  const sessionSettings = session?.status === "open" && (
    <details className="session-settings">
      <summary>Session settings</summary>
      <form
        key={`${session.id}-${session.initiative}-${session.difficulty}`}
        onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          void act(() =>
            command("settings", `/tutor/sessions/${session.id}/settings`, {
              initiative: data.get("initiative") as Initiative,
              difficulty: data.get("difficulty") as Difficulty,
            } satisfies Schema<"TutorSettingsInput">),
          );
        }}
      >
        <label>
          Tutor style for this session
          <select
            name="initiative"
            defaultValue={session.initiative}
            disabled={disabled}
          >
            <InitiativeOptions />
          </select>
        </label>
        <label>
          Activity difficulty
          <select
            name="difficulty"
            defaultValue={session.difficulty}
            disabled={disabled}
          >
            <DifficultyOptions />
          </select>
        </label>
        <button disabled={disabled}>Save session settings</button>
        <p className="fine">
          Difficulty changes future activities and guidance. Tutor style changes
          how much the tutor suggests next steps. Supplied homework is used for
          related practice only.
        </p>
      </form>
      <button
        disabled={disabled || hasResponseDraft}
        onClick={() =>
          void act(() =>
            command("finish", `/sessions/${session.id}/finish`, {}),
          )
        }
      >
        Finish session
      </button>
    </details>
  );
  const sessionControls = session?.status === "open" && (
    <>
      <details className="activity-source" open={!problem || undefined}>
        <summary>
          {problem
            ? "Use different practice material"
            : "Choose practice material"}
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
              onChange={(event) => setSource(event.target.value as Source)}
              disabled={disabled}
            >
              <option value="topic">My topic</option>
              <option value="reference_text">Pasted text or assignment</option>
              <option value="reference_photo">
                Photo of a passage or assignment
              </option>
            </select>
          </label>
          {source !== "topic" && (
            <p className="notice">
              The tutor uses your material to create different practice on the
              same concepts. It does not answer the supplied assignment. For
              reading practice, include the passage; the tutor cannot access a
              book from its title.
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
              Choose “Create practice activity”, then send a photo from your
              phone or upload one here. You will see its reading before the new
              practice.
            </p>
          )}
          <button
            className="primary"
            disabled={
              disabled ||
              Boolean(text.trim() || photoDraft) ||
              (source === "reference_text" && !reference.trim()) ||
              (source === "reference_photo" && !features?.photos_available)
            }
          >
            Create practice activity
          </button>
        </form>
        <ContextHelp topic="How is my reference used?">
          <p>
            A passage or assignment helps the tutor choose related concepts and
            a different activity. It cannot retrieve a book or webpage for you.
            Paste or photograph the part you want to study.
          </p>
        </ContextHelp>
      </details>
      {sessionSettings}
    </>
  );

  return (
    <section
      className="tutor"
      aria-label="AI tutor"
      aria-busy={working || active}
    >
      {navigationNotice && changingSessionDisabled && (
        <p role="status" className="notice">
          {navigationNotice}
        </p>
      )}
      <section
        hidden={page !== "history"}
        aria-labelledby="saved-sessions-heading"
      >
        <h2 id="saved-sessions-heading">Saved sessions</h2>
        <p>Open a saved session to review your work or keep practicing.</p>
        {hasDraft && (
          <p className="notice">
            You have an unsent draft in Practice. Send or clear it before
            opening a different session.
          </p>
        )}
        {blocked && (
          <p role="status">
            Finish or retry your pending request in Practice before opening
            another session.
          </p>
        )}
        {features && history.length === 0 && (
          <div className="card empty-state">
            <h3>No saved sessions yet</h3>
            <p>Your sessions will appear here after you start practicing.</p>
            <button onClick={() => onNavigate?.("practice")}>
              Go to Practice
            </button>
          </div>
        )}
        <div className="session-list">
          {history.map((item) => (
            <article className="card session-card" key={item.id}>
              <h3>{item.topic}</h3>
              <p className="fine">
                {item.status === "open" ? "In progress" : "Finished"} ·{" "}
                {item.problems.length}{" "}
                {item.problems.length === 1 ? "activity" : "activities"}
              </p>
              <button
                disabled={
                  item.id === session?.id ? blocked : changingSessionDisabled
                }
                onClick={() =>
                  void act(async () => {
                    if (item.id !== session?.id) await load(item.id);
                    setNewSession(false);
                    onNavigate?.("practice");
                  })
                }
              >
                {item.status === "open" ? "Continue session" : "Review session"}
              </button>
            </article>
          ))}
        </div>
      </section>
      <div hidden={page !== "practice"}>
        <div className="section-heading">
          <div>
            <h2>
              {newSession || !session
                ? "Start a practice session"
                : session.topic}
            </h2>
            {!session && (
              <p>
                Choose a topic. Then get an activity and send your work for
                feedback.
              </p>
            )}
          </div>
          {session && !newSession && (
            <button
              disabled={changingSessionDisabled}
              onClick={() => setNewSession(true)}
            >
              New session
            </button>
          )}
        </div>
        {!features && <p role="status">Checking tutor availability…</p>}
        {features?.tutoring_available && (
          <p className="fine">
            {features.text_processing === "mock"
              ? "Sample responses only. An actual AI model is needed for tutoring."
              : `Text processing: ${features.text_processing === "local_network" ? "your local network" : features.text_processing === "cloud" ? "cloud provider" : features.text_processing}.`}
          </p>
        )}
        {features && !features.tutoring_available && (
          <div className="notice" role="status">
            <h3>Tutoring is not available yet</h3>
            <p>{features.tutor_status}</p>
            <p>
              {isAdult
                ? "Use Settings to check the selected AI providers. For a demo installation, follow the private setup steps in Help."
                : "Ask the adult who manages this app to check its setup."}
            </p>
            <div className="actions">
              {isAdult && (
                <button onClick={() => onNavigate?.("settings")}>
                  Open Settings
                </button>
              )}
              <button onClick={() => onNavigate?.("help", "setup")}>
                Setup help
              </button>
            </div>
          </div>
        )}
        {(newSession || !session) && (
          <form
            className="card"
            onSubmit={(event) => {
              event.preventDefault();
              void act(() =>
                command("session", "/tutor/sessions", {
                  learner_id: learner,
                  topic,
                  initiative,
                  difficulty,
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
            <ContextHelp topic="What can I practice?">
              <p>
                Use any subject or question: fractions, persuasive writing,
                photosynthesis, or a passage you are reading. You can add
                reference material after starting the session.
              </p>
            </ContextHelp>
            <label>
              Activity difficulty
              <select
                value={difficulty}
                onChange={(event) =>
                  setDifficulty(event.target.value as Difficulty)
                }
                disabled={blocked}
              >
                <DifficultyOptions />
              </select>
            </label>
            <p className="fine">
              Choose Easier for foundational concepts or Harder for deeper,
              multi-step reasoning. You can change this during the session.
            </p>
            <details>
              <summary>Tutor options</summary>
              <label>
                Tutor style
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
              <p className="fine">
                Choose how much the tutor suggests next steps. You can change
                this during the session.
              </p>
            </details>
            <div className="actions">
              <button
                className="primary"
                disabled={
                  blocked ||
                  offline ||
                  !topic.trim() ||
                  !features?.tutoring_available
                }
              >
                Start session
              </button>
              {session && (
                <button
                  type="button"
                  disabled={blocked}
                  onClick={() => setNewSession(false)}
                >
                  Back to current session
                </button>
              )}
            </div>
          </form>
        )}
        {working && <BusyStatus message="Saving your request…" />}
        {pending && !working && (
          <div role="status" className="notice">
            <p>
              Your request may have reached the server. Retry it to check; this
              keeps the original request and avoids a duplicate.
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
          <div hidden={newSession}>
            {hasResponseDraft && (
              <p className="fine">
                Send or clear your draft before starting a different activity or
                session.
              </p>
            )}
            {session.status !== "open" && (
              <p className="notice">
                This session is finished. You can review it below or start a new
                session.
              </p>
            )}
            <div className="tutor-workspace">
              <article className="tutor-activity chat-column">
                {problem && (
                  <details className="activity-brief" open>
                    <summary>
                      <h3>
                        {problem.activity_state === "reference_capture"
                          ? "Reference material"
                          : "Current activity"}
                      </h3>
                    </summary>
                    <SafeText text={problem.problem_text} />
                    <p className="fine">
                      Saved automatically ·{" "}
                      {difficultyLabel(session.difficulty)} difficulty
                    </p>
                    {problem.concept_focus && (
                      <p className="fine">Focus: {problem.concept_focus}</p>
                    )}
                  </details>
                )}
                <TutorConversation
                  session={session}
                  offline={offline}
                  disabled={blocked}
                  active={pageActive && page === "practice" && !newSession}
                  act={act}
                  refresh={refresh}
                />
                <div className="tutor-response">
                  {active && (
                    <BusyStatus
                      message={
                        activeOperation?.status === "interpreting"
                          ? "Reading your photograph…"
                          : problem?.activity_state === "generating"
                            ? "Preparing your activity…"
                            : "Preparing tutor response…"
                      }
                    />
                  )}
                  {problem?.activity_state === "generating" && !active && (
                    <p role="status">
                      No activity is ready yet. Retry the failed request above,
                      or choose new practice material.
                    </p>
                  )}
                  {problem?.activity_state === "reference_capture" && (
                    <p>
                      Attach a photo of your reference material to create
                      related practice.
                    </p>
                  )}
                  {problem?.activity_state === "ready" && (
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
                          rows={2}
                          readOnly={disabled}
                          placeholder="Share your thinking, ask a question, or discuss a photo…"
                        />
                      </label>
                      <div className="composer-actions">
                        <button
                          type="button"
                          aria-expanded={attachmentsOpen}
                          aria-controls="tutor-attachments"
                          disabled={blocked}
                          onClick={() => setAttachmentsOpen(!attachmentsOpen)}
                        >
                          Attach photo
                        </button>
                        <details className="composer-menu">
                          <summary>Help</summary>
                          <div className="composer-options">
                            <button
                              type="button"
                              disabled={disabled}
                              onClick={() => void act(() => submit("hint", 1))}
                            >
                              Give me a hint
                            </button>
                            <button
                              type="button"
                              disabled={disabled}
                              onClick={() => void act(() => submit("hint", 2))}
                            >
                              Explain the concept
                            </button>
                            <button
                              type="button"
                              disabled={disabled}
                              onClick={() => void act(() => submit("hint", 3))}
                            >
                              Show a different example
                            </button>
                          </div>
                        </details>
                        <details className="composer-menu next-menu">
                          <summary>Next activity options</summary>
                          <div className="composer-options">
                            <button
                              type="button"
                              disabled={disabled || hasResponseDraft}
                              onClick={() => void act(() => activity("topic"))}
                            >
                              Next activity
                            </button>
                            <button
                              type="button"
                              disabled={disabled || hasResponseDraft}
                              onClick={() =>
                                void act(() =>
                                  activity("topic", "introductory"),
                                )
                              }
                            >
                              Easier next activity
                            </button>
                            <button
                              type="button"
                              disabled={disabled || hasResponseDraft}
                              onClick={() =>
                                void act(() => activity("topic", "challenge"))
                              }
                            >
                              Harder next activity
                            </button>
                          </div>
                        </details>
                        <button
                          className="primary send-message"
                          disabled={disabled || !text.trim()}
                        >
                          Send
                        </button>
                      </div>
                    </form>
                  )}
                  {problem && (
                    <div
                      id="tutor-attachments"
                      className="tutor-attachments"
                      hidden={
                        !attachmentsOpen &&
                        problem.activity_state !== "reference_capture" &&
                        !photoPending &&
                        !photoDraft
                      }
                    >
                      <p className="fine">{features?.photo_status}</p>
                      {(features?.photos_available ||
                        photoDraft ||
                        photoPending) && (
                        <>
                          <PhoneLink
                            key={`phone-${problem.id}-${problem.version}`}
                            problem={problem.id}
                            version={problem.version}
                            disabled={disabled || !features?.photos_available}
                            act={act}
                            onHelp={() => onNavigate?.("help", "phone")}
                          />
                          <PhotoInput
                            expanded
                            key={problem.id}
                            problem={problem.id}
                            version={problem.version}
                            disabled={
                              active ||
                              working ||
                              pending !== null ||
                              offline ||
                              !features?.photos_available ||
                              session.status !== "open"
                            }
                            onPendingChange={setPhotoPending}
                            onDraftChange={setPhotoDraft}
                            act={act}
                            onSaved={async () => {
                              await refresh();
                              setAttachmentsOpen(false);
                            }}
                            reference={
                              problem.activity_state === "reference_capture"
                            }
                          />
                        </>
                      )}
                    </div>
                  )}
                </div>
              </article>
              {session.status === "open" && (
                <aside className="tutor-sidebar" aria-label="Session tools">
                  <details open={!problem || undefined}>
                    <summary>Session &amp; material</summary>
                    {sessionControls}
                  </details>
                </aside>
              )}
            </div>
          </div>
        )}
        {features?.tutoring_available && (
          <ContextHelp topic="Where does my work go?">
            <p>
              {features.tutor_status} Text and references are processed by:{" "}
              {features.text_processing}.
            </p>
            <p>AI feedback can be mistaken and is not a verified grade.</p>
            <button onClick={() => onNavigate?.("help", "privacy")}>
              Privacy help
            </button>
          </ContextHelp>
        )}
      </div>
    </section>
  );
}
