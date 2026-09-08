import { useEffect, useRef, useState } from "react";
import { api, ApiError, newKey, type Schema } from "./client";

type Props = {
  learner: string;
  learners: Schema<"LearnerPublic">[];
  onLearner: (id: string) => void;
  onRefresh: () => Promise<void>;
  act: (action: () => Promise<void>) => Promise<void>;
};

function field(data: FormData, name: string): string {
  const value = data.get(name);
  return typeof value === "string" ? value : "";
}

export function LearnerAccounts({
  learner,
  learners,
  onLearner,
  onRefresh,
  act,
}: Props) {
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [devices, setDevices] = useState<
    Schema<"LearnerDevicePublic">[] | null
  >(null);
  const [deviceError, setDeviceError] = useState("");
  const [deviceRefresh, setDeviceRefresh] = useState(0);
  const version = useRef(0);
  const chosen = learners.find((item) => item.id === learner);
  const creating = adding || learners.length === 0;
  const chosenId = chosen?.id;
  const minimumPassword =
    window.location.protocol === "http:" &&
    ["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname)
      ? 6
      : 12;
  useEffect(() => {
    return () => {
      version.current += 1;
    };
  }, [learner]);
  useEffect(() => {
    let current = true;
    if (chosenId && !creating)
      void api<Schema<"LearnerDevicePublic">[]>(
        `/admin/learners/${chosenId}/devices`,
      ).then(
        (rows) => {
          if (current) {
            setDevices(rows);
            setDeviceError("");
          }
        },
        () => {
          if (current)
            setDeviceError("Could not load signed-in browsers. Try again.");
        },
      );
    return () => {
      current = false;
    };
  }, [chosenId, creating, deviceRefresh]);
  const run = (action: (current: () => boolean) => Promise<void>) => {
    const started = version.current;
    setBusy(true);
    setError("");
    setMessage("");
    void act(async () => {
      try {
        await action(() => started === version.current);
      } catch (cause) {
        if (started === version.current)
          setError(
            cause instanceof ApiError
              ? cause.message
              : "The change was not confirmed. Check your connection and try again.",
          );
      } finally {
        if (started === version.current) setBusy(false);
      }
    });
  };
  return (
    <section aria-label="Learner accounts">
      <p>
        Create one account per learner. They sign in with the username and
        password you set here. Select an account to manage its sign-in details,
        browsers, and saved work.
      </p>
      <div className="learner-accounts">
        <aside aria-label="Choose an account">
          <h2>Learners</h2>
          <ul className="account-list">
            {learners.map((item) => (
              <li key={item.id}>
                <button
                  disabled={busy}
                  aria-pressed={!creating && learner === item.id}
                  onClick={() => {
                    setAdding(false);
                    onLearner(item.id);
                  }}
                >
                  {item.alias}
                  {!item.has_password && <small>Password not set</small>}
                </button>
              </li>
            ))}
          </ul>
          <button
            disabled={busy}
            onClick={() => {
              setAdding(true);
              setError("");
              setMessage("");
            }}
          >
            Add learner account
          </button>
        </aside>
        <div>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          {message && (
            <p role="status" className="success-notice">
              {message}
            </p>
          )}
          {creating ? (
            <form
              className="card"
              onSubmit={(event) => {
                event.preventDefault();
                const form = event.currentTarget;
                const data = new FormData(form);
                run(async (current) => {
                  const row = await api<Schema<"LearnerPublic">>(
                    "/admin/learners",
                    "POST",
                    {
                      alias: field(data, "alias"),
                      password: field(data, "password"),
                      eligibility: field(
                        data,
                        "eligibility",
                      ) as Schema<"LearnerInput">["eligibility"],
                    } satisfies Schema<"LearnerInput">,
                    newKey(),
                  );
                  form.reset();
                  await onRefresh();
                  if (!current()) return;
                  setAdding(false);
                  setBusy(false);
                  onLearner(row.id);
                });
              }}
            >
              <h2>Add learner account</h2>
              <label>
                Learner username
                <input
                  name="alias"
                  required
                  maxLength={64}
                  autoComplete="off"
                  disabled={busy}
                />
              </label>
              <p className="fine">
                Use a unique username. The administrator account has its own
                username.
              </p>
              <label>
                Password
                <input
                  name="password"
                  type="password"
                  required
                  minLength={minimumPassword}
                  maxLength={256}
                  autoComplete="new-password"
                  disabled={busy}
                />
              </label>
              <p className="fine">
                At least {minimumPassword} characters. Share it with the
                learner; you can reset it here later.
              </p>
              <label>
                Age group
                <select name="eligibility" disabled={busy}>
                  <option value="unknown">Not specified</option>
                  <option value="minor">Under 18</option>
                  <option value="adult">18 or older</option>
                </select>
              </label>
              <p className="fine">
                Used to enforce the age restrictions you selected for AI
                connections.
              </p>
              <div className="actions">
                <button className="primary" disabled={busy}>
                  Create learner account
                </button>
                {learners.length > 0 && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => setAdding(false)}
                  >
                    Cancel
                  </button>
                )}
              </div>
            </form>
          ) : chosen ? (
            <section className="card" aria-label="Selected learner">
              <h2>{chosen.alias}</h2>
              <p>
                Age group:{" "}
                {chosen.eligibility === "adult"
                  ? "18 or older"
                  : chosen.eligibility === "minor"
                    ? "Under 18"
                    : "Not specified"}
              </p>
              <p>
                To practice, sign in with this learner’s username and password.
              </p>
              {!chosen.has_password && (
                <p className="notice">
                  This learner's saved work is available. Set a password below
                  so they can sign in on another device.
                </p>
              )}
              <form
                key={chosen.id + chosen.alias}
                onSubmit={(event) => {
                  event.preventDefault();
                  const form = event.currentTarget;
                  const data = new FormData(form);
                  const password = field(data, "password");
                  run(async (current) => {
                    await api(`/admin/learners/${chosen.id}/account`, "PATCH", {
                      alias: field(data, "alias"),
                      ...(password ? { password } : {}),
                    } satisfies Schema<"LearnerAccountUpdate">);
                    form.reset();
                    await onRefresh();
                    if (current()) {
                      setMessage(
                        password
                          ? "Password changed. Previous learner sign-ins have ended."
                          : "Username saved.",
                      );
                      setDeviceRefresh((value) => value + 1);
                    }
                  });
                }}
              >
                <h3>Sign-in details</h3>
                <label>
                  Learner username
                  <input
                    name="alias"
                    defaultValue={chosen.alias}
                    required
                    maxLength={64}
                    disabled={busy}
                  />
                </label>
                <label>
                  {chosen.has_password ? "New password" : "Set password"}
                  <input
                    name="password"
                    type="password"
                    required={!chosen.has_password}
                    minLength={minimumPassword}
                    maxLength={256}
                    autoComplete="new-password"
                    disabled={busy}
                  />
                </label>
                <p className="fine">
                  At least {minimumPassword} characters.{" "}
                  {chosen.has_password
                    ? "Leave blank to keep the current password. Changing it signs out this learner's browsers."
                    : "Set a password to let this learner sign in. Setting it ends any previous browser access."}
                </p>
                <button disabled={busy}>Save sign-in details</button>
              </form>
              <section aria-label="Signed-in browsers">
                <h3>Signed-in browsers</h3>
                <p>
                  These browsers can access {chosen.alias}'s practice and
                  history. The phone photo QR does not sign a browser into this
                  account.
                </p>
                <button
                  disabled={busy}
                  onClick={() => setDeviceRefresh((value) => value + 1)}
                >
                  Refresh browsers
                </button>
                {deviceError ? (
                  <p role="status">
                    {deviceError}{" "}
                    <button
                      onClick={() => setDeviceRefresh((value) => value + 1)}
                    >
                      Reload browsers
                    </button>
                  </p>
                ) : devices === null ? (
                  <p>Loading browsers…</p>
                ) : devices.length === 0 ? (
                  <p>No browsers are signed in as {chosen.alias}.</p>
                ) : (
                  <ul>
                    {devices.map((device) => (
                      <li key={device.id}>
                        Signed in {new Date(device.created_at).toLocaleString()}{" "}
                        <button
                          disabled={busy}
                          onClick={() =>
                            run(async (current) => {
                              await api(
                                `/admin/learners/${chosen.id}/devices/${device.id}`,
                                "DELETE",
                              );
                              if (current())
                                setDeviceRefresh((value) => value + 1);
                            })
                          }
                        >
                          Sign out this browser
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <button
                  disabled={busy}
                  onClick={() =>
                    run(async (current) => {
                      await api(`/admin/learners/${chosen.id}/revoke`, "POST");
                      if (current()) {
                        setDeviceRefresh((value) => value + 1);
                        setMessage(
                          `${chosen.alias}'s browsers are signed out.`,
                        );
                      }
                    })
                  }
                >
                  Sign out all learner browsers
                </button>
              </section>
              <section aria-label="Saved work">
                <h3>Saved work</h3>
                <div className="actions">
                  <button
                    disabled={busy}
                    onClick={() =>
                      run(async () => {
                        const result = await api<Schema<"LearnerExport">>(
                          `/admin/learners/${chosen.id}/export`,
                          "POST",
                        );
                        const url = URL.createObjectURL(
                          new Blob([JSON.stringify(result, null, 2)], {
                            type: "application/json",
                          }),
                        );
                        const link = document.createElement("a");
                        link.href = url;
                        link.download = "learner-export.json";
                        link.click();
                        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
                      })
                    }
                  >
                    Download saved practice
                  </button>
                  <button
                    className="danger"
                    disabled={busy}
                    onClick={() => {
                      if (
                        !window.confirm(
                          `Delete ${chosen.alias}'s account and saved work? This cannot be undone.`,
                        )
                      )
                        return;
                      run(async (current) => {
                        await api(`/admin/learners/${chosen.id}`, "DELETE");
                        await onRefresh();
                        if (current()) {
                          setBusy(false);
                          onLearner("");
                          setMessage("Learner account deleted.");
                        }
                      });
                    }}
                  >
                    Delete learner
                  </button>
                </div>
              </section>
            </section>
          ) : (
            <p>
              Choose a learner to manage their sign-in, browsers and saved work,
              or add a new account.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
