import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Schema } from "./client";
import { ContextHelp } from "./Help";
import { type Navigate } from "./navigation";
import { LearnerAccounts } from "./LearnerAccounts";
import {
  ProviderConnections,
  type ProviderSettingsSection,
} from "./ProviderConnections";

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

const providerSettingsSteps: Array<{
  id: ProviderSettingsSection;
  label: string;
  description: string;
}> = [
  {
    id: "connections",
    label: "Connections",
    description: "Add and edit models",
  },
  {
    id: "policy",
    label: "Data & privacy",
    description: "Cloud access and age groups",
  },
  {
    id: "tests",
    label: "Connection tests",
    description: "Try a sample request",
  },
  {
    id: "roles",
    label: "Active models",
    description: "Choose tutor and photo reader",
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
  const refreshSequence = useRef(0);
  const routesDirty = useRef(false);
  const focusSettingsContent = useRef(false);
  const settingsTabs = useRef<Array<HTMLButtonElement | null>>([]);
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
        text: "Cloud AI is off in Data & privacy.",
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
        <LearnerAccounts
          key={learner || "no-learner"}
          learner={learner}
          learners={learners}
          onLearner={onLearner}
          onRefresh={onRefresh}
          act={act}
        />
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
                aria-label="AI settings"
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
                      Active models
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
                                          ? "Open Data & privacy"
                                          : "Open Connection tests"}
                                    </button>
                                  ))}
                                </div>
                              </div>
                            ) : (
                              <p className="ready-state">Ready to use.</p>
                            )}
                            {selected?.requires_approval &&
                              issues.length === 0 && (
                                <p className="notice">
                                  This connection has passed its tests. Save
                                  below to let learners use it.
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
                      Save active models
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
