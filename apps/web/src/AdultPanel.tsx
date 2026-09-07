import { useCallback, useEffect, useRef, useState } from "react";
import { api, newKey, type Schema } from "./client";
import { ContextHelp } from "./Help";
import { followPage, pageUrl, type Navigate } from "./navigation";
import { ProviderConnections } from "./ProviderConnections";

type Props = {
  learner: string;
  learners: Schema<"LearnerPublic">[];
  onLearner: (id: string) => void;
  onRefresh: () => Promise<void>;
  page: "learners" | "settings";
  onNavigate: Navigate;
  onProvidersChanged?: () => void;
  act: (action: () => Promise<void>) => Promise<void>;
};

function processingLocation(provider?: Schema<"ProviderPublic">) {
  if (!provider) return "Not available";
  if (provider.boundary === "synthetic") return "Synthetic demo";
  if (provider.boundary === "local_network") return "Your local network";
  if (provider.boundary === "cloud") return "Cloud provider";
  return provider.boundary;
}

export function AdultPanel({
  learner,
  learners,
  onLearner,
  onRefresh,
  page,
  onNavigate,
  onProvidersChanged,
  act,
}: Props) {
  const [providers, setProviders] = useState<Schema<"ProvidersPublic"> | null>(
    null,
  );
  const [routes, setRoutes] = useState({ tutor: "", vision: "" });
  const [acknowledged, setAcknowledged] = useState(false);
  const [message, setMessage] = useState("");
  const [loadFailed, setLoadFailed] = useState(false);
  const learnerName = useRef<HTMLInputElement>(null);
  const learnerAge = useRef<HTMLSelectElement>(null);
  const pageVersion = useRef(0);
  const refreshSequence = useRef(0);
  useEffect(() => {
    return () => {
      pageVersion.current += 1;
    };
  }, [page]);
  const refreshProviders = useCallback(async () => {
    const sequence = ++refreshSequence.current;
    setLoadFailed(false);
    let result: Schema<"ProvidersPublic">;
    try {
      result = await api<Schema<"ProvidersPublic">>("/admin/providers");
    } catch (cause) {
      if (sequence === refreshSequence.current) setLoadFailed(true);
      throw cause;
    }
    if (sequence !== refreshSequence.current) return;
    setProviders(result);
    setRoutes(result.routes);
    setAcknowledged(false);
  }, []);
  useEffect(() => {
    if (page === "settings") void act(refreshProviders);
    return () => {
      refreshSequence.current += 1;
    };
  }, [act, page, refreshProviders]);
  const chosen = learners.find((row) => row.id === learner);
  const loopback = ["127.0.0.1", "localhost", "[::1]"].includes(
    window.location.hostname,
  );
  const selectedProviders = {
    tutor: providers?.providers.find((p) => p.id === routes.tutor),
    vision: providers?.providers.find((p) => p.id === routes.vision),
  };
  const routeAvailable = (
    provider: Schema<"ProviderPublic"> | undefined,
    stage: "tutor" | "vision",
  ) =>
    Boolean(
      provider?.enabled &&
      !provider.key_needs_replacement &&
      (provider.boundary !== "cloud" ||
        providers?.policy.allow_cloud_inference) &&
      (provider.audience !== "adult_only" ||
        providers?.policy.app_audience === "adult_only") &&
      (stage === "tutor"
        ? provider.tutor_probed
        : provider.image_input && provider.vision_probed),
    );

  return (
    <section className="admin">
      {page === "learners" ? (
        <>
          <p>
            Your adult sign-in manages this app. Learner profiles keep each
            person&apos;s practice separate, including your own. You can
            practice here without another login.
          </p>
          {chosen && (
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
              <button
                className="primary"
                onClick={() => onNavigate("practice")}
              >
                Start practice
              </button>
              <details>
                <summary>Saved data &amp; device access</summary>
                <p>
                  Download {chosen.alias}&apos;s saved practice, sign out their
                  devices, or delete this learner and their saved work.
                </p>
                <div className="actions">
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
                    Download saved practice
                  </button>
                  <button
                    onClick={() =>
                      void act(async () => {
                        await api(`/admin/learners/${learner}/revoke`, "POST");
                        setMessage(`${chosen.alias}'s devices are signed out.`);
                      })
                    }
                  >
                    Sign out learner devices
                  </button>
                  <button
                    className="danger"
                    onClick={() => {
                      const version = pageVersion.current;
                      if (
                        window.confirm(
                          `Delete ${chosen.alias}'s saved practice and revoke all their devices? This cannot be undone.`,
                        )
                      )
                        void act(async () => {
                          await api(`/admin/learners/${learner}`, "DELETE");
                          await onRefresh();
                          if (version !== pageVersion.current) return;
                          onLearner("");
                          setMessage("Learner deleted.");
                        });
                    }}
                  >
                    Delete learner
                  </button>
                </div>
              </details>
            </section>
          )}
          <div className="grid">
            <form
              className="card"
              onSubmit={(e) => {
                e.preventDefault();
                const form = e.currentTarget;
                const data = new FormData(form);
                const version = pageVersion.current;
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
                  await onRefresh();
                  // A completed request must not switch away from practice
                  // started after this panel was left.
                  if (version !== pageVersion.current) return;
                  onLearner(row.id);
                  form.reset();
                  setMessage(`${row.alias} added. You can start practice now.`);
                });
              }}
            >
              <h2>Add a learner</h2>
              <button
                type="button"
                onClick={() => {
                  if (!learnerName.current || !learnerAge.current) return;
                  learnerName.current.value = "Me";
                  learnerAge.current.value = "adult";
                  learnerName.current.focus();
                  learnerName.current.select();
                }}
              >
                Add yourself (adult)
              </button>
              <label>
                Learner name
                <input
                  ref={learnerName}
                  name="alias"
                  required
                  maxLength={64}
                  aria-describedby="learner-name-help"
                />
              </label>
              <p className="fine" id="learner-name-help">
                A nickname is enough. Each learner has separate saved work.
              </p>
              <label>
                Age group
                <select name="eligibility" ref={learnerAge}>
                  <option value="unknown">Not specified</option>
                  <option value="minor">Under 18</option>
                  <option value="adult">18 or older</option>
                </select>
              </label>
              <ContextHelp topic="Why ask for an age group?">
                <p>
                  Some AI providers are restricted to adults. This setting
                  controls which configured providers a learner can use. Leave
                  it unspecified if you are unsure; adult-only providers will
                  stay unavailable.
                </p>
              </ContextHelp>
              <button>Add learner</button>
            </form>
            <section className="card" aria-labelledby="pair-device-heading">
              <h2 id="pair-device-heading">Pair a learner device</h2>
              <p>
                Pair a phone, tablet, or second browser to practice as{" "}
                {chosen?.alias ?? "a learner"} without an adult password.
              </p>
              {loopback && (
                <p className="notice">
                  This address works only on this computer. For a phone, first
                  follow{" "}
                  <a
                    href={pageUrl("help", "phone")}
                    onClick={(e) => followPage(e, onNavigate, "help", "phone")}
                  >
                    phone connection setup
                  </a>{" "}
                  and open the same private HTTPS address on both devices.
                </p>
              )}
              <ol>
                <li>
                  On the learner&apos;s device, open this app and choose{" "}
                  <strong>Pair this device</strong> on the sign-in page.
                </li>
                <li>
                  Copy the request ID shown on that device into the box below.
                </li>
                <li>
                  Select the learner at the top of this page, then approve. Keep
                  the other page open; it signs in automatically.
                </li>
              </ol>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!chosen) return;
                  const form = e.currentTarget;
                  const data = new FormData(form);
                  void act(async () => {
                    await api(
                      `/admin/pairing/${data.get("pair") as string}/approve`,
                      "POST",
                      { learner_id: learner },
                    );
                    form.reset();
                    setMessage(
                      `Device approved for ${chosen.alias}. The other browser will sign in automatically.`,
                    );
                  });
                }}
              >
                <label>
                  Pairing request ID
                  <input
                    name="pair"
                    required
                    pattern="[a-fA-F0-9-]{36}"
                    aria-describedby="pair-request-help"
                  />
                </label>
                <p className="fine" id="pair-request-help">
                  Requests expire after five minutes. If it expires, request a
                  new ID on the learner&apos;s device.
                </p>
                {!chosen && <p>Select or add a learner before approving.</p>}
                <button disabled={!chosen}>Approve device</button>
              </form>
              <ContextHelp topic="Only need the phone camera?">
                <p>
                  Start an activity on the Practice page and choose{" "}
                  <strong>Take photo with phone</strong>. Scan its QR code with
                  your phone camera to send one photo. No pairing or phone
                  sign-in is needed.
                </p>
                <button onClick={() => onNavigate("help", "phone")}>
                  How phone photos work
                </button>
              </ContextHelp>
            </section>
          </div>
        </>
      ) : (
        <>
          {!providers ? (
            loadFailed ? (
              <button onClick={() => void act(refreshProviders)}>
                Retry AI settings
              </button>
            ) : (
              <p role="status">Loading AI settings…</p>
            )
          ) : (
            <>
              <ProviderConnections
                configuration={providers}
                onNavigate={onNavigate}
                act={act}
                onChanged={async () => {
                  await refreshProviders();
                  onProvidersChanged?.();
                }}
              />
              <form
                className="card"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (
                    !acknowledged ||
                    !routeAvailable(selectedProviders.tutor, "tutor") ||
                    !routeAvailable(selectedProviders.vision, "vision")
                  )
                    return;
                  void act(async () => {
                    await api("/admin/providers/routes", "POST", {
                      ...routes,
                      acknowledge_data_boundary: true,
                    });
                    await refreshProviders();
                    onProvidersChanged?.();
                    setMessage(
                      "AI settings saved. New requests use these providers.",
                    );
                  });
                }}
              >
                <h2>Choose providers</h2>
                <p>
                  Use a connection that passed its test. Saving these roles
                  changes where future learner work is sent.
                </p>
                <div className="grid">
                  {(["tutor", "vision"] as const).map((stage) => (
                    <div key={stage}>
                      <label>
                        {stage === "tutor" ? "Tutor" : "Photo reader"}
                        <select
                          name={stage}
                          value={routes[stage]}
                          onChange={(e) => {
                            setRoutes({ ...routes, [stage]: e.target.value });
                            setAcknowledged(false);
                          }}
                          aria-describedby={`${stage}-provider-help`}
                        >
                          {!providers.providers.some(
                            (p) =>
                              p.id === routes[stage] &&
                              p.enabled &&
                              (stage === "tutor" || p.image_input),
                          ) && (
                            <option value={routes[stage]} disabled>
                              {routes[stage]
                                ? `${routes[stage]} (unavailable)`
                                : "No provider available"}
                            </option>
                          )}
                          {providers.providers
                            .filter(
                              (p) =>
                                p.enabled &&
                                (stage === "tutor" || p.image_input),
                            )
                            .map((p) => (
                              <option
                                key={p.id}
                                value={p.id}
                                disabled={!routeAvailable(p, stage)}
                              >
                                {p.id}
                                {p.adapter === "mock"
                                  ? " (synthetic demo)"
                                  : ""}
                              </option>
                            ))}
                        </select>
                      </label>
                      <p className="fine" id={`${stage}-provider-help`}>
                        {stage === "tutor"
                          ? "Creates activities and gives feedback on text, including text read from photos."
                          : "Reads submitted photos before the tutor gives feedback."}{" "}
                        Processing:{" "}
                        {processingLocation(selectedProviders[stage])}.
                      </p>
                      {!routeAvailable(selectedProviders[stage], stage) && (
                        <p className="notice">
                          This connection needs an enabled, permitted model and
                          a successful{" "}
                          {stage === "tutor" ? "tutor" : "photo reader"} test
                          before it can be used.
                        </p>
                      )}
                      {selectedProviders[stage]?.requires_approval && (
                        <p className="notice">
                          This connection changed. Test it, then save AI
                          settings to approve its use for this role.
                        </p>
                      )}
                    </div>
                  ))}
                </div>
                {(selectedProviders.tutor?.adapter === "mock" ||
                  selectedProviders.vision?.adapter === "mock") && (
                  <p className="fine">
                    A synthetic demo provider returns sample responses. It
                    cannot teach or interpret your work.
                  </p>
                )}
                <label className="check">
                  <input
                    type="checkbox"
                    required
                    checked={acknowledged}
                    onChange={(e) => setAcknowledged(e.target.checked)}
                  />
                  I authorize sending text and photos to the providers selected
                  above.
                </label>
                <button
                  className="primary"
                  disabled={
                    !acknowledged ||
                    !routeAvailable(selectedProviders.tutor, "tutor") ||
                    !routeAvailable(selectedProviders.vision, "vision")
                  }
                >
                  Save AI settings
                </button>
                <ContextHelp topic="Where does learner work go?">
                  <p>
                    A cloud provider receives the content for its selected role.
                    A cloud tutor also receives text read by a local photo
                    reader. Changing settings does not resend earlier requests.
                    The app never switches providers automatically when one
                    fails.
                  </p>
                </ContextHelp>
              </form>
            </>
          )}
        </>
      )}
      {message && (
        <p role="status" className="notice">
          {message}
        </p>
      )}
    </section>
  );
}
