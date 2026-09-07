import { useCallback, useEffect, useRef, useState } from "react";
import { api, newKey, type Schema } from "./client";

type Props = {
  learner: string;
  onLearner: (id: string) => void;
  act: (action: () => Promise<void>) => Promise<void>;
};
export function AdultPanel({ learner, onLearner, act }: Props) {
  const [learners, setLearners] = useState<Schema<"LearnerPublic">[]>([]);
  const [profiles, setProfiles] = useState<Schema<"ProfilePublic">[]>([]);
  const [providers, setProviders] = useState<Schema<"ProvidersPublic"> | null>(
    null,
  );
  const [message, setMessage] = useState("");
  const refreshSequence = useRef(0);
  const refresh = useCallback(async () => {
    const sequence = ++refreshSequence.current;
    const [l, p, c] = await Promise.all([
      api<Schema<"LearnerPublic">[]>("/admin/learners"),
      api<Schema<"ProfilePublic">[]>("/admin/tutor-profiles"),
      api<Schema<"ProvidersPublic">>("/admin/providers"),
    ]);
    if (sequence !== refreshSequence.current) return;
    setLearners(l);
    setProfiles(p);
    setProviders(c);
  }, []);
  useEffect(() => {
    void act(refresh);
  }, [act, refresh]);
  const chosen = learners.find((row) => row.id === learner);
  return (
    <section className="admin">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Adult workspace</p>
          <h1>Set up a good practice session.</h1>
        </div>
        <label>
          Learner
          <select value={learner} onChange={(e) => onLearner(e.target.value)}>
            <option value="">Select a learner</option>
            {learners.map((l) => (
              <option key={l.id} value={l.id}>
                {l.alias}
              </option>
            ))}
          </select>
        </label>
      </div>
      <details>
        <summary>Manage learners and devices</summary>
        <div className="grid">
          <form
            className="card"
            onSubmit={(e) => {
              e.preventDefault();
              const form = e.currentTarget;
              const data = new FormData(form);
              void act(async () => {
                const row = await api<Schema<"LearnerPublic">>(
                  "/admin/learners",
                  "POST",
                  {
                    alias: data.get("alias"),
                    eligibility: data.get("eligibility"),
                  },
                  newKey(),
                );
                await refresh();
                onLearner(row.id);
                form.reset();
              });
            }}
          >
            <h2>Create a learner</h2>
            <label>
              Alias
              <input name="alias" required maxLength={64} />
            </label>
            <label>
              Eligibility
              <select name="eligibility">
                <option value="unknown">Unknown (restricted routes)</option>
                <option value="minor">Under 18</option>
                <option value="adult">Adult</option>
              </select>
            </label>
            <button>Create learner</button>
          </form>
          <form
            className="card"
            onSubmit={(e) => {
              e.preventDefault();
              const data = new FormData(e.currentTarget);
              void act(async () => {
                await api(
                  `/admin/pairing/${data.get("pair") as string}/approve`,
                  "POST",
                  { learner_id: learner },
                );
                setMessage(
                  "Approved. The requesting browser will finish pairing.",
                );
              });
            }}
          >
            <h2>Approve a device</h2>
            <p>Selected learner: {chosen?.alias ?? "select a learner first"}</p>
            <label>
              Pairing request ID
              <input name="pair" required pattern="[a-fA-F0-9-]{36}" />
            </label>
            <button disabled={!learner}>Approve this browser</button>
          </form>
        </div>
        {chosen && (
          <div className="actions">
            <button
              onClick={() =>
                void act(async () => {
                  await api(`/admin/learners/${learner}/revoke`, "POST");
                  setMessage("Learner devices revoked.");
                })
              }
            >
              Revoke learner devices
            </button>
            <button
              onClick={() =>
                void act(async () => {
                  const data = await api<Schema<"LearnerExport">>(
                    `/admin/learners/${learner}/export`,
                    "POST",
                  );
                  const url = URL.createObjectURL(
                    new Blob([JSON.stringify(data, null, 2)], {
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
              Export saved practice
            </button>
            <button
              className="danger"
              onClick={() => {
                if (
                  window.confirm(
                    `Delete ${chosen.alias}'s saved practice and revoke all their devices? This cannot be undone.`,
                  )
                )
                  void act(async () => {
                    await api(`/admin/learners/${learner}`, "DELETE");
                    onLearner("");
                    await refresh();
                  });
              }}
            >
              Delete learner
            </button>
          </div>
        )}
      </details>
      <details>
        <summary>Tutor profiles</summary>
        <form
          className="card"
          onSubmit={(e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            const body = {
              name: data.get("name"),
              profile_id: data.get("profile") || null,
              topics: data.getAll("topics"),
              difficulty: data.get("difficulty"),
              teaching_style: data.get("style"),
              verbosity: data.get("verbosity"),
              solution_policy: data.get("solution"),
              session_problem_limit: Number(data.get("limit")),
              custom_instructions: data.get("instructions"),
              presentation: {
                font_scale: Number(data.get("font")),
                reduced_motion: data.get("motion") === "on",
                compact_explanations: data.get("compact") === "on",
              },
            };
            void act(async () => {
              await api("/admin/tutor-profiles", "POST", body, newKey());
              await refresh();
              setMessage(
                "Profile version saved. Existing sessions retain their starting settings.",
              );
            });
          }}
        >
          <h2>Create a profile version</h2>
          <div className="grid">
            <label>
              Profile family
              <select name="profile">
                <option value="">New profile</option>
                {profiles
                  .filter(
                    (p, i, a) =>
                      a.findIndex((v) => v.profile_id === p.profile_id) === i,
                  )
                  .map((p) => (
                    <option key={p.id} value={p.profile_id}>
                      {p.settings.name} (v{p.version})
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Name
              <input name="name" required maxLength={64} />
            </label>
            <label>
              Difficulty
              <select name="difficulty">
                <option>standard</option>
                <option>introductory</option>
                <option>challenge</option>
              </select>
            </label>
            <label>
              Teaching style
              <select name="style">
                <option>guided</option>
                <option>direct</option>
                <option>worked_example</option>
              </select>
            </label>
            <label>
              Verbosity
              <select name="verbosity">
                <option>standard</option>
                <option>brief</option>
                <option>detailed</option>
              </select>
            </label>
            <label>
              Full solution
              <select name="solution">
                <option value="after_two_attempts">After two attempts</option>
                <option value="on_request">On request</option>
                <option value="adult_only">Adult only</option>
              </select>
            </label>
            <label>
              Problems per session
              <input
                type="number"
                name="limit"
                min={1}
                max={20}
                defaultValue={5}
              />
            </label>
            <label>
              Font scale
              <input
                type="number"
                name="font"
                min={1}
                max={1.5}
                step={0.1}
                defaultValue={1}
              />
            </label>
          </div>
          <fieldset>
            <legend>Topics</legend>
            {[
              "fractions.equivalent",
              "fractions.simplify",
              "fractions.add",
              "fractions.subtract",
              "fractions.multiply",
              "fractions.divide",
              "equations.linear",
            ].map((topic) => (
              <label className="check" key={topic}>
                <input
                  type="checkbox"
                  name="topics"
                  value={topic}
                  defaultChecked={topic === "fractions.add"}
                />
                {topic.replaceAll(".", " · ")}
              </label>
            ))}
          </fieldset>
          <label className="check">
            <input type="checkbox" name="motion" defaultChecked />
            Reduced motion
          </label>
          <label className="check">
            <input type="checkbox" name="compact" />
            Compact explanations
          </label>
          <label>
            Teaching preferences
            <textarea name="instructions" maxLength={2000} />
          </label>
          <p className="fine">
            English is the evaluated language. Preferences cannot change privacy
            or verification rules.
          </p>
          <div className="actions">
            <button>Save profile version</button>
            <button
              type="button"
              onClick={() =>
                void act(async () => {
                  const preview = await api<Schema<"Preview">>(
                    "/admin/tutor-profiles/preview",
                    "POST",
                    { name: "Synthetic preview" },
                  );
                  setMessage(
                    `${preview.problem}: ${preview.message} (${preview.source})`,
                  );
                })
              }
            >
              Preview a synthetic example
            </button>
          </div>
        </form>
      </details>
      <details>
        <summary>Provider routes and health</summary>
        <p>
          Server configuration defines endpoints and credentials. Probes send
          synthetic data only. Choosing cloud routes can transfer learner
          content; no automatic fallback occurs.
        </p>
        {providers && (
          <>
            <div className="provider-list">
              {providers.providers.map((p) => (
                <article className="card" key={p.id}>
                  <h3>{p.id}</h3>
                  <p>
                    {p.adapter} · {p.model}
                  </p>
                  <p>
                    {p.boundary} · {p.audience} ·{" "}
                    {p.enabled ? "enabled" : "disabled"}
                  </p>
                  <p>
                    Text probe: {p.tutor_probed ? "recorded" : "pending"}.
                    Vision probe: {p.vision_probed ? "recorded" : "pending"}.
                  </p>
                  <div className="actions">
                    {(["tutor", "vision"] as const).map((stage) => (
                      <button
                        key={stage}
                        disabled={
                          !p.enabled || (stage === "vision" && !p.image_input)
                        }
                        onClick={() => {
                          if (
                            p.adapter === "mock" ||
                            window.confirm(
                              "Authorize one synthetic provider request? Live providers may charge for this call.",
                            )
                          )
                            void act(async () => {
                              await api(
                                `/admin/providers/${p.id}/probe`,
                                "POST",
                                { stage, authorize_synthetic_call: true },
                              );
                              await refresh();
                              setMessage("Synthetic capability probe passed.");
                            });
                        }}
                      >
                        Probe {stage}
                      </button>
                    ))}
                  </div>
                </article>
              ))}
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const data = new FormData(e.currentTarget);
                void act(async () => {
                  await api("/admin/providers/routes", "POST", {
                    tutor: data.get("tutor"),
                    vision: data.get("vision"),
                    acknowledge_data_boundary: true,
                  });
                  await refresh();
                  setMessage(
                    "Routes changed. Existing operations will not be replayed to the new configuration.",
                  );
                });
              }}
            >
              <div className="grid">
                {(["tutor", "vision"] as const).map((stage) => (
                  <label key={stage}>
                    {stage} route
                    <select name={stage} defaultValue={providers.routes[stage]}>
                      {providers.providers
                        .filter((p) => p.enabled)
                        .map((p) => (
                          <option key={p.id}>{p.id}</option>
                        ))}
                    </select>
                  </label>
                ))}
              </div>
              <label className="check">
                <input type="checkbox" required />I reviewed and authorize these
                data boundaries.
              </label>
              <button>Save routes</button>
            </form>
          </>
        )}
      </details>
      {message && (
        <p role="status" className="notice">
          {message}
        </p>
      )}
    </section>
  );
}
