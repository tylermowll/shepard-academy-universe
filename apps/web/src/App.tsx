import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  api,
  newKey,
  onAuthenticationLost,
  setIdentity,
  type Schema,
} from "./client";
import { AdultPanel } from "./AdultPanel";
import { Tutor } from "./Tutor";
import { UpdateNotice } from "./UpdateNotice";
import { ContextHelp, HelpPage } from "./Help";
import { followPage, pageUrl, type Page, type Navigate } from "./navigation";
import { Setup } from "./Setup";
import { captureSetupAuthority, type SetupAuthority } from "./setup-authority";

const Research = lazy(() => import("./Research"));
const pageNames: Record<Page, string> = {
  practice: "Practice",
  history: "History",
  learners: "Learners & devices",
  settings: "Settings",
  help: "Help",
};
function readLocation() {
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("page") ?? "practice";
  return {
    page: Object.hasOwn(pageNames, requested)
      ? (requested as Page)
      : ("practice" as Page),
    help: params.get("help") ?? "practice",
  };
}

export function App({ setupAuthority }: { setupAuthority?: SetupAuthority }) {
  const setupHolder = useRef(setupAuthority ?? { token: "" });
  const [setupToken, setSetupToken] = useState(setupAuthority?.token ?? "");
  const clearSetupToken = useCallback(() => {
    setupHolder.current.token = "";
    setSetupToken("");
  }, []);
  const [identity, setSession] = useState<Schema<"SessionStatus"> | null>(null);
  const [error, setError] = useState("");
  const [offline, setOffline] = useState(!navigator.onLine);
  const [learner, setLearner] = useState("");
  const [pair, setPair] = useState<Schema<"PairPublic"> | null>(null);
  const [busy, setBusy] = useState(false);
  const [location, setLocation] = useState(readLocation);
  const [learners, setLearners] = useState<Schema<"LearnerPublic">[]>([]);
  const [learnersLoaded, setLearnersLoaded] = useState(false);
  const [settingsVersion, setSettingsVersion] = useState(0);
  const [researchOpen, setResearchOpen] = useState(false);
  const [tutorBusy, setTutorBusy] = useState(false);
  const [tutorDraft, setTutorDraft] = useState(false);
  const learnerSequence = useRef(0);
  const workspace = useRef<HTMLDivElement>(null);
  const scrollToTop = useRef(false);
  const navigate: Navigate = useCallback((page, help) => {
    scrollToTop.current = true;
    window.history.pushState(null, "", pageUrl(page, help));
    setLocation(readLocation());
  }, []);
  const isAdult = identity?.authenticated === true && identity.role === "adult";
  const authenticated = identity?.authenticated === true;
  const setupRequired = !authenticated && identity?.setup_required === true;
  const checkingSetup = !identity && !!setupToken;
  const page: Page =
    location.page === "help"
      ? "help"
      : !authenticated
        ? "practice"
        : !isAdult &&
            (location.page === "settings" || location.page === "learners")
          ? "practice"
          : location.page;
  const tutorVisible = page === "practice" || page === "history";
  useEffect(() => {
    const changed = () => {
      const authority = captureSetupAuthority();
      if (
        authority.token &&
        !authenticated &&
        (!identity || identity.setup_required)
      ) {
        setupHolder.current.token = authority.token;
        setSetupToken(authority.token);
      }
      setLocation(readLocation());
    };
    window.addEventListener("popstate", changed);
    window.addEventListener("hashchange", changed);
    return () => {
      window.removeEventListener("popstate", changed);
      window.removeEventListener("hashchange", changed);
    };
  }, [authenticated, identity]);
  useEffect(() => {
    document.title = `${authenticated || page === "help" ? pageNames[page] : setupRequired || checkingSetup ? "Create administrator account" : "Sign in"} · Shepard Academy Universe`;
    workspace.current
      ?.querySelector<HTMLElement>("h1")
      ?.focus({ preventScroll: true });
    if (scrollToTop.current) {
      window.scrollTo({ top: 0, left: 0, behavior: "instant" });
      scrollToTop.current = false;
    }
  }, [page, location, authenticated, setupRequired, checkingSetup]);
  const refreshLearners = useCallback(async () => {
    const sequence = ++learnerSequence.current;
    const rows = await api<Schema<"LearnerPublic">[]>("/admin/learners");
    if (sequence !== learnerSequence.current) return;
    setLearners(rows);
    setLearnersLoaded(true);
    setLearner((current) =>
      rows.some((row) => row.id === current) ? current : "",
    );
  }, []);
  const chooseLearner = (id: string) => {
    if (id === learner || tutorBusy) return;
    if (
      tutorDraft &&
      !window.confirm(
        "Switch learners and discard the unsent work in this tab? Submitted work is saved.",
      )
    )
      return;
    if (learner && learner !== id)
      window.history.replaceState(
        null,
        "",
        window.location.pathname + window.location.search,
      );
    setLearner(id);
  };
  const refresh = useCallback(async () => {
    const session = await api<Schema<"SessionStatus">>("/auth/session");
    if (session.authenticated || !session.setup_required) clearSetupToken();
    setIdentity(session.csrf_token, session.authenticated);
    setSession(session);
    setLearner((current) =>
      session.role === "adult" ? current : (session.learner_id ?? ""),
    );
    if (session.authenticated && session.role === "adult")
      await refreshLearners();
  }, [refreshLearners, clearSetupToken]);
  const setupComplete = useCallback(
    (session: Schema<"SessionStatus">) => {
      clearSetupToken();
      setIdentity(session.csrf_token, session.authenticated);
      setSession(session);
      setLearner(session.learner_id ?? "");
      navigate("settings");
      void refresh().catch(() => {
        setError(
          "Your account was created, but settings could not be refreshed. Reconnect to continue.",
        );
      });
    },
    [clearSetupToken, navigate, refresh],
  );
  const setupAlreadyClaimed = useCallback(() => {
    clearSetupToken();
    setSession((current) =>
      current ? { ...current, setup_required: false } : current,
    );
    void refresh().catch(() => {
      setError(
        "An administrator account already exists. Reconnect, then sign in with that account.",
      );
    });
  }, [clearSetupToken, refresh]);
  useEffect(
    () =>
      onAuthenticationLost(() => {
        clearSetupToken();
        setSession(null);
        setLearner("");
        setPair(null);
        learnerSequence.current += 1;
        setLearners([]);
        setLearnersLoaded(false);
        setResearchOpen(false);
        window.history.replaceState(
          null,
          "",
          window.location.pathname + window.location.search,
        );
        setError("Your session ended. Sign in or pair this device again.");
        void refresh().catch(() => {
          setError(
            "Your session ended. Reconnect to sign in or pair this device again.",
          );
        });
      }),
    [refresh, clearSetupToken],
  );
  const act = useCallback(async (action: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Connection lost. Reconnect to recover your saved work.",
      );
    } finally {
      setBusy(false);
    }
  }, []);
  useEffect(() => {
    if (!isAdult) return;
    let canceled = false;
    void refreshLearners().catch((cause: unknown) => {
      if (!canceled)
        setError(
          cause instanceof Error
            ? cause.message
            : "Could not load learners. Reconnect to try again.",
        );
    });
    return () => {
      canceled = true;
      learnerSequence.current += 1;
    };
  }, [isAdult, refreshLearners]);
  useEffect(() => {
    let canceled = false;
    void api<Schema<"SessionStatus">>("/auth/session")
      .then((session) => {
        if (canceled) return;
        if (session.authenticated || !session.setup_required) clearSetupToken();
        setIdentity(session.csrf_token, session.authenticated);
        setSession(session);
        setLearner(session.learner_id ?? "");
      })
      .catch(() => {
        if (!canceled)
          setError(
            "The server is unavailable. Reconnect to access your saved tutoring sessions.",
          );
      });
    return () => {
      canceled = true;
    };
  }, [clearSetupToken]);
  useEffect(() => {
    const online = () => setOffline(false);
    const lost = () => setOffline(true);
    window.addEventListener("online", online);
    window.addEventListener("offline", lost);
    return () => {
      window.removeEventListener("online", online);
      window.removeEventListener("offline", lost);
    };
  }, []);
  useEffect(() => {
    if (!pair || identity?.authenticated) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      void api<Schema<"PairPublic">>(`/pairing/requests/${pair.id}`)
        .then(async (result) => {
          if (result.approved) {
            await api(`/pairing/requests/${pair.id}/claim`, "POST");
            setPair(null);
            await refresh();
          }
        })
        .catch((cause) => {
          setPair(null);
          setError(cause instanceof Error ? cause.message : "Pairing expired.");
        });
    }, 2500);
    return () => window.clearInterval(timer);
  }, [pair, identity?.authenticated, refresh]);
  return (
    <main>
      <a className="skip-link" href="#workspace">
        Skip to page content
      </a>
      <header className="masthead">
        <a
          href={pageUrl("practice")}
          onClick={(event) => followPage(event, navigate, "practice")}
          className="wordmark"
        >
          Shepard Academy Universe
        </a>
        {identity?.authenticated && (
          <button
            onClick={() =>
              void act(async () => {
                await api("/auth/logout", "POST");
                setIdentity("");
                window.location.replace("/");
              })
            }
          >
            Sign out
          </button>
        )}
      </header>
      <nav className="page-tabs" aria-label="Main navigation">
        {(authenticated
          ? isAdult
            ? (Object.keys(pageNames) as Page[])
            : (["practice", "history", "help"] as Page[])
          : (["practice", "help"] as Page[])
        ).map((item) => (
          <a
            key={item}
            href={pageUrl(item)}
            aria-current={page === item ? "page" : undefined}
            onClick={(event) => followPage(event, navigate, item)}
          >
            {!authenticated && item === "practice"
              ? setupRequired || checkingSetup
                ? "Set up account"
                : "Sign in"
              : pageNames[item]}
          </a>
        ))}
      </nav>
      <UpdateNotice />
      {offline && (
        <p role="status" className="notice">
          You are offline. Server tutoring and uploads are unavailable. Saved
          operations continue on the server.
        </p>
      )}
      {error && (
        <div role="alert" className="error">
          {error} <button onClick={() => void act(refresh)}>Reconnect</button>
        </div>
      )}
      <div id="workspace" ref={workspace} tabIndex={-1} aria-busy={busy}>
        {page === "help" && (
          <HelpPage topic={location.help} onNavigate={navigate} />
        )}
        {!authenticated && (
          <div hidden={page === "help"}>
            {setupRequired ? (
              <Setup
                token={setupToken}
                onClearToken={clearSetupToken}
                onComplete={setupComplete}
                onExistingAccount={setupAlreadyClaimed}
                onNavigate={navigate}
              />
            ) : checkingSetup ? (
              <section className="welcome">
                <h1 tabIndex={-1}>Create administrator account</h1>
                <p role="status">Checking account setup…</p>
              </section>
            ) : (
              <section className="welcome">
                <h1 tabIndex={-1}>Sign in</h1>
                <p>
                  Sign in as an adult, or connect this browser to a learner.
                </p>
                <div className="grid">
                  <form
                    className="card"
                    onSubmit={(event) => {
                      event.preventDefault();
                      const data = new FormData(event.currentTarget);
                      void act(async () => {
                        const session = await api<Schema<"SessionStatus">>(
                          "/auth/login",
                          "POST",
                          {
                            login_name: data.get("login"),
                            password: data.get("password"),
                          },
                        );
                        clearSetupToken();
                        setIdentity(session.csrf_token, session.authenticated);
                        setSession(session);
                        setLearner(session.learner_id ?? "");
                      });
                    }}
                  >
                    <h2>Adult sign in</h2>
                    <p>For parents and adults who want to study.</p>
                    <label>
                      Login name
                      <input
                        name="login"
                        autoComplete="username"
                        required
                        maxLength={64}
                      />
                    </label>
                    <label>
                      Password
                      <input
                        name="password"
                        type="password"
                        autoComplete="current-password"
                        required
                        maxLength={256}
                      />
                    </label>
                    <button className="primary" disabled={busy || !identity}>
                      Sign in
                    </button>
                    <p className="fine">
                      Use the account created when this app was set up.
                    </p>
                    <ContextHelp topic="Can I manage the app and study too?">
                      <p>
                        Yes. Add yourself as a learner, then select your profile
                        in Practice. Use the same adult sign-in for both.
                      </p>
                      <button
                        type="button"
                        onClick={() => navigate("help", "accounts")}
                      >
                        Accounts and learners
                      </button>
                    </ContextHelp>
                    <ContextHelp topic="Need an account or a password reset?">
                      <p>
                        The first account is created with the private setup link
                        printed by <code>make start</code>. If an account
                        already exists, only the person running the app can
                        reset its password with <code>make admin</code> on that
                        computer.
                      </p>
                      <button
                        type="button"
                        onClick={() => navigate("help", "setup")}
                      >
                        Setup instructions
                      </button>
                    </ContextHelp>
                  </form>
                  <section className="card">
                    <h2>Connect a learner</h2>
                    <p>
                      Request access here, then ask an adult to approve it on
                      their signed-in computer.
                    </p>
                    {pair ? (
                      <>
                        <label>
                          Pairing request ID
                          <input readOnly value={pair.id} />
                        </label>
                        <p role="status">
                          Waiting for approval. Expires at{" "}
                          {new Date(pair.expires_at).toLocaleTimeString()}.
                        </p>
                        <p>
                          On the adult’s computer: open{" "}
                          <strong>Learners & devices</strong>, select your
                          learner, paste this ID, and choose{" "}
                          <strong>Approve device</strong>.
                        </p>
                      </>
                    ) : (
                      <button
                        disabled={busy || !identity}
                        onClick={() =>
                          void act(async () =>
                            setPair(
                              await api<Schema<"PairPublic">>(
                                "/pairing/requests",
                                "POST",
                                {},
                                newKey(),
                              ),
                            ),
                          )
                        }
                      >
                        Pair this device
                      </button>
                    )}
                    <ContextHelp topic="Only using your phone to take a photo?">
                      <p>
                        Use Take photo with phone inside a practice activity on
                        the computer. Scan that QR code; you do not need to pair
                        or sign in for a photo.
                      </p>
                      <button
                        type="button"
                        onClick={() => navigate("help", "phone")}
                      >
                        Phone setup
                      </button>
                    </ContextHelp>
                  </section>
                </div>
              </section>
            )}
          </div>
        )}
        {authenticated && (
          <>
            {page !== "help" && (
              <div className="page-heading">
                <div>
                  <h1 tabIndex={-1}>{pageNames[page]}</h1>
                  <p>
                    {page === "practice"
                      ? "Choose a topic and work through an activity."
                      : page === "history"
                        ? "Review or continue a saved session."
                        : page === "learners"
                          ? "Add learners and connect their browsers."
                          : "Choose the AI models that process your work."}
                  </p>
                </div>
                {isAdult && (tutorVisible || page === "learners") && (
                  <label className="learner-selector">
                    Learner
                    <select
                      value={learner}
                      disabled={tutorBusy}
                      onChange={(event) => chooseLearner(event.target.value)}
                    >
                      <option value="">
                        {learnersLoaded
                          ? "Select a learner"
                          : "Loading learners…"}
                      </option>
                      {learners.map((row) => (
                        <option key={row.id} value={row.id}>
                          {row.alias}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
            )}
            {isAdult && (page === "learners" || page === "settings") && (
              <AdultPanel
                key={page}
                learner={learner}
                onLearner={chooseLearner}
                learners={learners}
                onRefresh={refreshLearners}
                page={page}
                onNavigate={navigate}
                onProvidersChanged={() =>
                  setSettingsVersion((version) => version + 1)
                }
                act={act}
              />
            )}
            {learner && (
              <div hidden={!tutorVisible}>
                <Tutor
                  key={learner}
                  learner={learner}
                  act={act}
                  offline={offline}
                  page={page === "history" ? "history" : "practice"}
                  active={tutorVisible}
                  isAdult={isAdult}
                  onNavigate={navigate}
                  settingsVersion={settingsVersion}
                  onBusyChange={setTutorBusy}
                  onDraftChange={setTutorDraft}
                />
              </div>
            )}
            {!learner && tutorVisible && (
              <section className="card empty-state">
                <h2>
                  {learners.length
                    ? "Who is practicing?"
                    : "Add your first learner"}
                </h2>
                <p>
                  {learners.length
                    ? "Select a learner above to see their practice and saved sessions."
                    : "Create a profile for yourself or your child. Each person gets their own practice history; a nickname is enough."}
                </p>
                {isAdult && (
                  <button
                    className="primary"
                    onClick={() => navigate("learners")}
                  >
                    {learners.length ? "Manage learners" : "Add a learner"}
                  </button>
                )}
                <ContextHelp topic="What happens next?">
                  <p>
                    Choose a topic, get an activity, and submit your response.
                    You can type or send a photo. For actual feedback, an adult
                    must connect a model in Settings.
                  </p>
                  <button onClick={() => navigate("help", "practice")}>
                    Practice guide
                  </button>
                </ContextHelp>
              </section>
            )}
            {isAdult && (
              <div hidden={page !== "settings"}>
                <details
                  onToggle={(event) => {
                    if (event.currentTarget.open) setResearchOpen(true);
                  }}
                >
                  <summary>Advanced: browser model experiment</summary>
                  <p>
                    A separate text-only experiment. It is not needed for
                    tutoring or phone photos.
                  </p>
                  {researchOpen && (
                    <Suspense fallback={<p>Loading experiment…</p>}>
                      <Research />
                    </Suspense>
                  )}
                </details>
              </div>
            )}
          </>
        )}
      </div>
      <footer>
        <span>Shepard Academy Universe</span>
        <a
          href={pageUrl("help", "privacy")}
          onClick={(event) => followPage(event, navigate, "help", "privacy")}
        >
          Saved work & privacy
        </a>
      </footer>
    </main>
  );
}
