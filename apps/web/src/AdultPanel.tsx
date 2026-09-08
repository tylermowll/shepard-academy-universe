import { useCallback, useEffect, useRef, useState } from "react";
import { api, newKey, type Schema } from "./client";
import { ContextHelp } from "./Help";
import { followPage, pageUrl, type Navigate } from "./navigation";
import {
  ProviderConnections,
  type ProviderSettingsSection,
} from "./ProviderConnections";

type Props = {
  adultLoginName?: string;
  learner: string;
  learners: Schema<"LearnerPublic">[];
  onLearner: (id: string) => void;
  onRefresh: () => Promise<void>;
  page: "learners" | "settings";
  onNavigate: Navigate;
  onProvidersChanged?: () => void;
  act: (action: () => Promise<void>) => Promise<void>;
};

const providerSettingsSteps: Array<{
  id: ProviderSettingsSection;
  label: string;
  description: string;
}> = [
  {
    id: "connections",
    label: "Connections",
    description: "Save model access",
  },
  { id: "policy", label: "App permissions", description: "Allow data use" },
  { id: "tests", label: "Connection tests", description: "Check readiness" },
  {
    id: "roles",
    label: "Assign active connections",
    description: "Activate for the app",
  },
];

function processingLocation(provider?: Schema<"ProviderPublic">) {
  if (!provider) return "Not available";
  if (provider.boundary === "synthetic") return "Synthetic demo";
  if (provider.boundary === "local_network") return "Your local network";
  if (provider.boundary === "cloud") return "Cloud provider";
  return provider.boundary;
}

