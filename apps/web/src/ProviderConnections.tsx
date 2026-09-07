import { useEffect, useRef, useState } from "react";
import { api, ApiError, type Schema } from "./client";
import { ContextHelp } from "./Help";
import type { Navigate } from "./navigation";

type ConnectionInput = Schema<"ProviderConnectionInput">;
type Draft = Required<Omit<Schema<"ProviderConnectionCreate">, "api_key">> & {
  api_key: string;
};
type Props = {
  configuration: Schema<"ProvidersPublic">;
  onChanged: () => Promise<void>;
  onNavigate: Navigate;
  act: (action: () => Promise<void>) => Promise<void>;
};

const addresses: Record<ConnectionInput["adapter"], string> = {
  ollama: "http://127.0.0.1:11434",
  vllm: "http://127.0.0.1:8081/v1",
  compatible: "",
  meta: "https://api.meta.ai/v1",
};

function blankDraft(): Draft {
  return {
    id: "",
    adapter: "ollama",
    model: "",
    base_url: addresses.ollama,
    enabled: true,
    boundary: "local_network",
    audience: "mixed",
    eligibility_record: "",
    image_input: false,
    configured_context_limit: 32768,
    structured_output_mode: "native",
    api_key_action: "keep",
    api_key: "",
  };
}

function inputFor(provider: Schema<"ProviderPublic">): ConnectionInput {
  return {
    adapter: provider.adapter as ConnectionInput["adapter"],
    model: provider.model,
    base_url: provider.base_url ?? "",
    enabled: provider.enabled,
    boundary: provider.boundary as ConnectionInput["boundary"],
    audience: provider.audience as ConnectionInput["audience"],
    eligibility_record: provider.eligibility_record,
    image_input: provider.image_input,
    configured_context_limit: provider.configured_context_limit,
    structured_output_mode: provider.structured_output_mode,
    api_key_action: "keep",
  };
}

function saveError(cause: unknown) {
  if (cause instanceof ApiError) {
    if (cause.status === 401 || cause.status === 403)
      return "Only an authorized adult can change connections. Check your sign-in and the app policy.";
    if (cause.status === 409)
      return "This name is already in use, or the connection is selected for tutoring. Refresh the connections and check its current settings.";
    if (cause.status === 422)
      return "Check the server address, exact model name, audience, and API key choice. Your entries are still here.";
  }
  // Server/provider errors must never echo a credential into the page.
  return "The server did not confirm the save. Your entries are still here. Refresh connections to check before retrying.";
}

const probeMessages = {
  unavailable:
    "The app cannot reach the model server. Check Server address, make sure the model server is running, and check network access from the app server.",
  timeout:
    "The model test timed out. Make sure the server and model are running. Try a smaller model or a faster server, then test again.",
  authentication:
    "The model server rejected the API key, or the saved key could not be unlocked. Edit this connection and replace the key, then test again.",
  invalid_request:
    "The model server rejected the request. Check Model name and Connection type, then check Structured output under Advanced connection options.",
  malformed_output:
    "The model did not return the tutor's required response format. Check Model name and Structured output under Advanced connection options, then test again.",
  context_limit:
    "The model context limit is too small for tutoring. In Advanced connection options, match Model context limit to the model server's supported size.",
  cloud_disabled:
    "Cloud requests are off. Review and save App privacy & audience before testing this cloud connection.",
  audience_blocked:
    "This connection's Allowed users setting does not match who uses the app. Review both the connection and App privacy & audience.",
  invalid_endpoint:
    "The server address is blocked or does not match its network setting. Check Server address and Where this model runs; hosted services need the cloud setting.",
  unsupported_modality:
    "This model does not support the selected test. For photos, use a vision-capable model and enable This model supports photo input.",
  throttled:
    "The model server is limiting requests. Wait before testing again, and check the provider's usage limits.",
  probe_reading_failed:
    "The model could not clearly read the test photo. Check that the selected model and server support images, then try the photo-reader test again.",
} as const;

function probeError(cause: unknown) {
  if (cause instanceof ApiError) {
    if (cause.code && Object.hasOwn(probeMessages, cause.code))
      return probeMessages[cause.code as keyof typeof probeMessages];
    if (cause.status === 401 || cause.status === 403)
      return "Your adult sign-in is no longer authorized. Sign in again before testing this connection.";
    if (cause.status === 409)
      return "The connection or app policy changed during the test. Refresh connections, then test the current settings again.";
    if (cause.status === 429)
      return "Too many requests were made. Wait a minute before testing again.";
  }
  return "The connection test could not be completed. Check that the app and model servers are reachable, then retry. No successful test was confirmed.";
}

