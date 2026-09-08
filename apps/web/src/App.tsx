import { useCallback, useEffect, useRef, useState } from "react";
import { api, onAuthenticationLost, setIdentity, type Schema } from "./client";
import { AdultPanel } from "./AdultPanel";
import { Tutor } from "./Tutor";
import { UpdateNotice } from "./UpdateNotice";
import { ContextHelp, HelpPage } from "./Help";
import { followPage, pageUrl, type Page, type Navigate } from "./navigation";
import { Setup } from "./Setup";
import { captureSetupAuthority, type SetupAuthority } from "./setup-authority";

const pageNames: Record<Page, string> = {
  practice: "Practice",
  history: "History",
  learners: "Learners",
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
  const [busy, setBusy] = useState(false);
  const [location, setLocation] = useState(readLocation);
  const [learners, setLearners] = useState<Schema<"LearnerPublic">[]>([]);
  const [settingsVersion, setSettingsVersion] = useState(0);
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
          : isAdult &&
              (location.page === "practice" || location.page === "history")
            ? "learners"
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
    document.title = `${authenticated || page === "help" ? pageNames[page] : setupRequired || checkingSetup ? "Create administrator account" : "Sign in"} · Shepherd Academy Universe`;
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
    setLearner((current) =>
      rows.some((row) => row.id === current) ? current : "",
    );
  }, []);
  const chooseLearner = (id: string) => setLearner(id);
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
        learnerSequence.current += 1;
        setLearners([]);
        window.history.replaceState(
          null,
          "",
          window.location.pathname + window.location.search,
        );
        setError("Your session ended. Sign in again.");
        void refresh().catch(() => {
          setError("Your session ended. Reconnect to sign in again.");
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
          <img src="/icon.svg" alt="" width={32} height={32} />
          Shepherd Academy Universe
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
            ? (["learners", "settings", "help"] as Page[])
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
                <p>Use your administrator or learner username and password.</p>
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
                    <h2>Account sign-in</h2>
                    <p>
                      Learner accounts open only that learner’s practice and
                      history.
                    </p>
                    <label>
                      Username
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
                      Learners: use the account your administrator created for
                      you.
                    </p>

                    <ContextHelp topic="Need an account or a password reset?">
                      <p>
                        Ask your administrator to reset a learner password in
                        Learners. The administrator account is created with the
                        private setup link printed by <code>make start</code>.
                        If an account already exists, only the person running
                        the app can reset its password with{" "}
                        <code>make admin</code> on that computer.
                      </p>
                      <button
                        type="button"
                        onClick={() => navigate("help", "setup")}
                      >
                        Setup instructions
                      </button>
                    </ContextHelp>
                  </form>
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
                          ? "Manage learner accounts, passwords, and signed-in browsers."
                          : "Choose the AI models that process your work."}
                  </p>
                </div>
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
            {learner && !isAdult && (
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
                />
              </div>
            )}
          </>
        )}
      </div>
      <footer>
        <span>Shepherd Academy Universe</span>
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