export function AdultPanel({
  adultLoginName,
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
  const [settingsSection, setSettingsSection] =
    useState<ProviderSettingsSection>("connections");
  const [acknowledged, setAcknowledged] = useState(false);
  const [message, setMessage] = useState("");
  const [loadFailed, setLoadFailed] = useState(false);
  const learnerName = useRef<HTMLInputElement>(null);
  const learnerAge = useRef<HTMLSelectElement>(null);
  const pageVersion = useRef(0);
  const refreshSequence = useRef(0);
  const routesDirty = useRef(false);
  const focusSettingsContent = useRef(false);
  const settingsTabs = useRef<Array<HTMLButtonElement | null>>([]);
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
    if (!routesDirty.current) setRoutes(result.routes);
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
  const chooseSettingsSection = (
    next: ProviderSettingsSection,
    focusContent = false,
  ) => {
    focusSettingsContent.current = focusContent;
    if (next !== settingsSection) setMessage("");
    setSettingsSection(next);
  };
  useEffect(() => {
    if (page !== "settings" || !focusSettingsContent.current) return;
    focusSettingsContent.current = false;
    document.getElementById(`settings-${settingsSection}-heading`)?.focus();
  }, [page, settingsSection]);
  const routeIssues = (
    provider: Schema<"ProviderPublic"> | undefined,
    stage: "tutor" | "vision",
  ) => {
    if (!provider)
      return [
        {
          text: "Choose a connection.",
          section: "connections" as ProviderSettingsSection,
        },
      ];
    const issues: Array<{
      text: string;
      section: ProviderSettingsSection;
    }> = [];
    if (!provider.enabled)
      issues.push({
        text: "The connection is disabled.",
        section: "connections",
      });
    if (provider.key_needs_replacement)
      issues.push({
        text: "Its saved API key must be replaced.",
        section: "connections",
      });
    if (
      provider.boundary === "cloud" &&
      !providers?.policy.allow_cloud_inference
    )
      issues.push({
        text: "Cloud AI is off in App permissions.",
        section: "policy",
      });
    if (
      provider.audience === "adult_only" &&
      providers?.policy.app_audience !== "adult_only"
    )
      issues.push({
        text: "Its Allowed users setting does not match the app-wide audience.",
        section: "policy",
      });
    if (stage === "vision" && !provider.image_input)
      issues.push({
        text: "Photo input is not enabled for this connection.",
        section: "connections",
      });
    if (stage === "tutor" ? !provider.tutor_probed : !provider.vision_probed)
      issues.push({
        text: `Its ${stage === "tutor" ? "tutor" : "photo-reader"} test has not passed.`,
        section: "tests",
      });
    return issues;
  };

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
                  learnerName.current.value = adultLoginName?.trim() || "Me";
                  learnerAge.current.value = "adult";
                  learnerName.current.focus();
                  learnerName.current.select();
                }}
              >
                Create my practice profile
              </button>
              <p className="fine">
                This creates a learner profile for your practice and history. It
                stays separate from your administrator permissions.
              </p>
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
            <div className="settings-workflow">
              <div
                className="settings-tabs"
                role="tablist"
                aria-label="AI setup steps"
              >
                {providerSettingsSteps.map((step, index) => (
                  <button
                    key={step.id}
                    ref={(element) => {
                      settingsTabs.current[index] = element;
                    }}
                    id={`settings-tab-${step.id}`}
                    type="button"
                    role="tab"
                    aria-selected={settingsSection === step.id}
                    aria-controls="provider-settings-panel"
                    tabIndex={settingsSection === step.id ? 0 : -1}
                    onClick={() => chooseSettingsSection(step.id)}
                    onKeyDown={(event) => {
                      let next: number;
                      if (event.key === "ArrowRight")
                        next = (index + 1) % providerSettingsSteps.length;
                      else if (event.key === "ArrowLeft")
                        next =
                          (index - 1 + providerSettingsSteps.length) %
                          providerSettingsSteps.length;
                      else if (event.key === "Home") next = 0;
                      else if (event.key === "End")
                        next = providerSettingsSteps.length - 1;
                      else return;
                      event.preventDefault();
                      chooseSettingsSection(providerSettingsSteps[next]!.id);
                      settingsTabs.current[next]?.focus();
                    }}
                  >
                    <span className="settings-step-number">{index + 1}</span>
                    <span>
                      <strong>{step.label}</strong>
                      <small>{step.description}</small>
                    </span>
                  </button>
                ))}
              </div>
              <div
                id="provider-settings-panel"
                role="tabpanel"
                aria-labelledby={`settings-tab-${settingsSection}`}
              >
                <ProviderConnections
                  configuration={providers}
                  section={settingsSection}
                  onSectionChange={chooseSettingsSection}
                  onNavigate={onNavigate}
                  act={act}
                  onChanged={async () => {
                    await refreshProviders();
                    onProvidersChanged?.();
                  }}
                />
                {settingsSection === "roles" && (
                  <form
                    className="card role-assignment"
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
                        routesDirty.current = false;
                        await refreshProviders();
                        onProvidersChanged?.();
                        setMessage(
                          "Active connections saved. Future learner work will use these app-wide choices.",
                        );
                      });
                    }}
                  >
                    <h2 id="settings-roles-heading" tabIndex={-1}>
                      Assign active connections
                    </h2>
                    <p>
                      Choose the tutor and photo reader used across this app for
                      future learner work. Saving a connection never activates
                      it; this final step does.
                    </p>
                    <div className="grid">
                      {(["tutor", "vision"] as const).map((stage) => {
                        const selected = selectedProviders[stage];
                        const issues = routeIssues(selected, stage);
                        const actionSections = [
                          ...new Set(issues.map((issue) => issue.section)),
                        ];
                        return (
                          <div key={stage}>
                            <label>
                              {stage === "tutor"
                                ? "Tutor connection"
                                : "Photo reader connection"}
                              <select
                                name={stage}
                                value={routes[stage]}
                                onChange={(e) => {
                                  routesDirty.current = true;
                                  setRoutes({
                                    ...routes,
                                    [stage]: e.target.value,
                                  });
                                  setAcknowledged(false);
                                }}
                                aria-describedby={`${stage}-provider-help`}
                              >
                                {!providers.providers.some(
                                  (provider) => provider.id === routes[stage],
                                ) && (
                                  <option value={routes[stage]} disabled>
                                    {routes[stage]
                                      ? `${routes[stage]} (no longer available)`
                                      : "Choose a connection"}
                                  </option>
                                )}
                                {providers.providers.map((provider) => (
                                  <option
                                    key={provider.id}
                                    value={provider.id}
                                    disabled={
                                      stage === "vision" &&
                                      !provider.image_input
                                    }
                                  >
                                    {provider.id}
                                    {provider.adapter === "mock"
                                      ? " (synthetic demo)"
                                      : routeAvailable(provider, stage)
                                        ? " (ready)"
                                        : stage === "vision" &&
                                            !provider.image_input
                                          ? " (no photo input)"
                                          : " (setup needed)"}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <p className="fine" id={`${stage}-provider-help`}>
                              {stage === "tutor"
                                ? "Creates activities and gives feedback on text, including text read from photos."
                                : "Reads submitted photos before the tutor gives feedback. Connections without photo input cannot fill this role."}{" "}
                              Processing: {processingLocation(selected)}.
                            </p>
                            {issues.length > 0 ? (
                              <div className="notice route-readiness">
                                <p>
                                  <strong>
                                    {selected?.id ?? "This role"} is not ready
                                    yet:
                                  </strong>
                                </p>
                                <ul>
                                  {issues.map((issue) => (
                                    <li key={`${issue.section}-${issue.text}`}>
                                      {issue.text}
                                    </li>
                                  ))}
                                </ul>
                                <div className="actions">
                                  {actionSections.map((target) => (
                                    <button
                                      key={target}
                                      type="button"
                                      onClick={() =>
                                        chooseSettingsSection(target, true)
                                      }
                                    >
                                      {target === "connections"
                                        ? "Open Connections"
                                        : target === "policy"
                                          ? "Open App permissions"
                                          : "Open Connection tests"}
                                    </button>
                                  ))}
                                </div>
                              </div>
                            ) : (
                              <p className="ready-state">
                                Ready for app-wide use.
                              </p>
                            )}
                            {selected?.requires_approval &&
                              issues.length === 0 && (
                                <p className="notice">
                                  This connection changed. Saving below approves
                                  its current settings for this role.
                                </p>
                              )}
                          </div>
                        );
                      })}
                    </div>
                    {(selectedProviders.tutor?.adapter === "mock" ||
                      selectedProviders.vision?.adapter === "mock") && (
                      <p className="fine">
                        A synthetic demo connection returns sample responses. It
                        cannot teach or interpret learner work.
                      </p>
                    )}
                    <label className="check">
                      <input
                        type="checkbox"
                        required
                        checked={acknowledged}
                        onChange={(e) => setAcknowledged(e.target.checked)}
                      />
                      I authorize these app-wide connections to process future
                      learner text and photos.
                    </label>
                    <button
                      className="primary"
                      disabled={
                        !acknowledged ||
                        !routeAvailable(selectedProviders.tutor, "tutor") ||
                        !routeAvailable(selectedProviders.vision, "vision")
                      }
                    >
                      Save active connections
                    </button>
                    <ContextHelp topic="Where does learner work go?">
                      <p>
                        A cloud provider receives the content for its selected
                        role. A cloud tutor also receives text read by a local
                        photo reader. Changing these choices does not resend
                        earlier requests. The app never switches connections
                        automatically when one fails.
                      </p>
                    </ContextHelp>
                  </form>
                )}
              </div>
            </div>
          )}
        </>
      )}
      {message && (
        <aside
          role="status"
          className="notice settings-toast"
          aria-live="polite"
        >
          <p>{message}</p>
          <button type="button" onClick={() => setMessage("")}>
            Dismiss
          </button>
        </aside>
      )}
    </section>
  );
}
