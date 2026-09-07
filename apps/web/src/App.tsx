import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { api, newKey, setIdentity, type Schema } from "./client";
import { AdultPanel } from "./AdultPanel";
import { Practice } from "./Practice";
import { OfflinePractice } from "./OfflinePractice";
import { UpdateNotice } from "./UpdateNotice";

const Research = lazy(() => import("./Research"));

export function App() {
  const [identity, setSession] = useState<Schema<"SessionStatus"> | null>(null);
  const [error, setError] = useState("");
  const [offline, setOffline] = useState(!navigator.onLine);
  const [learner, setLearner] = useState("");
  const [pair, setPair] = useState<Schema<"PairPublic"> | null>(null);
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    const session = await api<Schema<"SessionStatus">>("/auth/session");
    setIdentity(session.csrf_token);
    setSession(session);
    setLearner(session.learner_id ?? "");
  }, []);
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
    let canceled = false;
    void api<Schema<"SessionStatus">>("/auth/session")
      .then((session) => {
        if (canceled) return;
        setIdentity(session.csrf_token);
        setSession(session);
        setLearner(session.learner_id ?? "");
      })
      .catch(() => {
        if (!canceled)
          setError(
            "The server is unavailable. Reconnect to access saved practice, or use public offline exercises.",
          );
      });
    return () => {
      canceled = true;
    };
  }, []);
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
        Skip to practice
      </a>
      <header className="masthead">
        <a href="/" className="wordmark">
          Math Practice Tutor
        </a>
        <span className="pill">One step at a time</span>
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
      <div id="workspace" aria-busy={busy}>
        {!identity?.authenticated ? (
          <section className="welcome">
            <p className="eyebrow">Small steps. Clear thinking.</p>
            <h1>Make room for a little math.</h1>
            <p className="lede">
              Work through a problem, learn from a mistake, and try again.
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
                    setIdentity(session.csrf_token);
                    setSession(session);
                  });
                }}
              >
                <h2>Adult sign in</h2>
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
                  Your administrator creates access on the server. No public
                  registration.
                </p>
              </form>
              <section className="card">
                <h2>Learner device</h2>
                <p>
                  Ask your adult to approve this browser for your learner alias.
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
              </section>
            </div>
          </section>
        ) : (
          <>
            {identity.role === "adult" && (
              <AdultPanel learner={learner} onLearner={setLearner} act={act} />
            )}
            {learner ? (
              <Practice
                key={learner}
                learner={learner}
                act={act}
                offline={offline}
              />
            ) : (
              <section className="card">
                <h2>Ready when you are</h2>
                <p>Create or select a learner to begin.</p>
              </section>
            )}
            <p className="fine">
              The adult who manages this deployment can review your saved
              practice. Photos expire within 24 hours; history defaults to 30
              days.
            </p>
          </>
        )}
      </div>
      <OfflinePractice />
      {identity?.role === "adult" && (
        <details>
          <summary>Optional browser model research</summary>
          <Suspense fallback={<p>Loading research controls…</p>}>
            <Research />
          </Suspense>
        </details>
      )}
      <footer>
        Exact mathematics. Room to revise.{" "}
        <span>Built-in help works without a model provider.</span>
      </footer>
    </main>
  );
}
