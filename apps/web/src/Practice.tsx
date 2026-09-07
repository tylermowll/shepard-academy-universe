import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, newKey, type Schema } from "./client";
import { PhotoInput } from "./PhotoInput";
import { SafeText } from "./SafeText";

type Props = {
  learner: string;
  offline: boolean;
  act: (action: () => Promise<void>) => Promise<void>;
};
type PendingCommand = {
  key: string;
  path: string;
  kind: "session" | "problem" | "submission";
  body: Readonly<
    | Schema<"SessionInput">
    | Schema<"ProblemInput">
    | Schema<"SubmissionInput">
    | Record<string, never>
  >;
  ambiguous: boolean;
};
export function Practice({ learner, offline, act }: Props) {
  const [history, setHistory] = useState<Schema<"SessionSummary">[]>([]);
  const [session, setSession] = useState<Schema<"SessionPublic"> | null>(null);
  const [profiles, setProfiles] = useState<Schema<"ProfilePublic">[]>([]);
  const [features, setFeatures] = useState<Schema<"Features"> | null>(null);
  const [progress, setProgress] = useState<Schema<"ProgressPublic"> | null>(
    null,
  );
  const [text, setText] = useState("");
  const [workText, setWorkText] = useState("");
  const [working, setWorking] = useState(false);
  const [pending, setPending] = useState<PendingCommand | null>(null);
  const [photoPending, setPhotoPending] = useState(false);
  const pendingCommand = useRef<PendingCommand | null>(null);
  const blocked = working || pending !== null || photoPending;
  const mounted = useRef(true);
  const loadSequence = useRef(0);
  const selectedSession = useRef("");
  const load = useCallback(
    async (id?: string) => {
      if (!mounted.current) return;
      const sequence = ++loadSequence.current;
      if (id) selectedSession.current = id;
      const [h, p, g, f, loaded] = await Promise.all([
        api<Schema<"SessionSummary">[]>("/sessions"),
        api<Schema<"ProfilePublic">[]>("/tutor-profiles"),
        api<Schema<"ProgressPublic">>(`/learners/${learner}/progress`),
        api<Schema<"Features">>(`/learners/${learner}/features`),
        id
          ? api<Schema<"SessionPublic">>(`/sessions/${id}`)
          : Promise.resolve(null),
      ]);
      if (!mounted.current || sequence !== loadSequence.current) return;
      setHistory(h.filter((s) => s.learner_id === learner));
      setProfiles(p);
      setProgress(g);
      setFeatures(f);
      if (loaded) {
        if (loaded.learner_id === learner) {
          setSession(loaded);
          window.location.hash = loaded.id;
        } else {
          selectedSession.current = "";
          setSession(null);
          window.history.replaceState(
            null,
            "",
            window.location.pathname + window.location.search,
          );
        }
      }
    },
    [learner],
  );
  useEffect(() => {
    mounted.current = true;
    const id = window.location.hash.slice(1);
    void act(() => load(/^[a-f0-9-]{36}$/.test(id) ? id : undefined));
    return () => {
      mounted.current = false;
      loadSequence.current += 1;
    };
  }, [act, load]);
  const sessionId = session?.id;
  useEffect(() => {
    if (!sessionId) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible" && navigator.onLine)
        void load(selectedSession.current).catch(() => {});
    }, 2500);
    return () => window.clearInterval(timer);
  }, [sessionId, load]);
  const refresh = async () => {
    if (selectedSession.current) await load(selectedSession.current);
  };
  const problem = session?.problems.find((p) => p.status === "assigned");
  const active =
    problem?.operations.some((o) =>
      [
        "queued",
        "checking",
        "tutoring",
        "interpreting",
        "awaiting_confirmation",
      ].includes(o.status),
    ) ?? false;
  const sendCommand = async (request: PendingCommand) => {
    setWorking(true);
    try {
      let created: Schema<"SessionPublic"> | undefined;
      try {
        if (request.kind === "session")
          created = await api<Schema<"SessionPublic">>(
            request.path,
            "POST",
            request.body,
            request.key,
          );
        else await api(request.path, "POST", request.body, request.key);
      } catch (cause) {
        // A rejection of a retry cannot disprove acceptance of an earlier call.
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
      setPending(null);
      if (request.kind === "submission") {
        setText("");
        setWorkText("");
      }
      if (created && mounted.current && created.learner_id === learner)
        await load(created.id);
      else await refresh();
    } finally {
      setWorking(false);
    }
  };
  const startCommand = async (
    command: Omit<PendingCommand, "key" | "ambiguous">,
  ) => {
    if (pendingCommand.current || photoPending) return;
    const request = { ...command, key: newKey(), ambiguous: false };
    pendingCommand.current = request;
    setPending(request);
    await sendCommand(request);
  };
  const submit = async (kind: "answer" | "question" | "hint", help = 0) => {
    if (!problem) return;
    await startCommand({
      path: `/problems/${problem.id}/submissions`,
      kind: "submission",
      body: {
        version: problem.version,
        kind,
        text: kind === "hint" ? "" : text,
        help_level: help,
        work_text: kind === "answer" ? workText : "",
      },
    });
  };
  const profile = session?.profile;
  const presentation = profile?.presentation;
  const scale =
    presentation &&
    typeof presentation === "object" &&
    "font_scale" in presentation
      ? Number(presentation.font_scale)
      : 1;
  return (
    <section
      className={
        presentation &&
        typeof presentation === "object" &&
        "compact_explanations" in presentation &&
        presentation.compact_explanations
          ? "practice compact"
          : "practice"
      }
      style={{
        fontSize: `${Number.isFinite(scale) ? Math.min(1.5, Math.max(1, scale)) : 1}em`,
      }}
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">Your practice</p>
          <h2>A little progress, one problem at a time.</h2>
        </div>
        <label>
          Saved sessions
          <select
            value={session?.id ?? ""}
            disabled={blocked}
            onChange={(e) => {
              const id = e.target.value;
              if (id)
                void act(async () => {
                  await load(id);
                });
            }}
          >
            <option value="">Choose a session</option>
            {history.map((s) => (
              <option key={s.id} value={s.id}>
                {new Date(s.created_at).toLocaleString()} · {s.status}
              </option>
            ))}
          </select>
        </label>
      </div>
      <form
        className="start-session"
        onSubmit={(e) => {
          e.preventDefault();
          const data = new FormData(e.currentTarget);
          const profileId = data.get("profile");
          void act(() =>
            startCommand({
              path: "/sessions",
              kind: "session",
              body: {
                learner_id: learner,
                profile_version_id:
                  typeof profileId === "string" && profileId ? profileId : null,
              },
            }),
          );
        }}
      >
        <label>
          Tutor profile
          <select name="profile" disabled={blocked}>
            <option value="">Built-in guided practice</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.settings.name} · v{p.version}
              </option>
            ))}
          </select>
        </label>
        <button className="primary" disabled={offline || blocked}>
          Start a new session
        </button>
      </form>
      {pending && !working && (
        <div role="status" className="notice">
          <p>
            The server has not acknowledged this request. Retry it to recover
            its result before continuing.
          </p>
          <button
            disabled={offline}
            onClick={() => void act(() => sendCommand(pending))}
          >
            {pending.kind === "session"
              ? "Retry session creation"
              : pending.kind === "problem"
                ? "Retry problem assignment"
                : "Retry saved submission"}
          </button>
        </div>
      )}
      {session && (
        <>
          <div className="actions">
            <span className="pill">
              {typeof profile?.name === "string"
                ? profile.name
                : "Guided practice"}{" "}
              · {session.status}
            </span>
            {session.status === "open" && (
              <button
                disabled={active || offline || blocked}
                onClick={() =>
                  void act(async () => {
                    await api(`/sessions/${session.id}/finish`, "POST");
                    await refresh();
                  })
                }
              >
                Finish session
              </button>
            )}
          </div>
          {!problem &&
            session.status === "open" &&
            session.problems.length >=
              session.profile.session_problem_limit && (
              <p role="status">
                You have reached this session’s problem limit. Finish this
                session to record its completion.
              </p>
            )}
          {!problem &&
            session.status === "open" &&
            session.problems.length < session.profile.session_problem_limit && (
              <form
                className="card"
                onSubmit={(e) => {
                  e.preventDefault();
                  const data = new FormData(e.currentTarget);
                  const skill = data.get("skill");
                  void act(() =>
                    startCommand({
                      path: `/sessions/${session.id}/problems`,
                      kind: "problem",
                      body: {
                        skill_id:
                          typeof skill === "string" ? skill : "fractions.add",
                      },
                    }),
                  );
                }}
              >
                <h3>Choose the next problem</h3>
                <label>
                  Skill
                  <select name="skill" disabled={blocked}>
                    {(Array.isArray(profile?.topics)
                      ? profile.topics
                      : ["fractions.add"]
                    ).map((topic) => (
                      <option key={String(topic)} value={String(topic)}>
                        {String(topic).replaceAll(".", " · ")}
                      </option>
                    ))}
                  </select>
                </label>
                <button className="primary" disabled={offline || blocked}>
                  Assign next problem
                </button>
                {features?.external_problems && (
                  <button
                    type="button"
                    disabled={offline || blocked}
                    onClick={() =>
                      void act(() =>
                        startCommand({
                          path: `/sessions/${session.id}/external-problem`,
                          kind: "problem",
                          body: {},
                        }),
                      )
                    }
                  >
                    Start external photo problem (unverified)
                  </button>
                )}
              </form>
            )}
          {problem && (
            <article className="problem card">
              <div className="section-heading">
                <span className="eyebrow">
                  {problem.skill_id.replaceAll(".", " · ")}
                </span>
                <span>Help used: level {problem.assistance_level}</span>
              </div>
              <h3 className="math-problem">{problem.problem_text}</h3>
              <p className="fine">
                Give your final answer as an integer, fraction, or decimal.
                Simplest form is checked separately.
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void act(() => submit("answer"));
                }}
              >
                <label>
                  Your answer or question
                  <textarea
                    value={text}
                    readOnly={blocked}
                    onChange={(e) => setText(e.target.value)}
                    maxLength={4000}
                    rows={2}
                    autoComplete="off"
                  />
                </label>
                <label>
                  Steps (optional; reasoning is not checked)
                  <textarea
                    value={workText}
                    readOnly={blocked}
                    onChange={(event) => setWorkText(event.target.value)}
                    maxLength={4000}
                    rows={2}
                  />
                </label>
                <div className="actions">
                  <button
                    className="primary"
                    disabled={
                      active || working || offline || blocked || !text.trim()
                    }
                  >
                    Check answer
                  </button>
                  <button
                    type="button"
                    disabled={
                      active || working || offline || blocked || !text.trim()
                    }
                    onClick={() => void act(() => submit("question", 2))}
                  >
                    Ask tutor
                  </button>
                </div>
              </form>
              <div className="actions">
                {([1, 2, 3, 4] as const).map((level) => (
                  <button
                    key={level}
                    disabled={active || working || offline || blocked}
                    onClick={() => void act(() => submit("hint", level))}
                  >
                    {
                      [
                        "",
                        "Hint",
                        "Direct explanation",
                        "Different example",
                        "Full solution",
                      ][level]
                    }
                  </button>
                ))}
                <button
                  disabled={active || offline || blocked}
                  onClick={() =>
                    void act(async () => {
                      await api(`/problems/${problem.id}/skip`, "POST", {
                        version: problem.version,
                      });
                      await refresh();
                    })
                  }
                >
                  Skip problem
                </button>
              </div>
              <p className="fine">{features?.photo_status}</p>
              {features?.photos_available && (
                <PhotoInput
                  key={problem.id}
                  problem={problem.id}
                  version={problem.version}
                  disabled={active || working || pending !== null || offline}
                  onPendingChange={setPhotoPending}
                  act={act}
                  onSaved={refresh}
                />
              )}
            </article>
          )}
          <section aria-labelledby="history-heading">
            <h3 id="history-heading">Session history</h3>
            {session.problems.length === 0 && <p>No problems assigned yet.</p>}
            {session.problems.map((p) => (
              <article className="history card" key={p.id}>
                <h4>
                  {p.problem_text} <span className="pill">{p.status}</span>
                </h4>
                {p.operations.map((op) => (
                  <section key={op.id} className="operation">
                    <p>
                      <strong>{op.kind}</strong> · {op.status}
                      {op.text && (
                        <>
                          {" "}
                          · Your entry:{" "}
                          <span className="user-text">{op.text}</span>
                        </>
                      )}
                    </p>
                    {op.work_text && (
                      <p className="user-text">Your steps: {op.work_text}</p>
                    )}
                    {op.safe_error && (
                      <p role="status" className="error">
                        {op.safe_error}
                      </p>
                    )}
                    {op.verdict && (
                      <p className={`verdict ${op.verdict.answer_status}`}>
                        Final answer:{" "}
                        <strong>{op.verdict.answer_status}</strong> · Format:{" "}
                        {op.verdict.format_status.replaceAll("_", " ")} ·
                        Reasoning:{" "}
                        {op.verdict.reasoning_status.replaceAll("_", " ")}
                      </p>
                    )}
                    {op.message && (
                      <>
                        <SafeText text={op.message} />
                        <p className="fine">
                          {op.source} · Assistance level {op.assistance_level}
                        </p>
                      </>
                    )}
                    {op.interpretation !== null &&
                      op.interpretation !== undefined && (
                        <p>
                          Transcription:{" "}
                          {op.interpretation ||
                            "Please enter what your work says."}
                        </p>
                      )}
                    {(op.ambiguities ?? []).map((a, i) => (
                      <p key={i} className="notice">
                        {a}
                      </p>
                    ))}
                    {op.status === "awaiting_confirmation" && (
                      <form
                        onSubmit={(e) => {
                          e.preventDefault();
                          const data = new FormData(e.currentTarget);
                          void act(async () => {
                            await api(
                              `/submissions/${op.id}/confirm-interpretation`,
                              "POST",
                              {
                                version: op.interpretation_version,
                                transcription: data.get("transcription"),
                                final_answer: data.get("final_answer") || null,
                              },
                            );
                            await refresh();
                          });
                        }}
                      >
                        <label>
                          Confirm or edit the transcription
                          <textarea
                            name="transcription"
                            required
                            maxLength={4000}
                            defaultValue={op.interpretation ?? ""}
                          />
                        </label>
                        {op.kind === "answer" && (
                          <label>
                            Final answer from this work
                            <input
                              name="final_answer"
                              maxLength={128}
                              defaultValue={
                                op.interpreted_final_answer ??
                                ((op.interpretation?.length ?? 0) <= 128
                                  ? (op.interpretation ?? "")
                                  : "")
                              }
                            />
                          </label>
                        )}
                        <button
                          className="primary"
                          disabled={offline || blocked}
                        >
                          Confirm this interpretation
                        </button>
                      </form>
                    )}
                    {op.status === "failed" && (
                      <button
                        disabled={offline || blocked}
                        onClick={() =>
                          void act(async () => {
                            await api(`/operations/${op.id}/retry`, "POST");
                            await refresh();
                          })
                        }
                      >
                        Retry operation
                      </button>
                    )}
                    {!["completed", "canceled"].includes(op.status) && (
                      <button
                        disabled={offline || blocked}
                        onClick={() =>
                          void act(async () => {
                            await api(`/operations/${op.id}/cancel`, "POST");
                            await refresh();
                          })
                        }
                      >
                        Cancel operation
                      </button>
                    )}
                  </section>
                ))}
              </article>
            ))}
          </section>
        </>
      )}
      {progress && (
        <aside className="progress card">
          <h3>Recorded progress</h3>
          <div className="stats">
            <div>
              <strong>{progress.correct_without_help}</strong>
              <span>Correct without help</span>
            </div>
            <div>
              <strong>{progress.correct_with_help}</strong>
              <span>Correct with help</span>
            </div>
            <div>
              <strong>{progress.incorrect}</strong>
              <span>Incorrect answers</span>
            </div>
          </div>
          <p className="fine">{progress.note}</p>
        </aside>
      )}
    </section>
  );
}
