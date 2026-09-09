import { useEffect, useRef, useState } from "react";
import { api, ApiError, setIdentity, type Schema } from "./client";
import { ContextHelp } from "./Help";
import type { Navigate } from "./navigation";

const setupErrors: Record<string, string> = {
  setup_link_invalid:
    "This setup link is invalid or has expired. Open a new link from the app’s terminal.",
  setup_unavailable:
    "Account setup is not available with this link. Open a new link from the app’s terminal.",
  setup_session_expired:
    "Setup permission has ended. Open a new setup link from the app’s terminal.",
  setup_claimed:
    "An administrator account already exists. Sign in with that account.",
  password_mismatch:
    "The passwords do not match. Enter the same password in both fields.",
  invalid_credentials:
    "Check the login name and password requirements, then try again.",
  setup_rate_limited:
    "Too many setup attempts. Wait a few minutes, then try again.",
};

export function Setup({
  token,
  onClearToken,
  onComplete,
  onExistingAccount,
  onNavigate,
}: {
  token: string;
  onClearToken: () => void;
  onComplete: (session: Schema<"SessionStatus">) => void;
  onExistingAccount: () => void;
  onNavigate: Navigate;
}) {
  const [status, setStatus] = useState<Schema<"SetupStatus"> | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [loadFailed, setLoadFailed] = useState(false);
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const setupCheck = useRef<{
    key: string;
    result: Promise<Schema<"SetupStatus">>;
  } | null>(null);
  const [fields, setFields] = useState({
    login: "",
    password: "",
    confirmation: "",
  });

  useEffect(() => {
    let canceled = false;
    const key = `${loadAttempt}:${token}`;
    if (setupCheck.current?.key !== key) {
      setupCheck.current = {
        key,
        result: api<Schema<"SetupStatus">>("/auth/setup").then((current) =>
          token && current.required && !current.available
            ? api<Schema<"SetupStatus">>("/auth/setup/session", "POST", {
                setup_token: token,
              } satisfies Schema<"SetupSessionRequest">)
            : current,
        ),
      };
    }
    void setupCheck.current.result
      .then((result) => {
        if (canceled) return;
        setStatus(result);
        setLoadFailed(false);
        if (token) setError("");
        if (!result.required) onExistingAccount();
        else if (result.available) onClearToken();
      })
      .catch((cause) => {
        if (canceled) return;
        if (
          cause instanceof ApiError &&
          cause.code &&
          ["setup_link_invalid", "setup_unavailable", "setup_claimed"].includes(
            cause.code,
          )
        ) {
          setError(setupErrors[cause.code] ?? "Could not open setup.");
          onClearToken();
          if (cause.code === "setup_claimed") onExistingAccount();
        } else setLoadFailed(true);
      });
    return () => {
      canceled = true;
    };
  }, [loadAttempt, onClearToken, onExistingAccount, token]);

  const clearCredentials = () => {
    setPassword("");
    setConfirmation("");
  };
  const refreshSetupIdentity = async () => {
    const session = await api<Schema<"SessionStatus">>("/auth/session");
    setIdentity(session.csrf_token, session.authenticated);
    if (session.authenticated && session.role === "adult") {
      clearCredentials();
      onComplete(session);
      return false;
    }
    if (!session.setup_required) {
      clearCredentials();
      onExistingAccount();
      return false;
    }
    return true;
  };
  const createAccount = async () => {
    if (!status?.available || busy) return;
    const length = Array.from(password).length;
    const next = {
      login: !login.trim()
        ? "Enter a login name."
        : Array.from(login.trim()).length > 64
          ? "Use no more than 64 characters for the login name."
          : /\p{C}/u.test(login)
            ? "Remove invisible or control characters from the login name."
            : "",
      password: !password
        ? "Enter a password."
        : length < status.minimum_password_length ||
            length > status.maximum_password_length
          ? `Use ${status.minimum_password_length}–${status.maximum_password_length} characters for your password.`
          : !password.trim()
            ? "Your password cannot be only spaces."
            : /\p{C}/u.test(password)
              ? "Remove invisible or control characters from the password."
              : "",
      confirmation: !confirmation
        ? "Enter the password again."
        : confirmation !== password
          ? "The passwords do not match."
          : "",
    };
    setFields(next);
    setError("");
    if (Object.values(next).some(Boolean)) return;
    setBusy(true);
    try {
      if (!(await refreshSetupIdentity())) return;
      const body: Schema<"SetupRequest"> = {
        login_name: login.trim(),
        password,
        password_confirmation: confirmation,
      };
      const session = await api<Schema<"SessionStatus">>(
        "/auth/setup",
        "POST",
        body,
      );
      clearCredentials();
      onClearToken();
      onComplete(session);
    } catch (cause) {
      const code = cause instanceof ApiError ? cause.code : undefined;
      // A lost response does not prove the account was not committed. Recover
      // the cookie-backed identity before offering another manual attempt.
      if (
        !(cause instanceof ApiError) ||
        cause.status >= 500 ||
        code === "setup_claimed"
      ) {
        try {
          const session = await api<Schema<"SessionStatus">>("/auth/session");
          if (session.authenticated && session.role === "adult") {
            clearCredentials();
            onClearToken();
            onComplete(session);
            return;
          }
          if (!session.setup_required) {
            clearCredentials();
            onClearToken();
            onExistingAccount();
            return;
          }
        } catch {
          // Keep the draft and fixed retry message if recovery is also offline.
        }
      }
      setError(
        code && Object.hasOwn(setupErrors, code)
          ? (setupErrors[code] ?? "Could not create the account. Try again.")
          : cause instanceof ApiError && cause.status === 403
            ? "Could not confirm setup permission. Try creating the account again."
            : "Could not create the account. Check that the app is running, then try again.",
      );
      if (
        code === "setup_session_expired" ||
        code === "setup_unavailable" ||
        code === "setup_claimed"
      ) {
        clearCredentials();
        onClearToken();
        setStatus((current) => current && { ...current, available: false });
      }
      if (code === "setup_claimed") onExistingAccount();
    } finally {
      setBusy(false);
    }
  };
  const cancelSetup = async () => {
    setBusy(true);
    try {
      if (!(await refreshSetupIdentity())) return;
      const next = await api<Schema<"SetupStatus">>(
        "/auth/setup/session",
        "DELETE",
      );
      clearCredentials();
      setError("");
      onClearToken();
      setStatus(next);
    } catch {
      setError("Could not cancel setup. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="welcome setup-page">
      <h1 tabIndex={-1}>Create administrator account</h1>
      <p>
        This account manages AI connections and learner accounts. To study,
        create a separate learner account after setup.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!status ? (
        loadFailed ? (
          <div className="card">
            <p role="alert">
              Could not check account setup. Check that the app is running, then
              retry.
            </p>
            <button
              type="button"
              onClick={() => {
                setLoadFailed(false);
                setLoadAttempt((value) => value + 1);
              }}
            >
              Retry setup check
            </button>
          </div>
        ) : (
          <p role="status">Checking account setup…</p>
        )
      ) : !status.available ? (
        <div className="card">
          <h2>Open the setup link from your terminal</h2>
          <p>
            On the computer running Shepherd Academy Universe, open the setup
            link printed by <code>make start</code>. Open it within 30 minutes.
            This browser then has eight hours to create the first account.
          </p>
          <p>
            If the link expired or no link is shown, run <code>make start</code>{" "}
            in the project folder for a new link. It connects to an existing
            Docker app. If the app is running in a terminal, press Ctrl+C to
            stop that run first. Choose your password here in the browser.
          </p>
          <p className="fine">
            Keep the link private. Once opened, setup permission survives
            refreshes and app restarts in this browser.
          </p>
        </div>
      ) : (
        <form
          className="card"
          noValidate
          aria-busy={busy}
          onSubmit={(event) => {
            event.preventDefault();
            void createAccount();
          }}
        >
          <p id="setup-password-requirements">
            Use {status.minimum_password_length}–
            {status.maximum_password_length} characters for your password. No
            uppercase letters, numbers, or symbols are required.
          </p>
          {status.local_passwords_allowed ? (
            <p className="fine">
              Six characters are allowed for this computer-only setup. A longer
              password is safer. Choose at least 12 now to use HTTPS or phone
              access later without resetting this password.
            </p>
          ) : (
            <p className="fine">
              This HTTPS or network setup requires at least{" "}
              {status.minimum_password_length} characters.
            </p>
          )}
          <label htmlFor="setup-login">Username</label>
          <input
            id="setup-login"
            name="login"
            autoComplete="username"
            required
            maxLength={64}
            disabled={busy}
            value={login}
            onChange={(event) => setLogin(event.target.value)}
            aria-invalid={!!fields.login}
            aria-describedby={fields.login ? "setup-login-error" : undefined}
          />
          {fields.login && (
            <p id="setup-login-error" role="alert" className="error">
              {fields.login}
            </p>
          )}
          <label htmlFor="setup-password">Password</label>
          <input
            id="setup-password"
            name="password"
            type="password"
            autoComplete="new-password"
            required
            disabled={busy}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            aria-invalid={!!fields.password}
            aria-describedby={`setup-password-requirements${fields.password ? " setup-password-error" : ""}`}
          />
          {fields.password && (
            <p id="setup-password-error" role="alert" className="error">
              {fields.password}
            </p>
          )}
          <label htmlFor="setup-confirmation">Confirm password</label>
          <input
            id="setup-confirmation"
            name="password_confirmation"
            type="password"
            autoComplete="new-password"
            required
            disabled={busy}
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
            aria-invalid={!!fields.confirmation}
            aria-describedby={
              fields.confirmation ? "setup-confirmation-error" : undefined
            }
          />
          {fields.confirmation && (
            <p id="setup-confirmation-error" role="alert" className="error">
              {fields.confirmation}
            </p>
          )}
          <p className="fine">
            Your password is not saved in browser storage. Help keeps this form
            open; reloading or closing the tab clears unsent entries.
          </p>
          <div className="actions">
            <button className="primary" disabled={busy}>
              {busy ? "Creating account…" : "Create account"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => void cancelSetup()}
            >
              Cancel setup
            </button>
          </div>
        </form>
      )}
      <ContextHelp topic="Why do I need a setup link?">
        <p>
          The private link proves you can access the computer running the app.
          It cannot reset or replace an existing account. Account creation does
          not download a model or call an AI provider.
        </p>
        <button type="button" onClick={() => onNavigate("help", "setup")}>
          Setup instructions
        </button>
      </ContextHelp>
    </section>
  );
}