export function ProviderConnections({
  configuration,
  onChanged,
  onNavigate,
  act,
}: Props) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editing, setEditing] = useState<Schema<"ProviderPublic"> | null>(null);
  const [terms, setTerms] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [testsOpen, setTestsOpen] = useState(false);
  const policyDetails = useRef<HTMLDetailsElement>(null);
  const editor = useRef<HTMLFormElement>(null);
  const editorOpen = draft !== null;
  useEffect(() => {
    if (editorOpen && editor.current) {
      editor.current
        .querySelector<HTMLInputElement>(
          editing ? 'input[name="model"]' : 'input[name="connection-name"]',
        )
        ?.focus({ preventScroll: true });
      editor.current.scrollIntoView?.({ block: "start" });
    }
  }, [editing, editorOpen]);
  const { policy, providers } = configuration;
  const keyDestinationChanged = Boolean(
    editing?.key_configured &&
    draft &&
    (draft.adapter !== editing.adapter || draft.base_url !== editing.base_url),
  );
  const keyMustChange =
    keyDestinationChanged || Boolean(editing?.key_needs_replacement);
  const metaKeyMissing = Boolean(
    draft?.adapter === "meta" &&
    draft.enabled &&
    !(draft.api_key_action === "replace"
      ? draft.api_key.trim()
      : draft.api_key_action === "keep" &&
        editing?.key_configured &&
        !editing.key_needs_replacement),
  );
  const change = <K extends keyof Draft>(field: K, value: Draft[K]) => {
    setDraft((current) => (current ? { ...current, [field]: value } : null));
    setTerms(false);
    setError("");
  };
  const cancel = () => {
    setDraft(null);
    setEditing(null);
    setTerms(false);
    setError("");
  };
  const start = (provider?: Schema<"ProviderPublic">) => {
    if (
      draft &&
      !window.confirm(
        "Discard the unsaved connection entries and start another?",
      )
    )
      return;
    setEditing(provider ?? null);
    setDraft(
      provider
        ? {
            ...blankDraft(),
            ...inputFor(provider),
            id: provider.id,
            api_key: "",
          }
        : blankDraft(),
    );
    setTerms(false);
    setMessage("");
    setError("");
  };
  const updateConnection = (
    provider: Schema<"ProviderPublic">,
    remove = false,
  ) => {
    if (
      remove &&
      !window.confirm(
        `Delete connection ${provider.id} and its saved API key? Saved practice is kept.`,
      )
    )
      return;
    void act(async () => {
      setBusy(true);
      setError("");
      try {
        await api(
          `/admin/providers/connections/${provider.id}`,
          remove ? "DELETE" : "PUT",
          remove
            ? undefined
            : ({
                ...inputFor(provider),
                enabled: !provider.enabled,
              } satisfies ConnectionInput),
        );
        await onChanged();
        setMessage(
          remove
            ? `${provider.id} deleted.`
            : `${provider.id} ${provider.enabled ? "disabled" : "enabled"}. Test it before selecting it for practice.`,
        );
      } catch (cause) {
        setError(saveError(cause));
      } finally {
        setBusy(false);
      }
    });
  };

  return (
    <section className="connection-setup" aria-labelledby="connections-heading">
      <div className="section-heading">
        <div>
          <h2 id="connections-heading">AI connections</h2>
          <p>Add a model, test the connection, then choose its role below.</p>
        </div>
        <button
          className="primary"
          disabled={policy.demo_mode || busy}
          onClick={() => start()}
        >
          Add AI connection
        </button>
      </div>
      {policy.demo_mode && (
        <p className="notice">
          This public demo cannot save live connections or API keys. Start a
          private installation to connect your models.{" "}
          <button onClick={() => onNavigate("help", "setup")}>
            Private setup help
          </button>
        </p>
      )}
      {!policy.demo_mode &&
        !providers.some(
          (provider) => provider.adapter !== "mock" && provider.enabled,
        ) && (
          <p className="notice">
            No live AI connection is enabled. Add your Ollama or vLLM server, or
            a hosted API connection.
          </p>
        )}
      {draft && (
        <form
          className="card connection-editor"
          ref={editor}
          aria-labelledby="connection-editor-heading"
          autoComplete="off"
          onSubmit={(event) => {
            event.preventDefault();
            if (!terms || busy || policy.demo_mode) return;
            const { id, api_key, ...values } = draft;
            const body = {
              ...values,
              eligibility_record: `Operator confirmed the model and provider terms permit ${draft.audience === "adult_only" ? "adult-only" : "mixed-age"} use.`,
              ...(draft.api_key_action === "replace" ? { api_key } : {}),
            } satisfies ConnectionInput;
            void act(async () => {
              setBusy(true);
              setError("");
              let saved = false;
              try {
                await api(
                  editing
                    ? `/admin/providers/connections/${editing.id}`
                    : "/admin/providers/connections",
                  editing ? "PUT" : "POST",
                  editing
                    ? body
                    : ({
                        ...body,
                        id,
                      } satisfies Schema<"ProviderConnectionCreate">),
                );
                saved = true;
                cancel();
                setTestsOpen(true);
                await onChanged();
                setMessage(
                  `${id} saved. No model request was sent. Test the connection, then select it for the tutor or photo reader below.`,
                );
              } catch (cause) {
                setError(
                  saved
                    ? "The connection was saved, but the list could not refresh. Refresh connections to continue."
                    : saveError(cause),
                );
              } finally {
                setBusy(false);
              }
            });
          }}
        >
          <h3 id="connection-editor-heading">
            {editing ? `Edit ${editing.id}` : "Add an AI connection"}
          </h3>
          <p className="fine">
            Saving stores the connection on your server. It does not call the
            model or change the providers used for practice. Leaving Settings
            discards unsaved entries, including the API key.
          </p>
          <fieldset disabled={busy}>
            <legend>Model and server</legend>
            <div className="grid">
              <label>
                Connection name
                <input
                  value={draft.id}
                  name="connection-name"
                  onChange={(event) => change("id", event.target.value)}
                  pattern="[a-z0-9]([a-z0-9_]|-){0,63}"
                  maxLength={64}
                  required
                  readOnly={Boolean(editing)}
                  autoComplete="off"
                  aria-describedby="connection-name-help"
                />
              </label>
              <label>
                Connection type
                <select
                  value={draft.adapter}
                  onChange={(event) => {
                    const adapter = event.target.value as Draft["adapter"];
                    setDraft({
                      ...draft,
                      adapter,
                      base_url: addresses[adapter],
                      model: "",
                      boundary:
                        adapter === "meta" || adapter === "compatible"
                          ? "cloud"
                          : "local_network",
                      audience: adapter === "meta" ? "adult_only" : "mixed",
                      api_key_action:
                        adapter === "meta" || adapter === "compatible"
                          ? "replace"
                          : "keep",
                      api_key: "",
                      image_input: false,
                    });
                    setTerms(false);
                  }}
                >
                  <option value="ollama">Ollama</option>
                  <option value="vllm">vLLM</option>
                  <option value="compatible">OpenAI-compatible API</option>
                  <option value="meta">Meta API</option>
                </select>
              </label>
            </div>
            <p className="fine" id="connection-name-help">
              Use a short name with lowercase letters, numbers, hyphens or
              underscores, such as home-vision.
            </p>
            <label>
              Server address
              <input
                type="url"
                value={draft.base_url}
                onChange={(event) => change("base_url", event.target.value)}
                required
                maxLength={2048}
                autoComplete="off"
                spellCheck={false}
                placeholder={
                  draft.adapter === "compatible"
                    ? "https://your-provider.example/v1"
                    : addresses[draft.adapter]
                }
                aria-describedby="server-address-help"
              />
            </label>
            <p className="fine" id="server-address-help">
              This address is reached by the app server. For Ollama on the same
              computer, use http://127.0.0.1:11434. For vLLM, use the address
              and port where you started its server.
            </p>
            <label>
              Model name
              <input
                value={draft.model}
                name="model"
                onChange={(event) => change("model", event.target.value)}
                required
                maxLength={256}
                autoComplete="off"
                spellCheck={false}
                placeholder="Exact model name from your server or API account"
                aria-describedby="model-name-help"
              />
            </label>
            <p className="fine" id="model-name-help">
              Copy the installed or served model name exactly. Saving a
              connection does not download or start a model.
            </p>
            <label className="check">
              <input
                type="checkbox"
                checked={draft.image_input}
                onChange={(event) =>
                  change("image_input", event.target.checked)
                }
              />
              This model supports photo input
            </label>
            <ContextHelp topic="Can one model handle text and photos?">
              <p>
                Yes, if the model and its server support image input. Select
                this option only when they do, then run both tests. A text-only
                model can be your tutor while another model reads photos.
              </p>
            </ContextHelp>
          </fieldset>
          <fieldset disabled={busy}>
            <legend>API key</legend>
            {editing && (
              <p className="fine">
                {editing.key_needs_replacement
                  ? "The saved key can no longer be read after a server secret change. Replace or remove it."
                  : editing.key_configured
                    ? "An API key is saved on the server. Its value is never shown here."
                    : "No API key is saved."}
              </p>
            )}
            <label>
              API key action
              <select
                value={draft.api_key_action}
                onChange={(event) => {
                  change(
                    "api_key_action",
                    event.target.value as Draft["api_key_action"],
                  );
                  setDraft((current) =>
                    current ? { ...current, api_key: "" } : null,
                  );
                }}
              >
                <option value="keep">
                  {editing?.key_configured ? "Keep saved key" : "No API key"}
                </option>
                <option value="replace">
                  {editing?.key_configured
                    ? "Replace saved key"
                    : "Add an API key"}
                </option>
                {editing?.key_configured && (
                  <option value="remove">Remove saved key</option>
                )}
              </select>
            </label>
            {draft.api_key_action === "replace" && (
              <label>
                API key
                <input
                  type="password"
                  value={draft.api_key}
                  onChange={(event) => change("api_key", event.target.value)}
                  required
                  autoComplete="new-password"
                  maxLength={8192}
                  spellCheck={false}
                />
              </label>
            )}
            {keyMustChange && draft.api_key_action === "keep" && (
              <p className="notice">
                Replace or remove the saved key before saving this changed
                connection.
              </p>
            )}
            {metaKeyMissing && (
              <p className="notice">
                An enabled Meta connection needs an API key.
              </p>
            )}
            <p className="fine">
              Local servers often need no key. Hosted APIs usually provide one
              in your account. Enter it only in this password field; it is never
              saved in browser storage.
            </p>
          </fieldset>
          <fieldset disabled={busy}>
            <legend>Users and data</legend>
            <div className="grid">
              <label>
                Where this model runs
                <select
                  value={draft.boundary}
                  disabled={draft.adapter === "meta"}
                  onChange={(event) =>
                    change("boundary", event.target.value as Draft["boundary"])
                  }
                >
                  <option value="local_network">
                    This computer or private network
                  </option>
                  <option value="cloud">Cloud service</option>
                </select>
              </label>
              <label>
                Allowed users
                <select
                  value={draft.audience}
                  disabled={draft.adapter === "meta"}
                  onChange={(event) =>
                    change("audience", event.target.value as Draft["audience"])
                  }
                >
                  <option value="mixed">Adults and children</option>
                  <option value="adult_only">Adults only</option>
                </select>
              </label>
            </div>
            {draft.adapter === "meta" && (
              <p className="notice">
                Meta connections are restricted to cloud processing and
                adult-only use in this app.
              </p>
            )}
            {draft.boundary === "cloud" && !policy.allow_cloud_inference && (
              <p className="notice">
                Cloud requests are currently off. You can save this connection,
                then allow cloud AI in App privacy &amp; audience before testing
                it.
              </p>
            )}
            <label className="check">
              <input
                type="checkbox"
                checked={terms}
                onChange={(event) => setTerms(event.target.checked)}
                required
              />
              I reviewed the model and provider terms for the users selected
              above.
            </label>
          </fieldset>
          <details>
            <summary>Advanced connection options</summary>
            <fieldset disabled={busy}>
              <label className="check">
                <input
                  type="checkbox"
                  checked={draft.enabled}
                  onChange={(event) => change("enabled", event.target.checked)}
                />
                Connection enabled
              </label>
              <label>
                Model context limit
                <input
                  type="number"
                  min={2048}
                  max={131072}
                  step={1}
                  value={draft.configured_context_limit}
                  onChange={(event) =>
                    change(
                      "configured_context_limit",
                      Number(event.target.value),
                    )
                  }
                  required
                />
              </label>
              <p className="fine">
                Use the context limit configured on your model server. This is a
                token budget, not a response length.
              </p>
              <label>
                Structured output
                <select
                  value={draft.structured_output_mode}
                  onChange={(event) =>
                    change(
                      "structured_output_mode",
                      event.target.value as Draft["structured_output_mode"],
                    )
                  }
                >
                  <option value="native">Server enforces JSON structure</option>
                  <option value="json_prompt">
                    Ask for JSON and validate it
                  </option>
                </select>
              </label>
              <p className="fine">
                For compatible servers without native structured output, choose
                the second option. Both require a successful connection test.
              </p>
            </fieldset>
          </details>
          <div className="actions">
            <button
              className="primary"
              disabled={
                busy ||
                !terms ||
                !draft.id.trim() ||
                !draft.model.trim() ||
                !draft.base_url.trim() ||
                (draft.api_key_action === "replace" && !draft.api_key.trim()) ||
                (keyMustChange && draft.api_key_action === "keep") ||
                metaKeyMissing
              }
            >
              Save connection
            </button>
            <button type="button" disabled={busy} onClick={cancel}>
              Cancel connection
            </button>
          </div>
        </form>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {message && (
        <p role="status" className="notice">
          {message}
        </p>
      )}
      <details
        open={testsOpen}
        onToggle={(event) => setTestsOpen(event.currentTarget.open)}
      >
        <summary>Connection tests &amp; provider details</summary>
        <p>
          A tutor test sends up to two sample text requests; a photo-reader test
          sends one sample image. Cloud providers may charge for these calls.
          Tests contain no learner work. Saving a connection does not run these
          tests.
        </p>
        <button disabled={busy} onClick={() => void act(onChanged)}>
          Refresh connections
        </button>
        <div className="provider-list">
          {providers.map((provider) => {
            const policyBlocked =
              (provider.boundary === "cloud" &&
                !policy.allow_cloud_inference) ||
              (provider.audience === "adult_only" &&
                policy.app_audience !== "adult_only");
            const selected = Object.values(configuration.routes).includes(
              provider.id,
            );
            return (
              <article className="card" key={provider.id}>
                <h3>
                  {provider.id}
                  {!provider.enabled && " (disabled)"}
                </h3>
                <p>
                  {provider.model} ·{" "}
                  {provider.boundary === "local_network"
                    ? "Local network"
                    : provider.boundary === "cloud"
                      ? "Cloud"
                      : "Synthetic demo"}{" "}
                  ·{" "}
                  {provider.audience === "adult_only"
                    ? "Adults only"
                    : "Mixed ages"}
                </p>
                <p>
                  Tutor:{" "}
                  {provider.tutor_probed ? "test recorded" : "not tested"}.
                  Photo reader:{" "}
                  {!provider.image_input
                    ? "not supported"
                    : provider.vision_probed
                      ? "test recorded"
                      : "not tested"}
                  .
                </p>
                {provider.key_needs_replacement && (
                  <p className="notice">
                    Replace the API key after the server secret changed.
                  </p>
                )}
                {provider.requires_approval && (
                  <p className="notice">
                    After testing, choose this connection for a role and save AI
                    settings to use it for practice.
                  </p>
                )}
                {policyBlocked && (
                  <p className="notice">
                    App policy currently blocks this connection.{" "}
                    <button
                      onClick={() => {
                        if (policyDetails.current) {
                          policyDetails.current.open = true;
                          policyDetails.current.scrollIntoView?.({
                            block: "start",
                          });
                        }
                      }}
                    >
                      Review app policy
                    </button>
                  </p>
                )}
                <div className="actions">
                  {(["tutor", "vision"] as const).map((stage) => (
                    <button
                      key={stage}
                      disabled={
                        busy ||
                        (policy.demo_mode && provider.adapter !== "mock") ||
                        !provider.enabled ||
                        policyBlocked ||
                        provider.key_needs_replacement ||
                        (stage === "vision" && !provider.image_input)
                      }
                      onClick={() => {
                        if (
                          provider.adapter !== "mock" &&
                          !window.confirm(
                            `Send ${stage === "tutor" ? "up to two sample text requests" : "one sample photo request"} to ${provider.id}? This provider may charge for these calls. No learner work is included.`,
                          )
                        )
                          return;
                        void act(async () => {
                          setBusy(true);
                          setError("");
                          setMessage("");
                          let tested = false;
                          try {
                            await api(
                              `/admin/providers/${provider.id}/probe`,
                              "POST",
                              {
                                stage,
                                authorize_synthetic_call: true,
                              } satisfies Schema<"ProbeInput">,
                            );
                            tested = true;
                            await onChanged();
                            setMessage(
                              `${provider.id}: ${stage === "tutor" ? "tutor" : "photo reader"} test passed.`,
                            );
                          } catch (cause) {
                            setError(
                              tested
                                ? "The test completed, but its results could not be refreshed. Refresh connections before choosing its roles."
                                : probeError(cause),
                            );
                          } finally {
                            setBusy(false);
                          }
                        });
                      }}
                    >
                      Test {stage === "tutor" ? "tutor" : "photo reader"}
                    </button>
                  ))}
                </div>
                <details>
                  <summary>Connection details</summary>
                  <p>
                    {provider.adapter}
                    {provider.base_url && <> · {provider.base_url}</>}
                  </p>
                  <p>
                    {provider.key_configured
                      ? "API key saved on the server."
                      : "No API key saved."}
                  </p>
                  <p className="fine">{provider.eligibility_record}</p>
                  {provider.managed ? (
                    <>
                      <div className="actions">
                        <button
                          disabled={busy || policy.demo_mode}
                          onClick={() => start(provider)}
                        >
                          Edit connection
                        </button>
                        <button
                          disabled={
                            busy ||
                            policy.demo_mode ||
                            (selected && provider.enabled)
                          }
                          onClick={() => updateConnection(provider)}
                        >
                          {provider.enabled
                            ? "Disable connection"
                            : "Enable connection"}
                        </button>
                        <button
                          className="danger"
                          disabled={busy || policy.demo_mode || selected}
                          onClick={() => updateConnection(provider, true)}
                        >
                          Delete connection
                        </button>
                      </div>
                      {selected && (
                        <p className="fine">
                          Choose a different tutor and photo reader before
                          disabling or deleting this connection.
                        </p>
                      )}
                    </>
                  ) : (
                    <p className="fine">
                      This connection is managed by the server administrator and
                      is read-only here. Add a new connection to manage its
                      settings in this app.
                    </p>
                  )}
                </details>
              </article>
            );
          })}
        </div>
      </details>
      <details ref={policyDetails}>
        <summary>App privacy &amp; audience</summary>
        <ProviderPolicy
          key={JSON.stringify(policy)}
          policy={policy}
          act={act}
          onChanged={async () => {
            await onChanged();
            setMessage(
              "App policy saved. Test the permitted connections before selecting their roles.",
            );
          }}
        />
      </details>
    </section>
  );
}

function ProviderPolicy({
  policy,
  act,
  onChanged,
}: Pick<Props, "act" | "onChanged"> & {
  policy: Schema<"ProvidersPublic">["policy"];
}) {
  const [cloud, setCloud] = useState(policy.allow_cloud_inference);
  const [audience, setAudience] = useState(policy.app_audience);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <form
      className="card"
      onSubmit={(event) => {
        event.preventDefault();
        if (!consent || busy || policy.demo_mode) return;
        void act(async () => {
          setBusy(true);
          setError("");
          try {
            await api("/admin/providers/policy", "POST", {
              allow_cloud_inference: cloud,
              app_audience: audience,
              acknowledge_data_boundary: true,
            } satisfies Schema<"ProviderPolicyInput">);
            await onChanged();
            setConsent(false);
          } catch {
            setError(
              "App policy could not be changed. Check your adult sign-in and the server-managed restrictions, then retry.",
            );
          } finally {
            setBusy(false);
          }
        });
      }}
    >
      <p>
        This policy applies to every learner and connection. Individual learner
        age restrictions still apply.
      </p>
      <label>
        Who uses this app?
        <select
          value={audience}
          disabled={busy || policy.audience_locked || policy.demo_mode}
          onChange={(event) => {
            setAudience(event.target.value as typeof audience);
            setConsent(false);
          }}
        >
          <option value="mixed">Adults and children</option>
          <option value="adult_only">Adults only</option>
        </select>
      </label>
      {policy.audience_locked && (
        <p className="fine">
          The server administrator has locked the app audience. Contact them to
          change it.
        </p>
      )}
      <label className="check">
        <input
          type="checkbox"
          checked={cloud}
          disabled={busy || policy.cloud_locked || policy.demo_mode}
          onChange={(event) => {
            setCloud(event.target.checked);
            setConsent(false);
          }}
        />
        Allow cloud AI for this app
      </label>
      {policy.cloud_locked && (
        <p className="fine">
          The server administrator has locked cloud access. Contact them to
          change it.
        </p>
      )}
      <p className="fine">
        Cloud providers receive the content for their selected role. A cloud
        tutor receives text read from photos, even if a local model reads the
        image. Enabling this policy alone sends no requests.
      </p>
      <label className="check">
        <input
          type="checkbox"
          checked={consent}
          disabled={busy || policy.demo_mode}
          onChange={(event) => setConsent(event.target.checked)}
          required
        />
        I confirm this audience and authorize the selected data boundary.
      </label>
      <button disabled={busy || !consent || policy.demo_mode}>
        Save app policy
      </button>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </form>
  );
}
